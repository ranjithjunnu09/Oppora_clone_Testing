"""
Standalone replica of Oppora's AUTOMATIC REPLY AGENT — the chain that runs on
a real inbound prospect reply (distinct from `reply_generation.py`, which
replicates the separate manual "AI reply" button in the campaign UI).

Backend-free copy of the exact AI logic — same prompts and structured-output
schemas as production. Deps: openai, pydantic only.

SOURCE OF TRUTH (kept byte-identical prompts + real graph edge order):
  sales/agent/reply_agents.py ->
    classify_intent()             (line ~200)
    decide_attachments()          (line ~254)  1-3 calls
    draft_reply()                 (line ~438)
    ai_send_decision()            (line ~821)  only runs if autonomy=True
    guardrail_check()             (line ~919)
    extract_referred_contacts()   (line ~1001)
  Graph wiring (verified against the real StateGraph edges, line ~1078-1154):
    classify_intent -> decide_attachments -> draft_reply -> guardrail_check
      -> extract_referred_contacts -> (autonomy? ai_decision : skip) -> [send/review]
  All 6 nodes run on ChatOpenAI(model="gpt-4.1-mini", temperature=0) in
  production via langchain_openai .with_structured_output(...).

WHAT IT DOES
  4-8 LLM calls per inbound reply (classify=1, attachments=1-3, draft=1,
  guardrail=1, referred_contacts=0-1, ai_send_decision=0-1 if autonomy is on).
  None of these are a tool-calling agent loop — it's a FIXED CHAIN of narrow
  structured-output calls, which is exactly why this is a good standalone
  candidate despite being called "an agent" in production.

  Deliberately NOT replicated (Django/DB-specific, not AI logic):
    - Fetching real attachments/ICP/campaign settings from the database
      (`decide_attachments` and `draft_reply` take plain dicts instead).
    - `send_email` node (the actual send action) and the `check_max_attempts`
      / `route_*` graph plumbing beyond the trivial booleans reproduced below.
    - The guardrail's Notification-on-failure side effect.

  Deliberately DIFFERENT (disclosed): production calls these via
  `ChatOpenAI(...).with_structured_output(Model)`; this file uses the raw
  `openai` SDK's `.beta.chat.completions.parse(...)` instead, for the same
  reason as the rest of this repo (no `langchain` dependency).

  A REAL INCONSISTENCY FOUND WHILE REPLICATING (kept, not silently fixed):
  `classify_intent`'s Pydantic field types `intent` as `Email_Status_Enum`
  (Lead/Interested/Moderate/Meeting booked/.../Bounced/Rejected — the CRM
  status enum) but the SYSTEM PROMPT instructs the model to classify into a
  totally different category set (positive_interest/request_info/
  out_of_office/not_interested/unsubscribe/objection_timing/
  objection_pricing/other). These do not overlap. Production's structured-
  output call would force the model to squeeze its answer into
  Email_Status_Enum's values even though the prompt asked for different
  labels — worth flagging back to the team, not something to fix here.

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python reply_agent_chain.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python reply_agent_chain.py --model my-open-model
"""
from __future__ import annotations

import argparse
import os
import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field
from openai import OpenAI


def _client(api_key: str | None = None, base_url: str | None = None, **kwargs) -> OpenAI:
    return OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        **kwargs,
    )


def _call(client, model, system, user, schema, label):
    """Shared structured-output call + usage print, used by every node below."""
    response = client.beta.chat.completions.parse(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format=schema,
    )
    u = response.usage
    cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
    print(f"[{label}] input={u.prompt_tokens} "
          f"cached={cached_tokens} "
          f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
          f"output={u.completion_tokens}")
    return response.choices[0].message.parsed


# ── Verbatim from common/text_sanitize.py (self-contained, no import needed) ──
_DASH_LITERALS = {"—": "-", "–": "-", "―": "-", "−": "-"}
_DASH_ENTITIES = re.compile(r"&(?:mdash|ndash|#8212|#8211|#x201[34]);", re.IGNORECASE)


def strip_em_dashes(text: str | None) -> str | None:
    if not isinstance(text, str) or not text:
        return text
    for ch, rep in _DASH_LITERALS.items():
        if ch in text:
            text = text.replace(ch, rep)
    if "&" in text:
        text = _DASH_ENTITIES.sub("-", text)
    return text


