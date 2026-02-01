from fastapi import FastAPI, HTTPException, Request, Query, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
import os
import uuid
import json
import asyncio
import redis
from app.api.components.knowledge_manager import KnowledgeManager
from app.tasks.wikipedia_import import (
    wikipedia_import_task,
    process_wikipedia_embeddings_task,
    ImportJobManager,
    NOTIFICATION_CHANNEL
)
from config import (
    EmbeddingConfig,
    TASK_WIKI_EMBEDDING,
    TASK_USER_DOCUMENT_EMBEDDING,
    TASK_RAG_SEARCH_EMBEDDING,
    PROVIDER_LOCAL,
    PROVIDER_OPENAI,
    settings,
)
import logging
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv()

app = FastAPI(title="Admin API", description="Administration API for knowledge management")

# Wikipedia dump upload directory
UPLOAD_DIR = os.environ.get("WIKIPEDIA_UPLOAD_DIR", "/tmp/wikipedia_dumps")

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class KnowledgeItem(BaseModel):
    content: str = Field(..., description="Main content")
    title: str = Field(..., description="Title of the article")
    url: Optional[str] = None
    id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class ImportRequest(BaseModel):
    source: str = Field(..., description="Source name (e.g. 'wikipedia')")
    items: List[KnowledgeItem]


class EmbeddingConfigRequest(BaseModel):
    """Embedding configuration for hybrid model support."""
    provider: str = Field(default="local", description="Provider: 'local' or 'openai'")
    model: str = Field(default="mxbai-embed-large", description="Embedding model name")
    dimension: int = Field(default=1024, description="Vector dimension")


class WikipediaImportRequest(BaseModel):
    file_path: str = Field(..., description="Path to Wikipedia dump file (.xml.bz2)")
    batch_size: int = Field(default=100, description="Number of articles per batch")
    max_articles: Optional[int] = Field(default=None, description="Maximum articles to import")
    min_content_length: int = Field(default=100, description="Minimum content length")
    embedding_config: Optional[EmbeddingConfigRequest] = Field(
        default=None,
        description="Embedding configuration (default: Local LLM for cost-effective processing)"
    )


class EmbeddingProcessRequest(BaseModel):
    batch_size: int = Field(default=50, description="Number of items per batch")
    max_batches: Optional[int] = Field(default=None, description="Maximum batches to process")
    embedding_config: Optional[EmbeddingConfigRequest] = Field(
        default=None,
        description="Embedding configuration (default: Local LLM)"
    )

@app.post("/api/v1/admin/knowledge/import-raw")
def import_raw_knowledge(request: ImportRequest):
    """
    Fast import of raw knowledge without embedding.
    """
    km = KnowledgeManager()

    start_time = time.time()

    if not request.items:
        return {"status": "success", "count": 0, "message": "No items to import"}

    # Convert Pydantic models to dicts for KM
    # Supporting both Pydantic v1 and v2 just in case, but prefer model_dump
    if hasattr(request.items[0], "model_dump"):
        items_dicts = [item.model_dump() for item in request.items]
    else:
        items_dicts = [item.dict() for item in request.items]

    result = km.import_raw_public_knowledge(source=request.source, items=items_dicts)
    end_time = time.time()

    result["execution_time_seconds"] = end_time - start_time

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Import failed"))

    return result

@app.post("/api/v1/admin/knowledge/process-embeddings")
def process_embeddings(limit: int = Query(50, description="Number of items to process")):
    """
    Trigger background processing of pending embeddings.
    """
    km = KnowledgeManager()
    result = km.process_pending_embeddings(batch_size=limit)

    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "Processing failed"))

    return result

@app.delete("/api/v1/service-catalog/reset")
async def reset_catalog():
    km = KnowledgeManager()
    result = km.reset_knowledge_base()
    if result["status"] == "success":
         return result
    raise HTTPException(status_code=500, detail=result.get("message", "Failed to reset catalog"))

