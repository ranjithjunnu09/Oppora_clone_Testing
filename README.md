# Oppora — Standalone AI Feature Replicas + Benchmark Console

Backend-free, byte-identical copies of Oppora's production AI features, plus a web console for
running them against any model and comparing the results.

Two layers, and the separation matters:

| Layer | What it is | Depends on |
|---|---|---|
| `classification/` `email_generation/` `lead_scoring/` | The AI logic. Byte-identical prompts and schemas from production. Still run standalone from the CLI. | `openai`, `pydantic` only |
| `api/` + `frontend/` | A console that calls those files over HTTP and records tokens, latency and cost. | FastAPI, React |

Claude is the default benchmark target; the OpenAI models production actually runs on stay
selectable so every Claude result can be read against a real baseline.

**The feature files are never modified by the console.** That is the whole point: they exist to
benchmark alternative models against Oppora's real prompts, so anything that edits them
invalidates the comparison. The console is just another caller, alongside your terminal.

---

## Quick start

```bash
# 1. Python side
pip install -r requirements.txt
cp .env.example .env          # then add your ANTHROPIC_API_KEY
uvicorn api.main:app --reload --port 8000

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

Vite proxies `/api` to port 8000, so you only ever open `localhost:5173`.

The CLI entry points still work exactly as before, untouched:

```bash
python email_generation/campaign_ai_variable.py --model gpt-4.1-nano
```

---

## What the console does

- **12 features** across the 9 feature files, each with a form generated from its real inputs.
- **Multi-model comparison** — pick two or more models and one run per model executes in parallel
  under a shared batch id, with cost/latency/output-token charts and a delta table.
- **Per-call breakdown** — chained features are several LLM calls, and aggregate numbers hide which
  node is slow or expensive. Every call expands to its exact prompt and raw response.
- **Cache visibility** — cached input reads bill at 10% on Anthropic and 25% on OpenAI, so the
  cache-hit rate is the cheapest available win. It is surfaced per call and per run, priced with
  each provider's own multiplier.
- **Pipeline graph** — the automatic reply agent renders as the 6-node graph it actually is, in the
  real production edge order.
- **Rule compliance scoring** — every email output is scored against the production prompt's own
  stated constraints, with the offending text and source rule shown per violation. No LLM judge.
- **Repeats + variance** — N runs per model, reporting mean/min/max and a clean rate, because one
  run of an open model is not evidence.
- **Migration readiness** — per-model verdict on whether quality held against a pinned baseline,
  beside the cost delta.
- **Run history** — every run persists to SQLite, so a baseline captured today is still comparable
  next month.
- **Self-hosted endpoints** — set a base URL in the header and add a custom model name to point
  everything at an OpenAI-compatible server.

---

## Providers

Claude models are reached through [Anthropic's OpenAI-SDK compatibility
layer](https://docs.anthropic.com/en/api/openai-sdk): `api/providers.py` swaps `base_url` and
`api_key` at call time based on the model name. Anything named `claude-*` routes to Anthropic,
everything else to OpenAI, and a base URL typed into the UI header overrides both so a self-hosted
endpoint still works. Prefix routing means a newly released Claude model works without a code
change.

**The 9 feature files are not modified for this.** They still build a plain `OpenAI()` client, which
is exactly why the compat layer was the right call.

### Three caveats that affect how you read results

**Structured output is not schema-guaranteed on Claude.** The compat layer ignores `strict`, and
eight of the twelve features pass `response_format=<PydanticModel>`. On Claude those can
occasionally return JSON that fails Pydantic validation. Such runs show as `degraded` or `failed`
rather than being silently swallowed — but when comparing quality, remember a failure there may be
the shim rather than the model. Anthropic recommends the native SDK's
[Structured Outputs](https://docs.claude.com/en/docs/build-with-claude/structured-outputs) for
guaranteed conformance; slotting a native provider in behind `api/providers.py` is the upgrade path.

**`predict_email_status` is not an apples-to-apples comparison.** Production runs it on o4-mini with
`reasoning_effort="high"`. That parameter is not supported through the compat layer, so it is
stripped for Anthropic routing and the Claude run is *not* thinking-enabled. The UI badges the
stripped parameter on the affected call so this is never invisible.

**Cache economics differ by provider.** OpenAI bills cache reads at 25% of input, Anthropic at 10%,
so the multiplier lives on the provider rather than being a global constant. Cache accounting may
also under-report through the compat layer.

### Pricing table

`api/providers.py` holds prices per 1M tokens. Unknown or self-hosted models report `$0` rather than
a misleading number. Note that **Claude Sonnet 5 is on introductory pricing ($2/$10) through
2026-08-31**, after which it moves to $3/$15 — update that line when it lands.

---

## Quality scoring (the migration decision)

The goal this repo serves is moving off frontier models onto open ones **without losing quality**.
That needs a number, not an eyeball, so `api/scoring.py` scores every generated output against the
constraints **the production prompts already state**.

That distinction matters: these are not quality criteria invented by the console. They are Oppora's
own stated requirements, quoted verbatim, so a failure is objectively a failure to follow the brief
— which is the first thing a weaker model gets wrong. No LLM judge is involved, so scoring is free,
instant and byte-for-byte reproducible.

Rules currently cover the six `email_generation` features. Each has its OWN rubric, because the
prompts genuinely differ — the campaign sequence enforces 50-80 words and a spam blacklist, while
`single_email_generation` asks for a formal template with no links at all and only three merge tags.
Scoring one against the other's rules would be wrong.

**What gets checked** (campaign sequence, as the richest example): body word count against the
50-80 target and the hard 125 cap, subject 3-7 words in sentence case with no ALL CAPS / `!` / fake
`Re:`, greeting in its own `<p>`, a required sign-off with a sender merge tag, the 24-word spam
blacklist, 14 banned phrases, em/en dashes, forbidden HTML (bold, tables, images, lists), link cap,
URL shorteners, only documented merge tags, no `[bracket]` placeholders, spintax wrapper correctness
plus the bare-pipe failure mode, `days_after >= 1`, and follow-ups getting progressively shorter.

**Scoring**: penalties from 100 — critical −25, major −10, minor −3. Each failure shows the offending
text and the prompt line it came from, so nothing has to be taken on trust.

### Repeats and why the worst run is the headline

Open models vary far more run-to-run than frontier ones, so **one run is not evidence**. Set repeats
in the picker and the batch reports mean, min, max and a "clean" rate (share of repeats with zero
critical failures) per model.

The `Migration readiness` table calls a model ready only when its mean is within 3 points of the
pinned baseline **and** at least 95% of repeats are free of critical failures. A model averaging
48 across runs of 97/0/97/0 is not shippable even though its best run ties the baseline — the mean
alone hides that, which is exactly why min and clean-rate are columns.

Pin any run as the baseline (`Pin as baseline` in the run header) so every later comparison measures
against a fixed reference rather than whichever run happened to be first.

### What this cannot tell you

Rules capture mechanical compliance only. A model can score 100 and still write lifeless copy that
nobody replies to. A passing score means "did not break the brief", not "this is good" — the second
still needs a human read. If you want subjective scoring too, an LLM-as-judge or a blind A/B pane
would slot in alongside; neither is built.

### Cost caveat for open models

Self-hosted models have no entry in the price table, so they report **$0** and the "Saving" column
will read −100%. That is not a real saving — your actual cost is whatever your serving infrastructure
costs. For open models, compare **tokens and latency**, and work the economics out from your own
GPU-hour or per-token vendor rate.

---

## Layout

```
├── classification/
│   └── classification_helpers.py         — 4 classifiers: industry, email pattern,
│                                           reply status (o4-mini, reasoning), bounce vs reject
├── email_generation/
│   ├── email_generation.py               — campaign sequence (initial + follow-ups)
│   ├── single_email_generation.py        — one templated email, merge tags left literal
│   ├── reply_generation.py               — the manual "AI reply" button
│   ├── lead_email_address_generation.py  — candidate address guessing
│   ├── campaign_ai_variable.py           — fills ONE merge tag; highest per-lead volume
│   └── reply_agent_chain.py              — the AUTOMATIC reply agent, 4-8 chained calls
├── lead_scoring/
│   ├── lead_recommendation.py            — generate → QA audit → fix (2-3 calls)
│   └── lead_scoring_batch.py             — up to 200 leads in one call; highest token count
├── api/
│   ├── main.py                           — FastAPI app, CORS, background execution
│   ├── providers.py                      — model→provider routing, pricing, param stripping
│   ├── instrumentation.py                — OpenAI SDK interceptor (usage, latency, prompts)
│   ├── scoring.py                        — deterministic rule rubrics per feature
│   ├── registry.py                       — the 12 features as declarative manifests
│   ├── adapters.py                       — the ONLY place that imports the feature files
│   └── db.py                             — SQLite run history
└── frontend/
    └── src/
        ├── lib/          — typed API client, shared types, formatters
        ├── components/   — ui primitives, layout, feature forms, result renderers,
        │                     metrics, quality (rule panel + migration verdict)
        ├── pages/        — dashboard, feature runner, history
        └── store/        — model selection, draft inputs, theme