# =============================================================================
# Schemas — verbatim from sales/agent/reply_agents.py
# =============================================================================

class Email_Status_Enum(str, Enum):
    """Verbatim from sales/sales_open_ai.py (imported by reply_agents.py).
    See the module docstring: this is the enum classify_intent's schema uses,
    even though its OWN prompt asks for a different category set."""
    LEAD = "Lead"
    INTERESTED = "Interested"
    MODERATE = "Moderate"
    MEETING_BOOKED = "Meeting booked"
    MEETING_COMPLETED = "Meeting completed"
    WON = "Won"
    OUT_OF_OFFICE = "Out of office"
    WRONG_PERSON = "Wrong person"
    NOT_INTERESTED = "Not interested"
    LOST = "Lost"
    BOUNCED = "Bounced"
    REJECTED = "Rejected"


class IntentClassification(BaseModel):
    intent: Email_Status_Enum = Field(description="The classified intent of the prospect's email.")
    confidence: float = Field(description="Confidence score between 0.0 and 1.0.")


class AttachmentDecision(BaseModel):
    should_include_attachments: bool = Field(description="Whether attachments should be included in this reply")
    reasoning: str = Field(description="Explanation for the decision")


class AttachmentAnalysis(BaseModel):
    attachment_id: int = Field(description="ID of the attachment")
    relevance_score: float = Field(description="Relevance score from 0.0 to 1.0 for the prospect's request")
    content_type: str = Field(description="Type of content (e.g., case_study, demo)")
    key_topics: List[str] = Field(description="Key topics covered in this attachment")
    reasoning: str = Field(description="Why this attachment is or isn't relevant")


class AttachmentSelection(BaseModel):
    selected_attachment_ids: List[int] = Field(description="List of attachment IDs to include in this reply")
    reasoning: str = Field(description="Explanation for why these specific attachments were selected")
    total_attachments_available: int = Field(description="Total number of attachments available")


class SendDecision(BaseModel):
    should_send: bool = Field(description="Whether to send the email immediately or save as draft")
    confidence: float = Field(description="Confidence level in this decision (0.0 to 1.0)")
    reasoning: str = Field(description="Explanation for the send vs draft decision")


class GuardrailCheck(BaseModel):
    is_safe: bool = Field(description="Whether the draft passes all safety checks")
    issues: List[str] = Field(description="List of any issues found")
    pii_detected: bool = Field(description="Whether PII was detected")


class ReferredContact(BaseModel):
    email: str = Field(description="Email address of the referred contact")
    name: str = Field(description="Name of the referred contact if mentioned, otherwise empty string")
    role: str = Field(description="Job title or role of the referred contact if mentioned, otherwise empty string")


class ReferredContactExtraction(BaseModel):
    has_referred_contacts: bool = Field(description="Whether the email contains referred contacts")
    referred_contacts: List[ReferredContact] = Field(description="List of referred contacts found in the email")


