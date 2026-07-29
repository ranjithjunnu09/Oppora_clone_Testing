"""
Standalone replica of Oppora's BATCH LEAD SCORING engine
(`filter_company_leads_by_filters`).

Backend-free copy of the exact AI logic — same prompts and structured-output
schema as production. Deps: openai, pydantic only.

SOURCE OF TRUTH (kept byte-identical prompts):
  planner/tools/planner_tools.py -> filter_company_leads_by_filters()  (line ~1061)
  Pydantic schema also from that file: ScoredLead (line ~37), LeadFilterResult (line ~44)

WHAT IT DOES
  Scores a BATCH of up to 200 leads at one company against a set of filters
  (department, management level, country, location, title, experience) and
  returns every lead that matches, each with a 0-100 fit score. This is
  Oppora's highest per-call TOKEN volume function: one call analyzes up to
  200 leads' full profile text (title, location, department, headline,
  skills, summary) in a single prompt — likely the single biggest per-call
  token count in the whole AI-generation surface, even though it's only
  gpt-4.1-mini.

  Production supports two prompt modes:
    - SIMPLE FILTER (the common case) — score leads against one filter set.
    - PRIORITY LADDER (fallback_sets) — score against a tiered ladder of
      progressively looser filter sets in one pass (tier 0 = primary,
      tier 1+ = fallbacks), tagging each lead with the lowest tier it fits.
  Both prompts are reproduced verbatim below; `score_leads_batch(...,
  fallback_sets=[...])` selects the ladder prompt automatically.

  After scoring, production dedupes (keep each lead's best tier/score),
  ranks by (tier ascending, score descending), and slices to `total_required`
  — that ranking/slicing logic is pure Python and is replicated exactly in
  `rank_and_select()` below.

  Deliberately NOT replicated (Django/DB-specific, not AI logic):
    - Fetching real Lead rows from the database (`_lead_row` here takes a
      plain dict instead of a Django Lead model instance).
    - `add_leads_to_lists(...)` and the DB-verified "how many actually got
      added" count — those are database writes, not part of the scoring call.
    - The `fallback_sets_enabled()` kill-switch check (an Oppora feature flag).

  Deliberately DIFFERENT (disclosed, not silent): production calls this model
  via `langchain_openai.ChatOpenAI(...).with_structured_output(LeadFilterResult)`.
  This file uses the raw `openai` SDK's `.beta.chat.completions.parse(...)`
  instead — functionally equivalent structured JSON output, but keeps this
  repo's dependency footprint at just `openai` + `pydantic` (no `langchain`),
  matching every other file here.

RUN
  pip install openai pydantic
  export OPENAI_API_KEY=sk-...
  python lead_scoring_batch.py
  # open-source model:  export OPENAI_BASE_URL=http://localhost:8000/v1
  #                     python lead_scoring_batch.py --model my-open-model
"""
from __future__ import annotations

import argparse
import os
from typing import List, Optional

from pydantic import BaseModel, Field
from openai import OpenAI


# ── Output schema — verbatim from planner/tools/planner_tools.py ──

class ScoredLead(BaseModel):
    """A lead from the analyzed batch with its fit score against the filters"""
    lead_id: int = Field(description="Lead ID from the analyzed batch")
    score: int = Field(description="Fit score 0-100. 100 = perfect match on every filter. Higher = better match.", ge=0, le=100)
    priority_tier: int = Field(default=0, ge=0, description="Lowest priority tier whose criteria this lead matches: 0 = primary (highest priority), 1 = first fallback, 2 = second, etc. Always 0 when no priority ladder is provided.")


class LeadFilterResult(BaseModel):
    """Pydantic model for structured lead filtering response (filters only, no objectives)"""
    scored_leads: List[ScoredLead] = Field(description="Every lead from the batch that matches the filters, each with a 0-100 fit score. Exclude leads that contradict the filters. Do NOT cap the count — return all matches; the caller slices the top N.")


