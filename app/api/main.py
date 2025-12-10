from copy import deepcopy
import json
from fastapi import FastAPI, Request, HTTPException, Query
from typing import Any, Dict, List, Optional
import logging
import os
from dotenv import load_dotenv

# .env ファイルを読み込む
load_dotenv()

from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.state_manager import StateManager
from app.api.components.knowledge_manager import KnowledgeManager
from pydantic import BaseModel, Field, HttpUrl

app = FastAPI()

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_OPENING_QUESTION = "何か気になることはありますか？"


class CaptureRequest(BaseModel):
    user_id: str
    url: str
    title: str
    content: str
    screenshot_url: Optional[str] = None


@app.post("/api/v1/webhook/capture")
async def capture_webhook(payload: CaptureRequest):
    repo = DBClient()
    knowledge_manager = KnowledgeManager()

    # Save raw capture
    capture_id = repo.save_captured_page(
        user_id=payload.user_id,
        url=payload.url,
        title=payload.title,
        content=payload.content,
        screenshot_url=payload.screenshot_url
    )
    if not capture_id:
        raise HTTPException(status_code=500, detail="Failed to save captured page")

    # Process for Knowledge Base (L1/L3)
    # Simple logic: check domain for Public status
    visibility = "private"
    memory_type = "user_hypothesis" # Treating captured content as user-related context

    # Example logic for public domains (extend as needed)
    trusted_domains = [".go.jp", ".ac.jp"]
    if any(payload.url.endswith(domain) or f"{domain}/" in payload.url for domain in trusted_domains):
        visibility = "public"
        memory_type = "shared_fact"

    # Summarize content (Simple truncation for now, could use LLM)
    summary_content = f"Title: {payload.title}\nURL: {payload.url}\n\n{payload.content[:1000]}"

    meta = {
        "source_url": payload.url,
        "title": payload.title,
        "capture_id": capture_id
    }

    if visibility == "public":
        knowledge_manager.add_shared_fact(
            content=summary_content,
            source="webhook_capture",
            meta=meta
        )
    else:
        knowledge_manager.add_user_memory(
            user_id=payload.user_id,
            content=summary_content,
            memory_type=memory_type,
            meta=meta
        )

    return {"status": "success", "capture_id": capture_id, "visibility": visibility}


# ユーザー登録エンドポイント
@app.post("/api/v1/users")
async def create_user(request: Request) -> Dict[str, str]:
    try:
        data = await request.json()
    except Exception:
        data = {}
    line_user_id = data.get("line_user_id")
    repo = DBClient()
    user_id = repo.create_user(line_user_id=line_user_id)
    return {"user_id": user_id}

from app.api.workflow import WorkflowManager

# ... (imports)

# LINEのWebhookエンドポイント
@app.post("/api/v1/user-message")
async def post_usermessage(request: Request) -> str:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ai_client = AIClient()
    message = body.get("message", "")
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    if message is None:
        raise HTTPException(status_code=400, detail="message is required")

    repo = DBClient()
    user_message_id = repo.insert_message(user_id, "user", message)
    if not user_message_id:
        raise HTTPException(status_code=500, detail="Failed to store user message")

    # Initialize WorkflowManager
    workflow_manager = WorkflowManager(ai_client)

    # Load state and history
    history = repo.get_recent_conversation(user_id)
    stored_state = repo.get_user_state(user_id)
    current_state = StateManager.get_state_with_defaults(stored_state)

    # Initialize context
    initial_state = StateManager.init_conversation_context(
        user_message=message,
        dialog_history=history,
        interest_profile=current_state["interest_profile"],
        active_hypotheses=current_state["active_hypotheses"]
    )
    initial_state["user_id"] = user_id # Add user_id to state

    # Check for latest captured page context
    latest_page = repo.get_latest_captured_page(user_id)
    if latest_page:
        initial_state["captured_page"] = latest_page

    # Invoke workflow
    final_state = workflow_manager.invoke(initial_state)
    bot_message = final_state.get("bot_message", "申し訳ありません、エラーが発生しました。")

    # Save updated state
    repo.upsert_user_state(
        user_id,
        final_state["interest_profile"],
        final_state["active_hypotheses"]
    )

    # Save analysis result
    analysis_to_save = {
        "interest_profile": final_state["interest_profile"],
        "active_hypotheses": final_state["active_hypotheses"],
        "hypotheses": final_state.get("hypotheses"),
        "response_plan": final_state.get("response_plan")
    }
    repo.record_analysis(user_id, user_message_id, analysis_to_save)

    repo.insert_message(user_id, "ai", bot_message)
    return bot_message

