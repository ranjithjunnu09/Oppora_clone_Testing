"""
Standalone replica of Oppora's AI LEAD RECOMMENDATION pipeline
(`top_lead_generate_with_quality_check`).

Backend-free copy of the exact AI logic — same prompts, same Pydantic schemas,
same model calls as production, so output matches Oppora. Deps: openai,
pydantic only.

SOURCE OF TRUTH (kept byte-identical):
  sales/sales_open_ai.py ->
    top_lead_generate()                  (line ~1010)
    quality_check_leads()                (line ~1120)
    fix_lead_recommendations()           (line ~1171)
    top_lead_generate_with_quality_check()   (line ~1224)

WHAT IT DOES
  A self-correcting 3-step loop over one free-text lead request:
    1. GENERATE — pick the best leads per company for the request.
    2. QA CHECK  — an independent "quality assurance" pass audits the
       generated leads against the original request and returns a structured
       score + itemized issues (0-100 scale; is_acceptable requires score >= 80
       AND no unresolved critical/high issues).
    3. FIX       — only runs if QA failed. Re-generates addressing the
       specific issues the QA pass found.
  Best case: 2 LLM calls (generate + QA pass). Worst case: 3 (generate + QA +
  fix). Production measured ~3 credits per company/lead across a 2-item batch
  (6 total calls) — i.e. this loop, not the plain single-shot generation, is
  where lead-scoring cost actually comes from.

  Intentionally NOT replicated: the `@traceable` LangSmith decorator on each
  production function (requires the full Oppora/LangSmith setup) and the
  `wrap_openai(...)` wrapper — both are observability-only and don't change
  the AI logic. A plain `OpenAI()` client is used here instead, exactly like
  the other files in this repo.

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python lead_recommendation.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python lead_recommendation.py --model my-open-model
"""
from __future__ import annotations

import argparse
import os
from typing import List, Optional

from pydantic import BaseModel
from openai import OpenAI


# ── Output schemas — verbatim from sales/sales_open_ai.py ──

class Lead(BaseModel):
    id: int
    name: str
    title: str
    ai_recommendation: str


class CompanyLeads(BaseModel):
    name: str
    leads: List[Lead]


class TopLeads(BaseModel):
    companies: List[CompanyLeads]


class QualityIssue(BaseModel):
    issue_type: str          # "missing_field", "invalid_data", "logic_error", "format_error"
    description: str
    severity: str             # "low", "medium", "high", "critical"
    affected_company: str
    affected_lead: Optional[str]
    suggestion: str


class QualityReport(BaseModel):
    overall_score: float       # 0-100
    issues: List[QualityIssue]
    recommendations: List[str]
    is_acceptable: bool


class LeadQualityCheck(BaseModel):
    name: str
    title: str
    ai_recommendation: str
    quality_score: float
    issues: List[str]
    is_valid: bool


class CompanyQualityCheck(BaseModel):
    name: str
    leads: List[LeadQualityCheck]
    company_score: float
    total_issues: int


class TopLeadsQualityCheck(BaseModel):
    companies: List[CompanyQualityCheck]
    overall_quality_score: float
    total_critical_issues: int
    quality_report: QualityReport


