"""Minimal import tests for the Phase 2 LangGraph workflow foundation."""

import unittest

from workflow.state import ProposalState, WorkflowState


class WorkflowImportTests(unittest.TestCase):
    """Import checks for the flat MVP workflow package."""

    def test_workflow_state_imports(self) -> None:
        """WorkflowState should be available with the ProposalState alias."""
        self.assertIs(WorkflowState, ProposalState)


if __name__ == "__main__":
    unittest.main()

