import unittest
from unittest.mock import patch, MagicMock
import os
import sys
from pathlib import Path

# Add app to path
sys.path.append(str(Path(__file__).resolve().parents[3]))

from app.api.ai_client import AIClient

class TestAIClientSwitch(unittest.TestCase):

    @patch.dict(os.environ, {}, clear=True)
    def test_init_without_openai_key(self):
        """Test initialization when OPENAI_API_KEY is NOT set."""
        client = AIClient()
        self.assertIsNone(client.openai_client)
        print("Verified: AIClient uses Local LLM when OPENAI_API_KEY is missing.")

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_init_with_openai_key(self):
        """Test initialization when OPENAI_API_KEY IS set."""
        client = AIClient()
        self.assertIsNotNone(client.openai_client)
        print("Verified: AIClient uses OpenAI API when OPENAI_API_KEY is present.")

    @patch("app.api.ai_client.requests.post")
    @patch.dict(os.environ, {}, clear=True)
    def test_analyze_interaction_local(self, mock_post):
        """Test analyze_interaction uses requests.post (Local LLM) when key is missing."""
        client = AIClient()

        # Mock response
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": '{"test": "local"}'}
        mock_post.return_value = mock_response

        client.analyze_interaction([], {}, "hello")

        mock_post.assert_called_once()
        print("Verified: analyze_interaction calls Local LLM endpoint.")

    @patch("app.api.ai_client.OpenAI")
    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_analyze_interaction_openai(self, MockOpenAI):
        """Test analyze_interaction uses openai_client when key is present."""
        # Setup mock client
        mock_client_instance = MagicMock()
        MockOpenAI.return_value = mock_client_instance

        mock_completion = MagicMock()
        mock_completion.choices[0].message.content = '{"test": "openai"}'
        mock_client_instance.chat.completions.create.return_value = mock_completion

        client = AIClient()
        client.analyze_interaction([], {}, "hello")

        mock_client_instance.chat.completions.create.assert_called_once()
        print("Verified: analyze_interaction calls OpenAI API.")

if __name__ == "__main__":
    unittest.main()
