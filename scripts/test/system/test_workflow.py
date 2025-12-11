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
                "resident_profile": {"basic": {"age": 30}},
                "service_needs": {"explicit_needs": {"desired_services": ["medical"]}}
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
                "message_text": "Hello, here is info."
            }
        ]

        manager = WorkflowManager(mock_ai_client)

        context = StateManager.init_conversation_context(
            user_message="help",
            dialog_history=[],
            resident_profile={},
            service_needs={}
        )

        final_state = manager.invoke(context)

        self.assertEqual(final_state["resident_profile"]["basic"]["age"], 30)
        self.assertEqual(len(final_state["hypotheses"]), 1)
        self.assertTrue(final_state["hypotheses"][0]["should_call_rag"])
        self.assertIn("retrieval_evidence", final_state)
        # RAGManager is not mocked in WorkflowManager (it's instantiated directly),
        # so it should run the mock implementation and return results.
        self.assertTrue(len(final_state["retrieval_evidence"].get("service_candidates", [])) > 0)
        self.assertEqual(final_state["bot_message"], "Hello, here is info.")

if __name__ == '__main__':
    unittest.main()