@app.post("/api/v1/service-catalog/import")
async def import_catalog(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(data, list):
         raise HTTPException(status_code=400, detail="Expected a list of catalog entries")

    km = KnowledgeManager()
    result = km.import_catalog(data)

    if result.get("status") == "partial_failure":
        return result # Return partial success with details

    return result


# =============================================================================
# Wikipedia Import API Endpoints
# =============================================================================

@app.post("/api/v1/admin/wikipedia/upload")
async def upload_wikipedia_dump(file: UploadFile = File(...)):
    """
    Upload a Wikipedia dump file (.xml.bz2) for import.
    """
    if not file.filename.endswith(('.xml.bz2', '.xml')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Expected .xml.bz2 or .xml file"
        )

    # Create upload directory if not exists
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # Generate unique filename
    file_id = str(uuid.uuid4())[:8]
    filename = f"{file_id}_{file.filename}"
    file_path = os.path.join(UPLOAD_DIR, filename)

    try:
        # Save uploaded file
        with open(file_path, "wb") as buffer:
            chunk_size = 1024 * 1024  # 1MB chunks
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                buffer.write(chunk)

        file_size = os.path.getsize(file_path)

        return {
            "status": "success",
            "file_path": file_path,
            "filename": filename,
            "file_size": file_size,
            "message": f"File uploaded successfully: {filename}"
        }

    except Exception as e:
        logger.error(f"File upload failed: {e}")
        # Clean up partial file
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.post("/api/v1/admin/wikipedia/import")
async def start_wikipedia_import(request: WikipediaImportRequest):
    """
    Start a Wikipedia dump import job.

    By default, uses Local LLM embedding (TASK_WIKI_EMBEDDING) for cost-effective processing.
    You can override this by providing embedding_config in the request.
    """
    # Validate file exists
    if not os.path.exists(request.file_path):
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {request.file_path}"
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Create job manager
    job_manager = ImportJobManager(job_id)

    # Prepare embedding config
    embedding_config_dict = None
    if request.embedding_config:
        embedding_config_dict = {
            "provider": request.embedding_config.provider,
            "model": request.embedding_config.model,
            "dimension": request.embedding_config.dimension
        }

    # Create job record
    config = {
        "batch_size": request.batch_size,
        "max_articles": request.max_articles,
        "min_content_length": request.min_content_length,
        "embedding_config": embedding_config_dict or TASK_WIKI_EMBEDDING.to_dict()
    }
    job_data = job_manager.create_job(request.file_path, config)

    # Start Celery task
    task = wikipedia_import_task.delay(
        job_id=job_id,
        file_path=request.file_path,
        batch_size=request.batch_size,
        max_articles=request.max_articles,
        min_content_length=request.min_content_length,
        embedding_config=embedding_config_dict
    )

    return {
        "status": "started",
        "job_id": job_id,
        "task_id": str(task.id),
        "message": "Wikipedia import job started",
        "embedding_config": config["embedding_config"],
        "job": job_data
    }


@app.get("/api/v1/admin/wikipedia/jobs")
async def list_wikipedia_jobs(limit: int = Query(20, description="Number of jobs to return")):
    """
    List recent Wikipedia import jobs.
    """
    jobs = ImportJobManager.list_jobs(limit)
    return {
        "status": "success",
        "jobs": jobs,
        "count": len(jobs)
    }


@app.get("/api/v1/admin/wikipedia/jobs/{job_id}")
async def get_wikipedia_job(job_id: str):
    """
    Get status of a specific Wikipedia import job.
    """
    job_manager = ImportJobManager(job_id)
    job = job_manager.get_job()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "status": "success",
        "job": job
    }


@app.post("/api/v1/admin/wikipedia/jobs/{job_id}/cancel")
async def cancel_wikipedia_job(job_id: str):
    """
    Request cancellation of a running Wikipedia import job.
    """
    success = ImportJobManager.cancel_job(job_id)

    if success:
        return {
            "status": "success",
            "message": "Cancellation requested"
        }
    else:
        raise HTTPException(
            status_code=400,
            detail="Job not found or not in a cancellable state"
        )


@app.post("/api/v1/admin/wikipedia/process-embeddings")
async def start_embedding_processing(request: EmbeddingProcessRequest):
    """
    Start background processing of pending embeddings.

    By default, uses Local LLM embedding (TASK_WIKI_EMBEDDING) for cost-effective processing.
    You can override this by providing embedding_config in the request.
    """
    # Prepare embedding config
    embedding_config_dict = None
    if request.embedding_config:
        embedding_config_dict = {
            "provider": request.embedding_config.provider,
            "model": request.embedding_config.model,
            "dimension": request.embedding_config.dimension
        }

    task = process_wikipedia_embeddings_task.delay(
        batch_size=request.batch_size,
        max_batches=request.max_batches,
        embedding_config=embedding_config_dict
    )

    return {
        "status": "started",
        "task_id": str(task.id),
        "message": "Embedding processing task started",
        "embedding_config": embedding_config_dict or TASK_WIKI_EMBEDDING.to_dict()
    }


