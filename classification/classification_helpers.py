"""
Standalone replica of 4 of Oppora's small AI CLASSIFIER/EXTRACTOR functions.

Backend-free copies of the exact prompts and structured-output schemas as
production. Deps: openai, pydantic only.

SOURCE OF TRUTH (kept byte-identical prompts):
  sales/sales_open_ai.py ->
    get_companies_industry()     (line ~288)  gpt-4.1-mini-2025-04-14
    extract_email_pattern()      (line ~643)  gpt-4.1-mini
    email_status_predict()       (line ~1420) o4-mini, reasoning_effort="high"
    delivery_failure_predict()   (line ~1485) gpt-4.1-mini

WHAT THESE DO
  Four small, narrow, single-call classifiers/extractors — the "long tail"
  behind Oppora's bigger generation features. Each is one LLM call, cheap
  individually, but each fires at real volume across the platform (company
  enrichment, email-pattern guessing, inbound-reply triage, bounce/reject
  triage). Bundled into one file because they share the exact same shape:
  one prompt in, one small structured field out.

  1. classify_company_industry(companies)
     Given a batch of company dicts, returns each with its industry +
     approx employee size filled in.
  2. extract_email_pattern(lead_name, lead_email)
     Infers the {first_name}.{last_name}@{domain}-style pattern from one
     known (name, email) pair — used to guess other emails at the same company.
  3. predict_email_status(prompt)
     Classifies an inbound reply into one of 12 fixed statuses (Interested,
     Meeting booked, Not interested, Bounced, ...). NOTE: this is the one
     function in this bundle that uses A DIFFERENT, REASONING model
     (o4-mini, reasoning_effort="high") — worth benchmarking separately
     from the other three gpt-4.1-mini calls.
  4. predict_delivery_failure(prompt)
     Classifies a bounce-back/NDR email as "bounced" (bad address) vs
     "rejected" (server refused it) from the SMTP diagnostic text.

  Deliberately SIMPLIFIED (disclosed, not silent): production's `industry`
  field is a dynamically-built Enum covering Oppora's full LinkedIn industry
  taxonomy (hundreds of values, built from a shared constants list at import
  time — see `_build_industry_enum()` / `IndustryType` in the source file).
  Replicating that whole taxonomy here would bloat this file without adding
  anything to a model-comparison test, so `industry` is a plain `str` below.
  `EmployeeSize` (8 fixed buckets) IS small enough to replicate verbatim, so
  that one is kept exactly as production defines it.

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python classification_helpers.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python classification_helpers.py --model my-open-model
  # o4-mini classifier specifically:
  #                     python classification_helpers.py --reasoning-model o4-mini
"""
from __future__ import annotations

import argparse
import os
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


# =============================================================================
# 1. classify_company_industry — mirrors get_companies_industry()
# =============================================================================

class EmployeeSize(str, Enum):
    """Verbatim from sales/sales_open_ai.py. CrustData dropped '1-10';
    smallest bucket is now '2-10'."""
    SIZE_1_10 = "2-10"
    SIZE_11_50 = "11-50"
    SIZE_51_200 = "51-200"
    SIZE_201_500 = "201-500"
    SIZE_501_1000 = "501-1000"
    SIZE_1001_5000 = "1001-5000"
    SIZE_5001_10000 = "5001-10000"
    SIZE_10000_PLUS = "10001+"


class Industry(BaseModel):
    """`industry` simplified to `str` here — see module docstring."""
    name: str
    domain: Optional[str] = Field(None, description="Company official website domain")
    website: Optional[str] = Field(None, description="Company official website")
    industry: str = Field(..., description="Company industry")
    approx_employee_size: EmployeeSize = Field(..., description="Approximate employee count range")
    linkedin: str
    location: Optional[str] = Field(None, description="Company location")


class CompanyIndustry(BaseModel):
    companies: List[Industry]


def classify_company_industry(
    companies: list[dict],
    *,
    model: str = "gpt-4.1-mini-2025-04-14",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> list[Industry]:
    """Mirrors get_companies_industry(). `companies` is a list of dicts with
    whatever raw fields you have (domain, linkedin_url, official site text,
    etc.) — the model fills in industry + approx_employee_size for each."""
    client = _client(api_key, base_url, **kwargs)
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system",
             "content": "You are an expert at company domain, industry and employee size analyzer. "
                        "You will be given all company domain, industry, approx employee size, linkedin_url "
                        "from their linkedin and official site then should convert it into the given structure."},
            {"role": "user",
             "content": f"I need all this companies industry and approx employee size. Here is all companies list: {companies} "},
        ],
        response_format=CompanyIndustry,
    )
    u = completion.usage
    cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
    print(f"[classify_company_industry] input={u.prompt_tokens} "
          f"cached={cached_tokens} "
          f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
          f"output={u.completion_tokens}")
    message = completion.choices[0].message
    return message.parsed.companies if message.parsed else []


