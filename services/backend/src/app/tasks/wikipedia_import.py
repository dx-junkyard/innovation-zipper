"""
Wikipedia Import Celery Tasks

Handles background processing of Wikipedia dump files for RAG import.
Supports hybrid model configuration for cost-effective embedding generation.
"""

import os
import json
import time
import redis
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.core.celery_app import celery_app
from app.utils.wikipedia_parser import (
    parse_wikipedia_dump,
    batch_articles,
    WikipediaImportStats
)
from app.api.components.knowledge_manager import KnowledgeManager
from config import (
    TASK_WIKI_EMBEDDING,
    EmbeddingConfig,
    generate_collection_name,
)

logger = logging.getLogger(__name__)

# Redis key patterns for job management
JOB_STATUS_KEY = "wikipedia_import:job:{job_id}"
JOB_LIST_KEY = "wikipedia_import:jobs"
NOTIFICATION_CHANNEL = "wikipedia_import:notifications"
NOTIFICATION_HISTORY_KEY = "wikipedia_import:notifications_history"


def get_redis_client() -> redis.Redis:
    """Get Redis client from environment."""
    redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    return redis.from_url(redis_url)


class ImportJobManager:
    """
    Manages Wikipedia import job status in Redis.
    """

    def __init__(self, job_id: str):
        self.job_id = job_id
        self.redis = get_redis_client()
        self.status_key = JOB_STATUS_KEY.format(job_id=job_id)

    def create_job(self, file_path: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new import job."""
        # Include embedding configuration in job data
        embedding_config = config.get("embedding_config", TASK_WIKI_EMBEDDING.to_dict())
        collection_name = generate_collection_name(
            "knowledge_base",
            EmbeddingConfig(**embedding_config) if isinstance(embedding_config, dict) else embedding_config
        )

        job_data = {
            "job_id": self.job_id,
            "status": "pending",
            "file_path": file_path,
            "config": config,
            "embedding_config": embedding_config,
            "collection_name": collection_name,
            "created_at": datetime.now().isoformat(),
            "started_at": None,
            "completed_at": None,
            "progress": {
                "total_parsed": 0,
                "total_imported": 0,
                "total_errors": 0,
                "current_batch": 0,
                "estimated_total": config.get("max_articles"),
                "percent_complete": 0
            },
            "errors": [],
            "message": "Job created, waiting to start..."
        }

        # Store job data
        self.redis.set(self.status_key, json.dumps(job_data))
        self.redis.expire(self.status_key, 86400 * 7)  # 7 days TTL

        # Add to job list
        self.redis.lpush(JOB_LIST_KEY, self.job_id)
        self.redis.ltrim(JOB_LIST_KEY, 0, 99)  # Keep last 100 jobs

        return job_data

    def update_status(
        self,
        status: str,
        message: str = None,
        progress: Dict[str, Any] = None,
        errors: List[str] = None
    ):
        """Update job status."""
        job_data = self.get_job()
        if not job_data:
            return

        job_data["status"] = status

        if message:
            job_data["message"] = message

        if progress:
            job_data["progress"].update(progress)
            # Calculate percent complete
            if job_data["progress"].get("estimated_total"):
                job_data["progress"]["percent_complete"] = min(100, int(
                    job_data["progress"]["total_parsed"] /
                    job_data["progress"]["estimated_total"] * 100
                ))

        if errors:
            job_data["errors"].extend(errors)
            # Keep only last 50 errors
            job_data["errors"] = job_data["errors"][-50:]

        if status == "running" and not job_data.get("started_at"):
            job_data["started_at"] = datetime.now().isoformat()

        if status in ["completed", "failed", "cancelled"]:
            job_data["completed_at"] = datetime.now().isoformat()

        self.redis.set(self.status_key, json.dumps(job_data))

        # Publish notification for real-time updates
        self._publish_notification(status, message, job_data)

    def get_job(self) -> Optional[Dict[str, Any]]:
        """Get job data."""
        data = self.redis.get(self.status_key)
        if data:
            return json.loads(data)
        return None

    def add_error(self, error: str):
        """Add an error to the job."""
        job_data = self.get_job()
        if job_data:
            job_data["errors"].append({
                "timestamp": datetime.now().isoformat(),
                "message": error
            })
            job_data["errors"] = job_data["errors"][-50:]
            job_data["progress"]["total_errors"] = len(job_data["errors"])
            self.redis.set(self.status_key, json.dumps(job_data))

            # Notify about error
            self._publish_notification("error", error, job_data)

    def _publish_notification(self, event_type: str, message: str, job_data: Dict):
        """Publish notification to Redis channel and store in history."""
        notification = {
            "type": event_type,
            "job_id": self.job_id,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "progress": job_data.get("progress", {}),
            "collection_name": job_data.get("collection_name"),
            "embedding_config": job_data.get("embedding_config")
        }

        # Publish for real-time subscribers
        self.redis.publish(NOTIFICATION_CHANNEL, json.dumps(notification))

        # Store in history for polling-based clients
        if event_type in ["error", "completed", "failed", "cancelled", "running"]:
            self.redis.lpush(NOTIFICATION_HISTORY_KEY, json.dumps(notification))
            self.redis.ltrim(NOTIFICATION_HISTORY_KEY, 0, 99)
            self.redis.expire(NOTIFICATION_HISTORY_KEY, 86400)

    @staticmethod
    def list_jobs(limit: int = 20) -> List[Dict[str, Any]]:
        """List recent jobs."""
        r = get_redis_client()
        job_ids = r.lrange(JOB_LIST_KEY, 0, limit - 1)

        jobs = []
        for job_id in job_ids:
            if isinstance(job_id, bytes):
                job_id = job_id.decode('utf-8')
            key = JOB_STATUS_KEY.format(job_id=job_id)
            data = r.get(key)
            if data:
                jobs.append(json.loads(data))

        return jobs

    @staticmethod
    def cancel_job(job_id: str) -> bool:
        """Request job cancellation."""
        r = get_redis_client()
        key = JOB_STATUS_KEY.format(job_id=job_id)
        data = r.get(key)

        if data:
            job_data = json.loads(data)
            if job_data["status"] == "running":
                job_data["status"] = "cancelling"
                job_data["message"] = "Cancellation requested..."
                r.set(key, json.dumps(job_data))
                return True

        return False


@celery_app.task(name="wikipedia_import_task", bind=True)
def wikipedia_import_task(
    self,
    job_id: str,
    file_path: str,
    batch_size: int = 100,
    max_articles: Optional[int] = None,
    min_content_length: int = 100,
    embedding_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Main task for importing Wikipedia dump.

    Uses TASK_WIKI_EMBEDDING by default for cost-effective processing with local LLM.

    Args:
        job_id: Unique job identifier
        file_path: Path to Wikipedia dump file (.xml.bz2)
        batch_size: Number of articles per batch
        max_articles: Maximum articles to import (None for all)
        min_content_length: Minimum content length to include
        embedding_config: Optional embedding configuration override (dict form)

    Returns:
        Import result summary
    """
    job_manager = ImportJobManager(job_id)
    stats = WikipediaImportStats()

    # Parse embedding config
    if embedding_config:
        embed_config = EmbeddingConfig(**embedding_config)
    else:
        embed_config = TASK_WIKI_EMBEDDING

    logger.info(
        f"Wikipedia import using embedding config: "
        f"provider={embed_config.provider}, model={embed_config.model}, "
        f"dimension={embed_config.dimension}"
    )

    try:
        # Validate file
        if not os.path.exists(file_path):
            error_msg = f"File not found: {file_path}"
            job_manager.update_status("failed", error_msg)
            return {"status": "error", "message": error_msg}

        # Update status to running
        job_manager.update_status(
            "running",
            f"Starting import from {os.path.basename(file_path)}..."
        )

        # Initialize knowledge manager with specific embedding config
        km = KnowledgeManager(embedding_config=embed_config)
        collection_name = km.collection_name

        logger.info(f"Importing to collection: {collection_name}")

        # Parse and import
        logger.info(f"Starting Wikipedia import: {file_path}")

        articles = parse_wikipedia_dump(
            file_path,
            min_content_length=min_content_length,
            max_articles=max_articles,
            skip_redirects=True,
            clean_markup=True
        )

        for batch in batch_articles(articles, batch_size):
            # Check for cancellation
            current_job = job_manager.get_job()
            if current_job and current_job.get("status") == "cancelling":
                job_manager.update_status(
                    "cancelled",
                    f"Job cancelled after {stats.total_imported} articles"
                )
                return {
                    "status": "cancelled",
                    "imported": stats.total_imported,
                    "collection": collection_name
                }

            stats.current_batch += 1
            batch_start = time.time()

            # Prepare items for import
            items = []
            for article in batch:
                items.append({
                    "id": article["id"],
                    "title": article["title"],
                    "content": article["content"],
                    "url": article["url"],
                    "metadata": {
                        **article.get("metadata", {}),
                        "summary": article.get("summary", "")
                    }
                })
                stats.total_parsed += 1

            # Import batch using the configured embedding config
            try:
                result = km.import_raw_public_knowledge(
                    source="wikipedia",
                    items=items,
                    embedding_config=embed_config
                )

                if result["status"] == "success":
                    stats.total_imported += result.get("count", len(items))
                else:
                    error_msg = result.get("message", "Unknown error")
                    stats.add_error(f"Batch {stats.current_batch}: {error_msg}")
                    job_manager.add_error(error_msg)

            except Exception as e:
                error_msg = f"Batch {stats.current_batch} failed: {str(e)}"
                logger.error(error_msg)
                stats.add_error(error_msg)
                job_manager.add_error(error_msg)

            batch_time = time.time() - batch_start

            # Update progress
            job_manager.update_status(
                "running",
                f"Imported {stats.total_imported} articles ({batch_time:.1f}s/batch)",
                progress={
                    "total_parsed": stats.total_parsed,
                    "total_imported": stats.total_imported,
                    "total_errors": stats.total_errors,
                    "current_batch": stats.current_batch
                }
            )

            logger.info(
                f"Batch {stats.current_batch}: "
                f"parsed={stats.total_parsed}, "
                f"imported={stats.total_imported}, "
                f"time={batch_time:.2f}s"
            )

        # Complete
        job_manager.update_status(
            "completed",
            f"Import completed: {stats.total_imported} articles imported to {collection_name}",
            progress=stats.to_dict()
        )

        return {
            "status": "completed",
            "job_id": job_id,
            "collection": collection_name,
            "embedding_config": embed_config.to_dict(),
            **stats.to_dict()
        }

    except Exception as e:
        error_msg = f"Import failed: {str(e)}"
        logger.error(error_msg, exc_info=True)
        job_manager.update_status("failed", error_msg)
        job_manager.add_error(error_msg)

        return {
            "status": "error",
            "job_id": job_id,
            "message": error_msg,
            **stats.to_dict()
        }


@celery_app.task(name="process_wikipedia_embeddings_task")
def process_wikipedia_embeddings_task(
    batch_size: int = 50,
    max_batches: Optional[int] = None,
    embedding_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Background task to process pending embeddings for Wikipedia articles.

    Uses TASK_WIKI_EMBEDDING by default for cost-effective processing with local LLM.

    Args:
        batch_size: Number of items per batch
        max_batches: Maximum number of batches to process (None for all)
        embedding_config: Optional embedding configuration override (dict form)

    Returns:
        Processing result summary
    """
    # Parse embedding config
    if embedding_config:
        embed_config = EmbeddingConfig(**embedding_config)
    else:
        embed_config = TASK_WIKI_EMBEDDING

    logger.info(
        f"Processing embeddings with config: "
        f"provider={embed_config.provider}, model={embed_config.model}"
    )

    km = KnowledgeManager(embedding_config=embed_config)
    collection_name = km.collection_name
    total_processed = 0
    batch_count = 0

    try:
        while True:
            result = km.process_pending_embeddings(
                batch_size=batch_size,
                embedding_config=embed_config
            )

            if result["status"] != "success":
                logger.error(f"Embedding processing failed: {result.get('message')}")
                break

            processed = result.get("processed", 0)
            if processed == 0:
                logger.info("No more pending embeddings")
                break

            total_processed += processed
            batch_count += 1

            logger.info(f"Processed {processed} embeddings (total: {total_processed})")

            if max_batches and batch_count >= max_batches:
                logger.info(f"Reached max_batches limit: {max_batches}")
                break

            # Small delay between batches to avoid overloading
            time.sleep(0.5)

        return {
            "status": "completed",
            "total_processed": total_processed,
            "batches": batch_count,
            "collection": collection_name,
            "embedding_config": embed_config.to_dict()
        }

    except Exception as e:
        logger.error(f"Embedding processing task failed: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "total_processed": total_processed,
            "collection": collection_name
        }


@celery_app.task(name="get_embedding_status_task")
def get_embedding_status_task(
    embedding_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Get status of pending embeddings for a specific configuration.

    Args:
        embedding_config: Optional embedding configuration (dict form)

    Returns:
        Status information including pending count
    """
    if embedding_config:
        embed_config = EmbeddingConfig(**embedding_config)
    else:
        embed_config = TASK_WIKI_EMBEDDING

    km = KnowledgeManager(embedding_config=embed_config)

    pending_count = km.get_pending_embedding_count(embed_config)
    collections = km.list_available_collections()

    return {
        "pending_count": pending_count,
        "collection": km.collection_name,
        "embedding_config": embed_config.to_dict(),
        "all_collections": collections
    }
