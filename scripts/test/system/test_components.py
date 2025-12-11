import unittest
from unittest.mock import MagicMock, patch
from app.api.components.situation_analyzer import SituationAnalyzer
from app.api.components.hypothesis_generator import HypothesisGenerator
from app.api.components.rag_manager import RAGManager
from app.api.components.response_planner import ResponsePlanner
from app.api.state_manager import StateManager

class TestComponents(unittest.TestCase):
    def setUp(self):
        self.mock_ai_client = MagicMock()
        self.context = StateManager.init_conversation_context(
            user_message="子供の医療費について知りたい",
            dialog_history=[],
            resident_profile={},
            service_needs={}
        )

    def test_situation_analyzer(self):
        analyzer = SituationAnalyzer(self.mock_ai_client)

        # Mock LLM response
        self.mock_ai_client.generate_response.return_value = {
            "resident_profile": {"basic": {"age": 30}},
            "service_needs": {"explicit_needs": {"desired_services": ["medical_subsidy"]}}
        }

        updated_context = analyzer.analyze(self.context)

        self.assertEqual(updated_context["resident_profile"]["basic"]["age"], 30)
        self.assertIn("medical_subsidy", updated_context["service_needs"]["explicit_needs"]["desired_services"])

    def test_hypothesis_generator(self):
        generator = HypothesisGenerator(self.mock_ai_client)

        # Mock LLM response
        self.mock_ai_client.generate_response.return_value = {
            "hypotheses": [
                {"id": "H1", "need_label": "Medical", "should_call_rag": True}
            ]
        }

        updated_context = generator.generate(self.context)

        self.assertEqual(len(updated_context["hypotheses"]), 1)
        self.assertEqual(updated_context["hypotheses"][0]["id"], "H1")

    def test_rag_manager(self):
        manager = RAGManager()
        self.context["hypotheses"] = [
            {"id": "H1", "need_label": "Medical", "likely_services": ["Child Medical Subsidy"], "should_call_rag": True}
        ]

        updated_context = manager.retrieve_knowledge(self.context)

        candidates = updated_context["retrieval_evidence"]["service_candidates"]
        self.assertTrue(len(candidates) > 0)
        self.assertEqual(candidates[0]["name"], "Child Medical Subsidy")

    def test_response_planner(self):
        planner = ResponsePlanner(self.mock_ai_client)

        # Mock LLM response
        self.mock_ai_client.generate_response.return_value = {
            "response_plan": {"main_hypothesis_id": "H1"},
            "message_text": "Here is the info."
        }

        updated_context, message = planner.plan_response(self.context)

        self.assertEqual(updated_context["response_plan"]["main_hypothesis_id"], "H1")
        self.assertEqual(message, "Here is the info.")

if __name__ == '__main__':
    unittest.main()
