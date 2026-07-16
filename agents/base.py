"""Base interface shared by future proposal-generation agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


AgentEventType = Literal["started", "completed", "failed"]


class AgentLogEvent(BaseModel):
    """Structured log event emitted around a single agent run."""

    agent_name: str
    event_type: AgentEventType
    input_snapshot: Any | None = None
    output_snapshot: Any | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


AgentLogHook = Callable[[AgentLogEvent], None]


class BaseAgent(ABC):
    """Common interface for controlled, single-step agents.

    Concrete agents implement ``_run``. The public ``run`` method stays shared
    so every agent emits the same start, completion, and failure log events.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        prompt_path: str | Path,
        log_hook: AgentLogHook | None = None,
    ) -> None:
        """Create an agent with metadata and an optional log hook.

        Args:
            name: Human-readable agent name used in logs and run history.
            description: Short responsibility statement for this agent.
            prompt_path: Path to the prompt file used by the agent.
            log_hook: Optional callback that receives structured log events.
        """
        if not name.strip():
            raise ValueError("Agent name cannot be empty.")
        if not description.strip():
            raise ValueError("Agent description cannot be empty.")

        self.name = name
        self.description = description
        self.prompt_path = Path(prompt_path)
        self._log_hook = log_hook

    def run(self, input_data: Any) -> Any:
        """Run the agent once and return its validated output.

        Args:
            input_data: Structured input for this agent. Future concrete
                agents should validate it with a Pydantic schema before use.

        Returns:
            The structured output produced by the concrete agent.
        """
        self._emit_log("started", input_snapshot=input_data)

        try:
            output = self._run(input_data)
        except Exception as exc:
            self._emit_log(
                "failed",
                input_snapshot=input_data,
                error_message=str(exc),
            )
            raise

        self._emit_log(
            "completed",
            input_snapshot=input_data,
            output_snapshot=output,
        )
        return output

    @abstractmethod
    def _run(self, input_data: Any) -> Any:
        """Execute agent-specific logic for one structured input."""

    def _emit_log(
        self,
        event_type: AgentEventType,
        *,
        input_snapshot: Any | None = None,
        output_snapshot: Any | None = None,
        error_message: str | None = None,
    ) -> None:
        """Send a structured event to the configured log hook, if present."""
        if self._log_hook is None:
            return

        self._log_hook(
            AgentLogEvent(
                agent_name=self.name,
                event_type=event_type,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
                error_message=error_message,
            )
        )