from fastapi.responses import StreamingResponse

@app.post("/api/v1/user-message-stream")
async def post_usermessage_stream(request: Request) -> StreamingResponse:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    ai_client = AIClient()
    message = body.get("message", "")
    user_id = body.get("user_id")

    if not user_id or message is None:
        raise HTTPException(status_code=400, detail="Missing user_id or message")

    repo = DBClient()
    user_message_id = repo.insert_message(user_id, "user", message)
    if not user_message_id:
        raise HTTPException(status_code=500, detail="Failed to store user message")

    workflow_manager = WorkflowManager(ai_client)

    # Load state and history
    history = repo.get_recent_conversation(user_id)
    stored_state = repo.get_user_state(user_id)
    current_state = StateManager.get_state_with_defaults(stored_state)

    initial_state = StateManager.init_conversation_context(
        user_message=message,
        dialog_history=history,
        interest_profile=current_state["interest_profile"],
        active_hypotheses=current_state["active_hypotheses"]
    )
    initial_state["user_id"] = user_id # Add user_id to state

    # Check for latest captured page context
    latest_page = repo.get_latest_captured_page(user_id)
    if latest_page:
        initial_state["captured_page"] = latest_page

    async def event_generator():
        # Node name mapping
        node_messages = {
            "situation_analysis": "興味・関心を分析しています...",
            "hypothesis_generation": "検証すべき仮説を立てています...",
            "rag_retrieval": "関連情報を検索しています...",
            "response_planning": "回答を生成しています..."
        }

        final_state = initial_state

        # Stream the workflow execution
        # workflow_manager.graph is a CompiledGraph, stream returns an iterator of events
        # Note: langgraph stream yields updates keyed by node name
        for output in workflow_manager.graph.stream(initial_state):
            for node_name, state_update in output.items():
                if node_name in node_messages:
                    yield json.dumps({
                        "type": "progress",
                        "step": node_name,
                        "message": node_messages[node_name]
                    }, ensure_ascii=False) + "\n"

                # Update final state tracking
                final_state.update(state_update)

        # After loop, final_state should be close to final.
        # Note: 'bot_message' comes from response_planning
        bot_message = final_state.get("bot_message", "申し訳ありません、エラーが発生しました。")

        # Save updated state
        repo.upsert_user_state(
            user_id,
            final_state.get("interest_profile", {}),
            final_state.get("active_hypotheses", {})
        )

        # Save analysis
        analysis_to_save = {
            "interest_profile": final_state.get("interest_profile"),
            "active_hypotheses": final_state.get("active_hypotheses"),
            "hypotheses": final_state.get("hypotheses"),
            "response_plan": final_state.get("response_plan")
        }
        repo.record_analysis(user_id, user_message_id, analysis_to_save)
        repo.insert_message(user_id, "ai", bot_message)

        yield json.dumps({
            "type": "result",
            "message": bot_message
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.get("/api/v1/user-messages")
async def get_user_messages(user_id: str = Query(..., description="ユーザーID"), limit: int = Query(10, ge=1, le=100, description="取得件数")) -> List[Dict]:
    repo = DBClient()
    messages = repo.get_user_messages(user_id=user_id, limit=limit)
    return messages



if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
