import os
import logging
from typing import Dict, Any, List, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
from app.api.db import DBClient
from app.api.ai_client import AIClient
from config import (
    EmbeddingConfig,
    TASK_RAG_SEARCH_EMBEDDING,
    generate_collection_name,
    get_active_embedding_config,
)

logger = logging.getLogger(__name__)


class RAGManager:
    """
    RAG（検索拡張生成）管理コンポーネント。

    Supports hybrid model configuration for embeddings, automatically routing
    to the correct collection based on the embedding model being used.
    """

    BASE_COLLECTION_NAME = "knowledge_base"

    def __init__(
        self,
        ai_client: AIClient,
        embedding_config: Optional[EmbeddingConfig] = None
    ):
        """
        Initialize RAGManager with AI client and optional embedding config.

        Args:
            ai_client: AIClient instance for embeddings
            embedding_config: Embedding configuration (default: TASK_RAG_SEARCH_EMBEDDING)
        """
        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        self.db_client = DBClient()
        self.ai_client = ai_client

        # Set embedding configuration
        self._embedding_config = embedding_config or TASK_RAG_SEARCH_EMBEDDING
        self._collection_name = self._generate_collection_name(self._embedding_config)

        logger.info(
            f"RAGManager initialized with collection: {self._collection_name}, "
            f"provider: {self._embedding_config.provider}"
        )

    @property
    def collection_name(self) -> str:
        """Get current collection name."""
        return self._collection_name

    @property
    def embedding_config(self) -> EmbeddingConfig:
        """Get current embedding configuration."""
        return self._embedding_config

    def _generate_collection_name(self, embedding_config: EmbeddingConfig) -> str:
        """Generate collection name based on embedding configuration."""
        return generate_collection_name(self.BASE_COLLECTION_NAME, embedding_config)

    def switch_embedding_config(self, embedding_config: EmbeddingConfig) -> None:
        """
        Switch to a different embedding configuration.

        Args:
            embedding_config: New embedding configuration to use
        """
        self._embedding_config = embedding_config
        self._collection_name = self._generate_collection_name(embedding_config)
        logger.info(f"RAGManager switched to collection: {self._collection_name}")

    def retrieve_knowledge(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        仮説に基づいて知識を検索する。
        """
        hypotheses = context.get("hypotheses", [])
        retrieval_evidence = {"results": []}
        user_id = context.get("user_id", "")

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
        """Get embedding using configured provider and model."""
        text = text.replace("\n", " ")
        return self.ai_client.get_embedding(text, embedding_config=self._embedding_config)

    def _search_knowledge(
        self,
        hypothesis: Dict[str, Any],
        user_id: str,
        category: str = None
    ) -> List[Dict[str, Any]]:
        """
        仮説に基づいて知識を検索する（権限フィルタ + カテゴリフィルタ付き）。
        """
        query_text = hypothesis.get("search_query") or hypothesis.get("statement")

        if not query_text:
            return []

        # Check if collection exists
        if not self.qdrant_client.collection_exists(self._collection_name):
            logger.warning(f"Collection {self._collection_name} does not exist")
            return []

        try:
            query_vector = self._get_embedding(query_text)

            if not query_vector:
                logger.warning("Failed to generate query embedding")
                return []

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
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=5
            )

            results = []
            for hit in search_result.points:
                payload = hit.payload
                source_type = "public_fact" if payload.get("visibility") == "public" else "private_memory"
                meta = payload.get("meta") or {}

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
            logger.error(f"[✗] RAG Search Error: {e}")
            return []

    def search_by_text(
        self,
        query_text: str,
        user_id: str = "",
        category: str = None,
        limit: int = 5,
        score_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Perform direct text search in the knowledge base.

        Args:
            query_text: Text to search for
            user_id: User ID for visibility filtering
            category: Optional category filter
            limit: Maximum number of results
            score_threshold: Minimum score threshold

        Returns:
            List of search results
        """
        if not query_text:
            return []

        if not self.qdrant_client.collection_exists(self._collection_name):
            logger.warning(f"Collection {self._collection_name} does not exist")
            return []

        try:
            query_vector = self._get_embedding(query_text)

            if not query_vector:
                logger.warning("Failed to generate query embedding")
                return []

            # Build visibility filter
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
            ) if user_id else Filter(
                must=[
                    FieldCondition(key="visibility", match=MatchValue(value="public"))
                ]
            )

            # Apply category filter if specified
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
                collection_name=self._collection_name,
                query=query_vector,
                query_filter=search_filter,
                limit=limit,
                score_threshold=score_threshold
            )

            results = []
            for hit in search_result.points:
                payload = hit.payload
                meta = payload.get("meta") or {}

                results.append({
                    "id": str(hit.id),
                    "content": payload.get("content"),
                    "type": payload.get("type"),
                    "visibility": payload.get("visibility"),
                    "meta": meta,
                    "title": meta.get("title"),
                    "score": hit.score
                })

            return results

        except Exception as e:
            logger.error(f"[✗] RAG text search error: {e}")
            return []

    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics for the current collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            if not self.qdrant_client.collection_exists(self._collection_name):
                return {
                    "exists": False,
                    "collection_name": self._collection_name,
                    "embedding_config": self._embedding_config.to_dict()
                }

            info = self.qdrant_client.get_collection(self._collection_name)

            return {
                "exists": True,
                "collection_name": self._collection_name,
                "vectors_count": info.vectors_count,
                "points_count": info.points_count,
                "status": info.status.value,
                "embedding_config": self._embedding_config.to_dict()
            }

        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {
                "exists": False,
                "error": str(e),
                "collection_name": self._collection_name
            }
