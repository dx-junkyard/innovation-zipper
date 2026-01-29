import os
import json
import hashlib
import uuid
import logging
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, ScoredPoint, Filter, FieldCondition, MatchValue

from app.api.db import DBClient
from app.api.ai_client import AIClient
from app.api.components.graph_manager import GraphManager
from config import (
    EMBEDDING_DIMENSION,
    EmbeddingConfig,
    TASK_WIKI_EMBEDDING,
    TASK_USER_DOCUMENT_EMBEDDING,
    TASK_RAG_SEARCH_EMBEDDING,
    get_active_embedding_config,
    generate_collection_name,
)

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """
    Manages the knowledge base (Second Brain) including User Context (L1),
    AI Insights (L2), and Shared Knowledge (L3).
    Handles import, embedding generation, and persistence to Qdrant.

    Supports dynamic collection management based on embedding model configuration
    to prevent vector dimension mismatch issues.
    """

    # Base collection name prefix
    BASE_COLLECTION_NAME = "knowledge_base"

    def __init__(self, embedding_config: Optional[EmbeddingConfig] = None):
        """
        Initialize KnowledgeManager with optional embedding configuration.

        Args:
            embedding_config: Embedding configuration to use. If None, uses default
                            (TASK_RAG_SEARCH_EMBEDDING).
        """
        self.db_client = DBClient()
        self.ai_client = AIClient()
        self.graph_manager = GraphManager()

        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)

        # Set embedding configuration
        self._embedding_config = embedding_config or get_active_embedding_config()
        self._collection_name = self._generate_collection_name(self._embedding_config)
        self._vector_size = self._embedding_config.dimension

        logger.info(
            f"KnowledgeManager initialized with collection: {self._collection_name}, "
            f"dimension: {self._vector_size}, provider: {self._embedding_config.provider}"
        )

    @property
    def collection_name(self) -> str:
        """Get the current collection name."""
        return self._collection_name

    @property
    def vector_size(self) -> int:
        """Get the current vector size."""
        return self._vector_size

    @property
    def embedding_config(self) -> EmbeddingConfig:
        """Get the current embedding configuration."""
        return self._embedding_config

    def _generate_collection_name(self, embedding_config: EmbeddingConfig) -> str:
        """Generate collection name based on embedding configuration."""
        return generate_collection_name(self.BASE_COLLECTION_NAME, embedding_config)

    def get_collection_for_config(self, embedding_config: EmbeddingConfig) -> str:
        """
        Get collection name for a specific embedding configuration.

        Args:
            embedding_config: Embedding configuration

        Returns:
            Collection name string
        """
        return self._generate_collection_name(embedding_config)

    def switch_embedding_config(self, embedding_config: EmbeddingConfig) -> None:
        """
        Switch to a different embedding configuration.
        This changes the target collection for subsequent operations.

        Args:
            embedding_config: New embedding configuration to use
        """
        self._embedding_config = embedding_config
        self._collection_name = self._generate_collection_name(embedding_config)
        self._vector_size = embedding_config.dimension
        logger.info(
            f"Switched to collection: {self._collection_name}, "
            f"dimension: {self._vector_size}"
        )

    def list_available_collections(self) -> List[Dict[str, Any]]:
        """
        List all knowledge base collections with their metadata.

        Returns:
            List of collection info dictionaries
        """
        try:
            collections = self.qdrant_client.get_collections()
            kb_collections = []

            for collection in collections.collections:
                if collection.name.startswith(self.BASE_COLLECTION_NAME):
                    info = self.qdrant_client.get_collection(collection.name)
                    kb_collections.append({
                        "name": collection.name,
                        "vectors_count": info.vectors_count,
                        "points_count": info.points_count,
                        "status": info.status.value,
                    })

            return kb_collections
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def is_duplicate_content(self, content: str, threshold: float = 0.98) -> bool:
        """
        Check if similar content already exists in the knowledge base using vector similarity.
        """
        if not content.strip():
            return False

        vector = self.ai_client.get_embedding(content, embedding_config=self._embedding_config)
        if not vector:
            return False

        try:
            if not self.qdrant_client.collection_exists(self._collection_name):
                return False

            results = self.qdrant_client.query_points(
                collection_name=self._collection_name,
                query=vector,
                limit=1
            )

            if results.points and results.points[0].score >= threshold:
                return True

        except Exception as e:
            logger.error(f"[!] Qdrant duplicate check failed: {e}")
            return False

        return False

    def _setup_qdrant_collection(self, collection_name: Optional[str] = None, vector_size: Optional[int] = None):
        """
        Create Qdrant collection if it doesn't exist.

        Args:
            collection_name: Collection name to create (default: self._collection_name)
            vector_size: Vector dimension (default: self._vector_size)
        """
        target_collection = collection_name or self._collection_name
        target_size = vector_size or self._vector_size

        if not self.qdrant_client.collection_exists(target_collection):
            try:
                self.qdrant_client.create_collection(
                    collection_name=target_collection,
                    vectors_config=VectorParams(size=target_size, distance=Distance.COSINE),
                )
                logger.info(f"Created collection: {target_collection} with dimension {target_size}")
            except Exception as e:
                if "already exists" in str(e) or "Conflict" in str(e):
                    pass
                else:
                    logger.error(f"[!] Failed to create collection: {e}")
                    raise e

    def add_user_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "user_hypothesis",
        category: str = None,
        meta: Dict[str, Any] = None,
        embedding_config: Optional[EmbeddingConfig] = None
    ) -> bool:
        """
        L1/L2: Save private user memory or AI insight.

        Args:
            user_id: User identifier
            content: Content to save
            memory_type: Type of memory (user_hypothesis, document_chunk, etc.)
            category: Optional category
            meta: Additional metadata
            embedding_config: Optional embedding config (default: TASK_USER_DOCUMENT_EMBEDDING)
        """
        config = embedding_config or TASK_USER_DOCUMENT_EMBEDDING
        collection = self._generate_collection_name(config)

        self._setup_qdrant_collection(collection, config.dimension)

        entry_id = str(uuid.uuid4())
        vector = self.ai_client.get_embedding(content, embedding_config=config)

        if not vector:
            logger.error(f"[!] Failed to generate embedding for memory: {content[:30]}...")
            return False

        payload = {
            "user_id": user_id,
            "category": category,
            "type": memory_type,
            "visibility": "private",
            "content": content,
            "meta": meta or {}
        }

        try:
            self.qdrant_client.upsert(
                collection_name=collection,
                wait=True,
                points=[PointStruct(
                    id=entry_id,
                    vector=vector,
                    payload=payload
                )]
            )

            # Sync to Knowledge Graph if applicable
            if category and category != "General":
                source_type = self.graph_manager.SOURCE_AI_INFERRED
                if memory_type == "user_stated":
                    source_type = self.graph_manager.SOURCE_USER_STATED

                self.graph_manager.add_user_interest(
                    user_id=user_id,
                    concept_name=category,
                    confidence=0.8,
                    source_type=source_type
                )

                if memory_type == "user_hypothesis":
                    self.graph_manager.add_hypothesis(text=content, evidence_ids=[entry_id], properties=meta)
                    self.graph_manager.link_hypothesis_to_concept(content, category)

                elif memory_type == "document_chunk":
                    self.graph_manager.add_chunk(text=content, evidence_ids=[entry_id], properties=meta)

                    file_title = meta.get("title") if meta else None
                    if file_title:
                        self.graph_manager.link_chunk_to_document(
                            chunk_text=content,
                            file_node_text=file_title,
                            rel_type="PART_OF"
                        )

            return True
        except Exception as e:
            logger.error(f"[✗] Qdrant/Neo4j upsert failed: {e}")
            return False

    def add_shared_fact(
        self,
        content: str,
        source: str = "system",
        meta: Dict[str, Any] = None,
        embedding_config: Optional[EmbeddingConfig] = None
    ) -> bool:
        """
        L3: Save shared public fact.
        """
        config = embedding_config or self._embedding_config
        collection = self._generate_collection_name(config)

        self._setup_qdrant_collection(collection, config.dimension)

        md5_hash = hashlib.md5(content.encode()).hexdigest()
        entry_id = str(uuid.UUID(hex=md5_hash))

        vector = self.ai_client.get_embedding(content, embedding_config=config)

        if not vector:
            return False

        payload = {
            "user_id": "system",
            "type": "shared_fact",
            "visibility": "public",
            "content": content,
            "meta": meta or {"source": source}
        }

        try:
            self.qdrant_client.upsert(
                collection_name=collection,
                wait=True,
                points=[PointStruct(
                    id=entry_id,
                    vector=vector,
                    payload=payload
                )]
            )
            return True
        except Exception as e:
            logger.error(f"[✗] Qdrant upsert failed: {e}")
            return False

    def import_raw_public_knowledge(
        self,
        source: str,
        items: List[Dict],
        embedding_config: Optional[EmbeddingConfig] = None
    ) -> Dict:
        """
        Import raw public knowledge (e.g. Wikipedia) without embedding.
        Fast import with zero-vectors.

        Args:
            source: Source identifier (e.g., "wikipedia")
            items: List of items to import
            embedding_config: Embedding config for the target collection
                            (default: TASK_WIKI_EMBEDDING for cost-effective processing)
        """
        config = embedding_config or TASK_WIKI_EMBEDDING
        collection = self._generate_collection_name(config)
        vector_size = config.dimension

        self._setup_qdrant_collection(collection, vector_size)
        points = []

        # Use a zero vector of the correct dimension
        dummy_vector = [0.0] * vector_size

        for item in items:
            content = item.get("content", "")
            title = item.get("title", "")

            # Generate ID
            raw_id = item.get("id")
            if raw_id:
                unique_str = f"{source}:{raw_id}"
                md5_hash = hashlib.md5(unique_str.encode()).hexdigest()
                item_id = str(uuid.UUID(hex=md5_hash))
            else:
                unique_str = f"{source}:{title}:{content[:100]}"
                md5_hash = hashlib.md5(unique_str.encode()).hexdigest()
                item_id = str(uuid.UUID(hex=md5_hash))

            # Construct payload with embedding config info for later processing
            payload = {
                "user_id": "system",
                "type": "public_knowledge",
                "visibility": "public",
                "content": content,
                "meta": {
                    "title": title,
                    "url": item.get("url"),
                    "is_embedded": False,
                    "is_classified": False,
                    "source": source,
                    "embedding_model": config.model,
                    "embedding_provider": config.provider,
                    **item.get("metadata", {})
                }
            }

            points.append(PointStruct(
                id=item_id,
                vector=dummy_vector,
                payload=payload
            ))

        if points:
            try:
                self.qdrant_client.upsert(
                    collection_name=collection,
                    wait=False,
                    points=points
                )
                logger.info(f"Imported {len(points)} items to collection: {collection}")
                return {"status": "success", "count": len(points), "collection": collection}
            except Exception as e:
                logger.error(f"[✗] Raw import failed: {e}")
                return {"status": "error", "message": str(e)}

        return {"status": "success", "count": 0, "collection": collection}

    def process_pending_embeddings(
        self,
        batch_size: int = 50,
        embedding_config: Optional[EmbeddingConfig] = None
    ) -> Dict:
        """
        Process pending embeddings for raw imported items.

        Args:
            batch_size: Number of items to process per batch
            embedding_config: Embedding config to use (default: TASK_WIKI_EMBEDDING)
        """
        config = embedding_config or TASK_WIKI_EMBEDDING
        collection = self._generate_collection_name(config)

        if not self.qdrant_client.collection_exists(collection):
            return {"status": "error", "message": f"Collection {collection} does not exist"}

        filter_condition = Filter(
            must=[
                FieldCondition(
                    key="meta.is_embedded",
                    match=MatchValue(value=False)
                )
            ]
        )

        try:
            scroll_result, _ = self.qdrant_client.scroll(
                collection_name=collection,
                scroll_filter=filter_condition,
                limit=batch_size,
                with_payload=True,
                with_vectors=False
            )

            processed_count = 0
            points_to_update = []

            for point in scroll_result:
                payload = point.payload
                meta = payload.get("meta", {})

                title = meta.get("title", "")
                content = payload.get("content", "")

                text_to_embed = f"{title}\n\n{content}"

                # Generate embedding using the specified config
                vector = self.ai_client.get_embedding(text_to_embed, embedding_config=config)

                if vector:
                    meta["is_embedded"] = True
                    payload["meta"] = meta

                    points_to_update.append(PointStruct(
                        id=point.id,
                        vector=vector,
                        payload=payload
                    ))
                    processed_count += 1

            if points_to_update:
                self.qdrant_client.upsert(
                    collection_name=collection,
                    wait=True,
                    points=points_to_update
                )

            return {"status": "success", "processed": processed_count, "collection": collection}

        except Exception as e:
            logger.error(f"[✗] Process pending embeddings failed: {e}")
            return {"status": "error", "message": str(e)}

    def import_catalog(self, catalog_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Import legacy service catalog data as Shared Knowledge (L3).
        """
        self.db_client.create_service_catalog_table()
        self._setup_qdrant_collection()

        success_count = 0
        error_count = 0
        points = []

        for entry in catalog_data:
            try:
                unique_str = entry.get("タイトル", "") + entry.get("URL", {}).get("items", "")
                md5_hash = hashlib.md5(unique_str.encode()).hexdigest()
                entry_id = str(uuid.UUID(hex=md5_hash))
                entry["id"] = entry_id

                self.db_client.insert_service_catalog_entry(entry)

                text_to_embed = f"{entry.get('タイトル', '')} {entry.get('サービス内容', '')} {entry.get('対象者', '')} {entry.get('条件・申し込み方法', '')}"
                vector = self.ai_client.get_embedding(text_to_embed, embedding_config=self._embedding_config)

                if vector:
                    payload = {
                        "user_id": "system",
                        "type": "service_catalog",
                        "visibility": "public",
                        "content": text_to_embed,
                        "meta": {
                            "title": entry.get("タイトル"),
                            "url": entry.get("URL", {}),
                            "service_labels": entry.get("サービスラベル", []),
                            "target_labels": entry.get("対象者ラベル", [])
                        }
                    }

                    points.append(PointStruct(
                        id=entry_id,
                        vector=vector,
                        payload=payload
                    ))
                    success_count += 1
                else:
                    error_count += 1

            except Exception as e:
                logger.error(f"[✗] Error processing entry {entry.get('タイトル')}: {e}")
                error_count += 1

        if points:
            try:
                self.qdrant_client.upsert(
                    collection_name=self._collection_name,
                    wait=True,
                    points=points
                )
            except Exception as e:
                return {"status": "partial_failure", "success": success_count, "error": error_count, "qdrant_error": str(e)}

        return {"status": "completed", "success": success_count, "error": error_count}

    def reset_knowledge_base(self, embedding_config: Optional[EmbeddingConfig] = None) -> Dict[str, Any]:
        """
        Reset the knowledge base for a specific embedding configuration.

        Args:
            embedding_config: Embedding config whose collection to reset.
                            If None, resets the current active collection.
        """
        config = embedding_config or self._embedding_config
        collection = self._generate_collection_name(config)

        db_success = self.db_client.truncate_service_catalog()

        qdrant_success = False
        try:
            if self.qdrant_client.collection_exists(collection):
                self.qdrant_client.delete_collection(collection)
                self._setup_qdrant_collection(collection, config.dimension)
                qdrant_success = True
            else:
                self._setup_qdrant_collection(collection, config.dimension)
                qdrant_success = True
        except Exception as e:
            logger.error(f"[✗] Qdrant reset failed: {e}")
            qdrant_success = False

        try:
            self.graph_manager.clear_database()
        except Exception as e:
            logger.warning(f"[!] Graph reset warning: {e}")

        if db_success and qdrant_success:
            return {"status": "success", "message": f"Knowledge base '{collection}' reset successfully."}
        else:
            return {
                "status": "error",
                "message": "Failed to reset knowledge base.",
                "details": {"db_truncated": db_success, "qdrant_cleared": qdrant_success}
            }

    def get_pending_embedding_count(self, embedding_config: Optional[EmbeddingConfig] = None) -> int:
        """
        Get count of items pending embedding generation.

        Args:
            embedding_config: Embedding config for target collection
        """
        config = embedding_config or TASK_WIKI_EMBEDDING
        collection = self._generate_collection_name(config)

        if not self.qdrant_client.collection_exists(collection):
            return 0

        try:
            count_result = self.qdrant_client.count(
                collection_name=collection,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="meta.is_embedded",
                            match=MatchValue(value=False)
                        )
                    ]
                )
            )
            return count_result.count
        except Exception as e:
            logger.error(f"Failed to count pending embeddings: {e}")
            return 0