# =============================================================================
# 2. extract_email_pattern — mirrors extract_email_pattern()
# =============================================================================

class EmailPatternResponse(BaseModel):
    email_pattern: str


def extract_email_pattern(
    lead_name: str,
    lead_email: str,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> str | None:
    """Mirrors extract_email_pattern(). Infers the {first_name}.{last_name}@{domain}
    -style pattern from one known (name, email) pair."""
    prompt = f"""
    Given the lead name: {lead_name} and the lead email: {lead_email}, analyze and provide the email pattern.If you want give character then use like this first_name[character_position]. If pattern is not matching then return None
    Here is the some example patterns= [
        "{{first_name}}@{{domain}}",
        "{{first_name[0]}}{{last_name}}@{{domain}}",
        "{{last_name}}{{first_name[0]}}@{{domain}}",
        "{{first_name}}.{{last_name}}@{{domain}}",
        "{{first_name}}{{last_name}}@{{domain}}",
        "{{last_name}}@{{domain}}",
        "{{first_name[0]}}.{{last_name}}@{{domain}}",
        "{{first_name}}{{last_name[0]}}@{{domain}}",
         "{{first_name}}.{{last_name[0]}}@{{domain}}",
        "{{first_name[0]}}{{last_name[0]}}@{{domain}}",
        "{{last_name}}{{first_name}}@{{domain}}",
        "{{last_name}}.{{first_name}}@{{domain}}",
        "{{last_name[0]}}{{first_name}}@{{domain}}",
        "{{last_name[0]}}{{first_name[0]}}@{{domain}}",
        "{{first_name}}-{{last_name}}@{{domain}}",
    ]
    Output format example: {{"email_pattern":"{{first_name}}.{{last_name}}@{{domain}}"}}
    """
    client = _client(api_key, base_url, **kwargs)
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": "You are an AI that extracts email patterns from given names and emails."},
            {"role": "user", "content": prompt},
        ],
        response_format=EmailPatternResponse,
    )
    u = completion.usage
    cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
    print(f"[extract_email_pattern] input={u.prompt_tokens} "
          f"cached={cached_tokens} "
          f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
          f"output={u.completion_tokens}")
    message = completion.choices[0].message
    return message.parsed.email_pattern if message.parsed else None


# =============================================================================
# 3. predict_email_status — mirrors email_status_predict()
#    NOTE: reasoning model (o4-mini), unlike the other 3 in this file.
# =============================================================================

class EmailStatusEnum(str, Enum):
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


class EmailStatus(BaseModel):
    status: EmailStatusEnum


# Verbatim prompt template from sales/sales_open_ai.py — fill {email_content}.
EMAIL_STATUS_PROMPT_TEMPLATE = """
#Task: Analyze the given email reply and previous messages of the conversations then determine its status based on the predefined categories.

#Email Status Options:
Lead
Interested
Moderate
Meeting booked
Meeting completed
Won
Out of office
Wrong person
Not interested
Lost
Bounced
Rejected
Email Content:
"User Reply:
{email_content}"

#Instructions:
##Carefully review the email content and assign the most appropriate status from the options above. Ensure the selected status accurately reflects the user's intent or the context of the reply according to previous messages.
"""


def predict_email_status(
    prompt: str,
    *,
    model: str = "o4-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> str | None:
    """Mirrors email_status_predict(). `prompt` is normally
    EMAIL_STATUS_PROMPT_TEMPLATE.format(email_content=...). Uses a REASONING
    model (o4-mini, reasoning_effort="high") — if your open-model target
    doesn't support reasoning_effort, drop that kwarg."""
    client = _client(api_key, base_url, **kwargs)
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system",
                 "content": "#You are an expert in analyzing email replies and determining their status. "
                            "Use the provided options to accurately classify the intent or outcome of the email reply."},
                {"role": "user", "content": prompt},
            ],
            reasoning_effort="high",
            response_format=EmailStatus,
        )
        u = response.usage
        cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
        print(f"[predict_email_status] input={u.prompt_tokens} "
              f"cached={cached_tokens} "
              f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
              f"output={u.completion_tokens}")
        message = response.choices[0].message
        return message.parsed.status.value if message.parsed else None
    except Exception as e:
        print(f"predict_email_status error: {e}")
        return None


# =============================================================================
# 4. predict_delivery_failure — mirrors delivery_failure_predict()
# =============================================================================

class DeliveryFailureType(str, Enum):
    BOUNCED = "bounced"
    REJECTED = "rejected"


class DeliveryFailureClassification(BaseModel):
    failure_type: DeliveryFailureType


