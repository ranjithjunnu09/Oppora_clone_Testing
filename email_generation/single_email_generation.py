"""
Standalone replica of Oppora's SINGLE-EMAIL generator (`generate_ai_email`).

Backend-free copy of the exact AI logic — same prompt, schema, and model call as
production, so output matches Oppora. Deps: openai, pydantic only.

SOURCE OF TRUTH (kept byte-identical):
  sales/sales_open_ai.py -> generate_ai_email()  and class EmailBody

WHAT IT DOES
  Generates one professional HTML email (subject + body) using {first_name}
  {last_name} {company} as MERGE TAGS (left as literal placeholders — Oppora fills
  them per-recipient later). It is a template generator, so by default it takes no
  inputs, exactly like production.

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python single_email_generation.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python single_email_generation.py --model my-open-model
"""
from __future__ import annotations

import argparse
import json
import os

from pydantic import BaseModel, Field
from openai import OpenAI


# ── Output schema — verbatim from sales/sales_open_ai.py::EmailBody ──
class EmailBody(BaseModel):
    subject: str = Field(description="Email subject line — concise, no spam words, no 'Re:' prefix")
    body: str = Field(description="HTML email body using <p> tags. MUST end with a professional sign-off like '<p>Best,<br>{from_first_name}</p>' or '<p>Cheers,<br>{from_first_name}</p>'. Keep under 120 words.")


# ── The call — verbatim from generate_ai_email() ──
# System + user prompt are exactly Oppora's. `first_name`/`last_name`/`company`
# default to the literal merge tags (production passes nothing); override only if
# you want the model to write with concrete values instead of placeholders.
def generate_ai_email(
    *,
    first_name: str = "{first_name}",
    last_name: str = "{last_name}",
    company: str = "{company}",
    model: str = "gpt-4.1-mini-2025-04-14",
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str | None, str | None]:
    """Returns (subject, body). Mirrors Oppora's generate_ai_email()."""
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    messages = [
        {"role": "system",
         "content": "You are an expert at writing professional email messages. "
                    "Generate an email in HTML format. The email should not contain any links."},
        {"role": "user",
         "content": f"Generate a professional email message for {first_name} {last_name} "
                    f"who works at {company}. The email should be engaging and formal, "
                    f"and it should not contain any links. Don't use other variable except "
                    f"{first_name} {last_name} and {company}. Format it using HTML tags."},
    ]
    try:
        resp = client.beta.chat.completions.parse(
            model=model, messages=messages, temperature=0.7, response_format=EmailBody,
        )
        parsed = resp.choices[0].message.parsed
        return (parsed.subject, parsed.body) if parsed else (None, None)
    except Exception:
        # Fallback for endpoints without .beta...parse()
        schema = {"type": "json_schema",
                  "json_schema": {"name": "EmailBody", "schema": EmailBody.model_json_schema(), "strict": False}}
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.7, response_format=schema)
            data = json.loads(resp.choices[0].message.content)
        except Exception:
            resp = client.chat.completions.create(
                model=model, temperature=0.7,
                messages=messages + [{"role": "system",
                                      "content": "Return ONLY JSON: {\"subject\":..., \"body\":...}"}],
            )
            c = resp.choices[0].message.content or ""
            data = json.loads(c[c.find("{"):c.rfind("}") + 1])
        obj = EmailBody(**data)
        return obj.subject, obj.body


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("EMAIL_MODEL", "gpt-4.1-mini-2025-04-14"))
    args = ap.parse_args()
    subject, body = generate_ai_email(model=args.model)
    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}")
    print("\nSubject:", subject)
    print("Body:\n", body)
