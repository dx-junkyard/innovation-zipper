from copy import deepcopy
import json
from fastapi import FastAPI, Request, HTTPException, Query
from typing import Any, Dict, List, Optional
import logging
import os
from dotenv import load_dotenv
import redis
import hashlib

# .env ファイルを読み込む
load_dotenv()

from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.workflow import WorkflowManager
from app.api.state_manager import StateManager
from app.api.components.knowledge_manager import KnowledgeManager
from app.tasks.analysis import run_workflow_task, process_capture_task, process_document_task
from pydantic import BaseModel, Field, HttpUrl
import requests
import aiofiles
import uuid
from fastapi import UploadFile, File, Form

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# クラス定義を追加
class LineAuthRequest(BaseModel):
    code: str
    redirect_uri: str

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
    # Add dict method for easier serialization to Celery
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "screenshot_url": self.screenshot_url
        }

class TopicDeepDiveRequest(BaseModel):
    user_id: str
    topic: str


@app.post("/api/v1/webhook/capture")
async def capture_webhook(payload: CaptureRequest):
    """
    Receives browser capture data and offloads processing to a background task (Fire-and-Forget).
    """
    # Fire-and-forget: Push to Celery
    task = process_capture_task.delay(payload.to_dict())

    return {
        "status": "queued",
        "task_id": str(task.id),
        "message": "Capture received and processing started in background."
    }

# health
@app.get("/health")
async def health(request: Request) -> Dict[str, str]:
    return {"status": "ok"}

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

# LINEのWebhookエンドポイント
@app.post("/api/v1/user-message")
async def post_usermessage(request: Request) -> Dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

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

    # Start background task for analysis
    task = run_workflow_task.delay(user_id, message, user_message_id)

    # Fetch Hot Cache from Redis for immediate suggestions
    suggestions = []
    try:
        redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        cached_data = r.get(f"hot_cache:{user_id}")
        if cached_data:
            cache_json = json.loads(cached_data)
            suggestions = cache_json.get("suggestions", [])
    except Exception as e:
        logger.warning(f"Failed to fetch hot cache for user {user_id}: {e}")

    # Quick Reply
    quick_reply = "分析を開始しました。しばらくお待ちください。"

    return {
        "message": quick_reply,
        "task_id": str(task.id),
        "status": "processing",
        "suggestions": suggestions  # Include cached suggestions
    }

@app.get("/api/v1/dashboard/innovations")
async def get_innovation_history(user_id: str = Query(..., description="User ID"), limit: int = 10):
    repo = DBClient()
    history = repo.get_innovation_history(user_id, limit)
    return {"history": history}

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
            "message": bot_message,
            "interest_profile": final_state.get("interest_profile")
        }, ensure_ascii=False) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")

@app.get("/api/v1/user-messages")
async def get_user_messages(user_id: str = Query(..., description="ユーザーID"), limit: int = Query(10, ge=1, le=100, description="取得件数")) -> List[Dict]:
    repo = DBClient()
    messages = repo.get_user_messages(user_id=user_id, limit=limit)
    return messages

# 以下のエンドポイントを追加してください
@app.post("/api/v1/topic-deep-dive")
async def topic_deep_dive(request: TopicDeepDiveRequest):
    ai_client = AIClient()
    repo = DBClient()

    # Get recent conversation for context
    history = repo.get_recent_conversation(request.user_id)

    dialog_text = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])

    prompt = f"""これまでの会話を踏まえ、トピック『{request.topic}』についてこれまでの流れを簡潔にまとめ、ユーザーの知的好奇心を刺激するような鋭い質問を1つ提示してください。

# 会話履歴:
{dialog_text}

JSON形式で {{'summary': '...', 'question': '...'}} と出力してください。"""

    response = ai_client.generate_response(prompt)
    if not response:
        return {"summary": "情報の生成に失敗しました。", "question": "他に気になるトピックはありますか？"}

    return response

@app.post("/api/v1/auth/line")
async def line_auth(request: LineAuthRequest):
    # 環境変数からシークレットを取得
    channel_id = os.environ.get("LINE_CHANNEL_ID")
    channel_secret = os.environ.get("LINE_CHANNEL_SECRET")
    
    if not channel_id or not channel_secret:
        raise HTTPException(status_code=500, detail="Server configuration error: LINE secrets not set")

    # 1. アクセストークンの取得
    token_url = "https://api.line.me/oauth2/v2.1/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "authorization_code",
        "code": request.code,
        "redirect_uri": request.redirect_uri, # 拡張機能から送られてきたURIを使用
        "client_id": channel_id,
        "client_secret": channel_secret
    }
    
    try:
        response = requests.post(token_url, headers=headers, data=data)
        response.raise_for_status()
        tokens = response.json()
    except Exception as e:
        logger.error(f"LINE Token Exchange Failed: {e}, Response: {response.text}")
        raise HTTPException(status_code=400, detail="Failed to exchange token with LINE")

    # 2. プロフィール情報の取得 (またはIDトークンの検証)
    # ここでは簡単のためアクセストークンを使ってプロフィールを取得します
    profile_url = "https://api.line.me/v2/profile"
    try:
        profile_resp = requests.get(profile_url, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        profile_resp.raise_for_status()
        profile = profile_resp.json()
        line_user_id = profile.get("userId")
    except Exception as e:
         logger.error(f"LINE Profile Fetch Failed: {e}")
         raise HTTPException(status_code=400, detail="Failed to fetch user profile")

    # 3. ユーザーの作成または取得
    repo = DBClient()
    user_id = repo.create_user(line_user_id=line_user_id)
    
    return {"user_id": user_id, "line_user_id": line_user_id}


@app.post("/api/v1/user-files/upload")
async def upload_user_file(
    user_id: str = Form(...),
    title: str = Form(...),
    is_public: bool = Form(False),
    file: UploadFile = File(...)
):
    """
    Handles PDF file upload, saves it, records in DB, and triggers background processing.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    # Check for duplicates using hash
    repo = DBClient()
    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    # Check if duplicate exists
    if repo.check_file_exists(user_id, file_hash):
        raise HTTPException(status_code=400, detail="このファイルは既に登録されています。")

    # Generate unique ID for the file
    file_id = str(uuid.uuid4())

    # Define storage path (ensure app/uploads exists)
    upload_dir = "/app/uploads"
    os.makedirs(upload_dir, exist_ok=True)

    # Create safe filename
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{file_id}{file_ext}"
    file_path = os.path.join(upload_dir, safe_filename)

    # Save file to disk
    try:
        # Since we already read the content, we can just write it.
        # But aiofiles expects async write.
        async with aiofiles.open(file_path, 'wb') as out_file:
            await out_file.write(content)
    except Exception as e:
        logger.error(f"File save failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to save file.")

    # Insert into MySQL
    if not repo.insert_user_file(user_id, file.filename, file_path, title, file_hash, is_public):
        # Cleanup file if DB fails
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(status_code=500, detail="Database insertion failed.")

    # Trigger Background Task
    task = process_document_task.delay(user_id, file_path, title, file_id)

    return {
        "status": "uploaded",
        "file_id": file_id,
        "task_id": str(task.id),
        "message": "File uploaded and processing started."
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
