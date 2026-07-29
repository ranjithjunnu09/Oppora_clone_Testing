"""
Standalone replica of Oppora's CAMPAIGN AI VARIABLE generator
(`_generate_ai_template_response`).

Backend-free copy of the exact AI logic — same system prompt and model call as
production, so output matches Oppora. Deps: openai only.

SOURCE OF TRUTH (kept byte-identical):
  sales/campaigns/utils.py -> _generate_ai_template_response()  (line ~504)

WHAT IT DOES
  Fills a SINGLE placeholder variable inside an email template — e.g. the
  `{ai_icebreaker}` variable a campaign template references — by weaving the
  lead/company/job fields the user's AiTemplate prompt references into one
  natural sentence. This is NOT the whole email; it generates the merge-tag
  VALUE that later gets substituted into the template body for one lead.

  This is the highest per-item VOLUME call in the whole AI-personalization
  path: production runs it ONCE PER LEAD when a campaign has AI variables
  enabled (a 500-lead AI-personalized campaign = 500 calls to this exact
  function). Measured production cost: ~1 credit per call. gpt-4.1-mini,
  max_tokens=300, so it's short and cheap per-call, but volume-driven overall
  — exactly the shape worth checking against a cheaper/open model.

  Placeholders the real AiTemplate prompts commonly reference (all optional —
  pass only the ones your prompt uses; unset ones are replaced with ""):
    {company} {first_name} {last_name} {lead_job_title} {job_location}
    {job_opening_title} {position}

  Post-processing: production also strips em/en dashes from the output
  (common.text_sanitize.strip_em_dashes) because the system prompt's own rule
  #6 ("never use em dashes") isn't 100% reliable on its own — this is
  replicated verbatim below rather than imported, to keep this file
  dependency-free.

RUN
  pip install openai
  export OPENAI_API_KEY=sk-...
  python campaign_ai_variable.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python campaign_ai_variable.py --model my-open-model
"""
from __future__ import annotations

import argparse
import os
import re

from openai import OpenAI


# ── Verbatim from common/text_sanitize.py (self-contained, no import needed) ──
_DASH_LITERALS = {
    "—": "-",  # em dash
    "–": "-",  # en dash
    "―": "-",  # horizontal bar
    "−": "-",  # minus sign
}
_DASH_ENTITIES = re.compile(r"&(?:mdash|ndash|#8212|#8211|#x201[34]);", re.IGNORECASE)


def strip_em_dashes(text: str | None) -> str | None:
    """Return text with em/en dashes (unicode + HTML entities) replaced by '-'."""
    if not isinstance(text, str) or not text:
        return text
    for ch, rep in _DASH_LITERALS.items():
        if ch in text:
            text = text.replace(ch, rep)
    if "&" in text:
        text = _DASH_ENTITIES.sub("-", text)
    return text


# ── The call — verbatim from _generate_ai_template_response() ──
def generate_ai_template_response(
    prompt: str,
    *,
    company: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    lead_job_title: str | None = None,
    job_location: str | None = None,
    job_opening_title: str | None = None,
    position: str | None = None,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Mirrors _generate_ai_template_response(). `prompt` is the AiTemplate's
    raw variable prompt (e.g. "Write one line referencing {first_name}'s role
    as {lead_job_title} at {company}"); the named args fill its placeholders.

    Production passes a Company model instance and reads `company.name` — here
    `company` is just the plain string, so the placeholder substitution below
    matches exactly but there's no Django model to construct.
    """
    system_message = """
    You are a helpful and creative AI assistant specializing in crafting personalized and engaging sentences.

    Here's how you should operate:

    1.  **Identify All Placeholders:** Locate all bracketed variables within the user's `prompt`.
    2.  **Understand Context (Implicit):** Infer the relationship between the placeholders and the overall context of a potential email.
    3.  **Integrate Fluently:** Weave all the identified placeholders into a single sentence that flows naturally and sounds like genuine communication. Avoid clunky phrasing or direct concatenation of the fields.
    4.  **Personalize and Engage:** Aim to create a sentence that feels personal and relevant to the recipient, making the email more engaging and impactful.
    5.  **Deliver One Polished Sentence:** Provide a single, well-crafted sentence that effectively incorporates all the given fields.
    6.  **Punctuation:** Never use em dashes or en dashes (the long dashes). Use a comma, period, or a spaced hyphen instead.
    """

    # Replace placeholders with provided values (unset -> "", same as production).
    prompt = prompt.replace("{company}", company or "")
    prompt = prompt.replace("{first_name}", first_name or "")
    prompt = prompt.replace("{last_name}", last_name or "")
    prompt = prompt.replace("{lead_job_title}", lead_job_title or "")
    prompt = prompt.replace("{job_location}", job_location or "")
    prompt = prompt.replace("{job_opening_title}", job_opening_title or "")
    prompt = prompt.replace("{position}", position or "")

    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=300,
    )
    u = response.usage
    print(f"[generate_ai_template_response] input={u.prompt_tokens} "
          f"cached={u.prompt_tokens_details.cached_tokens} "
          f"({u.prompt_tokens_details.cached_tokens / u.prompt_tokens * 100:.1f}%) "
          f"output={u.completion_tokens}")

    return strip_em_dashes(response.choices[0].message.content)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("VARIABLE_MODEL", "gpt-4.1-mini"))
    args = ap.parse_args()

    # A realistic AiTemplate prompt — this is the {ai_icebreaker} variable, the
    # most common real-world use of this function.
    demo_prompt = (
        "Write one warm, specific opening line referencing {first_name}'s role "
        "as {lead_job_title} at {company}, hinting we help teams like theirs "
        "book more sales meetings with AI-driven outreach."
    )

    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}\n")
    result = generate_ai_template_response(
        demo_prompt,
        company="Notion",
        first_name="Sarah",
        last_name="Johnson",
        lead_job_title="VP of Sales",
        model=args.model,
    )
    print("\n--- generated variable value ---\n")
    print(result)
