"""Preflight checks for the isolated SLM execution path."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import requests

from rag.knowledge_base import DEFAULT_KNOWLEDGE_BASE_DIR
from workflow.preflight import (
    DEFAULT_OUTPUT_DIR,
    PreflightIssue,
    check_preflight,
)

from slm.config import SLMConfig, load_slm_config, required_context_tokens


_ENDPOINT_TIMEOUT_SECONDS = 3

# Measuring the window means prefilling a probe of the required size, which took
# 334s for 23k tokens on the reference CPU machine. Paying that on every run
# would get the guard switched off, so the measurement is cached per endpoint,
# model, and requirement -- exactly the inputs whose change can invalidate it.
CONTEXT_WINDOW_CACHE_PATH = Path(__file__).resolve().with_name(
    "context_window_cache.json"
)


@dataclass(frozen=True, slots=True)
class SLMPreflightResult:
    """Dependency status for an SLM run, independent of Gemini semantics."""

    slm_endpoint_available: bool
    tavily_available: bool
    knowledge_base_available: bool
    output_writable: bool
    knowledge_base_dir: Path
    output_dir: Path
    issues: tuple[PreflightIssue, ...] = ()
    context_window_tokens: int | None = None

    @property
    def errors(self) -> tuple[PreflightIssue, ...]:
        """Return mandatory issues that must stop the SLM workflow."""
        return tuple(issue for issue in self.issues if not issue.recoverable)

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        """Return optional dependency issues that permit degraded execution."""
        return tuple(issue for issue in self.issues if issue.recoverable)

    @property
    def is_ready(self) -> bool:
        """Whether every mandatory SLM dependency is available."""
        return not self.errors

    @property
    def degraded(self) -> bool:
        """Whether execution can continue without every optional dependency."""
        return self.is_ready and bool(self.warnings)


def _models_endpoint(base_url: str) -> str:
    return f"{base_url.rstrip('/')}/models"


def _auth_headers(api_key: str) -> dict[str, str]:
    """Authenticate the reachability probe.

    A local server ignores this, but every hosted endpoint answers an
    unauthenticated ``/models`` with 401 -- which this check would otherwise
    report as ``slm_endpoint_unreachable``, pointing at the network instead of
    at the credential.
    """
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _measure_context_window(config: SLMConfig) -> int:
    """Measure the endpoint's effective context window with one probe request."""
    from slm.client import SLMClient

    return SLMClient(config).measure_context_window(
        required_context_tokens(config)
    )


def _cache_key(config: SLMConfig, required_tokens: int) -> str:
    """Identify one measurement by everything that can invalidate it."""
    return f"{config.base_url}|{config.model_name}|{required_tokens}"


