"""Preflight checks for the isolated SLM execution path."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import requests

from rag.knowledge_base import DEFAULT_KNOWLEDGE_BASE_DIR
from workflow.preflight import (
    DEFAULT_OUTPUT_DIR,
    PreflightIssue,
    check_preflight,
)

from slm.config import load_slm_config


_ENDPOINT_TIMEOUT_SECONDS = 3


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


def check_slm_preflight(
    *,
    base_url: str | None = None,
    environ: Mapping[str, str] | None = None,
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_knowledge_base: bool = True,
    create_output_dir: bool = True,
) -> SLMPreflightResult:
    """Check shared dependencies and probe the configured SLM endpoint."""

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

    active_base_url = (
        load_slm_config().base_url if base_url is None else base_url.strip()
    )
    endpoint_available = False
    try:
        response = requests.get(
            _models_endpoint(active_base_url),
            timeout=_ENDPOINT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        endpoint_available = True
    except requests.RequestException as exc:
        issues.append(
            PreflightIssue(
                code="slm_endpoint_unreachable",
                message=(
                    f"SLM endpoint is unreachable at {_models_endpoint(active_base_url)} "
                    f"({exc}). 请确认 ollama serve 已启动。"
                ),
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
    )


__all__ = ["SLMPreflightResult", "check_slm_preflight"]