# Verbatim prompt template from sales/sales_open_ai.py — fill {subject}/{body_content}.
DELIVERY_FAILURE_PROMPT_TEMPLATE = """
#Task: Classify this email delivery failure notification as either "bounced" or "rejected".

#Definitions:
- **bounced**: The recipient address/mailbox is the problem — recipient not found, invalid address, mailbox unavailable/full, user unknown, no such user, SMTP code 5.1.x / 5.2.x.
- **rejected**: The recipient server refused the message itself — spam, virus, policy/security violation, blocked sender, reputation/blacklist, content blocked, SMTP code 5.7.x.

#Important:
"Undeliverable:", "Delivery Status Notification", "Non-Delivery Report" and "Mail Delivery Failed" are generic NDR prefixes used for BOTH kinds — ignore them. Decide from the diagnostic reason and SMTP code in the body. If the body shows no address error, prefer rejected.

#Email subject:
{subject}

#Email body (plain text):
{body_content}

#Instructions:
Classify the failure type based on the body diagnostic above. Respond with exactly one value: bounced or rejected.
"""


def predict_delivery_failure(
    prompt: str,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> str | None:
    """Mirrors delivery_failure_predict(). `prompt` is normally
    DELIVERY_FAILURE_PROMPT_TEMPLATE.format(subject=..., body_content=...)."""
    client = _client(api_key, base_url, **kwargs)
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system",
                 "content": (
                     "You are an expert at classifying email delivery failure notifications (NDRs). "
                     "Subject prefixes like 'Undeliverable:', 'Delivery Status Notification', 'Non-Delivery Report' "
                     "and 'Mail Delivery Failed' are GENERIC — providers use them for both kinds of failure, so NEVER "
                     "decide from the subject alone. Decide from the diagnostic reason in the body: the SMTP enhanced "
                     "status code and the human-readable explanation. "
                     "BOUNCED = the address/mailbox is the problem (5.1.x recipient not found / invalid address, "
                     "5.2.x mailbox unavailable or full, user unknown, no such user). "
                     "REJECTED = the recipient server refused the message itself (5.7.x policy/security, spam, virus, "
                     "blocked sender, reputation/blacklist, content violation). "
                     "When the body has no clear address error, prefer rejected. "
                     "Respond with exactly one of: bounced, rejected."
                 )},
                {"role": "user", "content": prompt},
            ],
            response_format=DeliveryFailureClassification,
        )
        u = response.usage
        cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
        print(f"[predict_delivery_failure] input={u.prompt_tokens} "
              f"cached={cached_tokens} "
              f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
              f"output={u.completion_tokens}")
        message = response.choices[0].message
        return message.parsed.failure_type.value if message.parsed else None
    except Exception as e:
        print(f"predict_delivery_failure error: {e}")
        return None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("CLASSIFY_MODEL", "gpt-4.1-mini"))
    ap.add_argument("--reasoning-model", default=os.environ.get("REASONING_MODEL", "o4-mini"))
    args = ap.parse_args()
    base_url = os.environ.get("OPENAI_BASE_URL")
    print(f"MODEL: {args.model}   REASONING_MODEL: {args.reasoning_model}   "
          f"BASE_URL: {base_url or 'api.openai.com'}\n")

    print("1) classify_company_industry")
    companies = classify_company_industry(
        [{"name": "Notion", "domain": "notion.so",
          "linkedin_url": "https://linkedin.com/company/notionhq",
          "raw_text": "Notion is an all-in-one workspace for notes, docs, and project "
                      "management. ~2,000 employees per LinkedIn."}],
        model=args.model,
    )
    for c in companies:
        print(f"  {c.name}: industry={c.industry!r} size={c.approx_employee_size.value}")

    print("\n2) extract_email_pattern")
    pattern = extract_email_pattern("Sarah Johnson", "sarah.johnson@notion.so", model=args.model)
    print(f"  pattern={pattern!r}")

    print(f"\n3) predict_email_status (model={args.reasoning_model})")
    status = predict_email_status(
        EMAIL_STATUS_PROMPT_TEMPLATE.format(
            email_content="Thanks for reaching out! Can we set up a call next Tuesday at 2pm?"
        ),
        model=args.reasoning_model,
    )
    print(f"  status={status!r}")

    print("\n4) predict_delivery_failure")
    failure = predict_delivery_failure(
        DELIVERY_FAILURE_PROMPT_TEMPLATE.format(
            subject="Undeliverable: Re: Quick question",
            body_content="Your message wasn't delivered because the recipient's email "
                        "address wasn't found. Please check the recipient's email address "
                        "and try to resend. 550 5.1.1 The email account that you tried to "
                        "reach does not exist.",
        ),
        model=args.model,
    )
    print(f"  failure_type={failure!r}")
