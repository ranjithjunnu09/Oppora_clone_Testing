"""
FastAPI server — the HTTP layer over the standalone feature files.

This is *not* where AI logic lives. It receives JSON from the browser, calls
the untouched functions in classification/ | email_generation/ | lead_scoring/
through api/adapters.py, records token usage via api/instrumentation.py, and
persists the run to SQLite.

Run:
    uvicorn api.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, instrumentation, providers, scoring
from .adapters import ADAPTERS
from .registry import (
    CATEGORIES,
    FEATURES,
    FEATURES_BY_ID,
    MODEL_PRESETS,
    OPEN_MODEL_SUGGESTIONS,
)

load_dotenv()

app = FastAPI(
    title="Oppora AI Benchmark Console",
    description="Run Oppora's production AI features against any OpenAI-compatible model and compare output, tokens, latency and cost.",
    version="1.0.0",
)

# Vite dev server runs on 5173; 4173 is `vite preview`.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_executor = ThreadPoolExecutor(max_workers=8)


@app.on_event("startup")
def _startup() -> None:
    db.init()
    instrumentation.install()


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    feature_id: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    models: list[str] = Field(
        default_factory=list,
        description="One run is created per model. Two or more turns this into a comparison.",
    )
    base_url: str | None = Field(
        None, description="Point at a self-hosted OpenAI-compatible endpoint."
    )
    api_key: str | None = Field(None, description="Overrides OPENAI_API_KEY for this run only.")
    repeats: int = Field(
        1, ge=1, le=20,
        description=(
            "Runs per model. Open models vary far more run-to-run than frontier "
            "ones, so a single sample is not evidence. 5 is a reasonable default "
            "when deciding whether quality holds."
        ),
    )


class RunHandle(BaseModel):
    batch_id: str
    run_ids: list[str]


# ─────────────────────────────────────────────────────────────────────────────
# Execution
# ─────────────────────────────────────────────────────────────────────────────

def _execute(run_id: str, feature_id: str, model: str, inputs: dict, base_url: str | None,
             api_key: str | None) -> None:
    """Runs in a worker thread. Records usage, persists success or failure."""
    adapter = ADAPTERS[feature_id]

    # Route by model name: `claude-*` goes to Anthropic's OpenAI-compat endpoint,
    # everything else to OpenAI. An explicit base_url from the UI always wins,
    # which is how a self-hosted endpoint is targeted.
    _provider, kw = providers.resolve(model, base_url, api_key)
    kw = dict(kw)  # type: ignore[assignment]

    with instrumentation.capture(run_id) as recorder:
        try:
            result = adapter(inputs, model, **kw)
            metrics = recorder.as_dict()

            # Deterministic rule scoring against the production prompt's own
            # constraints. Returns None for features with no rubric yet.
            quality = scoring.score(feature_id, result, inputs)

            # Several feature files catch their own exceptions and return None
            # (predict_email_status, predict_delivery_failure, top_lead_generate,
            # score_leads_batch, fix_lead_recommendations). Those runs would
            # otherwise be indistinguishable from a clean pass while carrying an
            # empty result — which would quietly corrupt a model comparison.
            failed = [c for c in metrics["calls"] if c.get("error")]
            if failed:
                db.finish_run(
                    run_id,
                    result,
                    metrics,
                    quality=quality,
                    status="degraded",
                    error=(
                        f"{len(failed)} of {metrics['call_count']} LLM call(s) failed, but the "
                        f"feature swallowed the exception and returned a value anyway. "
                        f"First failure: {failed[0]['error']}"
                    ),
                )
            else:
                db.finish_run(run_id, result, metrics, quality=quality)
        except Exception as exc:
            db.fail_run(
                run_id,
                f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc(limit=6)}",
                recorder.as_dict(),
            )


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> dict:
    configured = providers.configured_providers()
    return {
        "status": "ok",
        "providers": [
            {
                "id": p.id,
                "name": p.name,
                "env_key": p.env_key,
                "configured": configured[p.id],
                "notes": p.notes,
            }
            for p in providers.PROVIDERS.values()
        ],
        # Retained for backwards compatibility with the earlier OpenAI-only shape.
        "openai_key_configured": configured["openai"],
        "anthropic_key_configured": configured["anthropic"],
        "default_base_url": os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        "feature_count": len(FEATURES),
    }


@app.get("/api/features")
def features() -> dict:
    return {
        "categories": CATEGORIES,
        "features": [f.to_dict() for f in FEATURES],
        "models": MODEL_PRESETS,
        "open_model_suggestions": OPEN_MODEL_SUGGESTIONS,
        "model_providers": {m: providers.provider_for(m).id for m in MODEL_PRESETS},
    }


@app.get("/api/features/{feature_id}")
def feature(feature_id: str) -> dict:
    f = FEATURES_BY_ID.get(feature_id)
    if not f:
        raise HTTPException(404, f"Unknown feature: {feature_id}")
    return f.to_dict()


@app.post("/api/run", response_model=RunHandle)
def run(req: RunRequest) -> RunHandle:
    feature = FEATURES_BY_ID.get(req.feature_id)
    if not feature:
        raise HTTPException(404, f"Unknown feature: {req.feature_id}")

    models = req.models or [feature.default_model]
    batch_id = uuid.uuid4().hex[:12]
    run_ids: list[str] = []

    for model in models:
        for i in range(req.repeats):
            run_id = uuid.uuid4().hex[:12]
            run_ids.append(run_id)
            db.create_run(
                run_id, req.feature_id, model, req.inputs, req.base_url, batch_id,
                repeat_index=i,
            )
            _executor.submit(
                _execute, run_id, req.feature_id, model, req.inputs, req.base_url, req.api_key
            )

    return RunHandle(batch_id=batch_id, run_ids=run_ids)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


def _aggregate(runs: list[dict]) -> list[dict]:
    """Collapse repeats into one row per model.

    Reports min/max alongside the mean because for a migration decision the
    WORST observed run matters more than the average — an open model whose
    quality score swings 100/40/95 is not safe to ship even though it averages
    78. `pass_rate` is the share of repeats with no critical rule failure.
    """
    by_model: dict[str, list[dict]] = {}
    for r in runs:
        by_model.setdefault(r["model"], []).append(r)

    out = []
    for model, group in by_model.items():
        settled = [r for r in group if r["status"] in ("succeeded", "degraded")]
        scored = [r for r in settled if r.get("quality_score") is not None]
        qs = [r["quality_score"] for r in scored]
        costs = [r["total_cost_usd"] for r in settled]
        lats = [r["total_latency_ms"] for r in settled]

        def _clean(r: dict) -> bool:
            q = r.get("quality") or {}
            return (q.get("summary") or {}).get("critical", 1) == 0

        out.append({
            "model": model,
            "provider": providers.provider_for(model).id,
            "repeats": len(group),
            "completed": len(settled),
            "failed": sum(1 for r in group if r["status"] == "failed"),
            "degraded": sum(1 for r in group if r["status"] == "degraded"),
            "quality_mean": round(sum(qs) / len(qs), 1) if qs else None,
            "quality_min": min(qs) if qs else None,
            "quality_max": max(qs) if qs else None,
            "pass_rate": (
                round(sum(1 for r in scored if _clean(r)) / len(scored) * 100, 0)
                if scored else None
            ),
            "cost_mean": round(sum(costs) / len(costs), 6) if costs else 0.0,
            "cost_max": max(costs) if costs else 0.0,
            "latency_mean": int(sum(lats) / len(lats)) if lats else 0,
            "latency_max": max(lats) if lats else 0,
            "stripped_params": sorted({
                p for r in settled for c in (r.get("calls") or [])
                for p in (c.get("stripped_params") or [])
            }),
        })
    return out


@app.get("/api/batch/{batch_id}")
def get_batch(batch_id: str) -> dict:
    runs = db.list_batch(batch_id)
    if not runs:
        raise HTTPException(404, "Batch not found")
    feature_id = runs[0]["feature_id"]
    return {
        "batch_id": batch_id,
        "runs": runs,
        "settled": all(r["status"] in ("succeeded", "degraded", "failed") for r in runs),
        "by_model": _aggregate(runs),
        "baseline": db.get_baseline(feature_id),
    }


@app.post("/api/runs/{run_id}/baseline")
def pin_baseline(run_id: str) -> dict:
    """Pin this run as the reference for its feature. Migration verdicts are
    measured against it rather than against whichever run came first."""
    if not db.get_run(run_id):
        raise HTTPException(404, "Run not found")
    db.set_baseline(run_id)
    return {"status": "pinned", "run_id": run_id}


@app.get("/api/history")
def history(feature_id: str | None = None, limit: int = 100) -> dict:
    return {"runs": db.list_runs(feature_id, limit)}


@app.get("/api/stats")
def stats() -> dict:
    return db.stats()


@app.delete("/api/history")
def clear_history() -> dict:
    db.delete_all()
    return {"status": "cleared"}


@app.get("/api/logs")
def logs(limit: int = 200, status: str | None = None, feature_id: str | None = None) -> dict:
    """Detailed call-level logs for the Logs page.

    Returns every individual LLM call across all runs — with prompt,
    response, tokens, latency, error and stripped_params — so you can
    see exactly what was sent to the model and what came back.
    """
    runs = db.list_runs(feature_id, limit)
    entries: list[dict] = []

    for run in runs:
        if status and run.get("status") != status:
            continue
        full = db.get_run(run["id"])
        if not full:
            continue
        calls = full.get("calls") or []
        for call in calls:
            entries.append({
                "run_id": run["id"],
                "feature_id": run["feature_id"],
                "batch_id": run.get("batch_id"),
                "run_status": run["status"],
                "run_created_at": run["created_at"],
                "run_error": run.get("error"),
                # per-call fields
                "call_index": call.get("index", 0),
                "call_label": call.get("label", f"call {call.get('index', 0) + 1}"),
                "model": call.get("model", run["model"]),
                "provider": call.get("provider", "anthropic"),
                "latency_ms": call.get("latency_ms", 0),
                "prompt_tokens": call.get("prompt_tokens", 0),
                "cached_tokens": call.get("cached_tokens", 0),
                "completion_tokens": call.get("completion_tokens", 0),
                "total_tokens": call.get("total_tokens", 0),
                "cost_usd": call.get("cost_usd", 0.0),
                "cache_hit_rate": call.get("cache_hit_rate", 0.0),
                "stripped_params": call.get("stripped_params", []),
                "messages": call.get("messages", []),
                "response_text": call.get("response_text"),
                "error": call.get("error"),
            })

    # Sort newest first
    entries.sort(key=lambda e: e["run_created_at"], reverse=True)
    return {"logs": entries, "total": len(entries)}
