"""
Standalone replica of Oppora's AI EMAIL-REPLY generator (`_generate_ai_reply`).

Backend-free copy of the exact AI logic — same system+user prompt and model call
as production, so replies match Oppora. Deps: openai only (plain text output).

SOURCE OF TRUTH (kept byte-identical):
  sales/campaigns/api/v1/views.py -> _generate_ai_reply()

WHAT IT DOES
  Given a conversation `context` (original email + follow-ups + replies received),
  a free-text `user_instruction`, and a `tone`, it writes a natural email reply
  body (plain text, 2-3 paragraphs, one CTA). gpt-4.1-mini, max_tokens=400.

RUN
  pip install openai
  export OPENAI_API_KEY=sk-...
  python reply_generation.py
  # open-source:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #               python reply_generation.py --model my-open-model
"""
from __future__ import annotations

import argparse
import os

from openai import OpenAI


def generate_ai_reply(
    context: dict,
    user_instruction: str = "",
    tone: str = "professional",
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> str:
    """Mirrors Oppora's _generate_ai_reply(). Returns the reply body (plain text).

    `context` shape (all optional):
        {
          "subject": str,
          "main_message": str,                       # the original email
          "follow_ups": [{"subject","message"}, ...],
          "replies":    [{"subject","message"}, ...] # replies received
        }
    """
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )

    # ── system message — verbatim from production ──
    system_message = f"""
        You are a professional email assistant. Generate a personalized email reply based on the conversation history and user instructions.

        Tone: {tone}

        REQUIREMENTS:
        - Generate ONLY the email body content (no signatures or headers)
        - NEVER use placeholder text like [your name], [company name], etc.
        - Keep responses concise (2-3 paragraphs max)
        - Include a clear call-to-action
        - Sound natural and human-like
        - Reference recent conversation context when relevant
        - Consider the full conversation history to provide contextually appropriate responses
        """

    # ── user prompt — verbatim conversation-timeline construction ──
    user_prompt = f"""
        CONVERSATION HISTORY:

        Original Email:
        Subject: {context.get('subject', 'N/A')}
        Message: {context.get('main_message', 'N/A')}
        """

    if context.get('follow_ups'):
        user_prompt += "\n\nAll follow-up emails sent:"
        for i, follow_up in enumerate(context['follow_ups'], 1):
            user_prompt += f"\n{i}. {follow_up.get('message', '')}"

    if context.get('replies'):
        user_prompt += "\n\nAll replies received:"
        for i, reply in enumerate(context['replies'], 1):
            user_prompt += f"\n{i}. {reply.get('message', '')}"

    user_prompt += f"""

        User Instructions: {user_instruction if user_instruction else 'Generate an appropriate professional reply'}

        Based on the FULL conversation history above, generate a compelling email reply that continues the conversation naturally and addresses all relevant points from the conversation.
        """

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=400,
    )
    return (resp.choices[0].message.content or "").strip()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("EMAIL_MODEL", "gpt-4.1-mini"))
    args = ap.parse_args()

    demo_context = {
        "subject": "Quick question about your outbound process",
        "main_message": "Hi Marcus, I help SaaS sales teams book more meetings with an AI SDR "
                        "that researches each prospect and writes the outreach. Worth a quick chat?",
        "follow_ups": [
            {"subject": None, "message": "Just floating this back up — teams using us see ~20% higher reply rates."},
        ],
        "replies": [
            {"subject": "RE: Quick question", "message": "Interesting. How is your data different from Apollo, "
                                                         "and do you integrate with HubSpot? What's pricing like?"},
        ],
    }

    reply = generate_ai_reply(
        demo_context,
        user_instruction="Answer their questions about data, HubSpot integration, and pricing; offer a short call.",
        tone="friendly and consultative",
        model=args.model,
    )
    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}")
    print("\n--- generated reply ---\n")
    print(reply)
