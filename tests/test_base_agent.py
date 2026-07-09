"""Unit tests for the Sprint 7.1 base agent interface."""

import unittest
from typing import Any

from agents.base import AgentLogEvent, BaseAgent


class MockAgent(BaseAgent):
    """Small test double that echoes a deterministic structured response."""

    def _run(self, input_data: Any) -> dict[str, Any]:
        """Return a predictable output for the provided input."""
        return {"agent": self.name, "received": input_data}


class FailingMockAgent(BaseAgent):
    """Small test double that raises to exercise failure logging."""

    def _run(self, input_data: Any) -> dict[str, Any]:
        """Raise a controlled failure for the provided input."""
        raise RuntimeError("mock failure")


class BaseAgentTests(unittest.TestCase):
    """Tests for shared agent execution and logging behavior."""

    def test_mock_agent_run_returns_output_and_logs_events(self) -> None:
        """A concrete mock agent should run once and emit start/completion logs."""
        events: list[AgentLogEvent] = []
        agent = MockAgent(
            name="Mock Agent",
            description="Echoes structured input for tests.",
            prompt_path="prompts/mock_agent.md",
            log_hook=events.append,
        )
        input_data = {"topic": "AI education"}

        output = agent.run(input_data)

        self.assertEqual(
            output,
            {"agent": "Mock Agent", "received": input_data},
        )
        self.assertEqual([event.event_type for event in events], ["started", "completed"])
        self.assertEqual(events[0].agent_name, "Mock Agent")
        self.assertEqual(events[0].input_snapshot, input_data)
        self.assertEqual(events[1].output_snapshot, output)

    def test_failed_run_logs_failure_and_reraises(self) -> None:
        """Agent failures should be logged before the original error is raised."""
        events: list[AgentLogEvent] = []
        agent = FailingMockAgent(
            name="Failing Agent",
            description="Raises a controlled test error.",
            prompt_path="prompts/failing_agent.md",
            log_hook=events.append,
        )

        with self.assertRaisesRegex(RuntimeError, "mock failure"):
            agent.run({"topic": "AI education"})

        self.assertEqual([event.event_type for event in events], ["started", "failed"])
        self.assertEqual(events[-1].error_message, "mock failure")

    def test_agent_metadata_cannot_be_blank(self) -> None:
        """BaseAgent rejects blank names and descriptions used by logs."""
        with self.assertRaisesRegex(ValueError, "Agent name cannot be empty"):
            MockAgent(name=" ", description="Valid description", prompt_path="prompt.md")

        with self.assertRaisesRegex(ValueError, "Agent description cannot be empty"):
            MockAgent(name="Valid name", description=" ", prompt_path="prompt.md")


if __name__ == "__main__":
    unittest.main()