# ── Lead row formatting — verbatim column shape from _lead_row(), but takes a
# plain dict instead of a Django Lead model instance ──
def _lead_row(lead: dict) -> str:
    """`lead` keys: id, name, title, location, department, management_level,
    experience_years, headline, skills (list[str] or str), summary."""
    headline = (lead.get("headline") or "").replace("\n", " ").replace("|", " ")[:200]
    skills_raw = lead.get("skills") or []
    skills = ", ".join(str(s) for s in skills_raw[:8]) if isinstance(skills_raw, list) else str(skills_raw)[:200]
    summary = (lead.get("summary") or "").replace("\n", " ").replace("|", " ")[:400]
    yrs = lead.get("experience_years")
    yrs_str = str(yrs) if yrs not in (None, "") else ""
    return (
        f"{lead['id']} | {lead.get('name', '')} | "
        f"title={lead.get('title', '')} | "
        f"location={lead.get('location', '')} | "
        f"department={lead.get('department', '')} | management_level={lead.get('management_level', '')} | "
        f"experience_years={yrs_str} | "
        f"headline={headline} | "
        f"skills={skills} | "
        f"summary={summary}"
    )


def _fmt_tier(f: dict) -> str:
    """Verbatim from _fmt_tier() — formats one tier of a fallback ladder."""
    parts = []
    title = f.get("title") or f.get("job_title")
    if title:
        parts.append(f"title={title}")
    if f.get("departments"):
        parts.append(f"departments={f.get('departments')}")
    mgmt = f.get("management_level") or f.get("management_levels")
    if mgmt:
        parts.append(f"management_level={mgmt}")
    if f.get("location"):
        parts.append(f"location={f.get('location')}")
    if f.get("country"):
        parts.append(f"country={f.get('country')}")
    exp = f.get("experience") or f.get("years_experience")
    if exp:
        parts.append(f"experience={exp}")
    return ", ".join(parts) if parts else "(no geo/role constraints - any lead at the company)"