```

---

## Design notes worth knowing

**Why an interceptor instead of editing the files.** Each feature file `print()`s its token usage
and returns only its final result. A browser cannot read stdout. `api/instrumentation.py` patches
the OpenAI SDK for the duration of one run and records every call that passes through, so usage
becomes data without touching the replicas. In `openai>=2.x`,
`client.beta.chat.completions` and `client.chat.completions` resolve to the *same* class, so the
patch is guarded against double-wrapping — otherwise every call would be counted twice.

**Why the registry.** Twelve features with twelve different input shapes would otherwise mean
twelve bespoke pages. Each feature declares its fields, default model and result renderer; the
frontend builds forms and result panes generically. Adding a 10th file means one manifest entry
plus one adapter function, and no frontend changes.

**Why polling, not streaming.** `lead_scoring_batch` sends up to 200 leads in a single prompt and
`reply_agent_chain` fires up to 8 sequential calls. Both outlive a comfortable HTTP timeout, so the
API executes them on a worker thread and the frontend polls the batch id. Upgrading to SSE for
live node-by-node progress is a contained change if you want it later.

**The `degraded` run status.** Five functions across the feature files catch their own exceptions
and return `None` (`predict_email_status`, `predict_delivery_failure`, `top_lead_generate`,
`score_leads_batch`, `fix_lead_recommendations`). Without special handling, a run against a broken
endpoint would look like a clean pass carrying an empty result — quietly corrupting a model
comparison. The API layer detects that a recorded call failed even though the adapter returned, and
marks the run `degraded` with an explanatory note. This is handled in `api/`, not by changing the
feature files.

**Cost figures are estimates.** `api/providers.py` holds the price table and applies each
provider's own cached-input multiplier. Extend `PRICING` as needed.

**SQLite on network shares.** The run database defaults to `api/runs.db`. Mounted or networked
filesystems often lack the file locking SQLite needs and produce `disk I/O error` on write. Point
`OPPORA_DB_PATH` at a local path in that case.

---

## Known production inconsistency (replicated, not fixed)

`reply_agent_chain.py` — `classify_intent`'s Pydantic field types `intent` as `Email_Status_Enum`
(Lead / Interested / Meeting booked / …), but its own system prompt instructs the model to classify
into a completely different, non-overlapping set (`positive_interest`, `request_info`,
`unsubscribe`, …). Structured output forces the answer into the enum regardless of what the prompt
asked for. This is real in production and is preserved here deliberately — it is worth raising with
the team rather than silently fixing in a replica.

---

## Adding a new feature

1. Copy the production function's prompts and Pydantic models verbatim into the right category
   folder, keeping the per-call token-usage print and a `__main__` demo.
2. Add a `SOURCE OF TRUTH` docstring pointing at the real `file:function`.
3. Add an adapter in `api/adapters.py` — translation only, no prompt logic.
4. Add a `Feature(...)` manifest in `api/registry.py`, choosing an existing `result_type` or adding
   a renderer in `frontend/src/components/results/ResultRenderer.tsx`.
