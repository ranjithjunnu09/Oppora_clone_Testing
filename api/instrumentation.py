"""
OpenAI client interceptor.

WHY THIS EXISTS
  The 9 standalone feature files print token usage to stdout and return only
  their final result. A browser cannot read stdout. Rather than editing those
  files (which would break the "byte-identical to production" property this
  repo exists for), we patch the OpenAI SDK for the duration of a single run
  and record every call that passes through it.

  Nothing in classification/, email_generation/ or lead_scoring/ changes.
"""
from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .providers import estimate_cost, provider_for

# Per-run call log. A contextvar (not a global) so concurrent runs stay isolated.
_current_run: contextvars.ContextVar["RunRecorder | None"] = contextvars.ContextVar(
    "current_run", default=None
)


@dataclass
class LLMCall:
    """One captured LLM call, in the order it happened."""

    index: int
    label: str
    model: str
    latency_ms: int
    prompt_tokens: int = 0
    cached_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    provider: str = "openai"
    #  Params dropped because the routed provider does not accept them.
    #  Surfaced in the UI so a comparison is never silently unfair.
    stripped_params: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    response_text: str | None = None
    error: str | None = None

    @property
    def cache_hit_rate(self) -> float:
        return (self.cached_tokens / self.prompt_tokens * 100) if self.prompt_tokens else 0.0


class RunRecorder:
    """Collects every LLM call made during one feature run."""

    def __init__(self, run_id: str | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.calls: list[LLMCall] = []
        self.started_at = time.time()

    def record(self, call: LLMCall) -> None:
        self.calls.append(call)

    @property
    def total_prompt_tokens(self) -> int:
        return sum(c.prompt_tokens for c in self.calls)

    @property
    def total_cached_tokens(self) -> int:
        return sum(c.cached_tokens for c in self.calls)

    @property
    def total_completion_tokens(self) -> int:
        return sum(c.completion_tokens for c in self.calls)

    @property
    def total_cost_usd(self) -> float:
        return sum(c.cost_usd for c in self.calls)

    @property
    def total_latency_ms(self) -> int:
        return int((time.time() - self.started_at) * 1000)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "call_count": len(self.calls),
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "total_latency_ms": self.total_latency_ms,
            "cache_hit_rate": (
                round(self.total_cached_tokens / self.total_prompt_tokens * 100, 2)
                if self.total_prompt_tokens
                else 0.0
            ),
            "calls": [
                {**asdict(c), "cache_hit_rate": round(c.cache_hit_rate, 2)} for c in self.calls
            ],
        }


def _extract_usage(resp: Any) -> dict[str, int]:
    u = getattr(resp, "usage", None)
    if u is None:
        return {}
    details = getattr(u, "prompt_tokens_details", None)
    cdetails = getattr(u, "completion_tokens_details", None)
    return {
        "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
        "cached_tokens": (getattr(details, "cached_tokens", 0) or 0) if details else 0,
        "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
        "total_tokens": getattr(u, "total_tokens", 0) or 0,
        "reasoning_tokens": (
            (getattr(cdetails, "reasoning_tokens", 0) or 0) if cdetails else 0
        ),
    }


def _response_text(resp: Any) -> str | None:
    try:
        msg = resp.choices[0].message
        parsed = getattr(msg, "parsed", None)
        if parsed is not None:
            return (
                parsed.model_dump_json(indent=2)
                if hasattr(parsed, "model_dump_json")
                else str(parsed)
            )
        return getattr(msg, "content", None)
    except Exception:
        return None


def _safe_messages(messages: Any) -> list[dict[str, Any]]:
    """Keep prompts inspectable in the UI but bounded in size."""
    out: list[dict[str, Any]] = []
    try:
        for m in messages or []:
            content = m.get("content", "")
            if isinstance(content, str) and len(content) > 20_000:
                content = content[:20_000] + f"\n\n... [truncated, {len(content)} chars total]"
            out.append({"role": m.get("role", "?"), "content": content})
    except Exception:
        pass
    return out


_WRAPPED_MARKER = "__oppora_instrumented__"


def _wrap(original, label_prefix: str):
    """Wrap a completions method so each call is timed and recorded.

    Idempotent: in openai>=2.x `client.beta.chat.completions` resolves to the
    SAME Completions class as `client.chat.completions`, so without this guard
    `.parse` would be wrapped twice and every call double-counted.
    """
    if getattr(original, _WRAPPED_MARKER, False):
        return original

    def wrapper(self, *args, **kwargs):
        recorder = _current_run.get()
        if recorder is None:
            return original(self, *args, **kwargs)

        model = kwargs.get("model", "unknown")
        messages = kwargs.get("messages", [])
        provider = provider_for(model)

        # Drop params the routed provider rejects. This is transport
        # translation, not a prompt change — the feature files stay untouched.
        # Notably `reasoning_effort` is not supported through Anthropic's
        # OpenAI-compat layer, and predict_email_status passes it.
        stripped = [p for p in provider.unsupported_params if p in kwargs]
        for p in stripped:
            kwargs.pop(p, None)

        idx = len(recorder.calls)
        started = time.perf_counter()
        try:
            resp = original(self, *args, **kwargs)
        except Exception as exc:
            recorder.record(
                LLMCall(
                    index=idx,
                    label=f"{label_prefix} {idx + 1}",
                    model=model,
                    provider=provider.id,
                    stripped_params=stripped,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    messages=_safe_messages(messages),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
            raise

        call = LLMCall(
            index=idx,
            label=f"{label_prefix} {idx + 1}",
            model=model,
            provider=provider.id,
            stripped_params=stripped,
            latency_ms=int((time.perf_counter() - started) * 1000),
            messages=_safe_messages(messages),
            response_text=_response_text(resp),
            **_extract_usage(resp),
        )
        call.cost_usd = estimate_cost(
            model, call.prompt_tokens, call.cached_tokens, call.completion_tokens
        )
        recorder.record(call)
        return resp

    setattr(wrapper, _WRAPPED_MARKER, True)
    return wrapper


_patched = False


def install() -> None:
    """Patch the OpenAI SDK once, at server start. Idempotent."""
    global _patched
    if _patched:
        return
    from openai.resources.chat.completions import Completions

    Completions.create = _wrap(Completions.create, "call")
    if hasattr(Completions, "parse"):
        Completions.parse = _wrap(Completions.parse, "call")
    try:
        from openai.resources.beta.chat.completions import (
            Completions as BetaCompletions,
        )

        BetaCompletions.parse = _wrap(BetaCompletions.parse, "call")
    except Exception:
        # Older/newer SDK layouts may not expose the beta resource; the
        # non-beta patch above already covers the call path in that case.
        pass
    _patched = True


@contextlib.contextmanager
def capture(run_id: str | None = None):
    """Record every LLM call made inside this block."""
    install()
    recorder = RunRecorder(run_id)
    token = _current_run.set(recorder)
    try:
        yield recorder
    finally:
        _current_run.reset(token)
