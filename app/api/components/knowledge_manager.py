import os
import json
import hashlib
import uuid
from typing import List, Dict, Any, Optional
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance, ScoredPoint, Filter, FieldCondition, MatchValue

from app.api.db import DBClient
from app.api.ai_client import AIClient
from app.api.components.graph_manager import GraphManager
from config import EMBEDDING_DIMENSION

class KnowledgeManager:
    """
    Manages the knowledge base (Second Brain) including User Context (L1),
    AI Insights (L2), and Shared Knowledge (L3).
    Handles import, embedding generation, and persistence to Qdrant.
    """
    def __init__(self):
        self.db_client = DBClient()
        self.ai_client = AIClient()
        self.graph_manager = GraphManager()

        self.qdrant_host = os.getenv("QDRANT_HOST", "localhost")
        self.qdrant_port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = "knowledge_base" # Renamed from service_catalog
        self.qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port)
        self.vector_size = EMBEDDING_DIMENSION

    def is_duplicate_content(self, content: str, threshold: float = 0.98) -> bool:
        """
        Check if similar content already exists in the knowledge base using vector similarity.
        """
        # Save time if content is empty
        if not content.strip():
            return False

        # Generate embedding as in add_user_memory
        vector = self.ai_client.get_embedding(content)
        if not vector:
            return False
        
        # Search Qdrant
        try:
            if not self.qdrant_client.collection_exists(self.collection_name):
                return False

            results = self.qdrant_client.query_points(
                collection_name=self.collection_name,
                query=vector,
                limit=1
            )
            
            # query_points returns a QueryResponse object, access points via .points
            if results.points and results.points[0].score >= threshold:
                return True
            
        except Exception as e:
            print(f"[!] Qdrant duplicate check failed: {e}")
            return False
            
        return False

    def _setup_qdrant_collection(self):
        """Create Qdrant collection if it doesn't exist."""
        if not self.qdrant_client.collection_exists(self.collection_name):
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def add_user_memory(self, user_id: str, content: str, memory_type: str = "user_hypothesis", category: str = "General", meta: Dict[str, Any] = None) -> bool:
        """
        L1/L2: Save private user memory or AI insight.
        """
        self._setup_qdrant_collection()

        entry_id = str(uuid.uuid4())
        vector = self.ai_client.get_embedding(content)

        if not vector:
            print(f"[!] Failed to generate embedding for memory: {content[:30]}...")
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
                collection_name=self.collection_name,
                wait=True,
                points=[PointStruct(
                    id=entry_id,
                    vector=vector,
                    payload=payload
                )]
            )

            # Sync to Knowledge Graph if applicable
            # Treat category as a Concept if valid
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

                # If memory is a hypothesis, add it
                if memory_type == "user_hypothesis":
                    self.graph_manager.add_hypothesis(text=content, evidence_ids=[entry_id], properties=meta)
                    self.graph_manager.link_hypothesis_to_concept(content, category)

                # If memory is a document chunk, also add it as hypothesis node for now to ensure visibility in graph
                elif memory_type == "document_chunk":
                    # We treat document chunks as hypotheses/claims from a file source
                    self.graph_manager.add_hypothesis(text=content, evidence_ids=[entry_id], properties=meta)
                    # Optionally link to a "Document" concept or similar if needed, but for now just presence is key

            return True
        except Exception as e:
            print(f"[✗] Qdrant/Neo4j upsert failed: {e}")
            return False

    def add_shared_fact(self, content: str, source: str = "system", meta: Dict[str, Any] = None) -> bool:
        """
        L3: Save shared public fact.
        """
        self._setup_qdrant_collection()

        # Deterministic ID based on content to avoid duplicates for shared facts?
        # Or just random UUID. Let's use MD5 of content for deduplication.
        md5_hash = hashlib.md5(content.encode()).hexdigest()
        entry_id = str(uuid.UUID(hex=md5_hash))

        vector = self.ai_client.get_embedding(content)

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
                collection_name=self.collection_name,
                wait=True,
                points=[PointStruct(
                    id=entry_id,
                    vector=vector,
                    payload=payload
                )]
            )
            return True
        except Exception as e:
            print(f"[✗] Qdrant upsert failed: {e}")
            return False

    def import_catalog(self, catalog_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Import legacy service catalog data as Shared Knowledge (L3).
        """
        self.db_client.create_service_catalog_table() # Keep DB table for full details fallback
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

                # Insert into MySQL (Legacy compatibility)
                self.db_client.insert_service_catalog_entry(entry)

                # Generate Embedding
                text_to_embed = f"{entry.get('タイトル', '')} {entry.get('サービス内容', '')} {entry.get('対象者', '')} {entry.get('条件・申し込み方法', '')}"
                vector = self.ai_client.get_embedding(text_to_embed)

                if vector:
                    # New Schema Mapping
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
                print(f"[✗] Error processing entry {entry.get('タイトル')}: {e}")
                error_count += 1

        if points:
            try:
                self.qdrant_client.upsert(
                    collection_name=self.collection_name,
                    wait=True,
                    points=points
                )
            except Exception as e:
                return {"status": "partial_failure", "success": success_count, "error": error_count, "qdrant_error": str(e)}

        return {"status": "completed", "success": success_count, "error": error_count}

    def reset_knowledge_base(self) -> Dict[str, Any]:
        """Reset the knowledge base."""
        # 1. Truncate MySQL table
        db_success = self.db_client.truncate_service_catalog()

        # 2. Delete Qdrant collection
        qdrant_success = False
        try:
            if self.qdrant_client.collection_exists(self.collection_name):
                self.qdrant_client.delete_collection(self.collection_name)
                self._setup_qdrant_collection()
                qdrant_success = True
            else:
                self._setup_qdrant_collection()
                qdrant_success = True
        except Exception as e:
            print(f"[✗] Qdrant reset failed: {e}")
            qdrant_success = False

        # 3. Clear Graph Database
        try:
            self.graph_manager.clear_database()
        except Exception as e:
            print(f"[!] Graph reset warning: {e}")

        if db_success and qdrant_success:
            return {"status": "success", "message": "Knowledge base reset successfully."}
        else:
            return {
                "status": "error",
                "message": "Failed to reset knowledge base.",
                "details": {"db_truncated": db_success, "qdrant_cleared": qdrant_success}
            }
