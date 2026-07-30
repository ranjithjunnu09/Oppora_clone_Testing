"""
Standalone replica of Oppora's AI EMAIL-GENERATION feature
(campaign personalized email sequences).

WHY THIS FILE EXISTS
--------------------
This is a faithful, backend-free copy of the exact AI logic Oppora uses to
generate cold-outreach email sequences. Same system+user prompt, same output
schema, same model call as production — so the emails it produces match what
Oppora produces. No Django, no database, no campaign/credit plumbing: it depends
only on `openai` and `pydantic`.

Purpose: swap the model/endpoint (e.g. point OPENAI_BASE_URL at an open-source
model's OpenAI-compatible server) and compare output quality against Oppora,
running the SAME feature with the SAME inputs.

WHERE THIS COMES FROM IN OPPORA (source of truth — kept byte-identical)
----------------------------------------------------------------------
  * Prompt : sales/campaigns/utils.py   -> build_personalized_email_prompt()
  * Schema : sales/sales_open_ai.py      -> EmailSequence / EmailStep / FollowUpStep
  * Call   : sales/campaigns/utils.py   -> generate_personalized_emails_bulk()
             (client.beta.chat.completions.parse, model="gpt-4.1-mini",
              response_format=EmailSequence)

HOW TO RUN
----------
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...                 # your paid key (baseline)
  python email_generation.py

  # To test an open-source / self-hosted model (OpenAI-compatible endpoint):
  export OPENAI_BASE_URL=http://localhost:8000/v1
  export OPENAI_API_KEY=whatever-your-server-wants
  python email_generation.py --model my-open-model

Deps: openai>=1.40, pydantic>=2.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import List, Optional

from pydantic import BaseModel, Field
from openai import OpenAI


# ─────────────────────────────────────────────────────────────────────────────
# OUTPUT SCHEMA  — verbatim from sales/sales_open_ai.py
# The field descriptions are part of the structured-output schema the model
# receives, so they are copied exactly (they influence the result).
# ─────────────────────────────────────────────────────────────────────────────
class EmailStep(BaseModel):
    """A single email in a sequence."""
    subject: str = Field(description="Email subject line — concise, no spam words, no 'Re:' prefix")
    body: str = Field(description="HTML email body. MUST end with a professional sign-off like '<p>Best,<br>{from_first_name}</p>' or '<p>Cheers,<br>{from_first_name}</p>'. Use <p> tags for paragraphs. Keep under 120 words.")


class FollowUpStep(BaseModel):
    """A follow-up email step."""
    subject: Optional[str] = Field(None, description="None means same thread (no new subject)")
    body: str = Field(description="HTML email body. MUST end with a professional sign-off like '<p>Best,<br>{from_first_name}</p>'. Use <p> tags. Keep shorter than initial email.")
    days_after: int = Field(ge=1, description="Days after previous step")
    #  Present in production's FollowUpStep and previously missing here. The
      #  schema IS the structured-output contract sent to the model, so omitting
      #  a field changes what gets generated — this was a real fidelity gap.
    angle: str = Field(description="e.g. 'bump', 'social_proof', 'new_angle', 'breakup'")


class EmailSequence(BaseModel):
    """Full email sequence: initial + follow-ups."""
    initial: EmailStep
    follow_ups: List[FollowUpStep]


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT BUILDER — verbatim from sales/campaigns/utils.py::build_personalized_email_prompt
# The ONLY change vs Oppora: the optional campaign-variable-registry block
# (which needs the DB) is dropped — it is best-effort in Oppora too (wrapped in
# try/except) and the merge-tag inventory it would add is already covered by the
# static "MERGE TAGS" rule below. Everything else is identical.
# ─────────────────────────────────────────────────────────────────────────────
def build_personalized_email_prompt(
    user_prompt: str,
    lead_data: dict | None = None,
    icp_profile: dict | None = None,
    writing_style: dict | None = None,
    research_brief: str | None = None,
    campaign_context: dict | None = None,
    sequence_steps: int = 3,
    include_spintax: bool = False,
    variants_count: int = 1,
    campaign_id: int | None = None,
    existing_copy: dict | None = None,
) -> tuple:
    """Build (system_prompt, user_prompt) for AI email sequence generation."""
    sections = []

    sections.append(
        "You are an elite B2B cold email writer. Your emails consistently achieve 10-25% reply rates "
        "because you follow one principle: write like a helpful human, not a marketer. "
        "Every cold email competes with 50+ others in the inbox, so yours must feel like it was "
        "written specifically for the recipient, by someone who genuinely researched their situation. "
        "Never use em dashes or en dashes (the long dashes); use a comma, period, or a spaced hyphen instead."
    )

    if (user_prompt or "").strip():
        sections.append(
            "## SOURCE OF TRUTH — THE USER'S BRIEF\n"
            "The brief in the next message (under 'WHAT TO PITCH') defines the offer, the core value, "
            "and the call to action. It OVERRIDES everything else. ICP context below is background for "
            "tone and persona only — never let it replace or water down what the user asked you to pitch. "
            "If the brief names a concrete offer (a discount, % off, free trial, pricing, bonus, deadline), "
            "that offer MUST appear in the sequence — usually as the reason to act, in the CTA or an early "
            "follow-up. State it plainly (e.g. '30% off the starter plan for your first year') — no caps, "
            "no exclamation, no urgency."
        )

    if writing_style:
        style_rules = []
        if writing_style.get("tone"):
            style_rules.append(f"- Tone: {writing_style['tone']}")
        if writing_style.get("avg_sentence_length"):
            style_rules.append(f"- Keep sentences under {writing_style['avg_sentence_length']} words")
        if writing_style.get("greeting_style"):
            style_rules.append(f"- Open with: {writing_style['greeting_style']}")
        if writing_style.get("sign_off_style"):
            style_rules.append(f"- Sign off with: {writing_style['sign_off_style']}")
        if writing_style.get("patterns"):
            style_rules.append(f"- Patterns: {', '.join(writing_style['patterns'])}")
        if writing_style.get("forbidden_phrases"):
            style_rules.append(f"- NEVER use: {', '.join(writing_style['forbidden_phrases'])}")
        if writing_style.get("avg_email_length_words"):
            style_rules.append(f"- Target email length: ~{writing_style['avg_email_length_words']} words")
        if writing_style.get("example_openings"):
            style_rules.append(f"- Example openings you like: {', '.join(writing_style['example_openings'][:3])}")

        if style_rules:
            sections.append("## YOUR WRITING STYLE\n" + "\n".join(style_rules))

    if icp_profile:
        company_ctx = icp_profile.get("company_context", {})
        buyer = icp_profile.get("buyer_persona", {})
        messaging = icp_profile.get("messaging", {})
        target_company = icp_profile.get("target_company", {})

        about_parts = []
        if company_ctx.get("description") or company_ctx.get("product_description"):
            about_parts.append(f"- What you do: {company_ctx.get('description') or company_ctx.get('product_description')}")
        if company_ctx.get("value_proposition"):
            about_parts.append(f"- Value proposition: {company_ctx['value_proposition']}")
        if company_ctx.get("key_differentiators"):
            diffs = company_ctx["key_differentiators"]
            if isinstance(diffs, list):
                diffs = ", ".join(diffs)
            about_parts.append(f"- Key differentiators: {diffs}")

        buyer_parts = []
        if buyer.get("job_titles"):
            titles = buyer["job_titles"]
            if isinstance(titles, list):
                titles = ", ".join(titles)
            buyer_parts.append(f"- Target buyer titles: {titles}")
        if buyer.get("pain_points"):
            pain = buyer["pain_points"]
            if isinstance(pain, list):
                pain = ", ".join(pain)
            buyer_parts.append(f"- Their pain points: {pain}")
        if buyer.get("buying_triggers"):
            triggers = buyer["buying_triggers"]
            if isinstance(triggers, list):
                triggers = ", ".join(triggers)
            buyer_parts.append(f"- Buying triggers (why they'd act now): {triggers}")

        msg_parts = []
        if messaging.get("preferred_tone"):
            msg_parts.append(f"- Tone: {messaging['preferred_tone']} — MATCH THIS TONE in every email")
        if messaging.get("elevator_pitch"):
            msg_parts.append(f"- Elevator pitch: {messaging['elevator_pitch']}")
        if messaging.get("messaging_angles"):
            angles = messaging["messaging_angles"]
            if isinstance(angles, list):
                angles = ", ".join(angles)
            msg_parts.append(f"- Messaging angles to use: {angles}")
        if messaging.get("call_to_action"):
            msg_parts.append(f"- Call to action: {messaging['call_to_action']}")

        market_parts = []
        if target_company.get("industries"):
            industries = target_company["industries"]
            if isinstance(industries, list):
                industries = ", ".join(industries)
            market_parts.append(f"- Target industries: {industries}")

        icp_section = "## ICP CONTEXT (who you're selling to)\n"
        if about_parts:
            icp_section += "**Your company:**\n" + "\n".join(about_parts) + "\n\n"
        if buyer_parts:
            icp_section += "**Target buyer:**\n" + "\n".join(buyer_parts) + "\n\n"
        if msg_parts:
            icp_section += "**How to message them:**\n" + "\n".join(msg_parts) + "\n\n"
        if market_parts:
            icp_section += "**Target market:**\n" + "\n".join(market_parts) + "\n"

        if about_parts or buyer_parts or msg_parts or market_parts:
            sections.append(icp_section.strip())
    else:
        sections.append(
            "## NO ICP CONFIGURED\n"
            "There is NO ICP profile for this organization. Do NOT invent generic pain points, "
            "buyer personas, or value propositions.\n"
            "Treat the user's request below as the ENTIRE source of truth for the offer, audience, "
            "and tone. If the user's brief is thin, keep claims generic and concrete (no fake stats, "
            "no fabricated case studies)."
        )

    if research_brief:
        sections.append(f"## ABOUT THIS PROSPECT (from web research)\n{research_brief}")

    # NOTE: Oppora injects a per-campaign variable inventory here via
    # sales.campaigns.variables_registry (best-effort, DB-backed). Omitted in this
    # standalone; the merge tags it would list are already in the MERGE TAGS rule.

    greeting_eg = (
        "{random}Hi|Hey|Hello{endrandom} {first_name},"
        if include_spintax
        else "Hi {first_name},"
    )

    rules = [
        "═══ EMAIL BODY (50-80 words — #1 rule) ═══\n"
        "- Format: HTML (<p>, <br>) but WRITE like plain text. No bold, no colors, no tables, no bullet points.\n"
        "- Structure (a greeting + exactly 3 parts):\n"
        "  0. GREETING (REQUIRED): '" + greeting_eg + "' MUST be its OWN <p>. The hook starts in a SEPARATE <p>. NEVER put the greeting and hook in the same paragraph.\n"
        "  1. HOOK (1-2 sentences): Reference something SPECIFIC — their {lead_job_title} at {company}, a pain point, their situation.\n"
        "     NOT 'I hope this finds you well' or 'I came across your profile'. Be SPECIFIC.\n"
        "  2. VALUE (1-2 sentences): What you can do for THEM. Connect to a real pain point. Not about you.\n"
        "  3. CTA (1 sentence): Single, soft, binary question. Easy to reply yes/no.\n"
        "- 50-80 words sweet spot (2.4x higher reply rate than 200+ words). NEVER exceed 125 words.",

        "═══ SUBJECT LINE (3-7 words) ═══\n"
        "- Sentence case (capitalize the first word only), conversational — like a colleague, not a marketer\n"
        "- Use {company} in subject (21.9% open lift) — more effective than {first_name} (9.6% lift)\n"
        "- Curiosity-driven or question-based\n"
        "- NEVER: all caps, exclamation marks, 'Re:' or 'Fwd:' fakes, clickbait",

        "═══ MERGE TAGS ═══\n"
        "**Recipient variables (use 2-3 naturally — {company} + {lead_job_title} is the best combo):**\n"
        "- {first_name} = recipient's first name\n"
        "- {last_name} = recipient's last name\n"
        "- {lead_job_title} = recipient's CURRENT job title (who they ARE). NEVER treat as a job opening.\n"
        "- {job_opening_title} = a job posting at their company (ONLY if discussing hiring)\n"
        "- {company} = recipient's company name\n"
        "- {job_location} = recipient's location\n\n"
        "**Sender variables — ALWAYS end every email with a professional sign-off:**\n"
        "- {from_first_name}, {from_last_name} = sender's name\n"
        "- {from_email} = sender's email\n"
        "- {from_phone_number} = sender's phone\n"
        "- {signature} = sender's full signature block\n"
        "Every email MUST end with: <p>Best,<br>{from_first_name}</p> or <p>Cheers,<br>{signature}</p>",

        "═══ SOFT CTAs THAT WORK ═══\n"
        "- 'Would it make sense to share how we did this for [similar company]?'\n"
        "- 'Open to seeing how this could work for {company}?'\n"
        "- 'Worth a quick conversation?'\n"
        "- 'Should I send over the details?'\n"
        "NEVER: 'Book a 30-min demo', 'Click here', 'Let me know if interested', 'Let's chat'\n"
        "Single CTA only — emails with 1 CTA perform 371% better than multiple CTAs.",

        "═══ FOLLOW-UP RULES ═══\n"
        "- Follow-up 1 (after 2-3 days): Brief bump + ONE new piece of value or social proof. 30-50 words.\n"
        "- Follow-up 2 (after 4-5 days): Different angle entirely — new pain point, case study, insight. 40-60 words.\n"
        "- Follow-up 3/breakup (after 7-10 days): Short graceful exit. 20-40 words. Often gets most replies (loss aversion).\n"
        "- Each follow-up must add a NEW angle — never repeat the initial email's pitch.\n"
        "- Get progressively shorter.",

        "═══ DELIVERABILITY CHECKLIST ═══\n"
        "Every email MUST pass ALL checks:\n"
        "✓ Under 80 words (NEVER over 125)\n"
        "✓ Zero images, zero HTML formatting (no bold, colors, tables)\n"
        "✓ Maximum 1 link in body\n"
        "✓ No URL shorteners (bit.ly, tinyurl)\n"
        "✓ Single CTA — one question, one ask\n"
        "✓ Conversational tone — sounds like a person, not a template\n"
        "✓ Ends with professional sign-off\n\n"
        "SPAM WORD BLACKLIST — NEVER use:\n"
        "FREE, GUARANTEED, ACT NOW, LIMITED TIME, CLICK HERE, BUY NOW, DISCOUNT, OFFER, DEAL, "
        "WINNER, CONGRATULATIONS, NO OBLIGATION, RISK-FREE, 100%, DOUBLE YOUR, EARN, URGENT, "
        "EXCLUSIVE, LAST CHANCE, DON'T MISS, SPECIAL PROMOTION, BARGAIN, CHEAP, SAVE BIG\n"
        "NOTE: these are spam-FRAMING words to avoid — they do NOT mean 'drop the offer'. If the user's "
        "brief states a real offer, convey its substance factually (e.g. '30% off the starter plan for "
        "your first year') without these words, caps, or urgency.\n\n"
        "BANNED PHRASES:\n"
        "'I hope this finds you well', 'I came across your profile', 'I'd love to connect', "
        "'touching base', 'leveraging', 'synergy', 'streamline', 'circle back', 'best-in-class', "
        "'cutting-edge', 'revolutionary', 'game-changing', 'I noticed that you', "
        "'I love what you're doing at {company}'",
    ]
    if include_spintax:
        rules.append(
            "═══ SPINTAX (MANDATORY — the user turned this on) ═══\n"
            "Wrap the GREETING, the CTA, and the SIGN-OFF in spintax so each send varies: "
            "{random}option1|option2|option3{endrandom}\n"
            "- Greeting: {random}Hi|Hey|Hello{endrandom} {first_name},\n"
            "- CTA: {random}Open to|Would it make sense to{endrandom} a quick chat about {company}?\n"
            "- Sign-off: {random}Best|Cheers|Thanks{endrandom},\n"
            "CRITICAL: always use the literal {random}...{endrandom} tokens. NEVER write bare "
            "pipe options like 'Hi|Hey|Hello' or '{Hi|Hey|Hello}' — without the wrapper they are "
            "not randomized and the recipient sees the raw 'Hi|Hey|Hello'.\n"
            "EVERY email (initial AND every follow-up AND every variant) MUST contain at least the "
            "greeting spintax plus one more (CTA or sign-off). Do NOT spintax the personalized hook "
            "or the value sentence — only the formulaic parts."
        )
    else:
        rules.append(
            "═══ NO SPINTAX ═══\n"
            "Do NOT use spintax syntax ({random}...{endrandom}) anywhere. Write plain greetings, "
            "CTAs, and sign-offs."
        )
    sections.append("## RULES\n\n" + "\n\n".join(rules))

    sections.append(
        "## CRITICAL REMINDER\n"
        "Every single email body (initial AND every follow-up) MUST end with a professional sign-off.\n"
        "The last HTML element in every body field must be: <p>Best,<br>{from_first_name}</p> "
        "(or Cheers, Thanks, Regards — pick what fits the tone).\n"
        "An email without a sign-off is INCOMPLETE and will be rejected."
    )

    system_prompt = "\n\n".join(sections)

    # ── User prompt ──
    user_parts = []
    if (user_prompt or "").strip():
        user_parts.append(
            "═══ WHAT TO PITCH (the core of every email — do NOT ignore it or swap in generic value) ═══\n"
            f"{user_prompt}"
        )
    else:
        user_parts.append("Write a relevant cold-outreach sequence from the ICP context above.")

    if existing_copy:
        import re as _re
        _es = (existing_copy.get("subject") or "").strip()
        _eb = _re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", " ", existing_copy.get("body") or "")).strip()
        if _es or _eb:
            _draft = []
            if _es:
                _draft.append(f"Subject: {_es}")
            if _eb:
                _draft.append(f"Body: {_eb}")
            user_parts.append(
                "═══ THE USER ALREADY DRAFTED THIS — build on it, don't discard ═══\n"
                + "\n".join(_draft)
                + "\nKeep their angle, offer, and voice; refine it and extend it into the full sequence."
            )

    if lead_data:
        lead_info = []
        if lead_data.get("name"):
            lead_info.append(f"Name: {lead_data['name']}")
        if lead_data.get("job_title"):
            lead_info.append(f"Title: {lead_data['job_title']}")
        if lead_data.get("company_name"):
            lead_info.append(f"Company: {lead_data['company_name']}")
        if lead_info:
            user_parts.append("Prospect: " + ", ".join(lead_info))

    _fu_count = max(sequence_steps - 1, 0)
    if _fu_count <= 0:
        user_parts.append(
            "\nGenerate a single initial email only — NO follow-ups (return an empty follow-ups list)."
        )
    else:
        user_parts.append(
            f"\nGenerate a complete email sequence with 1 initial email + {_fu_count} follow-ups."
        )
        user_parts.append(
            "Follow-up angles should progress: bump (short, same thread) → new angle (different value prop / case study) → breakup (final, short)."
        )

    if variants_count > 1:
        user_parts.append(
            f"\nGenerate {variants_count} DISTINCT variants of the full sequence. "
            "Each variant should use a meaningfully different approach (e.g., question opener vs social proof vs direct value prop). "
            "Not just word swaps."
        )

    final_user_prompt = "\n\n".join(user_parts)

    return system_prompt, final_user_prompt


# ─────────────────────────────────────────────────────────────────────────────
# THE GENERATION CALL — mirrors generate_personalized_emails_bulk()'s core:
#   client.beta.chat.completions.parse(model="gpt-4.1-mini",
#       messages=[system, user], response_format=EmailSequence)
# Returns the parsed EmailSequence as a dict (the raw AI output — the thing to
# compare across models). Includes a fallback for endpoints that don't implement
# the beta .parse() helper (many open-source OpenAI-compatible servers).
# ─────────────────────────────────────────────────────────────────────────────
def generate_email_sequence(
    *,
    template_prompt: str,
    lead_data: dict | None = None,
    icp_profile: dict | None = None,
    writing_style: dict | None = None,
    research_brief: str | None = None,
    sequence_steps: int = 3,
    include_spintax: bool = False,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> dict:
    """Generate an email sequence exactly as Oppora does. Returns a dict:
        {"initial": {"subject","body"},
         "follow_ups": [{"subject","body","days_after"}, ...]}
    """
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),  # None -> real OpenAI
        **kwargs,
    )

    system_prompt, user_prompt = build_personalized_email_prompt(
        user_prompt=template_prompt,
        lead_data=lead_data,
        icp_profile=icp_profile,
        writing_style=writing_style,
        research_brief=research_brief,
        sequence_steps=sequence_steps,
        include_spintax=include_spintax,
        variants_count=1,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Primary path — IDENTICAL to Oppora (OpenAI structured outputs).
    try:
        resp = client.beta.chat.completions.parse(
            model=model,
            messages=messages,
            response_format=EmailSequence,
        )
        return resp.choices[0].message.parsed.model_dump()
    except Exception as e_parse:
        # Fallback for OpenAI-compatible endpoints without .beta...parse().
        # (a) try response_format=json_schema, (b) fall back to plain + JSON extract.
        schema = {
            "type": "json_schema",
            "json_schema": {"name": "EmailSequence", "schema": EmailSequence.model_json_schema(), "strict": False},
        }
        try:
            resp = client.chat.completions.create(model=model, messages=messages, response_format=schema)
            content = resp.choices[0].message.content
            data = json.loads(content)
        except Exception:
            resp = client.chat.completions.create(
                model=model,
                temperature=0.7,
                messages=messages + [{
                    "role": "system",
                    "content": "Return ONLY a JSON object with keys 'initial' "
                               "({subject, body}) and 'follow_ups' (list of "
                               "{subject, body, days_after}). No prose, no markdown.",
                }],
            )
            content = resp.choices[0].message.content or ""
            start, end = content.find("{"), content.rfind("}")
            data = json.loads(content[start:end + 1])

        return EmailSequence(**data).model_dump()


# ─────────────────────────────────────────────────────────────────────────────
# EXAMPLE — realistic inputs matching what Oppora passes per lead. Run this file
# directly to generate a sequence and print it. Swap --model / OPENAI_BASE_URL to
# compare an open-source model against the OpenAI baseline.
# ─────────────────────────────────────────────────────────────────────────────
def _demo(model: str):
    template_prompt = (
        "We help B2B SaaS sales teams book more meetings with an AI SDR that "
        "researches each prospect and writes personalized outreach. Offer: 30% "
        "off the starter plan for the first year if they start a trial this month."
    )

    lead_data = {
        "name": "Marcus Delgado",
        "job_title": "VP of Sales",
        "company_name": "Ledgerline",
    }

    icp_profile = {
        "company_context": {
            "description": "AI-powered sales prospecting and outreach platform for outbound teams",
            "value_proposition": "Book more qualified meetings without adding headcount",
            "key_differentiators": ["Per-prospect research", "Reply-rate optimized copy", "CRM-native"],
        },
        "buyer_persona": {
            "job_titles": ["VP Sales", "Head of Sales", "Director of Sales"],
            "pain_points": ["Reps spend hours on manual research", "Low reply rates", "Ramping SDRs is slow"],
            "buying_triggers": ["Recently raised funding", "Hiring SDRs", "Missed pipeline targets"],
        },
        "messaging": {
            "preferred_tone": "consultative",
            "elevator_pitch": "An AI SDR that researches every prospect and writes outreach that gets replies",
            "call_to_action": "Start a free trial",
        },
        "target_company": {"industries": ["SaaS", "Fintech"]},
    }

    writing_style = {
        "tone": "direct and warm",
        "avg_sentence_length": 16,
        "greeting_style": "Hi {first_name},",
        "sign_off_style": "Best, {from_first_name}",
        "forbidden_phrases": ["touching base", "circle back"],
    }

    result = generate_email_sequence(
        template_prompt=template_prompt,
        lead_data=lead_data,
        icp_profile=icp_profile,
        writing_style=writing_style,
        research_brief=None,
        sequence_steps=3,       # 1 initial + 2 follow-ups
        include_spintax=False,
        model=model,
    )

    print("=" * 78)
    print(f"MODEL: {model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com (default)'}")
    print("=" * 78)
    print("\n### INITIAL")
    print("Subject:", result["initial"]["subject"])
    print(result["initial"]["body"])
    for i, fu in enumerate(result["follow_ups"], 1):
        print(f"\n### FOLLOW-UP {i}  (+{fu['days_after']} days)")
        print("Subject:", fu.get("subject"))
        print(fu["body"])
    print("\n--- raw JSON ---")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Oppora email-generation replica")
    ap.add_argument("--model", default=os.environ.get("EMAIL_MODEL", "gpt-4.1-mini"),
                    help="Model name (swap for your open-source model)")
    args = ap.parse_args()
    _demo(args.model)
