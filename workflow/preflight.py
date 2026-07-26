"""Deterministic dependency checks that run before any paid LLM request."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from rag.knowledge_base import DEFAULT_KNOWLEDGE_BASE_DIR

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT_DIR / "outputs"


@dataclass(frozen=True, slots=True)
class PreflightIssue:
    """One actionable dependency or filesystem problem found before a run."""

    code: str
    message: str
    recoverable: bool = False


@dataclass(frozen=True, slots=True)
class PreflightResult:
    """Complete preflight status, including an explicit Tavily availability flag."""

    gemini_available: bool
    tavily_available: bool
    knowledge_base_available: bool
    output_writable: bool
    knowledge_base_dir: Path
    output_dir: Path
    issues: tuple[PreflightIssue, ...] = ()

    @property
    def errors(self) -> tuple[PreflightIssue, ...]:
        """Return issues that must stop the workflow before its first LLM call."""
        return tuple(issue for issue in self.issues if not issue.recoverable)

    @property
    def warnings(self) -> tuple[PreflightIssue, ...]:
        """Return non-fatal issues that put the workflow in degraded mode."""
        return tuple(issue for issue in self.issues if issue.recoverable)

    @property
    def is_ready(self) -> bool:
        """Whether all mandatory dependencies are ready."""
        return not self.errors

    @property
    def degraded(self) -> bool:
        """Whether the workflow may run but without every optional dependency."""
        return self.is_ready and bool(self.warnings)


class PreflightError(RuntimeError):
    """Raised when mandatory preflight checks fail."""

    def __init__(self, result: PreflightResult) -> None:
        self.result = result
        details = "; ".join(issue.message for issue in result.errors)
        super().__init__(f"Workflow preflight failed: {details}")


def _normalized_path(path: str | Path) -> Path:
    """Return an absolute path without requiring the target to exist."""
    return Path(path).expanduser().resolve()


def _check_knowledge_base(path: Path) -> PreflightIssue | None:
    """Check that the configured knowledge-base directory exists and is readable."""
    if not path.is_dir():
        return PreflightIssue(
            code="knowledge_base_unavailable",
            message=f"Knowledge base directory does not exist: {path}",
        )

    try:
        next(path.iterdir(), None)
    except OSError as exc:
        return PreflightIssue(
            code="knowledge_base_unavailable",
            message=f"Knowledge base directory is not readable: {path} ({exc})",
        )
    return None


def _check_output_directory(
    path: Path,
    *,
    create_output_dir: bool,
) -> PreflightIssue | None:
    """Create, if allowed, and probe the output directory with a temporary file."""
    try:
        if create_output_dir:
            path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            return PreflightIssue(
                code="output_directory_unavailable",
                message=f"Output directory does not exist or is not a directory: {path}",
            )

        # A real write probe is more reliable than os.access(), especially on
        # Windows and when ACLs differ from the directory's basic attributes.
        with tempfile.NamedTemporaryFile(
            dir=path,
            prefix=".proposal-preflight-",
        ):
            pass
    except OSError as exc:
        return PreflightIssue(
            code="output_directory_not_writable",
            message=f"Output directory is not writable: {path} ({exc})",
        )
    return None


def check_preflight(
    *,
    environ: Mapping[str, str] | None = None,
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_knowledge_base: bool = True,
    allow_tavily_degradation: bool = True,
    create_output_dir: bool = True,
) -> PreflightResult:
    """Inspect required dependencies without calling Gemini or Tavily.

    The Gemini key and writable output directory are mandatory. The
    knowledge-base directory is also mandatory when ``require_knowledge_base``
    is true. Tavily is optional only when ``allow_tavily_degradation`` is true;
    in that case callers can continue in RAG-only/no-external-evidence mode.
    """
    if environ is None:
        load_dotenv()
        active_environ: Mapping[str, str] = os.environ
    else:
        active_environ = environ

    issues: list[PreflightIssue] = []
    gemini_available = bool(active_environ.get("GEMINI_API_KEY", "").strip())
    if not gemini_available:
        issues.append(
            PreflightIssue(
                code="gemini_api_key_missing",
                message=(
                    "GEMINI_API_KEY is not set. Configure it before starting "
                    "proposal generation."
                ),
            )
        )

    tavily_available = bool(active_environ.get("TAVILY_API_KEY", "").strip())
    if not tavily_available:
        issues.append(
            PreflightIssue(
                code="tavily_api_key_missing",
                message=(
                    "TAVILY_API_KEY is not set; controlled web research is "
                    "unavailable."
                ),
                recoverable=allow_tavily_degradation,
            )
        )

    resolved_knowledge_base = _normalized_path(knowledge_base_dir)
    knowledge_base_issue = (
        _check_knowledge_base(resolved_knowledge_base)
        if require_knowledge_base
        else None
    )
    if knowledge_base_issue is not None:
        issues.append(knowledge_base_issue)

    resolved_output_dir = _normalized_path(output_dir)
    output_issue = _check_output_directory(
        resolved_output_dir,
        create_output_dir=create_output_dir,
    )
    if output_issue is not None:
        issues.append(output_issue)

    return PreflightResult(
        gemini_available=gemini_available,
        tavily_available=tavily_available,
        knowledge_base_available=knowledge_base_issue is None,
        output_writable=output_issue is None,
        knowledge_base_dir=resolved_knowledge_base,
        output_dir=resolved_output_dir,
        issues=tuple(issues),
    )


def run_preflight_checks(
    *,
    environ: Mapping[str, str] | None = None,
    knowledge_base_dir: str | Path = DEFAULT_KNOWLEDGE_BASE_DIR,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    require_knowledge_base: bool = True,
    allow_tavily_degradation: bool = True,
    create_output_dir: bool = True,
) -> PreflightResult:
    """Return a ready status or raise once with every fatal preflight issue."""
    result = check_preflight(
        environ=environ,
        knowledge_base_dir=knowledge_base_dir,
        output_dir=output_dir,
        require_knowledge_base=require_knowledge_base,
        allow_tavily_degradation=allow_tavily_degradation,
        create_output_dir=create_output_dir,
    )
    if not result.is_ready:
        raise PreflightError(result)
    return result


__all__ = [
    "DEFAULT_OUTPUT_DIR",
    "PreflightError",
    "PreflightIssue",
    "PreflightResult",
    "check_preflight",
    "run_preflight_checks",
]