@app.get("/api/v1/admin/notifications/stream")
async def notification_stream():
    """
    Server-Sent Events (SSE) stream for real-time import notifications.
    """
    async def event_generator():
        redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        pubsub = r.pubsub()
        pubsub.subscribe(NOTIFICATION_CHANNEL)

        try:
            # Send initial connection event
            yield f"data: {json.dumps({'type': 'connected', 'message': 'Connected to notification stream'})}\n\n"

            while True:
                message = pubsub.get_message(timeout=1.0)
                if message and message['type'] == 'message':
                    data = message['data']
                    if isinstance(data, bytes):
                        data = data.decode('utf-8')
                    yield f"data: {data}\n\n"

                # Send heartbeat every 30 seconds
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            pubsub.unsubscribe(NOTIFICATION_CHANNEL)
            pubsub.close()
            raise

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/api/v1/admin/notifications")
async def get_notifications(
    limit: int = Query(20, description="Number of notifications to return"),
    since: Optional[str] = Query(None, description="Return notifications after this timestamp (ISO format)")
):
    """
    Get recent notifications for admin dashboard.
    Notifications are stored in Redis with a TTL.
    """
    redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)

    notifications_key = "wikipedia_import:notifications_history"

    try:
        # Get stored notifications
        raw_notifications = r.lrange(notifications_key, 0, limit - 1)
        notifications = []

        for raw in raw_notifications:
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            notif = json.loads(raw)

            # Filter by timestamp if provided
            if since:
                notif_time = notif.get("timestamp", "")
                if notif_time <= since:
                    continue

            notifications.append(notif)

        return {
            "status": "success",
            "notifications": notifications,
            "count": len(notifications)
        }

    except Exception as e:
        logger.error(f"Failed to get notifications: {e}")
        return {
            "status": "error",
            "message": str(e),
            "notifications": []
        }


@app.delete("/api/v1/admin/notifications")
async def clear_notifications():
    """
    Clear all notifications.
    """
    redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)

    notifications_key = "wikipedia_import:notifications_history"

    try:
        r.delete(notifications_key)
        return {"status": "success", "message": "Notifications cleared"}
    except Exception as e:
        logger.error(f"Failed to clear notifications: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/admin/stats")
