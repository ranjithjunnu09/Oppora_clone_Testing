"""
Provider routing and pricing.

The 9 feature files construct a plain `OpenAI()` client and call it. Anthropic
publishes an OpenAI-SDK-compatible endpoint, so Claude models are reached by
swapping base_url + api_key at call time — the feature files stay untouched and
the prompts stay byte-identical, which is the whole point of the repo.

  https://docs.anthropic.com/en/api/openai-sdk

KNOWN LIMITS OF THE COMPATIBILITY LAYER (disclosed, not hidden):
  * `strict` is ignored, so structured output is NOT schema-guaranteed. Eight of
    the twelve features pass `response_format=<PydanticModel>`; on Claude those
    can occasionally return JSON that fails Pydantic validation. Such runs
    surface as `degraded`/`failed` rather than being silently swallowed. When
    comparing output quality, keep in mind a failure here may be the shim, not
    the model. Anthropic recommends the native SDK's Structured Outputs for
    guaranteed conformance.
  * `reasoning_effort` is not a documented compat field. `predict_email_status`
    passes it (production runs that feature on o4-mini). It is stripped for
    Anthropic routing — see UNSUPPORTED_PARAMS below. That means the Claude run
    of that one feature is NOT thinking-enabled, so it is not an apples-to-apples
    comparison against o4-mini with reasoning_effort="high".
  * Prompt-cache accounting differs and may under-report through the shim.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1/"


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    env_key: str
    base_url: str | None
    #  Multiplier applied to cached input tokens when estimating cost.
    #  OpenAI bills cache reads at 25% of input; Anthropic at 10%.
    cached_input_multiplier: float
    #  Params the provider's endpoint does not accept, stripped before the call.
    unsupported_params: tuple[str, ...] = ()
    notes: str = ""


OPENAI = Provider(
    id="openai",
    name="OpenAI",
    env_key="OPENAI_API_KEY",
    base_url=None,  # SDK default
    cached_input_multiplier=0.25,
)

ANTHROPIC = Provider(
    id="anthropic",
    name="Anthropic",
    env_key="ANTHROPIC_API_KEY",
    base_url=ANTHROPIC_BASE_URL,
    cached_input_multiplier=0.10,
    unsupported_params=("reasoning_effort", "temperature"),
    notes=(
        "Reached through Anthropic's OpenAI-SDK compatibility layer. Structured "
        "output is not schema-guaranteed here (`strict` is ignored), and "
        "`reasoning_effort` and `temperature` are stripped."
    ),
)

PROVIDERS: dict[str, Provider] = {p.id: p for p in (ANTHROPIC, OPENAI)}


# ── Pricing, USD per 1M tokens: (input, output) ──────────────────────────────
# Display aid only. Unknown models report $0 rather than a misleading number.
PRICING: dict[str, tuple[float, float]] = {
    # Anthropic
    # NOTE: Sonnet 5 is on introductory pricing ($2/$10) through 2026-08-31,
    # after which it moves to $3/$15. Update this line when that lands.
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    # OpenAI — the models production actually runs on
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-mini-2025-04-14": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "o4-mini": (1.10, 4.40),
}


def provider_for(model: str) -> Provider:
    """Route by model-name prefix so newly released Claude models work without
    a code change — anything starting with `claude` goes to Anthropic."""
    return ANTHROPIC if model.lower().startswith("claude") else OPENAI


def resolve(
    model: str,
    base_url_override: str | None = None,
    api_key_override: str | None = None,
) -> tuple[Provider, dict[str, str]]:
    """Returns the provider plus the client kwargs the adapters should pass.

    An explicit base_url from the UI always wins — that is how a self-hosted
    OpenAI-compatible endpoint is targeted, and it must not be overwritten by
    prefix-based routing.
    """
    provider = provider_for(model)
    kw: dict[str, str] = {}

    if base_url_override:
        kw["base_url"] = base_url_override
    elif provider.base_url:
        kw["base_url"] = provider.base_url

    if provider.id == "anthropic":
        kw["default_headers"] = {"anthropic-version": "2023-06-01"}

    key = api_key_override or os.environ.get(provider.env_key)
    if key:
        kw["api_key"] = key

    return provider, kw


def estimate_cost(
    model: str, prompt_tokens: int, cached_tokens: int, completion_tokens: int
) -> float:
    rates = PRICING.get(model)
    if not rates:
        return 0.0
    in_rate, out_rate = rates
    multiplier = provider_for(model).cached_input_multiplier
    fresh = max(prompt_tokens - cached_tokens, 0)
    return (
        fresh * in_rate / 1_000_000
        + cached_tokens * in_rate * multiplier / 1_000_000
        + completion_tokens * out_rate / 1_000_000
    )


def configured_providers() -> dict[str, bool]:
    """Which providers have a usable API key, for the UI's status indicators."""
    return {p.id: bool(os.environ.get(p.env_key)) for p in PROVIDERS.values()}
