# Oppora — Standalone AI Feature Replicas

Backend-free, byte-identical copies of Oppora's production AI features. Each file needs only
`openai` (+ `pydantic` where structured output is used) — **no Django, no database, no internal
services.** Every function is swappable to a different model/provider via `--model` and
`OPENAI_BASE_URL`, which is the whole point: these exist to **benchmark open-source / alternative
models against Oppora's real production prompts**, output-for-output, without touching the live app.

## Why these exist

Oppora's AI cost sits in two very different shapes of workload:

1. **Agentic surfaces** (the main Ora assistant, Finder) — an LLM chooses tools and iterates.
   These can't be made standalone; they need live DB/tool access by design.
2. **Narrow, single-purpose calls** — "classify this," "write this one email," "score these
   leads." These are the majority of *call volume* and the best candidates for testing whether a
   cheaper/open model holds up on Oppora's actual prompts, because each one is a self-contained
   input → prompt → structured output unit.

Every file here is category 2. `SOURCE OF TRUTH` in each file's docstring points at the exact
production function it mirrors, so a change in behavior here is a signal to check the real one too.

## Layout

```
standalone_ai_features/
├── email_generation/
│   ├── email_generation.py              — campaign/sequence email generation
│   ├── single_email_generation.py       — generate_ai_email (one templated email, merge tags)
│   ├── reply_generation.py              — _generate_ai_reply (prospect reply drafting)
│   ├── lead_email_address_generation.py — email address pattern guessing
│   ├── campaign_ai_variable.py          — _generate_ai_template_response
│   │                                       (fills ONE merge-tag variable, e.g. {ai_icebreaker};
│   │                                        highest per-item call volume — runs once per lead)
│   └── reply_agent_chain.py             — the AUTOMATIC reply agent (sales/agent/reply_agents.py):
│                                           classify_intent -> decide_attachments -> draft_reply ->
│                                           guardrail_check -> extract_referred_contacts ->
│                                           (autonomy?) ai_send_decision. 5-10 calls/reply, real
│                                           StateGraph edge order verified, not guessed. Distinct
│                                           from reply_generation.py above (that's the MANUAL "AI
│                                           reply" button; this is the pipeline that runs
│                                           automatically on real inbound replies).
├── lead_scoring/
│   ├── lead_recommendation.py           — top_lead_generate_with_quality_check
│   │                                       (generate → QA-audit → fix, self-correcting loop)
│   └── lead_scoring_batch.py            — filter_company_leads_by_filters
│                                           (scores up to 200 leads/call against filters;
│                                            likely the single highest per-call token count
│                                            in the whole AI surface)
└── classification/
    └── classification_helpers.py         — 4 bundled classifiers/extractors:
                                             get_companies_industry, extract_email_pattern,
                                             email_status_predict (o4-mini, reasoning),
                                             delivery_failure_predict
```

Each subfolder is one *feature area*; each `.py` file inside is one *self-contained pipeline* you
can run on its own.

## Running any file

```bash
pip install openai pydantic
export OPENAI_API_KEY=sk-...
python <category>/<file>.py

# Point at an open-source / alternative model endpoint instead:
export OPENAI_BASE_URL=http://localhost:8000/v1
python <category>/<file>.py --model my-open-model
```

Every file prints its own token usage per call (`input=... cached=... output=...`), so you can
directly compare cost and cache behavior across models without any extra tooling.

## What "byte-identical" means here

- **Prompts are copied verbatim**, including exact wording, static system-prompt rubrics, and
  comments explaining *why* content is ordered the way it is (usually: prompt-caching eligibility —
  static content first, request-specific content last).
- **Pydantic schemas are copied verbatim** — same fields, same types, same structured-output contract.
- **Intentionally NOT replicated:** Oppora-specific observability (`@traceable`/LangSmith
  decorators, `wrap_openai(...)`). These wrap the call for internal tracing only and don't affect
  the AI logic — every file here uses a plain `OpenAI()` client instead.

## Adding a new feature here

1. Find the production function (see `AI_FEATURES.md` in the main repo for the full inventory of
   Oppora's AI features and which ones are narrow/single-purpose vs. agentic).
2. Copy its prompt(s) and Pydantic model(s) verbatim.
3. Thread `model` / `api_key` / `base_url` as keyword-only args, built into an `OpenAI()` client
   inline (see any existing file for the pattern).
4. Keep the per-call token-usage print — it's the primary tool for comparing models.
5. Add a `SOURCE OF TRUTH` docstring pointing at the real file:function, and a short `__main__` demo.
6. Put it in an existing category folder, or make a new one if it doesn't fit.
