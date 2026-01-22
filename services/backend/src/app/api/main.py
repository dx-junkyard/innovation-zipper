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
from app.api.components.graph_manager import GraphManager
from app.api.components.topic_client import TopicClient
from app.tasks.analysis import run_workflow_task, process_capture_task, process_document_task, save_analysis_result_task
from pydantic import BaseModel, Field, HttpUrl
import requests
import aiofiles
import uuid
from fastapi import UploadFile, File, Form
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.core.storage import storage
import io

app = FastAPI()

# Trust headers from Load Balancer/Proxy
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=["*"]
)

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

class ChatRequest(BaseModel):
    user_id: str
    message: str

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

@app.get("/api/v1/dashboard/knowledge-graph")
async def get_knowledge_graph(user_id: str = Query(..., description="User ID"), limit: int = 15):
    """
    Retrieves the user's central concepts as a knowledge graph structure.
    """
    graph_manager = GraphManager()

    # 1. Get Central Concepts
    concepts = graph_manager.get_central_concepts(user_id, limit=limit)

    # 2. Convert to Nodes and Edges format for UI
    nodes = []
    edges = []

    # Simple color scheme
    CONCEPT_COLOR = "#5DADE2"

    for concept in concepts:
        name = concept.get("name")
        degree = concept.get("degree", 1)

        # Scale size based on degree (min 15, max 50 approximately)
        size = 15 + min(degree * 2, 35)

        nodes.append({
            "id": name,
            "label": name,
            "size": size,
            "color": CONCEPT_COLOR,
            "type": "Concept"
        })

        # Optionally, we could add edges between these top concepts if they exist
        # For now, we return just the nodes as 'Hubs'

    # Use 'nodes' and 'edges' keys to match UI expectations
    return {"nodes": nodes, "edges": edges}

@app.get("/api/v1/dashboard/knowledge-graph/neighbors")
async def get_graph_neighbors(user_id: str = Query(..., description="User ID"), node_id: str = Query(..., description="Target Node ID")):
    """
    Retrieves neighbors for a specific node to support progressive expansion.
    """
    graph_manager = GraphManager()
    data = graph_manager.get_node_neighbors(user_id, node_id)

    # UI向けのフォーマット変換
    nodes = []
    for n in data["nodes"]:
        # Neo4jのlabelsリストから代表ラベル（Concept, Keyword等）を決定
        # 優先度: User > Hypothesis > Concept > Keyword > ...
        lbls = n.get("labels", [])
        node_type = "Concept" # Default
        if "User" in lbls: node_type = "User"
        elif "Hypothesis" in lbls: node_type = "Hypothesis"
        elif "Keyword" in lbls: node_type = "Keyword"
        elif "Document" in lbls: node_type = "Document"

        # プロパティをマージしてフロントエンドに渡す
        node_data = {
            "id": n["id"],
            "label": n["label"],
            "type": node_type,
            "labels": lbls,
            "properties": n.get("properties", {})  # 本文やメタデータを含む
        }
        nodes.append(node_data)

    return {"nodes": nodes, "edges": data["edges"]}

from fastapi.responses import StreamingResponse, FileResponse, RedirectResponse

@app.get("/api/v1/user-files/{file_id}/content")
async def get_file_content(file_id: str):
    """
    Redirects to a presigned URL for the PDF file content.
    """
    repo = DBClient()
    file_info = repo.get_file_info_by_uuid(file_id)

    if not file_info:
        raise HTTPException(status_code=404, detail="File not found in database")

    # file_path in DB is now the Object Key (S3)
    object_name = file_info["file_path"]

    url = storage.generate_presigned_url(object_name)
    if not url:
        raise HTTPException(status_code=404, detail="File not found or S3 error")

    return {"url": url}