def build_analysis_prompt(
    company_name: str,
    filters: dict,
    leads: list[dict],
    *,
    main_objective: str | None = None,
    fallback_sets: list[dict] | None = None,
    batch_num: int = 1,
) -> str:
    """Builds the exact analysis prompt production sends — verbatim from the
    two branches inside filter_company_leads_by_filters()."""
    all_leads_lines = [
        "Columns: id | name | title | location | department | management_level | experience_years | headline | skills | summary"
    ]
    all_leads_lines += [_lead_row(lead) for lead in leads]
    all_leads = "\n".join(all_leads_lines)

    if fallback_sets:
        tiers = [filters] + [fs for fs in fallback_sets if fs]
        lines = [f"  Tier {i}: {_fmt_tier(f)}" for i, f in enumerate(tiers)]
        ladder_block = (
            "PRIORITY LADDER (Tier 0 = highest priority; lower tiers are acceptable fallbacks):\n"
            + "\n".join(lines)
        )
        return f"""
You are selecting people at {company_name} who fill one of the ROLES in a priority ladder.
Keep a lead if it fits ANY tier; drop everyone else.

{ladder_block}

LEADS TO ANALYZE (Batch {batch_num}):
{all_leads}
Columns: id | name | title | location | department | management_level | experience_years | headline | skills | summary.
Some fields may be blank — infer the role from title + headline.

HOW TO MATCH each lead:
1. Find the LOWEST-numbered tier the lead fits. A lead fits a tier when BOTH hold:
   • TITLE — the lead's title is that tier's role or a clear real-world variant (be FLEXIBLE, match the role family):
       - "VP of Sales"      ⇄ "Vice President of Sales", "Sales VP", "Head of Sales", "Chief Revenue Officer", "VP Sales & Marketing"
       - "Director of Sales"⇄ "Sales Director", "Director of Sales Strategy", "Director of Sales, <region>", "Associate Director of Sales"
       - "Sales Manager"    ⇄ "Regional Sales Manager", "National Sales Manager", "Account Sales Manager", "Territory/Area Sales Manager", "Sr. Sales Manager"
   • DISCRETE — it meets that tier's department / management_level when the tier lists them, AND is in the tier's location/country.
2. Output EVERY lead that fits at least one tier: set "priority_tier" = the lowest tier number it fits, and "score" 0-100 = how well it fits that tier.
3. EXCLUDE (do NOT return) a lead that fits NO tier. Examples to exclude: non-sales roles
   (Field Technician, Project/Operations Specialist, Recruiter), blank or "N/A" titles, and anyone
   outside the required location/country. Merely working at {company_name} is NOT a match.

GUIDANCE:
- Prefer RECALL on title: if a title is plausibly the same role family as a tier, INCLUDE it. Only drop when the role is clearly different (not a sales leadership/management role) or out of geo.
- STRICT on geography and on any department/management_level a tier specifies — if the lead's field is present and contradicts it, that tier does not match (try the next tier).
- Every lead_id must come from the batch above.
"""

    filters_summary = ", ".join(f"{k}: {v}" for k, v in filters.items() if v)
    return f"""
You are filtering leads to identify which ones match the provided filter criteria.

COMPANY: {company_name}

MAIN OBJECTIVE (tie-breaker only): {main_objective}
APPLIED FILTERS:
{filters_summary}
LEADS TO ANALYZE (Batch {batch_num}):
{all_leads}

TASK:
1. Analyze each lead against the provided filters:
   - Departments: {filters.get('departments', 'Not specified')}
   - Management Levels: {filters.get('management_level', 'Not specified')}
   - Country: {filters.get('country', 'Not specified')}
   - Location: {filters.get('location', 'Not specified')}
   - Title: {filters.get('title', 'Not specified')}
   - Experience: {filters.get('experience', 'Not specified')}

2. Identify which leads MATCH the filters and assign each a fit score (0-100).

3. Return a structured response with:
   - "scored_leads": [{{"lead_id": <id>, "score": <0-100>}}, ...] — every matching lead from this batch with its 0-100 fit score.

LEAD DATA:
Each row has: id, name, title, location, department, management_level, experience_years, headline, skills.
(All leads in this batch belong to COMPANY above — company is not repeated per row.)
Some fields may be blank — not every provider populates every field. When a field is blank,
infer from title + headline rather than rejecting the lead.

MATCHING RULES:
- STRICT on discrete attributes when the lead row clearly contradicts the filter:
  country, location, management_level, department, experience_years.
  If the field is present and does not meet the filter → EXCLUDE (do not return).
  If the field is blank and the title/headline clearly does not match → EXCLUDE.
  If the field is blank and title/headline is compatible → INCLUDE (benefit of the doubt).
- FLEXIBLE on title only. Titles have many real-world variants — treat the filter as a
  seed for the role, not a literal string match.
  Examples of acceptable title matches:
  * "VP Sales" → "Vice President of Sales", "Sales VP", "Head of Sales"
  * "Marketing Manager" → "Marketing Lead", "Senior Marketing Manager", "Marketing Director"
  * "CTO" → "Chief Technology Officer", "VP Engineering", "Head of Technology"
  * "BDR" → "Business Development Representative", "Business Development Rep"
  When in doubt about title similarity, INCLUDE the lead.

- Use MAIN OBJECTIVE only as a tie-breaker (small score nudge) when two candidates are
  equally good on filters. Do not treat the MAIN OBJECTIVE as an additional filter.

SCORING GUIDE (0-100):
- 90-100: Matches every present filter on discrete fields AND title is a strong fit.
- 70-89: Matches every discrete filter; title is a reasonable variant of the filter.
- 50-69: Matches most discrete filters; title is loosely related.
- 1-49: Borderline — only include if you're confident it's a real match for the role.
- Do NOT include leads below borderline. Only return leads that genuinely match.

OUTPUT RULES:
- Return EVERY lead that matches the filters, each with its score — do not leave any matching lead out.
- Never include a lead that contradicts the filters.
- Every lead_id must come from the analyzed batch above.
"""


def score_leads_batch(
    company_name: str,
    filters: dict,
    leads: list[dict],
    *,
    main_objective: str | None = None,
    fallback_sets: list[dict] | None = None,
    batch_num: int = 1,
    model: str = "gpt-4.1-mini",
    api_key: str | None = None,
    base_url: str | None = None,
) -> LeadFilterResult | None:
    """One batch (<=200 leads) scored in one call. Returns None on failure
    (production continues to the next batch in that case)."""
    prompt = build_analysis_prompt(
        company_name, filters, leads,
        main_objective=main_objective, fallback_sets=fallback_sets, batch_num=batch_num,
    )
    client = OpenAI(
        api_key=api_key or os.environ.get("OPENAI_API_KEY"),
        base_url=base_url or os.environ.get("OPENAI_BASE_URL"),
    )
    try:
        response = client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format=LeadFilterResult,
        )
        u = response.usage
        print(f"[score_leads_batch] input={u.prompt_tokens} "
              f"cached={u.prompt_tokens_details.cached_tokens} "
              f"({u.prompt_tokens_details.cached_tokens / u.prompt_tokens * 100:.1f}%) "
              f"output={u.completion_tokens}")
        return response.choices[0].message.parsed
    except Exception as e:
        print(f"Error analyzing batch {batch_num}: {e}")
        return None


