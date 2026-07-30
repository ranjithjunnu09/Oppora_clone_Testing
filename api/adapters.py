"""
Adapters — the only place the API layer touches the standalone feature files.

Each function here does exactly three things:
  1. take plain JSON from the browser,
  2. call the untouched function in classification/ | email_generation/ | lead_scoring/,
  3. hand back something JSON-serialisable.

No prompt logic lives here. If you find yourself wanting to change a prompt,
change it in the feature file, not here — that file is the byte-identical
replica of production and is the thing being benchmarked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

# The repo root must be importable so `email_generation.x` etc. resolve.
# The three feature folders are namespace packages (no __init__.py) by design.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _dump(obj: Any) -> Any:
    """Recursively make Pydantic models / enums / dataclasses JSON-safe."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "value") and hasattr(obj, "name"):  # Enum
        return obj.value
    if isinstance(obj, dict):
        return {k: _dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_dump(v) for v in obj]
    return str(obj)


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def classify_company_industry(inputs: dict, model: str, **kw) -> Any:
    from classification.classification_helpers import classify_company_industry as fn

    return _dump(fn(inputs["companies"], model=model, **kw))


def extract_email_pattern(inputs: dict, model: str, **kw) -> Any:
    from classification.classification_helpers import extract_email_pattern as fn

    return {"email_pattern": fn(inputs["lead_name"], inputs["lead_email"], model=model, **kw)}


def predict_email_status(inputs: dict, model: str, **kw) -> Any:
    from classification.classification_helpers import (
        EMAIL_STATUS_PROMPT_TEMPLATE,
        predict_email_status as fn,
    )

    prompt = EMAIL_STATUS_PROMPT_TEMPLATE.format(email_content=inputs["email_content"])
    return {"status": fn(prompt, model=model, **kw)}


def predict_delivery_failure(inputs: dict, model: str, **kw) -> Any:
    from classification.classification_helpers import (
        DELIVERY_FAILURE_PROMPT_TEMPLATE,
        predict_delivery_failure as fn,
    )

    prompt = DELIVERY_FAILURE_PROMPT_TEMPLATE.format(
        subject=inputs["subject"], body_content=inputs["body_content"]
    )
    return {"status": fn(prompt, model=model, **kw)}


# ─────────────────────────────────────────────────────────────────────────────
# EMAIL GENERATION
# ─────────────────────────────────────────────────────────────────────────────

def email_sequence(inputs: dict, model: str, **kw) -> Any:
    from email_generation.email_generation import generate_email_sequence as fn

    return _dump(
        fn(
            template_prompt=inputs["template_prompt"],
            lead_data=inputs.get("lead_data") or None,
            icp_profile=inputs.get("icp_profile") or None,
            writing_style=inputs.get("writing_style") or None,
            research_brief=(inputs.get("research_brief") or "").strip() or None,
            sequence_steps=int(inputs.get("sequence_steps") or 3),
            include_spintax=bool(inputs.get("include_spintax")),
            model=model,
            **kw,
        )
    )


def campaign_ai_variable(inputs: dict, model: str, **kw) -> Any:
    from email_generation.campaign_ai_variable import generate_ai_template_response as fn

    return {
        "text": fn(
            inputs["prompt"],
            company=inputs.get("company") or None,
            first_name=inputs.get("first_name") or None,
            last_name=inputs.get("last_name") or None,
            lead_job_title=inputs.get("lead_job_title") or None,
            job_location=inputs.get("job_location") or None,
            job_opening_title=inputs.get("job_opening_title") or None,
            position=inputs.get("position") or None,
            model=model,
            **kw,
        )
    }


def reply_agent_chain(inputs: dict, model: str, **kw) -> Any:
    from email_generation.reply_agent_chain import run_reply_pipeline as fn

    result = fn(
        inputs["prospect_message"],
        attachments=inputs.get("attachments") or [],
        autonomy=bool(inputs.get("autonomy")),
        current_attempt=int(inputs.get("current_attempt") or 0),
        meeting_tool_url=inputs.get("meeting_tool_url") or "",
        tone=inputs.get("tone") or "friendly-professional",
        model=model,
        **kw,
    )
    return _dump(result)


def reply_generation(inputs: dict, model: str, **kw) -> Any:
    from email_generation.reply_generation import generate_ai_reply as fn

    return {
        "text": fn(
            inputs["context"],
            user_instruction=inputs.get("user_instruction") or "",
            tone=inputs.get("tone") or "professional",
            model=model,
            **kw,
        )
    }


def single_email_generation(inputs: dict, model: str, **kw) -> Any:
    from email_generation.single_email_generation import generate_ai_email as fn

    subject, body = fn(
        first_name=inputs.get("first_name") or "{first_name}",
        last_name=inputs.get("last_name") or "{last_name}",
        company=inputs.get("company") or "{company}",
        model=model,
        **kw,
    )
    return {"subject": subject, "body": body}


def lead_email_address_generation(inputs: dict, model: str, **kw) -> Any:
    from email_generation.lead_email_address_generation import generate_lead_email as fn

    lead_name, emails = fn(
        inputs["name"], inputs["company"], inputs["other_leads"], model=model, **kw
    )
    return {"lead_name": lead_name, "emails": emails or []}


# ─────────────────────────────────────────────────────────────────────────────
# LEAD SCORING
# ─────────────────────────────────────────────────────────────────────────────

def lead_recommendation(inputs: dict, model: str, **kw) -> Any:
    from lead_scoring.lead_recommendation import (
        top_lead_generate_with_quality_check as fn,
    )

    return {"companies": _dump(fn(inputs["prompt"], model=model, **kw) or [])}


def lead_scoring_batch(inputs: dict, model: str, **kw) -> Any:
    from lead_scoring.lead_scoring_batch import (
        build_analysis_prompt,
        rank_and_select,
        score_leads_batch as fn,
    )

    leads = inputs["leads"]
    filters = inputs["filters"]
    fallback_sets = inputs.get("fallback_sets") or None
    result = fn(
        inputs["company_name"],
        filters,
        leads,
        main_objective=(inputs.get("main_objective") or "").strip() or None,
        fallback_sets=fallback_sets,
        model=model,
        **kw,
    )
    if result is None:
        return {"scored_leads": [], "selected": [], "leads": leads, "prompt_preview": None}

    valid_ids = {int(lead["id"]) for lead in leads}
    top = rank_and_select(result, valid_ids, int(inputs.get("total_required") or 2))
    return {
        "scored_leads": _dump(result.scored_leads),
        "selected": top,
        "leads": leads,
        "prompt_preview": build_analysis_prompt(
            inputs["company_name"], filters, leads, fallback_sets=fallback_sets
        )[:4000],
    }


ADAPTERS: dict[str, Callable[..., Any]] = {
    "classify_company_industry": classify_company_industry,
    "extract_email_pattern": extract_email_pattern,
    "predict_email_status": predict_email_status,
    "predict_delivery_failure": predict_delivery_failure,
    "email_sequence": email_sequence,
    "campaign_ai_variable": campaign_ai_variable,
    "reply_agent_chain": reply_agent_chain,
    "reply_generation": reply_generation,
    "single_email_generation": single_email_generation,
    "lead_email_address_generation": lead_email_address_generation,
    "lead_recommendation": lead_recommendation,
    "lead_scoring_batch": lead_scoring_batch,
}
