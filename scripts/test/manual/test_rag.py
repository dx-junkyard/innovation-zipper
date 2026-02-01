import os
import sys
import json

# Add the project root to the python path
sys.path.append(os.path.join(os.path.dirname(__file__), "../../.."))

from app.api.components.rag_manager import RAGManager
from app.api.ai_client import AIClient
from dotenv import load_dotenv

load_dotenv()

# Mock context
context = {
    "hypotheses": [
        {
            "id": "h1",
            "hypothesis": "ユーザーは子育て支援サービスを探している可能性があります。",
            "reasoning": "子育て ショートステイ",
            "should_call_rag": True
        }
    ]
}

def load_mock_embedding():
    embedding_file = os.path.join(os.path.dirname(__file__), "../../../static/data/kosodate_and_kyoiku_service_catalog_embedding_openai.mini.json")
    with open(embedding_file, 'r') as f:
        data = json.load(f)
        return data["embeddings"][0]

def test_rag():
    print("Testing RAG...")

    # Mock _get_embedding to avoid OpenAI call if key is missing
    original_get_embedding = RAGManager._get_embedding

    # Mock OpenAI to avoid init error
    import sys
    from unittest.mock import MagicMock
    sys.modules["openai"] = MagicMock()

    try:
        mock_embedding = load_mock_embedding()
        RAGManager._get_embedding = lambda self, text: mock_embedding
        print("[!] Mocked _get_embedding with a pre-computed vector.")
    except Exception as e:
        print(f"[!] Could not load mock embedding: {e}")

    try:
        # Initialize AIClient and RAGManager
        ai_client = AIClient()
        rag_manager = RAGManager(ai_client)
        result = rag_manager.retrieve_knowledge(context)

        evidence = result.get("retrieval_evidence", {}).get("results", [])
        print(f"Found {len(evidence)} results.")

        for item in evidence:
            title = item.get('title') or item.get('meta', {}).get('title', 'Unknown')
            print(f"- {title} (Score: {item.get('score')})")
            content = item.get('content', '')
            if content:
                print(f"  Content: {content[:50]}...")

    except Exception as e:
        print(f"[✗] Test failed: {e}")
    finally:
        RAGManager._get_embedding = original_get_embedding

if __name__ == "__main__":
    test_rag()