# ── Static QA rubric — verbatim from sales/sales_open_ai.py ──
# Kept as a module-level constant so the system-message prefix is byte-identical
# on every call. It is intentionally long (>1,024 tokens) so OpenAI prompt
# caching activates: the cache matches the longest IDENTICAL leading span, so
# all request-specific data (original request + the leads) is sent in the user
# message AFTER this block — never inside it. Every line here is genuine QA
# guidance tied to the TopLeadsQualityCheck output schema, so it raises
# precision rather than padding the prompt.
QUALITY_CHECK_SYSTEM_PROMPT = """You are an expert quality assurance specialist for B2B lead-generation systems. You audit AI-generated lead recommendations and produce a rigorous, structured quality assessment. You are precise, skeptical, and evidence-driven: every judgement you make must be justified by something observable in the lead data or by a clear mismatch against the original request. You never invent facts about a lead, and you never penalize a lead for information that was simply not provided unless that field was explicitly required by the request.

ROLE AND MINDSET
You act as the final gatekeeper before lead recommendations reach a human sales operator. Your goal is to protect the operator's time: flag weak, irrelevant, malformed, or fabricated-looking leads, while confirming that strong, well-targeted leads pass cleanly. Be strict but fair. A lead is "good" when it plausibly matches the request and its data is internally consistent; it is "bad" when it contradicts the request, is missing required fields, or shows signs of fabrication.

EVALUATION CRITERIA (apply each to every lead and to the result set as a whole)
1. Data Completeness — Required fields (name, title, and any field named in the request) must be present, non-empty, and properly formatted. Treat placeholder values ("N/A", "unknown", empty strings, repeated dummy text) as missing.
2. Business Logic — Each lead must match the explicit criteria in the request: industry, geography, role, seniority, department, company attributes. A lead that violates a stated constraint is a logic error.
3. Relevance — The lead's role and company must be appropriate for the specific service or product implied by the request. A technically valid contact who would never be a buyer for this offering is low-relevance.
4. Role & Title Coherence — The job title must be a real, coherent title that matches the requested role family. Watch for titles that contradict the requested department or seniority (e.g. an intern returned for a VP-level request).
5. Seniority Balance — When the request implies a target seniority mix (e.g. decision-makers vs. practitioners), evaluate whether the set is appropriately balanced rather than skewed to irrelevant levels.
6. Geographic Relevance — Locations must fall within the requested country/region/city scope. Penalize leads clearly outside the requested geography unless the request allows it.
7. Company Coverage — Assess whether the number of leads per company is adequate and not redundant. Too few leaves coverage gaps; many near-duplicate contacts at one company add little value.
8. Industry Alignment — The companies represented should belong to industries relevant to the request and the offering. Flag obvious industry mismatches.
9. Data Authenticity — Watch for fabricated or templated data: implausible names, titles that read as generated filler, suspiciously uniform recommendations, or values that look auto-filled rather than sourced.

ISSUE TAXONOMY (use these exact issue_type values in the structured output)
- "missing_field": a required field is absent, empty, or a placeholder.
- "invalid_data": a field is present but malformed, implausible, or internally inconsistent.
- "logic_error": the lead contradicts an explicit constraint from the original request (wrong geography, wrong department, wrong seniority, wrong industry).
- "format_error": a field carries the right information in a structurally wrong shape (bad casing, stray markup, truncated text, wrong delimiter).

SEVERITY GUIDANCE (use these exact severity values)
- "critical": the lead is unusable or actively misleading — fabricated data, or a hard violation of a core request constraint. Such leads must lower acceptability.
- "high": a serious problem that would likely waste operator time or cause a misdirected outreach, but the lead is not wholly fabricated.
- "medium": a real problem that degrades quality but still leaves the lead potentially usable after light correction.
- "low": a minor or cosmetic problem with negligible business impact.

SCORING METHODOLOGY
Scores are on a 0-100 scale. 90-100 = excellent, clean match; 75-89 = good, minor issues only; 60-74 = acceptable but with notable gaps; 40-59 = weak, several real problems; below 40 = poor, largely unusable. Score each lead (quality_score) and each company (company_score) by aggregating the severity and count of its issues, then derive overall_quality_score as a holistic, weighted view of the whole set — not a naive average. A single critical fabrication should pull the overall score down sharply even amid otherwise good leads. Set is_valid on a lead to false when it carries any critical issue or an unresolved high-severity logic error. Count total_critical_issues across all leads, and per company set total_issues to the number of issues attributed to that company's leads.

REPORT REQUIREMENTS
Populate the quality_report with: overall_score (the same holistic 0-100 figure), a complete issues list (each tied to its affected_company and, where applicable, affected_lead, with a concrete, actionable suggestion), a recommendations list of specific improvements the generator should make, and is_acceptable. Mark is_acceptable true only when the set is genuinely fit to send to a human operator: no critical issues, an overall score at or above roughly 80, and no unaddressed high-severity logic errors. When in doubt, prefer to flag rather than silently pass, but never fabricate an issue that the data does not support.

INPUT FORMAT
The user message contains two sections: the ORIGINAL REQUEST (the criteria the leads were generated to satisfy — treat this as the ground truth for relevance and business-logic checks) followed by LEADS TO EVALUATE (the lead recommendations to audit). Evaluate strictly against the original request and return only the structured assessment."""


