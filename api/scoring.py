"""
Deterministic output quality scoring.

WHY THIS EXISTS
  The goal this repo serves is migrating off frontier models onto open ones
  "keeping quality the same". That decision needs a number, not an eyeball.

  Every rule below is lifted VERBATIM from the constraints the production
  prompts already state. That matters: these are not quality criteria invented
  here, they are Oppora's own stated requirements, so a failure is objectively
  a failure to follow the brief — the exact failure mode a weaker model shows
  first.

  No LLM is involved. Scoring is free, instant, and byte-for-byte reproducible,
  so a score captured today is comparable to one captured next month.

WHAT IT DELIBERATELY CANNOT MEASURE
  Rules capture mechanical compliance (length, forbidden words, structure,
  merge tags). They cannot judge whether a hook is genuinely specific, whether
  a CTA feels soft, or whether copy sounds human. A model can score 100 here
  and still write lifeless email. Treat a high score as "did not break the
  brief", not as "this is good copy" — the second still needs a human read.

SEVERITY WEIGHTS
  critical (25) — the prompt says the output is rejected / must never happen
  major    (10) — an explicit numbered rule violated
  minor     (3) — a soft target missed (e.g. outside the 50-80 word sweet spot)
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

# ─────────────────────────────────────────────────────────────────────────────
# Rule data, verbatim from email_generation/email_generation.py
# ─────────────────────────────────────────────────────────────────────────────

# "SPAM WORD BLACKLIST — NEVER use:" (build_personalized_email_prompt)
SPAM_WORDS = [
    "FREE", "GUARANTEED", "ACT NOW", "LIMITED TIME", "CLICK HERE", "BUY NOW",
    "DISCOUNT", "OFFER", "DEAL", "WINNER", "CONGRATULATIONS", "NO OBLIGATION",
    "RISK-FREE", "100%", "DOUBLE YOUR", "EARN", "URGENT", "EXCLUSIVE",
    "LAST CHANCE", "DON'T MISS", "SPECIAL PROMOTION", "BARGAIN", "CHEAP",
    "SAVE BIG",
]

# "BANNED PHRASES:" (build_personalized_email_prompt)
BANNED_PHRASES = [
    "I hope this finds you well", "I came across your profile",
    "I'd love to connect", "touching base", "leveraging", "synergy",
    "streamline", "circle back", "best-in-class", "cutting-edge",
    "revolutionary", "game-changing", "I noticed that you",
    "I love what you're doing at",
]

# "═══ MERGE TAGS ═══" — the complete documented inventory.
RECIPIENT_TAGS = {
    "first_name", "last_name", "lead_job_title", "job_opening_title",
    "company", "job_location",
}
SENDER_TAGS = {
    "from_first_name", "from_last_name", "from_email", "from_phone_number",
    "signature",
}
SPINTAX_TAGS = {"random", "endrandom"}
KNOWN_TAGS = RECIPIENT_TAGS | SENDER_TAGS | SPINTAX_TAGS

# "Every email MUST end with: <p>Best,<br>{from_first_name}</p> or
#  <p>Cheers,<br>{signature}</p>" plus "(or Cheers, Thanks, Regards — pick what
#  fits the tone)" from the CRITICAL REMINDER section.
SIGNOFF_WORDS = ["best", "cheers", "thanks", "regards", "warmly", "sincerely"]

# Em dash, en dash, horizontal bar, minus — "Never use em dashes or en dashes".
DASH_CHARS = ["—", "–", "―", "−"]
DASH_ENTITIES = re.compile(r"&(?:mdash|ndash|#8212|#8211|#x201[34]);", re.I)

# "Zero images, zero HTML formatting (no bold, colors, tables)" and
# "No bold, no colors, no tables, no bullet points."
FORBIDDEN_TAGS = ["b", "strong", "i", "em", "u", "table", "tr", "td", "ul", "ol", "li", "img", "font", "h1", "h2", "h3"]

URL_SHORTENERS = ["bit.ly", "tinyurl", "t.co/", "goo.gl", "ow.ly", "buff.ly", "is.gd"]


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

Severity = str  # "critical" | "major" | "minor"
WEIGHTS = {"critical": 25, "major": 10, "minor": 3}


@dataclass
class Check:
    id: str
    label: str
    severity: Severity
    passed: bool
    detail: str = ""
    #  Where it failed, e.g. "initial" or "follow_up[1]".
    scope: str = ""
    #  The offending text, so the UI can show exactly what tripped the rule.
    evidence: list[str] = field(default_factory=list)
    #  The prompt line this rule comes from, so nobody has to trust us.
    rule_source: str = ""


@dataclass
class QualityReport:
    score: float
    max_score: float
    checks: list[Check]
    summary: dict[str, int]
    scoreable: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "max_score": self.max_score,
            "scoreable": self.scoreable,
            "note": self.note,
            "summary": self.summary,
            "checks": [asdict(c) for c in self.checks],
        }


def _finalize(checks: list[Check], note: str = "") -> QualityReport:
    penalty = sum(WEIGHTS[c.severity] for c in checks if not c.passed)
    score = max(0.0, 100.0 - penalty)
    failed = [c for c in checks if not c.passed]
    return QualityReport(
        score=score,
        max_score=100.0,
        checks=checks,
        note=note,
        summary={
            "total": len(checks),
            "passed": len(checks) - len(failed),
            "failed": len(failed),
            "critical": sum(1 for c in failed if c.severity == "critical"),
            "major": sum(1 for c in failed if c.severity == "major"),
            "minor": sum(1 for c in failed if c.severity == "minor"),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

def html_to_text(html: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    t = re.sub(r"</p\s*>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    t = (
        t.replace("&nbsp;", " ").replace("&amp;", "&")
        .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
    )
    return re.sub(r"[ \t]+", " ", t).strip()


def word_count(html: str) -> int:
    """Counts words in the rendered text. Merge tags count as one word each,
    which is how a human reading the sent email would count them."""
    text = html_to_text(html)
    return len([w for w in re.split(r"\s+", text) if w]) if text else 0


def _find_spam_words(text: str) -> list[str]:
    """Word-boundary matched so 'offer' trips but 'coffee' does not.
    '100%' is matched literally since \\b does not work after '%'."""
    hits = []
    upper = text.upper()
    for word in SPAM_WORDS:
        if word == "100%":
            if "100%" in upper:
                hits.append(word)
            continue
        # Normalise the apostrophe variants in DON'T MISS.
        pattern = re.escape(word).replace("'", "['’]")
        if re.search(rf"\b{pattern}\b", upper):
            hits.append(word)
    return hits


def _find_banned_phrases(text: str) -> list[str]:
    hits = []
    lowered = text.lower()
    for phrase in BANNED_PHRASES:
        needle = phrase.lower().replace("'", "")
        haystack = lowered.replace("'", "").replace("’", "")
        if needle in haystack:
            hits.append(phrase)
    return hits


def _find_dashes(html: str) -> list[str]:
    hits = [c for c in DASH_CHARS if c in (html or "")]
    if DASH_ENTITIES.search(html or ""):
        hits.append("&mdash;/&ndash; entity")
    return hits


def _find_tags(text: str) -> list[str]:
    """All {placeholder} tokens present, excluding spintax option bodies."""
    return re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", text or "")


def _find_forbidden_html(html: str) -> list[str]:
    found = []
    for tag in FORBIDDEN_TAGS:
        if re.search(rf"<\s*{tag}(\s|>|/)", html or "", re.I):
            found.append(f"<{tag}>")
    if re.search(r"style\s*=", html or "", re.I):
        found.append("style=")
    return found


def _count_links(html: str) -> int:
    anchors = len(re.findall(r"<a\s", html or "", re.I))
    bare = len(re.findall(r"https?://", html_to_text(html or "")))
    return max(anchors, bare)


# ─────────────────────────────────────────────────────────────────────────────
# Shared body checks — used by the sequence and single-email rubrics
# ─────────────────────────────────────────────────────────────────────────────

def _body_checks(
    body: str,
    scope: str,
    *,
    min_words: int,
    max_words: int,
    hard_max: int,
    require_signoff: bool,
    spintax_expected: bool | None,
    check_greeting_paragraph: bool,
) -> list[Check]:
    checks: list[Check] = []
    text = html_to_text(body)
    words = word_count(body)

    # ── Length ───────────────────────────────────────────────────────────────
    checks.append(Check(
        id="word_hard_cap", label=f"Body at most {hard_max} words",
        severity="critical", passed=words <= hard_max, scope=scope,
        detail=f"{words} words",
        rule_source=f"'NEVER exceed {hard_max} words'",
    ))
    checks.append(Check(
        id="word_sweet_spot", label=f"Body in the {min_words}-{max_words} word target",
        severity="minor", passed=min_words <= words <= max_words, scope=scope,
        detail=f"{words} words",
        rule_source=f"'{min_words}-{max_words} words sweet spot'",
    ))

    # ── Sign-off ─────────────────────────────────────────────────────────────
    if require_signoff:
        tail = html_to_text(body)[-120:].lower()
        has_word = any(w in tail for w in SIGNOFF_WORDS)
        has_sender_tag = any(f"{{{t}}}" in body for t in SENDER_TAGS)
        checks.append(Check(
            id="signoff", label="Ends with a professional sign-off",
            severity="critical", passed=has_word and has_sender_tag, scope=scope,
            detail=(
                "found" if has_word and has_sender_tag
                else f"sign-off word: {has_word}, sender merge tag: {has_sender_tag}"
            ),
            rule_source="'An email without a sign-off is INCOMPLETE and will be rejected.'",
        ))

    # ── Greeting in its own paragraph ────────────────────────────────────────
    if check_greeting_paragraph:
        paras = re.findall(r"<p[^>]*>(.*?)</p\s*>", body or "", re.I | re.S)
        first = html_to_text(paras[0]) if paras else ""
        # A greeting paragraph should be short — just "Hi {first_name},"
        ok = bool(paras) and len(first.split()) <= 6 and first.rstrip().endswith(",")
        checks.append(Check(
            id="greeting_own_paragraph", label="Greeting is its own <p>",
            severity="major", passed=ok, scope=scope,
            detail=f"first paragraph: {first[:60]!r}" if paras else "no <p> found",
            evidence=[first[:120]] if paras and not ok else [],
            rule_source="'MUST be its OWN <p>. NEVER put the greeting and hook in the same paragraph.'",
        ))

    # ── Forbidden content ────────────────────────────────────────────────────
    spam = _find_spam_words(text)
    checks.append(Check(
        id="spam_words", label="No blacklisted spam words",
        severity="major", passed=not spam, scope=scope,
        detail=f"{len(spam)} found" if spam else "clean",
        evidence=spam, rule_source="'SPAM WORD BLACKLIST — NEVER use'",
    ))

    banned = _find_banned_phrases(text)
    checks.append(Check(
        id="banned_phrases", label="No banned phrases",
        severity="major", passed=not banned, scope=scope,
        detail=f"{len(banned)} found" if banned else "clean",
        evidence=banned, rule_source="'BANNED PHRASES'",
    ))

    dashes = _find_dashes(body)
    checks.append(Check(
        id="no_em_dashes", label="No em/en dashes",
        severity="major", passed=not dashes, scope=scope,
        detail=", ".join(dashes) if dashes else "clean",
        evidence=dashes,
        rule_source="'Never use em dashes or en dashes (the long dashes)'",
    ))

    # ── Formatting / deliverability ──────────────────────────────────────────
    bad_html = _find_forbidden_html(body)
    checks.append(Check(
        id="plain_html", label="No bold, colours, tables, images or lists",
        severity="major", passed=not bad_html, scope=scope,
        detail=", ".join(bad_html) if bad_html else "clean",
        evidence=bad_html,
        rule_source="'Zero images, zero HTML formatting (no bold, colors, tables)'",
    ))

    links = _count_links(body)
    checks.append(Check(
        id="link_cap", label="At most 1 link",
        severity="major", passed=links <= 1, scope=scope,
        detail=f"{links} links",
        rule_source="'Maximum 1 link in body'",
    ))

    shorteners = [s for s in URL_SHORTENERS if s in (body or "").lower()]
    checks.append(Check(
        id="no_shorteners", label="No URL shorteners",
        severity="major", passed=not shorteners, scope=scope,
        detail=", ".join(shorteners) if shorteners else "clean",
        evidence=shorteners, rule_source="'No URL shorteners (bit.ly, tinyurl)'",
    ))

    # ── Merge tags ───────────────────────────────────────────────────────────
    tags = _find_tags(body)
    unknown = sorted({t for t in tags if t not in KNOWN_TAGS})
    checks.append(Check(
        id="known_merge_tags", label="Only documented merge tags used",
        severity="critical", passed=not unknown, scope=scope,
        detail=f"unknown: {', '.join(unknown)}" if unknown else "all recognised",
        evidence=unknown,
        rule_source="'═══ MERGE TAGS ═══' inventory",
    ))

    # A literal '[bracket placeholder]' is the classic hallucinated stand-in.
    brackets = re.findall(r"\[[a-zA-Z][^\]]{2,30}\]", text)
    checks.append(Check(
        id="no_bracket_placeholders", label="No [bracket] placeholders",
        severity="critical", passed=not brackets, scope=scope,
        detail=f"{len(brackets)} found" if brackets else "clean",
        evidence=brackets[:5],
        rule_source="'NO placeholders like [company name] or [product]'",
    ))

    # ── Spintax ──────────────────────────────────────────────────────────────
    if spintax_expected is not None:
        has_wrapper = "{random}" in (body or "") and "{endrandom}" in (body or "")
        # Bare pipes outside a wrapper are the documented failure mode.
        stripped = re.sub(r"\{random\}.*?\{endrandom\}", "", body or "", flags=re.S)
        bare_pipe = bool(re.search(r"\w\s*\|\s*\w", html_to_text(stripped)))

        if spintax_expected:
            checks.append(Check(
                id="spintax_present", label="Spintax used with {random}...{endrandom}",
                severity="major", passed=has_wrapper, scope=scope,
                detail="wrapper found" if has_wrapper else "no {random} wrapper",
                rule_source="'EVERY email ... MUST contain at least the greeting spintax'",
            ))
        else:
            checks.append(Check(
                id="spintax_absent", label="No spintax when disabled",
                severity="major", passed=not has_wrapper, scope=scope,
                detail="clean" if not has_wrapper else "{random} present but spintax is off",
                rule_source="'Do NOT use spintax syntax ({random}...{endrandom}) anywhere.'",
            ))

        checks.append(Check(
            id="no_bare_pipes", label="No bare pipe options outside a wrapper",
            severity="critical", passed=not bare_pipe, scope=scope,
            detail="clean" if not bare_pipe else "recipient would see raw 'a|b|c'",
            rule_source="'NEVER write bare pipe options like Hi|Hey|Hello'",
        ))

    return checks


def _subject_checks(subject: str | None, scope: str, *, optional: bool = False) -> list[Check]:
    checks: list[Check] = []
    if subject is None:
        if not optional:
            checks.append(Check(
                id="subject_present", label="Subject present", severity="major",
                passed=False, scope=scope, detail="missing",
            ))
        return checks

    words = [w for w in re.split(r"\s+", subject.strip()) if w]
    checks.append(Check(
        id="subject_length", label="Subject is 3-7 words",
        severity="minor", passed=3 <= len(words) <= 7, scope=scope,
        detail=f"{len(words)} words", rule_source="'═══ SUBJECT LINE (3-7 words) ═══'",
    ))

    # Sentence case: capitalise the first word only. Merge tags and acronyms are
    # legitimately capitalised, so only flag ordinary lowercase-able words.
    offenders = []
    for w in words[1:]:
        if w.startswith("{") or not w[:1].isalpha():
            continue
        core = re.sub(r"[^A-Za-z]", "", w)
        if len(core) > 1 and core[0].isupper() and not core.isupper():
            offenders.append(w)
    checks.append(Check(
        id="subject_sentence_case", label="Subject is sentence case",
        severity="minor", passed=not offenders, scope=scope,
        detail=f"{len(offenders)} capitalised words" if offenders else "ok",
        evidence=offenders[:5],
        rule_source="'Sentence case (capitalize the first word only)'",
    ))

    all_caps = [w for w in words if len(re.sub(r"[^A-Za-z]", "", w)) > 2 and w.isupper()]
    has_bang = "!" in subject
    fake_thread = bool(re.match(r"^\s*(re|fwd)\s*:", subject, re.I))
    reasons = []
    if all_caps:
        reasons.append(f"ALL CAPS: {', '.join(all_caps)}")
    if has_bang:
        reasons.append("exclamation mark")
    if fake_thread:
        reasons.append("fake Re:/Fwd: prefix")
    checks.append(Check(
        id="subject_no_caps_or_bang", label="No ALL CAPS, '!' or fake Re:/Fwd:",
        severity="major",
        passed=not (all_caps or has_bang or fake_thread),
        scope=scope,
        detail="; ".join(reasons) if reasons else "ok",
        evidence=all_caps,
        rule_source="'NEVER: all caps, exclamation marks, Re: or Fwd: fakes'",
    ))

    spam = _find_spam_words(subject)
    checks.append(Check(
        id="subject_spam_words", label="No spam words in subject",
        severity="major", passed=not spam, scope=scope,
        detail=", ".join(spam) if spam else "clean", evidence=spam,
        rule_source="'SPAM WORD BLACKLIST'",
    ))

    dashes = _find_dashes(subject)
    checks.append(Check(
        id="subject_no_dashes", label="No em/en dashes in subject",
        severity="minor", passed=not dashes, scope=scope,
        detail=", ".join(dashes) if dashes else "clean", evidence=dashes,
    ))
    return checks


# ─────────────────────────────────────────────────────────────────────────────
# Per-feature rubrics
# ─────────────────────────────────────────────────────────────────────────────

def score_email_sequence(result: Any, inputs: dict) -> QualityReport:
    """email_generation/email_generation.py — the full campaign sequence."""
    if not isinstance(result, dict) or "initial" not in result:
        return QualityReport(0.0, 100.0, [Check(
            id="shape", label="Result matches EmailSequence schema",
            severity="critical", passed=False, detail="missing 'initial'",
        )], {"total": 1, "passed": 0, "failed": 1, "critical": 1, "major": 0, "minor": 0})

    spintax = bool(inputs.get("include_spintax"))
    checks: list[Check] = []

    initial = result.get("initial") or {}
    checks += _subject_checks(initial.get("subject"), "initial")
    checks += _body_checks(
        initial.get("body") or "", "initial",
        min_words=50, max_words=80, hard_max=125,
        require_signoff=True, spintax_expected=spintax,
        check_greeting_paragraph=True,
    )

    # Follow-up word targets, verbatim from '═══ FOLLOW-UP RULES ═══'.
    fu_targets = [(30, 50), (40, 60), (20, 40)]
    follow_ups = result.get("follow_ups") or []

    requested = int(inputs.get("sequence_steps") or 3)
    expected_fu = max(requested - 1, 0)
    checks.append(Check(
        id="followup_count", label=f"Produced {expected_fu} follow-up(s)",
        severity="major", passed=len(follow_ups) == expected_fu,
        detail=f"got {len(follow_ups)}, expected {expected_fu}",
        rule_source="sequence_steps input",
    ))

    prev_words = word_count(initial.get("body") or "")
    for i, fu in enumerate(follow_ups):
        scope = f"follow_up[{i + 1}]"
        lo, hi = fu_targets[i] if i < len(fu_targets) else (20, 60)
        checks += _subject_checks(fu.get("subject"), scope, optional=True)
        checks += _body_checks(
            fu.get("body") or "", scope,
            min_words=lo, max_words=hi, hard_max=125,
            require_signoff=True, spintax_expected=spintax,
            check_greeting_paragraph=False,
        )

        days = fu.get("days_after")
        checks.append(Check(
            id="days_after_valid", label="days_after is at least 1",
            severity="major", passed=isinstance(days, int) and days >= 1,
            scope=scope, detail=f"days_after={days}",
            rule_source="FollowUpStep.days_after ge=1",
        ))

        cur = word_count(fu.get("body") or "")
        checks.append(Check(
            id="progressively_shorter", label="Shorter than the previous step",
            severity="minor", passed=cur <= prev_words, scope=scope,
            detail=f"{cur} words vs {prev_words} previous",
            rule_source="'Get progressively shorter.'",
        ))
        prev_words = cur

    return _finalize(checks)


def score_single_email(result: Any, inputs: dict) -> QualityReport:
    """email_generation/single_email_generation.py.

    A DIFFERENT rubric on purpose: this prompt asks for a formal template with
    no links and 'under 120 words', and does NOT impose the 50-80 word cold
    email rules. Scoring it against the sequence rubric would be wrong.
    """
    if not isinstance(result, dict):
        return QualityReport(0.0, 100.0, [], {}, scoreable=False, note="unexpected shape")

    body = result.get("body") or ""
    checks = _subject_checks(result.get("subject"), "email")
    checks += _body_checks(
        body, "email",
        min_words=40, max_words=120, hard_max=120,
        require_signoff=True, spintax_expected=None,
        check_greeting_paragraph=False,
    )

    # "The email should not contain any links." — stricter than the sequence.
    links = _count_links(body)
    checks.append(Check(
        id="no_links_at_all", label="Contains no links",
        severity="major", passed=links == 0, scope="email",
        detail=f"{links} links",
        rule_source="'it should not contain any links'",
    ))

    # "Don't use other variable except {first_name} {last_name} and {company}"
    allowed = {"first_name", "last_name", "company"} | SENDER_TAGS
    extra = sorted({t for t in _find_tags(body) if t not in allowed})
    checks.append(Check(
        id="restricted_tags", label="Only {first_name} {last_name} {company} used",
        severity="major", passed=not extra, scope="email",
        detail=f"extra: {', '.join(extra)}" if extra else "ok", evidence=extra,
        rule_source="'Don't use other variable except {first_name} {last_name} and {company}'",
    ))
    return _finalize(checks)


def score_campaign_variable(result: Any, inputs: dict) -> QualityReport:
    """email_generation/campaign_ai_variable.py — fills ONE merge tag."""
    text = (result or {}).get("text") if isinstance(result, dict) else None
    if not text:
        return QualityReport(0.0, 100.0, [Check(
            id="present", label="Produced a value", severity="critical", passed=False,
        )], {"total": 1, "passed": 0, "failed": 1, "critical": 1, "major": 0, "minor": 0})

    checks: list[Check] = []

    # "Deliver One Polished Sentence" — rule 5 of the system prompt.
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]
    checks.append(Check(
        id="single_sentence", label="Exactly one sentence",
        severity="major", passed=len(sentences) == 1, scope="value",
        detail=f"{len(sentences)} sentences",
        rule_source="'Deliver One Polished Sentence'",
    ))

    dashes = _find_dashes(text)
    checks.append(Check(
        id="no_em_dashes", label="No em/en dashes",
        severity="critical", passed=not dashes, scope="value",
        detail=", ".join(dashes) if dashes else "clean", evidence=dashes,
        rule_source="rule 6 + strip_em_dashes() post-processing",
    ))

    # Unsubstituted tags mean the caller's placeholders leaked through.
    leftover = sorted(set(_find_tags(text)))
    checks.append(Check(
        id="no_unsubstituted_tags", label="No unsubstituted {placeholders}",
        severity="critical", passed=not leftover, scope="value",
        detail=f"leftover: {', '.join(leftover)}" if leftover else "clean",
        evidence=leftover,
        rule_source="placeholders are substituted before the call",
    ))

    brackets = re.findall(r"\[[a-zA-Z][^\]]{2,30}\]", text)
    checks.append(Check(
        id="no_bracket_placeholders", label="No [bracket] placeholders",
        severity="critical", passed=not brackets, scope="value",
        evidence=brackets[:5], detail=f"{len(brackets)} found" if brackets else "clean",
    ))

    banned = _find_banned_phrases(text)
    checks.append(Check(
        id="banned_phrases", label="No banned phrases",
        severity="minor", passed=not banned, scope="value",
        evidence=banned, detail=f"{len(banned)} found" if banned else "clean",
    ))

    words = len([w for w in re.split(r"\s+", text.strip()) if w])
    checks.append(Check(
        id="reasonable_length", label="Under 40 words (one line)",
        severity="minor", passed=words <= 40, scope="value", detail=f"{words} words",
        rule_source="max_tokens=300, one sentence",
    ))
    return _finalize(checks)


def score_reply_generation(result: Any, inputs: dict) -> QualityReport:
    """email_generation/reply_generation.py — the manual 'AI reply' button."""
    text = (result or {}).get("text") if isinstance(result, dict) else None
    if not text:
        return QualityReport(0.0, 100.0, [Check(
            id="present", label="Produced a reply", severity="critical", passed=False,
        )], {"total": 1, "passed": 0, "failed": 1, "critical": 1, "major": 0, "minor": 0})

    checks: list[Check] = []

    # "NEVER use placeholder text like [your name], [company name], etc."
    brackets = re.findall(r"\[[a-zA-Z][^\]]{2,30}\]", text)
    checks.append(Check(
        id="no_bracket_placeholders", label="No [placeholder] text",
        severity="critical", passed=not brackets, scope="reply",
        evidence=brackets[:5], detail=f"{len(brackets)} found" if brackets else "clean",
        rule_source="'NEVER use placeholder text like [your name], [company name]'",
    ))

    # "Keep responses concise (2-3 paragraphs max)"
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    checks.append(Check(
        id="paragraph_cap", label="At most 3 paragraphs",
        severity="major", passed=len(paras) <= 3, scope="reply",
        detail=f"{len(paras)} paragraphs",
        rule_source="'Keep responses concise (2-3 paragraphs max)'",
    ))

    # "Generate ONLY the email body content (no signatures or headers)"
    has_header = bool(re.match(r"^\s*(subject|to|from|cc)\s*:", text, re.I))
    checks.append(Check(
        id="no_headers", label="No email headers",
        severity="major", passed=not has_header, scope="reply",
        detail="clean" if not has_header else "starts with a header line",
        rule_source="'Generate ONLY the email body content (no signatures or headers)'",
    ))

    banned = _find_banned_phrases(text)
    checks.append(Check(
        id="banned_phrases", label="No banned phrases",
        severity="minor", passed=not banned, scope="reply",
        evidence=banned, detail=f"{len(banned)} found" if banned else "clean",
    ))
    return _finalize(
        checks,
        note="This prompt asks for plain text and a clear CTA. CTA presence is a "
             "judgement call, so it is intentionally not scored here.",
    )


def score_reply_agent_chain(result: Any, inputs: dict) -> QualityReport:
    """email_generation/reply_agent_chain.py — scores the drafted reply plus
    whether the chain's own guardrail and routing behaved."""
    if not isinstance(result, dict) or "draft" not in result:
        return QualityReport(0.0, 100.0, [Check(
            id="shape", label="Pipeline returned a draft", severity="critical", passed=False,
        )], {"total": 1, "passed": 0, "failed": 1, "critical": 1, "major": 0, "minor": 0})

    draft = result.get("draft") or ""
    text = html_to_text(draft)
    checks: list[Check] = []

    # "***Reply Format: HTML only. Use <br> tags for line breaks — never use
    #  plain newlines (\n).***"
    raw_newlines = "\n" in draft.strip()
    checks.append(Check(
        id="br_not_newlines", label="Uses <br>, not plain newlines",
        severity="major", passed=not raw_newlines, scope="draft",
        detail="clean" if not raw_newlines else "contains raw \\n",
        rule_source="'Every line break in the email MUST be a <br> tag'",
    ))

    # "Keep it SHORT - 2-3 sentences max"
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    checks.append(Check(
        id="sentence_cap", label="At most 3 sentences",
        severity="major", passed=len(sentences) <= 3, scope="draft",
        detail=f"{len(sentences)} sentences",
        rule_source="'Keep it SHORT - 2-3 sentences max'",
    ))

    # "Any brackets [ ] or placeholder text" is on the avoid list.
    brackets = re.findall(r"\[[^\]]{2,30}\]", text)
    checks.append(Check(
        id="no_brackets", label="No [brackets]",
        severity="critical", passed=not brackets, scope="draft",
        evidence=brackets[:5], detail=f"{len(brackets)} found" if brackets else "clean",
        rule_source="'NO placeholders like [company name] or [product]'",
    ))

    # "Markdown formatting like [text](url) - use plain URLs"
    markdown_link = bool(re.search(r"\[[^\]]+\]\([^)]+\)", draft))
    checks.append(Check(
        id="no_markdown_links", label="No markdown links",
        severity="major", passed=not markdown_link, scope="draft",
        detail="clean" if not markdown_link else "markdown link found",
        rule_source="'Markdown formatting like [text](url) - use plain URLs'",
    ))

    dashes = _find_dashes(draft)
    checks.append(Check(
        id="no_em_dashes", label="No em/en dashes",
        severity="major", passed=not dashes, scope="draft",
        evidence=dashes, detail=", ".join(dashes) if dashes else "clean",
        rule_source="'Em dashes or en dashes (the long dashes)' on the avoid list",
    ))

    # AI-speak the prompt explicitly lists under "What to avoid".
    ai_speak = [p for p in [
        "thanks for your interest", "i'd be happy to",
        "looking forward to your thoughts",
    ] if p in text.lower()]
    checks.append(Check(
        id="no_ai_speak", label="No listed AI-speak phrases",
        severity="major", passed=not ai_speak, scope="draft",
        evidence=ai_speak, detail=f"{len(ai_speak)} found" if ai_speak else "clean",
        rule_source="'What to avoid' list",
    ))

    # Meeting-link discipline: if no URL was supplied, the prompt forbids
    # mentioning scheduling at all.
    url = (inputs.get("meeting_tool_url") or "").strip()
    if not url:
        mentions = [w for w in ["calendar", "calendly", "schedule", "book a", "cal.com"]
                    if w in text.lower()]
        checks.append(Check(
            id="no_phantom_meeting_link", label="No scheduling talk without a link",
            severity="critical", passed=not mentions, scope="draft",
            evidence=mentions,
            detail="clean" if not mentions else "promises scheduling with no URL configured",
            rule_source="'If no meeting URL provided (empty): Do NOT mention scheduling'",
        ))
    else:
        # If it does share a link it must be the exact URL, not an invented one.
        if any(w in text.lower() for w in ["calendar", "cal.com", "calendly", "http"]):
            checks.append(Check(
                id="exact_meeting_url", label="Shares the exact configured URL",
                severity="critical", passed=url in draft, scope="draft",
                detail="exact URL present" if url in draft else f"expected {url}",
                rule_source="'use the EXACT URL provided'",
            ))

    # Chain behaviour: extract_referred_contacts should catch an address that
    # appears verbatim in the inbound message.
    inbound = inputs.get("prospect_message") or ""
    emails_in = set(re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", inbound))
    if emails_in:
        found = {c.get("email") for c in (result.get("referred_contacts") or [])}
        missed = sorted(emails_in - found)
        checks.append(Check(
            id="referred_contacts_found", label="Referred contacts extracted",
            severity="major", passed=not missed, scope="chain",
            evidence=missed,
            detail="all found" if not missed else f"missed {len(missed)}",
            rule_source="extract_referred_contacts node",
        ))

    guardrail = result.get("guardrail") or {}
    checks.append(Check(
        id="guardrail_passed", label="Guardrail passed",
        severity="major", passed=bool(guardrail.get("guardrail_passed")), scope="chain",
        detail=", ".join(guardrail.get("issues") or []) or "passed",
        evidence=guardrail.get("issues") or [],
        rule_source="guardrail_check node",
    ))
    return _finalize(checks)


def score_lead_email_addresses(result: Any, inputs: dict) -> QualityReport:
    """email_generation/lead_email_address_generation.py — address guessing."""
    emails = (result or {}).get("emails") if isinstance(result, dict) else None
    if not emails:
        return QualityReport(0.0, 100.0, [Check(
            id="present", label="Produced candidate addresses",
            severity="critical", passed=False,
        )], {"total": 1, "passed": 0, "failed": 1, "critical": 1, "major": 0, "minor": 0})

    checks: list[Check] = []
    checks.append(Check(
        id="max_five", label="At most 5 candidates",
        severity="major", passed=len(emails) <= 5, scope="emails",
        detail=f"{len(emails)} returned",
        rule_source="'You should give maximum 5 best pattern emails'",
    ))

    invalid = [e for e in emails if not re.fullmatch(r"[\w.+-]+@[\w-]+\.[\w.]+", str(e))]
    checks.append(Check(
        id="valid_syntax", label="All addresses are syntactically valid",
        severity="critical", passed=not invalid, scope="emails",
        evidence=[str(e) for e in invalid[:5]],
        detail=f"{len(invalid)} malformed" if invalid else "all valid",
    ))

    dupes = len(emails) != len(set(map(str.lower, map(str, emails))))
    checks.append(Check(
        id="no_duplicates", label="No duplicate candidates",
        severity="minor", passed=not dupes, scope="emails",
        detail="unique" if not dupes else "duplicates present",
    ))

    # Every candidate should sit on one domain — the colleague's company.
    domains = {str(e).split("@")[-1].lower() for e in emails if "@" in str(e)}
    checks.append(Check(
        id="single_domain", label="All candidates share one domain",
        severity="major", passed=len(domains) <= 1, scope="emails",
        evidence=sorted(domains) if len(domains) > 1 else [],
        detail=f"{len(domains)} domains",
        rule_source="pattern is inferred from same-company colleagues",
    ))
    return _finalize(checks)


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

SCORERS: dict[str, Callable[[Any, dict], QualityReport]] = {
    "email_sequence": score_email_sequence,
    "single_email_generation": score_single_email,
    "campaign_ai_variable": score_campaign_variable,
    "reply_generation": score_reply_generation,
    "reply_agent_chain": score_reply_agent_chain,
    "lead_email_address_generation": score_lead_email_addresses,
}


def score(feature_id: str, result: Any, inputs: dict) -> dict[str, Any] | None:
    """Returns a serialisable report, or None when the feature has no rubric
    yet (the classification and lead-scoring features)."""
    scorer = SCORERS.get(feature_id)
    if scorer is None or result is None:
        return None
    try:
        return scorer(result, inputs or {}).as_dict()
    except Exception as exc:
        # Scoring must never break a run.
        return {
            "score": 0.0, "max_score": 100.0, "scoreable": False,
            "note": f"scorer error: {type(exc).__name__}: {exc}",
            "summary": {}, "checks": [],
        }
