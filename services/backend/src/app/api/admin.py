from fastapi import FastAPI, HTTPException, Request, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import time
from app.api.components.knowledge_manager import KnowledgeManager
import logging
from dotenv import load_dotenv  # 追加

# .env ファイルを読み込む
load_dotenv()

app = FastAPI()

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
