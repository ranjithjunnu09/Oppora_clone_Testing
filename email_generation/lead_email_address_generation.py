"""
Standalone replica of Oppora's LEAD EMAIL-ADDRESS generator (`generate_lead_email`).

NOTE: this generates candidate email ADDRESSES for a person by inferring their
company's email pattern from known colleague addresses — it does NOT write email
content. Included here because it's an AI text-gen feature worth comparing across
models. Backend-free; deps: openai, pydantic.

SOURCE OF TRUTH (kept byte-identical):
  sales/sales_open_ai.py -> generate_lead_email()  and class Email

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python lead_email_address_generation.py
  # open-source:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #               python lead_email_address_generation.py --model my-open-model
"""
from __future__ import annotations

import argparse
import json
import os
from typing import List

from pydantic import BaseModel
from openai import OpenAI


# ── Output schema — verbatim from sales/sales_open_ai.py::Email ──
class Email(BaseModel):
    lead_name: str
    emails: List[str]


# ── The call — verbatim from generate_lead_email() ──
def generate_lead_email(
    name: str,
    company: str,
    other_leads: str,
    *,
    model: str = "gpt-4.1-mini-2025-04-14",
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[str | None, List[str] | None]:
    """Returns (lead_name, emails). Mirrors Oppora's generate_lead_email().

    other_leads: free text of known colleague emails at the same company, e.g.
        "Name: Jane Smith\\nEmail: jane.smith@acme.com"
    """
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    messages = [
        {"role": "system",
         "content": "You are an expert at generating email for a lead. "
                    "Generate emails of a lead using his/her company leads email pattern. "
                    "You should give maximum 5 best pattern emails"},
        {"role": "user",
         "content": f"Generate emails for {name}"
                    f"who works at {company}. Some of leads emails of same company are: {other_leads}"},
    ]
    try:
        resp = client.beta.chat.completions.parse(
            model=model, messages=messages, temperature=0.7, response_format=Email,
        )
        parsed = resp.choices[0].message.parsed
        return (parsed.lead_name, parsed.emails) if parsed else (None, None)
    except Exception:
        schema = {"type": "json_schema",
                  "json_schema": {"name": "Email", "schema": Email.model_json_schema(), "strict": False}}
        try:
            resp = client.chat.completions.create(model=model, messages=messages, temperature=0.7, response_format=schema)
            data = json.loads(resp.choices[0].message.content)
        except Exception:
            resp = client.chat.completions.create(
                model=model, temperature=0.7,
                messages=messages + [{"role": "system",
                                      "content": "Return ONLY JSON: {\"lead_name\":..., \"emails\":[...]}"}],
            )
            c = resp.choices[0].message.content or ""
            data = json.loads(c[c.find("{"):c.rfind("}") + 1])
        obj = Email(**data)
        return obj.lead_name, obj.emails


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("EMAIL_MODEL", "gpt-4.1-mini-2025-04-14"))
    args = ap.parse_args()
    lead_name, emails = generate_lead_email(
        name="John Dev",
        company="Bluebix Inc",
        other_leads="Name: Charlotte Kris\nEmail: charlotte.kris@bluebixinc.com",
        model=args.model,
    )
    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}")
    print("\nlead_name:", lead_name)
    print("emails:", emails)