def _read_cached_window(key: str) -> int | None:
    """Return a previously measured window, ignoring an unusable cache file."""
    try:
        cache = json.loads(
            CONTEXT_WINDOW_CACHE_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    value = cache.get(key) if isinstance(cache, Mapping) else None
    return value if isinstance(value, int) and value > 0 else None


def _write_cached_window(key: str, measured_tokens: int) -> None:
    """Persist one measurement; a read-only location must not fail preflight."""
    try:
        cache = json.loads(
            CONTEXT_WINDOW_CACHE_PATH.read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}
    cache[key] = measured_tokens
    try:
        CONTEXT_WINDOW_CACHE_PATH.write_text(
            json.dumps(cache, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except OSError:
        return


def _context_window_issue(
    measured_tokens: int,
    required_tokens: int,
    config: SLMConfig,
) -> PreflightIssue:
    """Describe an undersized context window and how to widen it."""
    return PreflightIssue(
        code="slm_context_window_too_small",
        message=(
            f"SLM endpoint serves only {measured_tokens} context tokens but "
            f"{required_tokens} are required by SLM_MAX_PROMPT_CHARS="
            f"{config.max_prompt_chars} plus SLM_MAX_OUTPUT_TOKENS="
            f"{config.max_output_tokens}. The server truncates oversized "
            "prompts silently, so requests lose their instruction header and "
            "fail strict validation for reasons the error never names. Either "
            "serve a wider window -- a hosted endpoint caps it per model, a "
            "local one usually needs an explicit context length such as "
            "Ollama's num_ctx -- or lower SLM_MAX_PROMPT_CHARS and "
            "SLM_MAX_OUTPUT_TOKENS until their sum fits."
        ),
    )


def check_slm_preflight(
    *,
    base_url: str | None = None,
    config: SLMConfig | None = None,
    environ: Mapping[str, str] | None = None,
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_knowledge_base: bool = True,
    create_output_dir: bool = True,
    context_window_probe: Callable[[SLMConfig], int] | None = None,
) -> SLMPreflightResult:
    """Check shared dependencies and probe the configured SLM endpoint.

    Besides reachability, this verifies that the endpoint can actually serve the
    context window the SLM budget assumes. That probe converts silent prompt
    truncation, which surfaces only as unexplained downstream validation
    failures, into an actionable startup error. The measurement is cached in
    ``CONTEXT_WINDOW_CACHE_PATH`` per endpoint, model, and requirement, so only
    the first run of a given configuration pays for it. Delete that file to
    force a re-measurement, or set ``SLM_CONTEXT_PROBE=0`` to skip the check.
    """

    shared_result = check_preflight(
        environ=environ,
        knowledge_base_dir=knowledge_base_dir,
        output_dir=output_dir,
        require_knowledge_base=require_knowledge_base,
        allow_tavily_degradation=True,
        create_output_dir=create_output_dir,
    )
    issues = [
        issue
        for issue in shared_result.issues
        if issue.code != "gemini_api_key_missing"
    ]

    active_config = load_slm_config() if config is None else config
    active_base_url = (
        active_config.base_url if base_url is None else base_url.strip()
    )
    endpoint_available = False
    try:
        response = requests.get(
            _models_endpoint(active_base_url),
            timeout=_ENDPOINT_TIMEOUT_SECONDS,
            headers=_auth_headers(active_config.api_key),
        )
        response.raise_for_status()
        endpoint_available = True
    except requests.RequestException as exc:
        issues.append(
            PreflightIssue(
                code="slm_endpoint_unreachable",
                message=(
                    f"SLM endpoint is unreachable at {_models_endpoint(active_base_url)} "
                    f"({exc}). 请确认 SLM_BASE_URL 正确、网络可达；"
                    "本地端点还需确认推理服务已启动。"
                ),
            )
        )

    context_window_tokens: int | None = None
    if endpoint_available and active_config.context_probe:
        required_tokens = required_context_tokens(active_config)
        cache_key = _cache_key(active_config, required_tokens)
        context_window_tokens = _read_cached_window(cache_key)
        if context_window_tokens is None:
            probe = context_window_probe or _measure_context_window
            try:
                context_window_tokens = probe(active_config)
            except Exception as exc:
                issues.append(
                    PreflightIssue(
                        code="slm_context_window_unverified",
                        message=(
                            "SLM context window probe failed "
                            f"({type(exc).__name__}: {exc}). Requests may be "
                            "truncated without warning; set SLM_CONTEXT_PROBE=0 "
                            "to run anyway."
                        ),
                    )
                )
            else:
                _write_cached_window(cache_key, context_window_tokens)
        if (
            context_window_tokens is not None
            and context_window_tokens < required_tokens
        ):
            issues.append(
                _context_window_issue(
                    context_window_tokens,
                    required_tokens,
                    active_config,
                )
            )

    return SLMPreflightResult(
        slm_endpoint_available=endpoint_available,
        tavily_available=shared_result.tavily_available,
        knowledge_base_available=shared_result.knowledge_base_available,
        output_writable=shared_result.output_writable,
        knowledge_base_dir=shared_result.knowledge_base_dir,
        output_dir=shared_result.output_dir,
        issues=tuple(issues),
        context_window_tokens=context_window_tokens,
    )


__all__ = ["SLMPreflightResult", "check_slm_preflight"]