async def get_admin_stats():
    """
    Get overall statistics for admin dashboard.
    """
    km = KnowledgeManager()

    try:
        # Get knowledge base stats
        collection_info = None
        if km.qdrant_client.collection_exists(km.collection_name):
            collection_info = km.qdrant_client.get_collection(km.collection_name)

        # Count pending embeddings
        pending_count = 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            scroll_result, _ = km.qdrant_client.scroll(
                collection_name=km.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="meta.is_embedded",
                            match=MatchValue(value=False)
                        )
                    ]
                ),
                limit=1,
                with_payload=False,
                with_vectors=False
            )
            # This gives us just a sample; for exact count we'd need to scroll all
            # For now, estimate based on collection
        except Exception:
            pass

        return {
            "status": "success",
            "stats": {
                "knowledge_base": {
                    "collection": km.collection_name,
                    "points_count": collection_info.points_count if collection_info else 0,
                    "vectors_count": collection_info.vectors_count if collection_info else 0
                },
                "recent_jobs": len(ImportJobManager.list_jobs(10))
            }
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {
            "status": "error",
            "message": str(e)
        }


# =============================================================================
# Hybrid Model Configuration API Endpoints
# =============================================================================

@app.get("/api/v1/admin/config/hybrid-model")
async def get_hybrid_model_config():
    """
    Get current hybrid model configuration for LLM and embedding tasks.
    """
    from config import (
        TASK_CAPTURE_FILTERING,
        TASK_HOT_CACHE,
        TASK_INTENT_ROUTING,
        TASK_INTEREST_EXPLORATION,
        TASK_SITUATION_ANALYSIS,
        TASK_HYPOTHESIS_GENERATION,
        TASK_STRUCTURAL_ANALYSIS,
        TASK_INNOVATION_SYNTHESIS,
        TASK_GAP_ANALYSIS,
        TASK_REPORT_GENERATION,
        TASK_RESPONSE_PLANNING,
    )

    return {
        "status": "success",
        "config": {
            "providers": {
                "local": {
                    "fast_model": settings.LOCAL_MODEL_FAST,
                    "smart_model": settings.LOCAL_MODEL_SMART,
                    "embedding_model": settings.LOCAL_EMBEDDING_MODEL,
                    "embedding_dimension": settings.LOCAL_EMBEDDING_DIMENSION,
                },
                "openai": {
                    "fast_model": settings.CLOUD_MODEL_FAST,
                    "smart_model": settings.CLOUD_MODEL_SMART,
                    "embedding_model": settings.CLOUD_EMBEDDING_MODEL,
                    "embedding_dimension": settings.CLOUD_EMBEDDING_DIMENSION,
                }
            },
            "task_assignments": {
                "llm_tasks": {
                    "capture_filtering": TASK_CAPTURE_FILTERING.to_dict(),
                    "hot_cache": TASK_HOT_CACHE.to_dict(),
                    "intent_routing": TASK_INTENT_ROUTING.to_dict(),
                    "interest_exploration": TASK_INTEREST_EXPLORATION.to_dict(),
                    "situation_analysis": TASK_SITUATION_ANALYSIS.to_dict(),
                    "hypothesis_generation": TASK_HYPOTHESIS_GENERATION.to_dict(),
                    "structural_analysis": TASK_STRUCTURAL_ANALYSIS.to_dict(),
                    "innovation_synthesis": TASK_INNOVATION_SYNTHESIS.to_dict(),
                    "gap_analysis": TASK_GAP_ANALYSIS.to_dict(),
                    "report_generation": TASK_REPORT_GENERATION.to_dict(),
                    "response_planning": TASK_RESPONSE_PLANNING.to_dict(),
                },
                "embedding_tasks": {
                    "wiki_embedding": TASK_WIKI_EMBEDDING.to_dict(),
                    "user_document_embedding": TASK_USER_DOCUMENT_EMBEDDING.to_dict(),
                    "rag_search_embedding": TASK_RAG_SEARCH_EMBEDDING.to_dict(),
                }
            }
        }
    }


@app.get("/api/v1/admin/collections")
async def list_knowledge_collections():
    """
    List all knowledge base collections with their metadata.
    Shows collections for different embedding models.
    """
    km = KnowledgeManager()

    try:
        collections = km.list_available_collections()

        # Also get pending embedding counts for each collection
        for collection in collections:
            try:
                # Try to extract embedding info from collection name
                name = collection["name"]
                if name.startswith("knowledge_base_"):
                    suffix = name[len("knowledge_base_"):]
                    # Format: model_dimension
                    parts = suffix.rsplit("_", 1)
                    if len(parts) == 2:
                        collection["embedding_model"] = parts[0].replace("_", "-")
                        collection["dimension"] = int(parts[1])
            except Exception:
                pass

        return {
            "status": "success",
            "collections": collections,
            "current_collection": km.collection_name,
            "current_embedding_config": km.embedding_config.to_dict()
        }

    except Exception as e:
        logger.error(f"Failed to list collections: {e}")
        return {
            "status": "error",
            "message": str(e),
            "collections": []
        }


@app.get("/api/v1/admin/collections/{collection_name}/stats")
async def get_collection_stats(collection_name: str):
    """
    Get detailed statistics for a specific collection.
    """
    km = KnowledgeManager()

    try:
        if not km.qdrant_client.collection_exists(collection_name):
            raise HTTPException(status_code=404, detail=f"Collection not found: {collection_name}")

        info = km.qdrant_client.get_collection(collection_name)

        # Count pending embeddings
        pending_count = 0
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            count_result = km.qdrant_client.count(
                collection_name=collection_name,
                count_filter=Filter(
                    must=[
                        FieldCondition(
                            key="meta.is_embedded",
                            match=MatchValue(value=False)
                        )
                    ]
                )
            )
            pending_count = count_result.count
        except Exception:
            pass

        return {
            "status": "success",
            "collection": {
                "name": collection_name,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status.value,
                "pending_embeddings": pending_count,
                "embedded_count": info.points_count - pending_count if info.points_count else 0
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get collection stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
