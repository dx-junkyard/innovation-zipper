import unittest
from unittest.mock import MagicMock
from app.api.workflow import WorkflowManager
from app.api.state_manager import StateManager

class TestWorkflow(unittest.TestCase):
    def test_workflow_execution(self):
        mock_ai_client = MagicMock()
        # Mock responses for each step
        mock_ai_client.generate_response.side_effect = [
            # SituationAnalyzer
            {
                "interest_profile": {"topics": ["AI"]},
                "active_hypotheses": {"list": []}
            },
            # HypothesisGenerator
            {
                "hypotheses": [
                    {"id": "H1", "need_label": "Medical", "likely_services": ["Medical Checkup"], "should_call_rag": True}
                ]
            },
            # ResponsePlanner
            {
                "response_plan": {"main_hypothesis_id": "H1"},
                "bot_message": "Hello, here is info."
            }
        ]

        manager = WorkflowManager(mock_ai_client)

        context = StateManager.init_conversation_context(
            user_message="help",
            dialog_history=[],
            interest_profile={},
            active_hypotheses={}
        )

        # Force mode to research to skip intent router and discovery default
        context["mode"] = "research"

        final_state = manager.invoke(context)

        # Verify changes based on logic.
        # Note: SituationAnalyzer mock response sets interest_profile
        self.assertEqual(final_state["interest_profile"]["topics"], ["AI"])
        self.assertEqual(len(final_state["hypotheses"]), 1)
        self.assertTrue(final_state["hypotheses"][0]["should_call_rag"])
        self.assertIn("retrieval_evidence", final_state)
        # RAGManager is not mocked in WorkflowManager (it's instantiated directly),
        # so it should run the mock implementation and return results.
        # However, RAGManager might depend on Qdrant which might fail if not mocked or available.
        # But let's see if it passes up to here.

if __name__ == '__main__':
    unittest.main()