@app.post("/api/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Server-Sent Events (SSE) streaming endpoint for True Streaming.
    """
    user_id = request.user_id
    message = request.message

    if not user_id or not message:
         raise HTTPException(status_code=400, detail="Missing user_id or message")

    ai_client = AIClient()
    repo = DBClient()

    # Store user message immediately
    user_message_id = repo.insert_message(user_id, "user", message)
    if not user_message_id:
        raise HTTPException(status_code=500, detail="Failed to store user message")

    workflow_manager = WorkflowManager(ai_client)

    # Initialize State
    history = repo.get_recent_conversation(user_id)
    stored_state = repo.get_user_state(user_id)
    current_state = StateManager.get_state_with_defaults(stored_state)

    initial_state = StateManager.init_conversation_context(
        user_message=message,
        dialog_history=history,
        interest_profile=current_state["interest_profile"],
        active_hypotheses=current_state["active_hypotheses"]
    )
    initial_state["user_id"] = user_id

    # Check for latest captured page context
    latest_page = repo.get_latest_captured_page(user_id)
    if latest_page:
        initial_state["captured_page"] = latest_page

    async def event_generator():
        final_state = initial_state.copy()

        # Friendly messages for step updates
        node_messages = {
            "situation_analysis": "状況を分析しています...",
            "hypothesis_generation": "仮説を立てています...",
            "rag_retrieval": "知識ベースを検索しています...",
            "gap_analysis": "情報の不足を分析しています...",
            "response_planning": "回答の方針を立てています...", # Updated message
            "intent_router": "意図を理解しています...",
            "discovery_exploration": "興味・関心を探索しています...",
            "structural_analysis": "構造分析を行っています...",
            "variant_generation": "アイデアのバリエーションを生成中...",
            "innovation_synthesis": "イノベーション案を統合中...",
            "report_generation": "レポートを作成中..."
        }

        try:
            # --- Phase 1: Thinking (Step Streaming) ---
            for step_output in workflow_manager.stream_invoke(initial_state):
                for node_name, state_update in step_output.items():
                    # Update final state
                    final_state.update(state_update)

                    # Yield step event
                    msg = node_messages.get(node_name, f"処理中... ({node_name})")
                    event_data = {
                        "type": "step",
                        "node": node_name,
                        "content": msg
                    }
                    yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

            # --- Phase 2: Writing (Token Streaming) ---
            # Yield event to indicate writing started
            yield f"data: {json.dumps({'type': 'step', 'node': 'writing', 'content': '回答を執筆しています...'}, ensure_ascii=False)}\n\n"

            response_plan = final_state.get("response_plan")

            # Fallback if plan is missing or empty
            if not response_plan:
                plan_text = "特になし。ユーザーの質問に適切に答えてください。"
            elif isinstance(response_plan, dict):
                 plan_text = json.dumps(response_plan, ensure_ascii=False, indent=2)
            else:
                 plan_text = str(response_plan)

            writing_prompt = f"""
以下の回答方針（Response Plan）に基づいて、ユーザーへの回答を作成してください。

# ユーザーの入力
{message}

# 回答方針
{plan_text}

# 制約
- マークダウン形式で記述してください。
- 方針に含まれる内容を網羅しつつ、自然な会話文にしてください。
- 丁寧な口調で話しかけてください。
"""
            full_response = ""

            # Streaming text generation
            # We use async generator here to prevent blocking the event loop

            async for token in ai_client.generate_stream(writing_prompt):
                if token:
                    full_response += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

            # Fallback if no response generated
            if not full_response:
                full_response = "申し訳ありません、回答の生成に失敗しました。"
                yield f"data: {json.dumps({'type': 'token', 'content': full_response}, ensure_ascii=False)}\n\n"

            # --- Completion ---
            final_state["bot_message"] = full_response

            complete_data = {
                "type": "complete",
                "bot_message": full_response, # Optional here since we streamed it, but good for final consistency
                "analysis_log": final_state.get("last_analysis_log"),
                "interest_profile": final_state.get("interest_profile")
            }
            yield f"data: {json.dumps(complete_data, ensure_ascii=False)}\n\n"

            # Offload heavy saving to background task
            save_analysis_result_task.delay(user_id, message, final_state, user_message_id)

        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            error_data = {"type": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

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
            "interest_profile": final_state.get("interest_profile"),
            "analysis_log": final_state.get("last_analysis_log")
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
    Handles PDF file upload, saves it to S3, records in DB, and triggers background processing.
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

    # Create safe filename (S3 Object Key)
    file_ext = os.path.splitext(file.filename)[1]
    safe_filename = f"{file_id}{file_ext}"
    object_name = safe_filename

    # Save file to S3
    try:
        # storage.upload_file expects a file-like object
        file_obj = io.BytesIO(content)
        storage.upload_file(file_obj, object_name, content_type="application/pdf")
    except Exception as e:
        logger.error(f"S3 Upload failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload file to storage.")

    # Insert into MySQL
    # Store object_name as file_path
    db_file_id = repo.insert_user_file(user_id, file.filename, object_name, title, file_hash, is_public)
    if not db_file_id:
        # Note: We might want to delete from S3 here if DB fails, but for now we skip complex rollback
        raise HTTPException(status_code=500, detail="Database insertion failed.")

    # Trigger Background Task
    # Pass object_name as file_path
    task = process_document_task.delay(user_id, object_name, title, file_id, db_file_id)

    return {
        "status": "uploaded",
        "file_id": file_id,
        "task_id": str(task.id),
        "message": "File uploaded and processing started."
    }


class ContentFeedbackRequest(BaseModel):
    user_id: str
    content_id: int
    content_type: str # 'file' or 'capture'
    new_categories: List[str]
    new_keywords: Optional[List[str]] = None
    text_to_learn: Optional[str] = None # Text content to use for learning

class ConversationFeedbackRequest(BaseModel):
    user_id: str
    new_category: str
    summary_to_learn: Optional[str] = None

@app.post("/api/v1/feedback/content")
async def feedback_content(request: ContentFeedbackRequest):
    repo = DBClient()
    topic_client = TopicClient()
    graph_manager = GraphManager()

    # 1. Update Database
    if request.content_type == 'file':
        success = repo.update_file_category(
            file_id=request.content_id,
            categories=request.new_categories,
            is_verified=True,
            keywords=request.new_keywords
        )
    elif request.content_type == 'capture':
        # Backward compatibility for captures (single category)
        primary_category = request.new_categories[0] if request.new_categories else "Uncategorized"
        success = repo.update_capture_category(request.content_id, primary_category, is_verified=True)
    else:
        raise HTTPException(status_code=400, detail="Invalid content_type")

    if not success:
        raise HTTPException(status_code=500, detail="Database update failed")

    # 2. Learn in Topic Service & Update Graph
    if request.new_categories:
        for cat in request.new_categories:
            if request.text_to_learn:
                # Truncate text if too long (e.g., 500 chars)
                text_snippet = request.text_to_learn[:500]
                topic_client.learn_text(text_snippet, cat)

            # 3. Update Knowledge Graph (Categories)
            graph_manager.add_user_interest(
                user_id=request.user_id,
                concept_name=cat,
                confidence=1.0,
                source_type=graph_manager.SOURCE_USER_STATED
            )

    # 4. Update Graph with Keywords (if provided and file type)
    if request.content_type == 'file' and request.new_keywords:
        # We need the file title to link keyword to document
        file_info = repo.get_file_by_id(request.content_id)
        if file_info:
            title = file_info.get("title")
            if title:
                for kw in request.new_keywords:
                    graph_manager.link_document_to_keyword(
                        document_text=title,
                        keyword=kw,
                        rel_type="TAGGED_WITH"
                    )

    return {"status": "success", "message": "Content updated and learned."}


@app.post("/api/v1/feedback/conversation")
async def feedback_conversation(request: ConversationFeedbackRequest):
    repo = DBClient()
    topic_client = TopicClient()
    graph_manager = GraphManager()

    # 1. Update User State (Interest Profile)
    state = repo.get_user_state(request.user_id)
    if state:
        interest_profile = state.get("interest_profile") or {}

        # Update
        interest_profile["current_category"] = request.new_category

        repo.upsert_user_state(request.user_id, interest_profile, state.get("active_hypotheses") or {})

        # 2. Learn
        if request.summary_to_learn:
             topic_client.learn_text(request.summary_to_learn, request.new_category)

        # 3. Update Graph
        graph_manager.add_user_interest(
            request.user_id,
            request.new_category,
            confidence=1.0,
            source_type=graph_manager.SOURCE_USER_STATED
        )

        return {"status": "success", "message": "Conversation context updated."}

    raise HTTPException(status_code=404, detail="User state not found")

@app.get("/api/v1/user-contents")
async def get_user_contents(user_id: str = Query(..., description="User ID")):
    repo = DBClient()
    contents = repo.get_all_user_contents(user_id)
    return {"contents": contents}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