def _client(api_key: str | None = None, base_url: str | None = None, **kwargs) -> OpenAI:
    return OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
        **kwargs,
    )


# ── Step 1: generate — verbatim from top_lead_generate() ──
def top_lead_generate(
    prompt: str,
    *,
    model: str = "claude-sonnet-5",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> list[CompanyLeads] | None:
    """Mirrors top_lead_generate(). Returns the generated companies/leads list."""
    client = _client(api_key, base_url, **kwargs)
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system",
                 "content": "You are an expert at selecting leads for sales outreach."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            response_format=TopLeads,
        )
        u = response.usage
        cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
        print(f"[top_lead_generate] input={u.prompt_tokens} "
              f"cached={cached_tokens} "
              f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
              f"output={u.completion_tokens}")
        parsed = response.choices[0].message.parsed
        return parsed.companies if parsed else None
    except Exception as e:
        print(f"top_lead_generate error: {e}")
        return None


# ── Step 2: QA check — verbatim from quality_check_leads() ──
def quality_check_leads(
    companies: list[CompanyLeads],
    original_prompt: str,
    *,
    model: str = "claude-sonnet-5",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> TopLeadsQualityCheck | None:
    """Mirrors quality_check_leads(). Audits `companies` against the original
    request and returns a structured score + itemized issues, or None on failure."""
    client = _client(api_key, base_url, **kwargs)
    try:
        companies_data = []
        for company in companies:
            companies_data.append({
                "name": company.name,
                "leads": [
                    {"id": lead.id, "name": lead.name, "title": lead.title,
                     "ai_recommendation": lead.ai_recommendation}
                    for lead in company.leads
                ],
            })

        # Dynamic content goes LAST so the static system prompt above stays a
        # stable, cacheable prefix. Do not move request-specific data earlier.
        user_content = (
            f"ORIGINAL REQUEST:\n{original_prompt}\n\n"
            f"LEADS TO EVALUATE:\n{companies_data}"
        )

        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": QUALITY_CHECK_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format=TopLeadsQualityCheck,
        )
        u = response.usage
        cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
        print(f"[quality_check_leads] input={u.prompt_tokens} "
              f"cached={cached_tokens} "
              f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
              f"output={u.completion_tokens}")
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Quality check error: {e}")
        return None