def rank_and_select(
    result: LeadFilterResult,
    valid_lead_ids: set[int],
    total_required: int,
) -> list[int]:
    """Verbatim ranking/slicing logic from filter_company_leads_by_filters():
    dedupe (keep each lead's best tier/score), sort by (tier asc, score desc),
    slice to total_required. `valid_lead_ids` guards against a model
    hallucinating an id outside the batch, same as production's batch_lead_id_set check."""
    best_by_lead: dict[int, tuple[int, int]] = {}
    for s in result.scored_leads:
        if s.lead_id not in valid_lead_ids:
            continue  # defends against cross-batch id hallucination
        cur = best_by_lead.get(s.lead_id)
        tier, score = s.priority_tier, s.score
        if cur is None or (tier, -score) < (cur[0], -cur[1]):
            best_by_lead[s.lead_id] = (tier, score)
    ranked = sorted(best_by_lead.items(), key=lambda kv: (kv[1][0], -kv[1][1]))
    return [lid for lid, _ in ranked[:total_required]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("SCORING_MODEL", "gpt-4.1-mini"))
    args = ap.parse_args()

    # A small realistic batch — production processes up to 200 per call.
    demo_leads = [
        {"id": 101, "name": "Sarah Johnson", "title": "VP of Sales", "location": "New York, NY",
         "department": "Sales", "management_level": "VP", "experience_years": 12,
         "headline": "VP of Sales @ Notion | Scaling B2B revenue teams",
         "skills": ["SaaS sales", "team leadership", "pipeline management"],
         "summary": "Leads a 40-person sales org, previously scaled ARR 3x at a prior startup."},
        {"id": 102, "name": "Mike Chen", "title": "Sales Development Rep", "location": "New York, NY",
         "department": "Sales", "management_level": "Individual Contributor", "experience_years": 1,
         "headline": "SDR at Notion", "skills": ["cold outreach", "SFDC"],
         "summary": "Entry-level SDR, 6 months in role."},
        {"id": 103, "name": "Priya Patel", "title": "Director of Revenue Operations", "location": "Austin, TX",
         "department": "Sales", "management_level": "Director", "experience_years": 8,
         "headline": "Director of RevOps | Notion", "skills": ["revops", "forecasting", "CRM architecture"],
         "summary": "Owns the full revenue operations function including forecasting and tooling."},
        {"id": 104, "name": "Tom Wu", "title": "Field Technician", "location": "New York, NY",
         "department": "Operations", "management_level": "Individual Contributor", "experience_years": 5,
         "headline": "Field Technician", "skills": ["hardware repair"],
         "summary": "On-site hardware support technician."},
        {"id": 105, "name": "Elena Ruiz", "title": "Head of Sales", "location": "London, UK",
         "department": "Sales", "management_level": "VP", "experience_years": 10,
         "headline": "Head of Sales, EMEA @ Notion", "skills": ["EMEA GTM", "enterprise sales"],
         "summary": "Runs EMEA sales; based in London, not the required geography for this search."},
    ]
    demo_filters = {
        "departments": ["Sales"],
        "management_level": ["VP", "Director"],
        "location": "New York",
        "title": ["VP of Sales", "Director of Sales"],
    }

    print(f"MODEL: {args.model}   BASE_URL: {os.environ.get('OPENAI_BASE_URL') or 'api.openai.com'}\n")
    result = score_leads_batch("Notion", demo_filters, demo_leads, model=args.model)

    print("\n--- scored leads ---\n")
    if result:
        for s in result.scored_leads:
            print(f"  lead_id={s.lead_id}  score={s.score}  tier={s.priority_tier}")

        valid_ids = {l["id"] for l in demo_leads}
        top = rank_and_select(result, valid_ids, total_required=2)
        print(f"\n--- top 2 selected (total_required=2) ---\n  {top}")
    else:
        print("(no result)")
