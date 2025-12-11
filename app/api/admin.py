from fastapi import FastAPI, HTTPException, Request
from typing import Dict, Any, List
from app.api.components.knowledge_manager import KnowledgeManager
import logging

app = FastAPI()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