# ── Step 3: fix (only runs on QA failure) — verbatim from fix_lead_recommendations() ──
def fix_lead_recommendations(
    companies: list[CompanyLeads],
    quality_report: QualityReport,
    original_prompt: str,
    *,
    model: str = "claude-sonnet-5",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> list[CompanyLeads]:
    """Mirrors fix_lead_recommendations(). Re-generates addressing only the
    high/critical issues the QA pass found; returns `companies` unchanged if
    there's nothing critical to fix or the fix call itself fails."""
    client = _client(api_key, base_url, **kwargs)
    try:
        critical_issues = [i for i in quality_report.issues if i.severity in ("high", "critical")]
        if not critical_issues:
            return companies  # No fixes needed

        fix_prompt = f"""
        You are an expert lead generation specialist. The quality checker has identified several issues with the previous lead recommendations that need to be fixed.

        ORIGINAL REQUEST: {original_prompt}

        CRITICAL ISSUES TO FIX:
        {chr(10).join(f"- {i.issue_type}: {i.description} (Company: {i.affected_company}, Lead: {i.affected_lead or 'N/A'})" for i in critical_issues)}

        QUALITY REQUIREMENTS:
        - Ensure all leads match the requested criteria exactly
        - Maintain proper balance between different types of roles as specified
        - Include appropriate number of leads per company
        - Verify geographic relevance
        - Ensure data completeness and accuracy
        - Match industry requirements from the original request
        - Focus on relevant departments and job titles for the target service/product

        Please regenerate the lead recommendations addressing these specific issues while maintaining the original requirements.
        """

        response = client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system",
                 "content": "You are an expert lead generation specialist who fixes quality issues in lead recommendations."},
                {"role": "user", "content": fix_prompt},
            ],
            temperature=0.5,
            response_format=TopLeads,
        )
        u = response.usage
        cached_tokens = getattr(u.prompt_tokens_details, "cached_tokens", 0) if getattr(u, "prompt_tokens_details", None) else 0
        print(f"[fix_lead_recommendations] input={u.prompt_tokens} "
              f"cached={cached_tokens} "
              f"({cached_tokens / (u.prompt_tokens or 1) * 100:.1f}%) "
              f"output={u.completion_tokens}")
        parsed = response.choices[0].message.parsed
        return parsed.companies if parsed else companies
    except Exception as e:
        print(f"Fix error: {e}")
        return companies  # Return original if fix failed


# ── Orchestrator — verbatim from top_lead_generate_with_quality_check() ──
def top_lead_generate_with_quality_check(
    prompt: str,
    *,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs,
) -> list[CompanyLeads] | None:
    """Mirrors top_lead_generate_with_quality_check(). 2 calls if QA passes
    (score >= 80 AND is_acceptable), 3 calls if QA fails and a fix is needed."""
    kw = dict(model=model, api_key=api_key, base_url=base_url, **kwargs)
    try:
        print("Generating initial lead recommendations...")
        initial_companies = top_lead_generate(prompt, **kw)
        if not initial_companies:
            print("Failed to generate initial recommendations")
            return None

        print("Performing quality check...")
        quality_result = quality_check_leads(initial_companies, prompt, **kw)
        if not quality_result:
            print("Quality check failed, returning initial results")
            return initial_companies

        if quality_result.quality_report.is_acceptable and quality_result.overall_quality_score >= 80:
            print(f"Quality check passed with score: {quality_result.overall_quality_score}")
            return initial_companies

        print(f"Quality check failed with score: {quality_result.overall_quality_score}")
        print(f"Critical issues found: {quality_result.total_critical_issues}")

        print("Fixing quality issues...")
        return fix_lead_recommendations(initial_companies, quality_result.quality_report, prompt, **kw)
    except Exception as e:
        print(f"Enhanced lead generation error: {e}")
        return top_lead_generate(prompt, **kw)  # Fallback to plain generation


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("LEAD_MODEL", "gpt-4.1-mini"))
    args = ap.parse_args()

    demo_prompt = (
        "Recommend up to 2 leads at each of these companies for an AI SDR "
        "sales tool: Stripe, Notion. Prioritize VP/Director of Sales or "
        "Revenue Operations. For each lead set ai_recommendation to a short "
        "sentence on why they're a good fit, and use id=1, 2, 3... "
        "sequentially across the whole result."
    )

    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}\n")
    result = top_lead_generate_with_quality_check(demo_prompt, model=args.model)

    print("\n--- final recommendations ---\n")
    if result:
        for company in result:
            print(f"{company.name}:")
            for lead in company.leads:
                print(f"  - {lead.name} ({lead.title}): {lead.ai_recommendation}")
    else:
        print("(no result)")
