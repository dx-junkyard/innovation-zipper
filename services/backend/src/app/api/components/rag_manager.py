import os
from typing import Dict, Any, List
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
from app.api.db import DBClient
from app.api.ai_client import AIClient

class RAGManager:
    """
    RAG（検索拡張生成）管理コンポーネント。
    """
    def __init__(self, ai_client: AIClient):
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = "knowledge_base" # Updated collection name
        self.qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        self.db_client = DBClient()
        self.ai_client = ai_client

    def retrieve_knowledge(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        仮説に基づいて知識を検索する。
        """
        hypotheses = context.get("hypotheses", [])
        retrieval_evidence = {"results": []}
        user_id = context.get("user_id", "") # Expect user_id in context

        # Extract current category from interest profile
        interest_profile = context.get("interest_profile", {})
        current_category = interest_profile.get("current_category")

        for hypothesis in hypotheses:
            if isinstance(hypothesis, dict) and hypothesis.get("should_call_rag"):
                results = self._search_knowledge(hypothesis, user_id, category=current_category)
                retrieval_evidence["results"].extend(results)

        context["retrieval_evidence"] = retrieval_evidence
        return context

    def _get_embedding(self, text: str) -> List[float]:
        text = text.replace("\n", " ")
        return self.ai_client.get_embedding(text)

    def _search_knowledge(self, hypothesis: Dict[str, Any], user_id: str, category: str = None) -> List[Dict[str, Any]]:
        """
        仮説に基づいて知識を検索する（権限フィルタ + カテゴリフィルタ付き）。
        """
        query_text = hypothesis.get("search_query") or hypothesis.get("statement")

        if not query_text:
            return []

        try:
            query_vector = self._get_embedding(query_text)

            # Base Visibility Filter: Public OR (Private AND current_user)
            visibility_filter = Filter(
                should=[
                    FieldCondition(key="visibility", match=MatchValue(value="public")),
                    Filter(
                        must=[
                            FieldCondition(key="visibility", match=MatchValue(value="private")),
                            FieldCondition(key="user_id", match=MatchValue(value=user_id))
                        ]
                    )
                ]
            )

            # Apply Category Filter if present
            if category:
                search_filter = Filter(
                    must=[
                        visibility_filter,
                        FieldCondition(key="category", match=MatchValue(value=category))
                    ]
                )
            else:
                search_filter = visibility_filter

            search_result = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=5
            )

            results = []
            for hit in search_result.points:
                payload = hit.payload
                source_type = "public_fact" if payload.get("visibility") == "public" else "private_memory"
                meta = payload.get("meta") or {}

                # Ensure title and file_id are explicitly available in results structure for easy access
                title = meta.get("title")
                file_id = meta.get("file_id")

                results.append({
                    "hypothesis_id": hypothesis.get("id"),
                    "source_type": source_type,
                    "type": payload.get("type"),
                    "content": payload.get("content"),
                    "meta": meta,
                    "title": title,
                    "file_id": file_id,
                    "score": hit.score
                })
            return results

        except Exception as e:
            print(f"[✗] RAG Search Error: {e}")
            return []
