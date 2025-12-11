import unittest
import json
from unittest.mock import MagicMock
from app.api.components.situation_analyzer import SituationAnalyzer
from app.api.state_manager import StateManager

class TestSerialization(unittest.TestCase):
    def test_analyze_with_string_timestamp(self):
        mock_ai_client = MagicMock()
        mock_ai_client.generate_response.return_value = {}

        analyzer = SituationAnalyzer(mock_ai_client)

        # Simulate history with string timestamp (as returned by fixed DBClient)
        history = [
            {
                "role": "user",
                "message": "hello",
                "created_at": "2023-10-27T10:00:00"
            }
        ]

        context = StateManager.init_conversation_context(
            user_message="hello",
            dialog_history=history,
            resident_profile={},
            service_needs={}
        )

        try:
            analyzer.analyze(context)
        except TypeError as e:
            self.fail(f"SituationAnalyzer raised TypeError: {e}")

if __name__ == '__main__':
    unittest.main()
