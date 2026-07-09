"""Unit tests for the Supervisor Agent (Sprint 7.2)."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from agents.base import AgentLogEvent
from agents.supervisor import SupervisorAgent, build_supervisor_prompt
from schemas.agent_outputs import SupervisorPlan


def _complete_brief() -> dict[str, str]:
    """A complete validated brief suitable for Supervisor tests."""
    return {
        "company_or_product_name": "AI Tutor for MBA Students",
        "industry": "EdTech / AI Education",
        "target_customer": "MBA students and business school applicants",
        "problem": "Students lack personalized business case coaching.",
        "solution": "An AI-driven proposal and case coaching platform.",
        "business_model": "Subscription plus institutional licensing",
        "geography": "US / North America",
        "proposal_goal": "investor",
    }


def _supervisor_plan_json() -> str:
    """Return a valid SupervisorPlan JSON payload for fake LLM responses."""
    plan = SupervisorPlan(
        plan_summary="Route analysis, writing, and critique through controlled agents.",
        tasks=[
            {
                "task_id": "research_scan",
                "agent_role": "research",
                "objective": "Identify market, customer, and competitor questions to analyze.",
                "input_requirements": ["Use only the validated user brief."],
                "expected_output": "ResearchAnalysis with unsupported claims clearly marked.",
                "depends_on": [],
            },
            {
                "task_id": "strategy_plan",
                "agent_role": "strategy",
                "objective": "Convert brief-supported insights into positioning and GTM logic.",
                "input_requirements": ["Use the user brief and research output."],
                "expected_output": "StrategyAnalysis with value proposition and GTM notes.",
                "depends_on": ["research_scan"],
            },
            {
                "task_id": "finance_assumptions",
                "agent_role": "finance",
                "objective": "Frame finance assumptions without presenting them as forecasts.",
                "input_requirements": ["Use the user brief and strategy output."],
                "expected_output": "FinanceAssumptions with clearly labeled assumptions.",
                "depends_on": ["strategy_plan"],
            },
            {
                "task_id": "proposal_writer",
                "agent_role": "writer",
                "objective": "Assemble a structured proposal from prior agent outputs only.",
                "input_requirements": [
                    "Use research, strategy, and finance outputs as source material."
                ],
                "expected_output": "ProposalDraft with low-confidence items marked.",
                "depends_on": ["research_scan", "strategy_plan", "finance_assumptions"],
            },
            {
                "task_id": "proposal_critic",
                "agent_role": "critic",
                "objective": "Review the draft for unsupported claims and logic gaps.",
                "input_requirements": ["Use the writer output and available evidence map."],
                "expected_output": "CritiqueReport with concrete issues and suggested fixes.",
                "depends_on": ["proposal_writer"],
            },
        ],
        selected_agents=["research", "strategy", "finance", "writer", "critic"],
        skipped_agents=[],
        needs_human_review=["Confirm whether investor is the intended reader."],
    )
    return plan.model_dump_json()


class FakeSupervisorLLM:
    """Mock Supervisor LLM that records the prompt and returns fixed JSON."""

    def __init__(self, response: str) -> None:
        """Store a canned response for the fake LLM."""
        self.response = response
        self.prompts: list[str] = []

    def generate_json(self, prompt: str) -> str:
        """Record the prompt and return the canned response."""
        self.prompts.append(prompt)
        return self.response


class SupervisorAgentTests(unittest.TestCase):
    """Tests for Supervisor prompt construction and validated routing output."""

    def test_build_supervisor_prompt_includes_brief_and_allowed_agents(self) -> None:
        """The Supervisor prompt contains user input and allowed agent roles."""
        prompt = build_supervisor_prompt(_complete_brief())

        self.assertIn("AI Tutor for MBA Students", prompt)
        self.assertIn("research", prompt)
        self.assertIn("strategy", prompt)
        self.assertIn("finance", prompt)
        self.assertIn("writer", prompt)
        self.assertIn("critic", prompt)

    def test_supervisor_agent_calls_mock_llm_and_returns_plan(self) -> None:
        """The Supervisor parses fake LLM JSON into a validated plan."""
        events: list[AgentLogEvent] = []
        llm = FakeSupervisorLLM(_supervisor_plan_json())
        agent = SupervisorAgent(llm_client=llm, log_hook=events.append)

        plan = agent.run(_complete_brief())

        self.assertIsInstance(plan, SupervisorPlan)
        self.assertEqual(len(llm.prompts), 1)
        self.assertEqual(plan.selected_agents, ["research", "strategy", "finance", "writer", "critic"])
        self.assertEqual(plan.tasks[-1].agent_role, "critic")
        self.assertEqual([event.event_type for event in events], ["started", "completed"])

    def test_supervisor_plan_rejects_research_conclusion_fields(self) -> None:
        """Supervisor output should not carry direct analysis conclusions."""
        with self.assertRaises(ValidationError):
            SupervisorPlan.model_validate(
                {
                    "plan_summary": "Route proposal work through controlled workers.",
                    "tasks": [
                        {
                            "task_id": "research_scan",
                            "agent_role": "research",
                            "objective": "Identify research questions for later analysis.",
                            "input_requirements": ["Use only the validated user brief."],
                            "expected_output": "ResearchAnalysis with unsupported claims marked.",
                            "depends_on": [],
                        }
                    ],
                    "selected_agents": ["research"],
                    "skipped_agents": [],
                    "needs_human_review": [],
                    "research_conclusions": "The market is large and growing.",
                }
            )


if __name__ == "__main__":
    unittest.main()
