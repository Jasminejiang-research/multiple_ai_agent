"""Unit tests for the deterministic InputValidator node (Sprint 5.2)."""

import unittest

from workflow.nodes import (
    REQUIRED_BRIEF_FIELDS,
    input_validator_node,
    validate_user_brief,
)
from workflow.state import WorkflowState


def _complete_brief() -> dict[str, str]:
    """A fully-populated, valid user brief covering all required fields."""
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


class ValidateUserBriefTests(unittest.TestCase):
    """Tests for the pure ``validate_user_brief`` helper."""

    def test_complete_brief_passes(self) -> None:
        """A complete, sufficiently detailed brief yields no issues."""
        self.assertEqual(validate_user_brief(_complete_brief()), [])

    def test_missing_field_is_reported(self) -> None:
        """A missing required field produces a 'Missing required field' issue."""
        brief = _complete_brief()
        del brief["problem"]

        issues = validate_user_brief(brief)

        self.assertIn("Missing required field: problem", issues)

    def test_empty_and_whitespace_fields_are_reported(self) -> None:
        """Empty or whitespace-only values count as missing."""
        brief = _complete_brief()
        brief["industry"] = ""
        brief["geography"] = "   "

        issues = validate_user_brief(brief)

        self.assertIn("Missing required field: industry", issues)
        self.assertIn("Missing required field: geography", issues)

    def test_too_short_field_is_reported(self) -> None:
        """A present but too-short value produces a length issue, not a missing one."""
        brief = _complete_brief()
        brief["problem"] = "slow"

        issues = validate_user_brief(brief)

        self.assertIn(
            "Field 'problem' is too short (minimum 10 characters)", issues
        )

    def test_empty_brief_reports_all_required_fields(self) -> None:
        """An empty brief flags every required field as missing."""
        issues = validate_user_brief({})

        for field in REQUIRED_BRIEF_FIELDS:
            self.assertIn(f"Missing required field: {field}", issues)


class InputValidatorNodeTests(unittest.TestCase):
    """Tests for the ``input_validator_node`` state transformation."""

    def test_complete_input_passes(self) -> None:
        """Complete input leaves ``missing_info`` empty and sets the step."""
        state: WorkflowState = {"user_brief": _complete_brief()}

        result = input_validator_node(state)

        self.assertEqual(result["missing_info"], [])
        self.assertEqual(result["current_step"], "input_validator")

    def test_missing_field_returns_missing_info(self) -> None:
        """Incomplete input populates ``missing_info`` with the issue list."""
        brief = _complete_brief()
        del brief["solution"]
        state: WorkflowState = {"user_brief": brief}

        result = input_validator_node(state)

        self.assertIn("Missing required field: solution", result["missing_info"])

    def test_node_does_not_mutate_input_state(self) -> None:
        """The node returns a partial update and does not alter the input brief."""
        brief = _complete_brief()
        state: WorkflowState = {"user_brief": brief}

        input_validator_node(state)

        self.assertEqual(state["user_brief"], brief)


if __name__ == "__main__":
    unittest.main()
