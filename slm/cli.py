"""Command-line entry point for the isolated SLM pipelines."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, TextIO

from storage.db import get_session
from storage.repositories import get_run
from workflow.llm_client import capture_llm_usage

from slm.pipeline import (
    run_slm_baseline,
    run_slm_multi_agent,
    run_slm_workflow,
)
from slm.preflight_slm import SLMPreflightResult, check_slm_preflight


_MODES = ("baseline", "workflow", "multi")
_EMPTY_TOKEN_USAGE: dict[str, int | float] = {
    "request_count": 0,
    "retry_count": 0,
    "prompt_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0,
    "approximate_cost": 0.0,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an isolated Qwen SLM proposal pipeline.",
    )
    parser.add_argument(
        "--mode",
        choices=_MODES,
        required=True,
        help="Pipeline to run.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="UTF-8 JSON input file.",
    )
    return parser


def _load_input(input_path: Path, *, mode: str) -> str | dict[str, Any]:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read input file {input_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"input file {input_path} is not valid JSON: "
            f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if mode == "baseline":
        if isinstance(payload, (str, dict)):
            return payload
        raise ValueError(
            "baseline input must be a JSON string or a JSON object"
        )

    if not isinstance(payload, dict):
        raise ValueError(f"{mode} input must be a JSON object")
    return payload


def _runner_for_mode(mode: str) -> Callable[[Any], Any]:
    if mode == "baseline":
        return run_slm_baseline
    if mode == "workflow":
        return run_slm_workflow
    if mode == "multi":
        return run_slm_multi_agent
    raise ValueError(f"unsupported mode: {mode}")


def _print_preflight_issues(
    result: SLMPreflightResult,
    *,
    stream: TextIO,
) -> None:
    for issue in result.issues:
        severity = "warning" if issue.recoverable else "error"
        print(
            f"SLM preflight {severity} [{issue.code}]: {issue.message}",
            file=stream,
        )


def _persisted_token_usage(run_id: str) -> dict[str, int | float] | None:
    """Read usage aggregated by the existing workflow logging layer."""
    try:
        with get_session() as session:
            run = get_run(session, run_id)
            if run is None or not run.token_usage:
                return None
            return dict(run.token_usage)
    except Exception:
        # Reporting must not turn a successfully saved proposal into a failed run.
        return None


def _token_usage(
    run_id: str,
    directly_captured: dict[str, int | float],
) -> dict[str, int | float]:
    persisted = _persisted_token_usage(run_id)
    source = persisted if persisted is not None else directly_captured
    return {
        key: source.get(key, default)
        for key, default in _EMPTY_TOKEN_USAGE.items()
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run one CLI invocation and return its process exit code."""
    args = _build_parser().parse_args(argv)

    try:
        preflight = check_slm_preflight(
            require_knowledge_base=args.mode == "multi",
        )
    except Exception as exc:
        print(f"SLM preflight could not run: {exc}", file=sys.stderr)
        return 3

    if preflight.issues:
        _print_preflight_issues(
            preflight,
            stream=sys.stdout if preflight.is_ready else sys.stderr,
        )
    if not preflight.is_ready:
        print(
            "SLM preflight failed; fix the errors above and retry.",
            file=sys.stderr,
        )
        return 3

    try:
        payload = _load_input(args.input, mode=args.mode)
    except ValueError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2

    started_at = time.perf_counter()
    try:
        with capture_llm_usage() as direct_usage:
            result = _runner_for_mode(args.mode)(payload)
    except Exception as exc:
        elapsed_seconds = time.perf_counter() - started_at
        print(
            f"SLM {args.mode} run failed after {elapsed_seconds:.3f}s: {exc}",
            file=sys.stderr,
        )
        return 1

    elapsed_seconds = time.perf_counter() - started_at
    usage = _token_usage(result.run_id, direct_usage.as_dict())
    print(f"run_id: {result.run_id}")
    print(f"output_path: {result.output_path}")
    print(f"elapsed_seconds: {elapsed_seconds:.3f}")
    print(
        "token_usage: "
        + json.dumps(usage, ensure_ascii=False, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