# =============================================================================
# Node 1: classify_intent
# =============================================================================
def classify_intent(
    prospect_message: str,
    *,
    product_context: str = "",
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> IntentClassification:
    """`product_context` mirrors the optional ICP-derived sentence production
    appends (e.g. "\\n    Context: We sell {description}. ...")."""
    few_shot_examples = [
        {"email": "This looks good. I'd like to learn more.", "intent": "interested"},
        {"email": "Please remove me from your list.", "intent": "unsubscribe"},
        {"email": "No thanks, not relevant to us.", "intent": "not_interested"},
        {"email": "I'm out of office until next Monday.", "intent": "out_of_office"},
        {"email": "Can we schedule a 15-minute call next week?", "intent": "meeting_booked"},
        {"email": "We went with another vendor.", "intent": "lost"},
    ]
    system_prompt = f"""
    You are an expert sales assistant. Classify the prospect's intent into one of:
    positive_interest, request_info, out_of_office, not_interested, unsubscribe,
    objection_timing, objection_pricing, other.
    Examples:
    {chr(10).join([f"- '{e['email']}' -> {e['intent']}" for e in few_shot_examples])}
    Pay special attention to requests for information, documents, case studies, or materials
    as these should be classified as 'request_info'.
    Base your classification solely on the content of the email provided.{product_context}
    """
    client = _client(api_key, base_url)
    return _call(client, model, system_prompt, prospect_message, IntentClassification, "classify_intent")


# =============================================================================
# Node 2: decide_attachments (1-3 calls: decide -> analyze each -> select)
# =============================================================================
def decide_attachments(
    prospect_message: str,
    intent: str,
    attachments: list[dict],
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """`attachments`: list of {"id": int, "file_name": str, "description": str}
    (production reads these off Django CampaignEmailSend.campaign.campaign_attachments,
    capped at 5). Returns {"should_include_attachments": bool, "selected_attachments": [int, ...]}."""
    client = _client(api_key, base_url)
    result = {"should_include_attachments": False, "selected_attachments": []}
    if not attachments:
        return result

    # Step 1 — should we include anything at all?
    decision_prompt = f"""
    Analyze this prospect's email reply and determine if attachments should be included in the response.

    Prospect's message: "{prospect_message}"
    Classified intent: {intent}

    Consider:
    - Does the prospect explicitly request information, materials, or documentation?
    - Are they asking for details, case studies, demos, or proposals?
    - Would attachments help answer their questions or move the conversation forward?
    - Is this an appropriate time to share materials (not if they're unsubscribing or not interested)?

    Available attachments: {len(attachments)} documents available
    """
    decision = _call(client, model, decision_prompt, prospect_message, AttachmentDecision, "decide_attachments:decision")
    if not decision.should_include_attachments:
        return result

    # Step 2 — analyze each attachment for relevance.
    analyses: list[AttachmentAnalysis] = []
    for att in attachments[:5]:
        ext = att["file_name"].rsplit(".", 1)[-1] if "." in att["file_name"] else "unknown"
        analysis_prompt = f"""
        Analyze this attachment for relevance to the prospect's request.

        Prospect's message: "{prospect_message}"
        Prospect's intent: {intent}

        Attachment details:
        - Name: {att['file_name']}
        - Description: {att.get('description', 'No description available')}
        - File type: {ext}

        Rate the relevance (0.0 to 1.0) and identify key topics this attachment covers.
        Consider if this specific attachment would help answer the prospect's questions or interests.
        """
        a = _call(client, model, analysis_prompt, prospect_message, AttachmentAnalysis,
                  f"decide_attachments:analyze#{att['id']}")
        a.attachment_id = att["id"]
        analyses.append(a)

    if not analyses:
        return result

    # Step 3 — select the best 1-3 based on the analysis.
    analysis_summary = "\n".join(
        f"Attachment {a.attachment_id}: Relevance {a.relevance_score}, Topics: {', '.join(a.key_topics)}, Reasoning: {a.reasoning}"
        for a in analyses
    )
    selection_prompt = f"""
    Based on the attachment analysis below, select the most relevant attachments to include in the reply.

    Prospect's message: "{prospect_message}"
    Prospect's intent: {intent}

    Attachment Analysis:
    {analysis_summary}

    Guidelines:
    - Select 1-3 most relevant attachments (don't overwhelm the prospect)
    - Prioritize attachments with higher relevance scores (>0.6)
    - Consider the prospect's specific request and intent
    - Balance comprehensiveness with relevance

    Total attachments available: {len(analyses)}
    """
    selection = _call(client, model, selection_prompt, prospect_message, AttachmentSelection, "decide_attachments:select")
    valid_ids = {a.attachment_id for a in analyses}
    selected = [i for i in selection.selected_attachment_ids if i in valid_ids]
    if selected:
        result["should_include_attachments"] = True
        result["selected_attachments"] = selected
    return result


# =============================================================================
# Node 3: draft_reply
# =============================================================================
def draft_reply(
    prospect_message: str,
    *,
    intent: str,
    current_attempt: int = 0,
    status_primary_goal: str = "book_meeting",
    status_fallback_goal: str = "nurture_relationship",
    meeting_tool_url: str = "",
    tone: str = "friendly-professional",
    should_include_attachments: bool = False,
    icp_context_str: str = "",
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """The core drafting call. Production also unpacks the full prior message
    history after the system prompt — pass just the latest prospect message
    here for a single-turn demo; for a real multi-turn conversation, prepend
    earlier turns to `prospect_message` yourself before calling."""
    system_prompt = f"""

    You are a real sales professional writing a personal email reply. Write naturally like you would text a colleague or friend.

    ***Reply Format: HTML only. Use <br> tags for line breaks — never use plain newlines (\\n). Every line break in the email MUST be a <br> tag.***
    {icp_context_str}

    **Your situation:**
    - This is follow-up #{current_attempt + 1}
    - Status detected: {intent}
    - Primary goal for this status: {status_primary_goal}
    - Fallback goal for this status: {status_fallback_goal}
    - Your tone: {tone}
    - Will include attachments: {should_include_attachments}
    - Your meeting link: {meeting_tool_url}

    **Critical rules:**
    1. Write like a REAL PERSON - no corporate speak, no templates, no AI language
    2. Use natural conversational language - contractions, casual phrasing
    3. NO placeholders like [company name] or [product] - be specific about what you do
    4. Keep it SHORT - 2-3 sentences max
    5. Sound genuine and personal, not scripted
    6. When sharing meeting links, use the EXACT URL provided: {meeting_tool_url} (if not empty)
    7. Prioritize the PRIMARY GOAL for this status, fall back to FALLBACK GOAL if primary doesn't fit

    **Goal Strategy:**
    - Primary Goal: {status_primary_goal}
    - Fallback Goal: {status_fallback_goal}
    - Adapt your response to achieve the primary goal first, but use the fallback goal if the prospect's response suggests the primary isn't appropriate

    **What to avoid:**
    - Em dashes or en dashes (the long dashes) - use a comma or period instead
    - "Thanks for your interest!" (too formal)
    - "I'd be happy to..." (robotic)
    - "Looking forward to your thoughts!" (AI speak)
    - Any brackets [ ] or placeholder text
    - Corporate jargon or sales speak
    - Markdown formatting like [text](url) - use plain URLs
    - Generic placeholder URLs like calendly.com/yourname

    **Write like this instead:**
    - "Hey [name], glad you're interested"
    - "So we basically help companies..."
    - "Want to hop on a quick call?"
    - "Let me know what works"
    - "Makes sense to chat for 15 mins?"
    - "Here's my calendar link: {meeting_tool_url}" (use the exact URL, no formatting)

    **Meeting strategy based on prospect intent and situation:**
    - **"meeting booked" intent**: Always include your meeting link since they explicitly asked for a meeting
    - **"interested" intent**: Include meeting link ONLY on follow-up attempts (attempt #2+), not on first reply
    - **"lead" intent**: Include meeting link ONLY if they mention words like "call", "meeting", "chat", "talk", "discuss", "schedule"
    - **Other intents** ("not interested", "out of office", "wrong person", "lost", "moderate", "won"): Do NOT include meeting link
    - **CRITICAL**: Only include meeting link if you have a valid URL: {meeting_tool_url}
    - **If no meeting URL provided (empty)**: Do NOT mention scheduling, calendar links, or booking calls
    - **Format**: Use the exact URL as plain text, no markdown formatting

    {f"**For attachments:** If including attachments, mention them naturally: 'I'm attaching some materials that should help' or 'Sent over the info you requested'" if should_include_attachments else "**Important:** Do NOT mention attachments, documents, or sending materials since none are being included in this reply."}

    **IMPORTANT:** Only use a meeting URL if one is actually provided ({meeting_tool_url}). If empty, do not mention meetings or scheduling.

    Write a natural, human response that doesn't sound like a bot or template and aligns with your goals for this specific status.
    """
    client = _client(api_key, base_url)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": prospect_message}],
    )
    u = response.usage
    cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
    print(f"[draft_reply] input={u.prompt_tokens} "
          f"cached={cached_tokens} "
          f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
          f"output={u.completion_tokens}")
    return strip_em_dashes(response.choices[0].message.content)


# =============================================================================
# Node 4: guardrail_check
# =============================================================================
_SERIOUS_PII_PATTERNS = [
    r'\b\d{3}-\d{2}-\d{4}\b',   # SSN
    r'\b\d{16}\b',              # Credit card numbers
    r'\b\d{3}-\d{3}-\d{4}\b',   # Phone numbers in XXX-XXX-XXXX format
]


def guardrail_check(
    draft: str,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict:
    """Returns {"guardrail_passed": bool, "issues": [...], "pii_detected": bool}."""
    compliance_prompt = """
    Review this sales email draft for SERIOUS safety violations only:

    Only flag if you find:
    1. Personal sensitive data (SSN, credit cards, private phone numbers)
    2. Extremely inappropriate language (profanity, threats)
    3. Obvious scam content or fraud
    4. Illegal activities

    DO NOT flag for:
    - Business documents, brochures, case studies
    - Normal sales language
    - Requests for information or meetings
    - Standard business communication

    Draft: "{draft}"

    Only mark as unsafe if there are SERIOUS compliance violations.
    """.format(draft=draft)

    serious_pii_found = any(re.search(p, draft) for p in _SERIOUS_PII_PATTERNS)
    client = _client(api_key, base_url)
    response = _call(client, model, compliance_prompt, draft, GuardrailCheck, "guardrail_check")
    return {
        "guardrail_passed": response.is_safe and not serious_pii_found,
        "issues": response.issues,
        "pii_detected": response.pii_detected or serious_pii_found,
    }


# =============================================================================
# Node 5: extract_referred_contacts
# =============================================================================
def extract_referred_contacts(
    prospect_message: str,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> list[dict]:
    system_prompt = """
        Extract all referred contacts from this email. A referred contact is any person mentioned with their email address.

        Instructions:
        - Find ALL email addresses that refer to other people (not the sender)
        - Extract the person's name if mentioned alongside the email
        - Extract their role/title if mentioned (e.g., "technical lead", "finance manager", "director")
        - Include emails in any format: parentheses, after "at", after commas, etc.
        - Read carefully to avoid including sender or sender referred contacts.

        Be thorough and extract every contact you find in the email.
        """
    client = _client(api_key, base_url)
    response = _call(client, model, system_prompt, f"Email to analyze:\n\n{prospect_message}",
                     ReferredContactExtraction, "extract_referred_contacts")
    if response.has_referred_contacts and response.referred_contacts:
        return [{"email": c.email, "name": c.name or "", "role": c.role or ""}
                for c in response.referred_contacts]
    return []


# =============================================================================
# Node 6: ai_send_decision (ONLY runs if autonomy=True, per the real graph edge)
# =============================================================================
def ai_send_decision(
    draft: str,
    intent: str,
    current_attempt: int,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> SendDecision:
    decision_prompt = f"""
    You are an experienced sales professional. Review this email draft and decide whether it should be sent immediately or saved as a draft for human review.

    Email Draft: "{draft}"
    Prospect Intent: {intent}
    Follow-up Attempt: #{current_attempt}

    Consider these factors:
    1. **Risk Level**: Is this a sensitive situation (e.g., legal, reputational, or high-stakes) that needs human oversight?
    2. **Message Quality**: Is the draft clear, professional, on-brand, and appropriate for the context?
    3. **Timing**: Is this the right moment to send, or would waiting (e.g., after internal alignment) be wiser?
    4. **Relationship Stage**: Is automation appropriate here? Early-stage or high-value prospects often warrant more care.
    5. **Content Complexity**: Does the message require strategic nuance, empathy, or creative problem-solving?
    6. **Factual Accuracy**: **Crucially, does the draft assert any specific, verifiable facts** (e.g., about product availability, pricing, free trials, compliance certifications, integrations, timelines, or company policies)?
        -> If the AI could be wrong, even slightly, about any of these, it **must** be reviewed by a human.
        -> **Never assume the AI knows current product details, pricing, or policy changes.**
    7. **Missing Content**: **CRITICAL, does the draft promise or reference content that is missing or empty?**
        -> Check for phrases like "here's the link", "here's my calendar", "attached document", "see below" when the actual content is missing or empty
        -> If the draft mentions links, attachments, or information but they are not provided or are empty, it **must** be a **DRAFT**
        -> Never send emails that promise content but deliver nothing

    Guidelines:
    - **SEND** only if:
        It's just an acknowledgment, confirmation, or light follow-up.
        It avoids specifics on pricing, compliance, features, or policies.
        It uses soft, open language (e.g., "happy to explore options").

    - **DRAFT** if:
        It mentions or implies pricing, compliance, features, policies, or guarantees.
        The prospect is high-value, early-stage, or asks a factual question.
        There's any uncertainty or risk of misrepresentation.

    **Golden Rule**:
    > If the email contains a statement that would be **embarrassing or damaging if factually wrong** OR **promises content that isn't delivered**, it must be a **DRAFT**.

    Make your decision ("SEND" or "DRAFT") and explain your reasoning clearly, citing specific phrases or risks from the draft.
    """
    client = _client(api_key, base_url)
    return _call(client, model, decision_prompt, draft, SendDecision, "ai_send_decision")


# =============================================================================
# Orchestrator — verbatim edge order from the real StateGraph wiring
# =============================================================================
def run_reply_pipeline(
    prospect_message: str,
    *,
    attachments: list[dict] | None = None,
    autonomy: bool = False,
    current_attempt: int = 0,
    meeting_tool_url: str = "",
    tone: str = "friendly-professional",
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> dict:
    """Runs the real node sequence: classify_intent -> decide_attachments ->
    draft_reply -> guardrail_check -> extract_referred_contacts ->
    (autonomy? ai_send_decision : skip). Returns a dict with every
    intermediate result, mirroring the graph's shared state object."""
    kw = dict(model=model, api_key=api_key, base_url=base_url, **kwargs)

    intent_result = classify_intent(prospect_message, **kw)
    intent = intent_result.intent.value

    att_result = decide_attachments(prospect_message, intent, attachments or [], **kw)

    draft = draft_reply(
        prospect_message, intent=intent, current_attempt=current_attempt,
        meeting_tool_url=meeting_tool_url, tone=tone,
        should_include_attachments=att_result["should_include_attachments"], **kw,
    )

    guardrail = guardrail_check(draft, **kw)
    if not guardrail["guardrail_passed"]:
        autonomy = False  # production forces human review on a guardrail failure

    referred = extract_referred_contacts(prospect_message, **kw)

    send_decision = None
    if autonomy:
        send_decision = ai_send_decision(draft, intent, current_attempt, **kw)
        final_decision = "send" if send_decision.should_send else "review"
    else:
        final_decision = "review"

    return {
        "intent": intent, "intent_confidence": intent_result.confidence,
        "should_include_attachments": att_result["should_include_attachments"],
        "selected_attachments": att_result["selected_attachments"],
        "draft": draft, "guardrail": guardrail, "referred_contacts": referred,
        "send_decision": send_decision, "final_decision": final_decision,
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("REPLY_AGENT_MODEL", "gpt-4.1-mini"))
    ap.add_argument("--autonomy", action="store_true",
                     help="Enable AI send-decision (runs the 6th LLM call).")
    args = ap.parse_args()

    demo_message = (
        "Thanks for reaching out! This actually looks interesting, can you send over "
        "a case study or two? Also loop in my colleague on this, Alex Kim "
        "(alex.kim@example.com), he's our technical lead and should see this too."
    )
    demo_attachments = [
        {"id": 1, "file_name": "case_study_saas.pdf", "description": "Case study: SaaS company grew reply rate 3x"},
        {"id": 2, "file_name": "pricing_sheet.pdf", "description": "Current pricing tiers"},
        {"id": 3, "file_name": "company_overview.pdf", "description": "General company one-pager"},
    ]

    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}   "
          f"autonomy={args.autonomy}\n")

    result = run_reply_pipeline(
        demo_message, attachments=demo_attachments, autonomy=args.autonomy,
        meeting_tool_url="https://cal.com/demo-rep/15min", model=args.model,
    )

    print("\n--- pipeline result ---\n")
    print(f"intent: {result['intent']} (confidence={result['intent_confidence']:.2f})")
    print(f"include attachments: {result['should_include_attachments']} -> {result['selected_attachments']}")
    print(f"guardrail: {result['guardrail']}")
    print(f"referred contacts: {result['referred_contacts']}")
    if result["send_decision"]:
        print(f"send decision: should_send={result['send_decision'].should_send} "
              f"({result['send_decision'].reasoning})")
    print(f"final_decision: {result['final_decision']}")
    print(f"\ndraft:\n{result['draft']}")
