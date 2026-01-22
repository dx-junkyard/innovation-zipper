import logging
import asyncio
import json
import os
import redis
import pypdf
import uuid
import tempfile
from typing import Dict, Any, Optional
from qdrant_client.models import PointStruct

from app.core.celery_app import celery_app
from app.core.storage import storage
from app.api.workflow import WorkflowManager
from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.state_manager import StateManager
from app.api.components.knowledge_manager import KnowledgeManager
from app.api.components.topic_client import TopicClient
from config import MODEL_CAPTURE_FILTERING, MODEL_HOT_CACHE

logger = logging.getLogger(__name__)

RAG_SIMILARITY_THRESHOLD = 0.75

@celery_app.task(name="run_workflow_task")
def run_workflow_task(user_id: str, message: str, user_message_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Executes the heavy analysis workflow in a background task.
    """
    logger.info(f"Starting workflow task for user_id={user_id}, msg_id={user_message_id}")

    try:
        # 1. Initialize Clients
        ai_client = AIClient()
        repo = DBClient()
        knowledge_manager = KnowledgeManager()
        workflow_manager = WorkflowManager(ai_client)

        # 2. Load context (History & State)
        history = repo.get_recent_conversation(user_id)
        stored_state = repo.get_user_state(user_id)
        current_state = StateManager.get_state_with_defaults(stored_state)

        # 3. Initialize Workflow State
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

        # 4. Run Workflow
        final_state = workflow_manager.invoke(initial_state)
        bot_message = final_state.get("bot_message", "申し訳ありません、エラーが発生しました。")

        # Offload heavy processing to background task
        save_analysis_result_task.delay(user_id, message, final_state, user_message_id)

        return {
            "status": "success",
            "bot_message": bot_message,
            "task_id": run_workflow_task.request.id
        }

    except Exception as e:
        logger.error(f"Error in workflow task for user_id={user_id}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(name="save_analysis_result_task")
def save_analysis_result_task(user_id: str, message: str, final_state: Dict[str, Any], user_message_id: Optional[str]):
    """
    Background task to save analysis results, update graphs, and trigger cache generation.
    """
    try:
        # Initialize Clients
        repo = DBClient()
        knowledge_manager = KnowledgeManager()

        # Extract bot_message if needed for logging/saving (though inserted here per requirements)
        bot_message = final_state.get("bot_message", "")

        # --- Topic Service Integration ---
        try:
            topic_client = TopicClient()
            # Note: logging is handled inside TopicClient
            analysis_result = topic_client.analyze_content(message)
            categories = analysis_result.get("categories", [])

            if categories:
                # 1. Save detailed data (for Graph)
                final_state["interest_profile"]["categories"] = categories

                # 2. Sync main context (for Conversation)
                primary_category = categories[0]["name"]
                final_state["interest_profile"]["current_category"] = primary_category

                logger.info(f"Updated category profile: Main='{primary_category}', Count={len(categories)}")
        except Exception as e:
            logger.warning(f"Topic prediction failed: {e}")
        # ---------------------------------

        # 5. Save Results

        # --- Knowledge Graph Update Logic ---
        try:
            profile = final_state.get("interest_profile", {})
            categories = profile.get("categories", [])
            current_category = profile.get("current_category")

            # If no categories list, fallback to current_category (backward compatibility)
            if not categories and current_category:
                categories = [{"name": current_category, "confidence": 0.9, "keywords": []}]

            for cat in categories:
                cat_name = cat.get("name")
                if cat_name:
                    logger.info(f"Updating KG with category: {cat_name}")
                    knowledge_manager.graph_manager.add_category_and_keywords(
                        user_id=user_id,
                        category_name=cat_name,
                        confidence=cat.get("confidence", 0.9),
                        keywords=cat.get("keywords", []),
                        source_type="ai_inferred"
                    )

            # Update Hypotheses
            hypotheses_data = final_state.get("active_hypotheses", {})
            hypotheses = hypotheses_data.get("hypotheses", []) if isinstance(hypotheses_data, dict) else []

            if hypotheses:
                logger.info(f"Updating KG with {len(hypotheses)} hypotheses")
                for h in hypotheses:
                    h_text = h.get("text") if isinstance(h, dict) else str(h)

                    if h_text:
                        knowledge_manager.graph_manager.add_hypothesis(text=h_text)
                        if current_category:
                            knowledge_manager.graph_manager.link_hypothesis_to_concept(h_text, current_category)

        except Exception as e:
             logger.error(f"Failed to update Knowledge Graph: {e}")
        # ------------------------------------

        # Save updated state to MySQL
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

        if user_message_id:
            repo.record_analysis(user_id, user_message_id, analysis_to_save)

        # Insert AI message
        if bot_message:
            repo.insert_message(user_id, "ai", bot_message)

        logger.info(f"Background analysis saved for user_id={user_id}.")

        # --- Trigger Hot Cache Generation ---
        generate_hot_cache_task.delay(user_id)

    except Exception as e:
        logger.error(f"Error in save_analysis_result_task for user_id={user_id}: {e}", exc_info=True)


@celery_app.task(name="process_document_task")
def process_document_task(user_id: str, file_path: str, title: str, file_id: str, db_file_id: Optional[int] = None):
    """
    Background task to process uploaded documents (PDF).
    """
    local_path = None
    try:
        logger.info(f"Starting process_document_task for {file_path}")
        km = KnowledgeManager()
        repo = DBClient()

        # file_path argument is treated as S3 Key (Object Name)
        object_name = file_path

        # Download from S3 to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            local_path = tmp_file.name

        try:
            storage.download_file(object_name, local_path)
        except Exception as e:
            logger.error(f"Failed to download file from S3: {e}")
            if os.path.exists(local_path):
                os.remove(local_path)
            return {"status": "error", "message": "File download failed"}

        text_content = ""
        try:
            reader = pypdf.PdfReader(local_path)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        except Exception as e:
            logger.error(f"Error reading PDF: {e}")
            return {"status": "error", "message": f"PDF reading failed: {str(e)}"}
        finally:
            # Cleanup temp file
            if local_path and os.path.exists(local_path):
                os.remove(local_path)

        if not text_content.strip():
             return {"status": "error", "message": "No text content extracted"}

        # ---------------------------------------------------------
        # [New Logic] Iterative Category Detection
        # ---------------------------------------------------------
        topic_client = TopicClient()
        detected_categories = []

        # 判定用パラメータ
        chunk_size_detect = 1500
        overlap_detect = 500
        max_chunks_to_check = 5
        confidence_threshold = 0.40 # しきい値

        for i in range(max_chunks_to_check):
            start = i * (chunk_size_detect - overlap_detect)
            end = start + chunk_size_detect
            if start >= len(text_content):
                break

            chunk_text = text_content[start:end]
            if not chunk_text.strip():
                continue

            logger.info(f"Analyzing chunk {i+1} for document categorization...")

            # リストで結果を取得 (analyze_contentを使用)
            result = topic_client.analyze_content(chunk_text)
            candidates = result.get("categories", [])

            # しきい値を超える有効なカテゴリがあるかフィルタリング
            valid_candidates = [c for c in candidates if c.get("confidence", 0) >= confidence_threshold]

            if valid_candidates:
                detected_categories = valid_candidates
                logger.info(f"Categories detected in chunk {i+1}: {[c['name'] for c in valid_candidates]}")
                break # 有効な判定が出たら終了

        # 結果の決定
        if detected_categories:
            primary_category = detected_categories[0]["name"]
        else:
            primary_category = "Uncategorized"
            logger.warning(f"No reliable categories found for document: {title}")

        # ---------------------------------------------------------
        # [New Logic] Graph Update: Create File Node & Link to Categories
        # ---------------------------------------------------------
        try:
            # 1. Update Graph (Categories)
            if detected_categories:
                for cat in detected_categories:
                    km.graph_manager.add_category_and_keywords(
                        user_id=user_id,
                        category_name=cat["name"],
                        confidence=cat.get("confidence", 0.5),
                        keywords=[],
                        source_type="document_analysis"
                    )

            # 2. Create File Node (Document)
            file_url = f"/api/v1/user-files/{file_id}/content"
            km.graph_manager.add_document(
                text=title,
                file_id=file_id,
                url=file_url,
                properties={"title": title, "summary": f"Uploaded file: {title}"}
            )

            # Link to ALL detected categories
            linked_categories = []
            if detected_categories:
                for cat in detected_categories:
                    cat_name = cat.get("name")
                    if cat_name and cat_name not in ["Uncategorized", "General"]:
                        km.graph_manager.link_document_to_concept(
                            document_text=title,
                            concept_name=cat_name,
                            rel_type="BELONGS_TO"
                        )
                        linked_categories.append(cat_name)

            logger.info(f"Created File Node for {title} linked to {linked_categories}")

            # 3. Keyword Extraction & Filtering
            extracted_keywords = []
            try:
                # Load blocklist from categories.json
                blocklist = set()
                categories_path = os.path.join(os.path.dirname(__file__), "../../topic-service/categories.json")
                if os.path.exists(categories_path):
                    with open(categories_path, 'r', encoding='utf-8') as f:
                        cats_data = json.load(f)
                        for main_cat, data in cats_data.items():
                            blocklist.add(main_cat.lower())
                            for sub in data.get("subcategories", []):
                                blocklist.add(sub.get("category").lower())

                # LLM Extraction
                prompt_path = os.path.join(os.path.dirname(__file__), "../static/prompts/keyword_extraction.txt")
                with open(prompt_path, 'r') as f:
                    keyword_prompt_template = f.read()

                # Use the first 2000 chars or so for extraction
                keyword_prompt = keyword_prompt_template.replace("{text}", text_content[:2000])
                kw_result = km.ai_client.generate_json(keyword_prompt) # Use existing AI client from KM

                raw_keywords = kw_result.get("keywords", []) if kw_result else []

                # Filter keywords: Deduplicate and blocklist check (Case Insensitive)
                unique_keywords = []
                seen = set()

                for k in raw_keywords:
                    k_clean = k.strip()
                    k_lower = k_clean.lower()

                    if len(k_clean) > 1 and k_lower not in blocklist and k_lower not in seen:
                        unique_keywords.append(k_clean)
                        seen.add(k_lower)

                extracted_keywords = unique_keywords[:10]

                logger.info(f"Extracted Keywords for {title}: {extracted_keywords}")

                # Link to Document in Graph
                for kw in extracted_keywords:
                    km.graph_manager.link_document_to_keyword(
                        document_text=title,
                        keyword=kw,
                        rel_type="TAGGED_WITH"
                    )

            except Exception as e:
                logger.error(f"Keyword extraction failed: {e}")

            # 4. Update File Categories & Keywords in MySQL
            if db_file_id:
                category_names = [c["name"] for c in detected_categories] if detected_categories else []
                # Use the new method signature allowing keywords
                repo.update_file_category(
                    file_id=db_file_id,
                    categories=category_names,
                    is_verified=False,
                    keywords=extracted_keywords
                )
                logger.info(f"Updated MySQL user_files categories/keywords for file {db_file_id}")

        except Exception as e:
            logger.error(f"Failed to update Interest Graph or DB: {e}")

        # ---------------------------------------------------------
        # Chunking & Saving (Existing Logic with updates)
        # ---------------------------------------------------------
        # Chunking & Saving
        chunk_size = 1000
        overlap = 100
        chunks = []
        for i in range(0, len(text_content), chunk_size - overlap):
            chunks.append(text_content[i:i + chunk_size])

        success_count = 0

        # --- 修正開始: 新しい保存ロジック ---
        for i, chunk in enumerate(chunks):
            chunk_id = str(uuid.uuid4())

            # 1. Embedding生成
            vector = km.ai_client.get_embedding(chunk)
            if not vector:
                continue

            # 2. Qdrant (Vector DB) へ保存
            # DocumentChunkとして保存し、検索可能にする
            payload = {
                "user_id": user_id,
                "category": primary_category,
                "type": "document_chunk",
                "visibility": "private",
                "content": chunk,
                "meta": {
                    "file_id": file_id,
                    "title": title,
                    "chunk_index": i,
                    "source": "uploaded_file"
                }
            }
            try:
                km._setup_qdrant_collection()
                km.qdrant_client.upsert(
                    collection_name=km.collection_name,
                    points=[PointStruct(id=chunk_id, vector=vector, payload=payload)]
                )
            except Exception as e:
                logger.error(f"Qdrant upsert failed: {e}")
                continue

            # 3. Graph (Structure) へ保存
            try:
                # Chunkノードを作成
                km.graph_manager.add_chunk(
                    text=chunk,
                    evidence_ids=[chunk_id],
                    properties={"index": i, "file_id": file_id}
                )

                # Fileノードにリンク (DocumentChunk -[PART_OF]-> Document)
                # ※ title は add_document で作成した text と一致させる必要があります
                km.graph_manager.link_chunk_to_document(
                    chunk_text=chunk,
                    file_node_text=title,
                    rel_type="PART_OF"
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Graph update failed for chunk {i}: {e}")
        # --- 修正終了 -----------------------

        logger.info(f"Processed {success_count} chunks for {title}")
        return {"status": "completed", "chunks_processed": success_count}

    except Exception as e:
        logger.error(f"Task failed: {e}", exc_info=True)
        return {"status": "failed", "error": str(e)}

@celery_app.task(name="process_capture_task")
def process_capture_task(payload: Dict[str, Any]):
    """
    Background task to process browser captures.
    """
    logger.info(f"Processing capture for url: {payload.get('url')}")

    try:
        user_id = payload.get("user_id")
        content = payload.get("content", "")
        url = payload.get("url", "")
        title = payload.get("title", "")
        screenshot_url = payload.get("screenshot_url")

        if not user_id or not content:
            logger.warning("Missing user_id or content in capture payload")
            return

        ai_client = AIClient()
        knowledge_manager = KnowledgeManager()
        repo = DBClient()

        if knowledge_manager.is_duplicate_content(content):
            logger.info(f"Duplicate content skipped: {url}")
            return {"status": "skipped", "reason": "duplicate"}

        prompt_path = os.path.join(os.path.dirname(__file__), "../static/prompts/content_filtering.txt")
        try:
            with open(prompt_path, "r") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            prompt_template = "Classify content: {content}. Return JSON {{category: 'Interest'|'Operation'|'Notification'}}"

        prompt = prompt_template.replace("{content}", content[:2000])
        classification_res = ai_client.generate_json(prompt, model=MODEL_CAPTURE_FILTERING)

        category = classification_res.get("category", "Notification")
        reason = classification_res.get("reason", "")

        logger.info(f"Capture classified as: {category} ({reason})")

        if category == "Interest":
            capture_id = repo.save_captured_page(
                user_id=user_id,
                url=url,
                title=title,
                content=content,
                screenshot_url=screenshot_url
            )

            visibility = "private"
            trusted_domains = [".go.jp", ".ac.jp"]
            if any(url.endswith(d) or f"{d}/" in url for d in trusted_domains):
                visibility = "public"

            summary = f"Title: {title}\nURL: {url}\n\n{content[:1000]}"
            meta = {"source_url": url, "title": title, "capture_id": capture_id}

            if visibility == "public":
                knowledge_manager.add_shared_fact(summary, "webhook_capture", meta)
            else:
                category_for_memory = "CapturedInterest"
                try:
                    topic_client = TopicClient()
                    # Logging handled inside TopicClient
                    analysis = topic_client.analyze_content(content[:500])
                    categories = analysis.get("categories", [])

                    if categories:
                        category_for_memory = categories[0]["name"]
                        meta["detected_categories"] = categories

                        for cat in categories:
                            knowledge_manager.graph_manager.add_category_and_keywords(
                                user_id=user_id,
                                category_name=cat["name"],
                                confidence=cat["confidence"],
                                keywords=cat["keywords"],
                                source_type="ai_inferred_capture"
                            )
                except Exception as e:
                    logger.warning(f"Topic analysis failed in capture: {e}")

                knowledge_manager.add_user_memory(
                    user_id=user_id,
                    content=summary,
                    memory_type="user_hypothesis",
                    category=category_for_memory,
                    meta=meta
                )

            logger.info(f"Saved 'Interest' content for user {user_id}")
            generate_hot_cache_task.delay(user_id)

        else:
            logger.info(f"Skipping storage for category: {category}")

    except Exception as e:
        logger.error(f"Error in process_capture_task: {e}", exc_info=True)


@celery_app.task(name="generate_hot_cache_task")
def generate_hot_cache_task(user_id: str):
    """
    Generates 'Hot Cache' (suggestions/questions) for the user based on recent context.
    Saves result to Redis.
    """
    logger.info(f"Generating Hot Cache for user_id={user_id}")

    try:
        # Initialize
        ai_client = AIClient()
        knowledge_manager = KnowledgeManager()
        graph_manager = knowledge_manager.graph_manager # Reuse attached graph manager
        repo = DBClient()

        # 1. Gather Context
        # Graph: Recent Interests
        interests_nodes = graph_manager.get_user_interests(user_id)
        interests = [i['name'] for i in interests_nodes[:5]] # Top 5

        # DB: Active Hypotheses
        user_state = repo.get_user_state(user_id)
        hypotheses_data = user_state.get("active_hypotheses", {})
        # Normalize hypothesis structure
        if isinstance(hypotheses_data, dict):
             hypotheses_list = hypotheses_data.get("hypotheses", [])
             # Extract text if objects
             hypotheses = [h['text'] if isinstance(h, dict) else str(h) for h in hypotheses_list]
        else:
            hypotheses = []

        # Vector: Fetch related memories
        memories = []
        if interests:
            query_text = " ".join(interests[:3])
            # Use raw Qdrant client from KnowledgeManager since search method isn't fully exposed
            try:
                embedding = ai_client.get_embedding(query_text)
                if embedding and knowledge_manager.qdrant_client.collection_exists(knowledge_manager.collection_name):
                    results = knowledge_manager.qdrant_client.query_points(
                        collection_name=knowledge_manager.collection_name,
                        query=embedding,
                        limit=3,
                        query_filter=None # We could filter by user_id here but keeping it broad for context
                    ).points

                    # 閾値によるフィルタリング
                    valid_results = [p for p in results if p.score >= RAG_SIMILARITY_THRESHOLD]

                    if not valid_results:
                        memories = []
                    else:
                        memories = [point.payload.get("content", "") for point in valid_results if point.payload]

            except Exception as e:
                logger.warning(f"Failed to fetch related memories: {e}")

        if not interests and not hypotheses:
            logger.info("No sufficient context for Hot Cache.")
            return

        # 2. LLM Generation
        prompt_path = os.path.join(os.path.dirname(__file__), "../static/prompts/hot_cache_generation.txt")
        try:
            with open(prompt_path, "r") as f:
                prompt_temp = f.read()
        except FileNotFoundError:
             prompt_temp = "Context: {interests}. Suggest 3 next questions in JSON {{suggestions: [...]}}"

        prompt = prompt_temp.format(
            interests=", ".join(interests),
            hypotheses=", ".join(hypotheses[:3]),
            memories="\n".join(memories) if memories else "None"
        )

        result = ai_client.generate_json(prompt, model=MODEL_HOT_CACHE)

        # 3. Save to Redis
        if result and "suggestions" in result:
            redis_url = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
            r = redis.from_url(redis_url)

            # Key: hot_cache:{user_id}
            # Expiration: 3600 seconds (1 hour) - Cache is short-lived context
            r.setex(
                f"hot_cache:{user_id}",
                3600,
                json.dumps(result)
            )
            logger.info(f"Hot cache updated for user {user_id}: {len(result['suggestions'])} suggestions")

    except Exception as e:
        logger.error(f"Error in generate_hot_cache_task: {e}", exc_info=True)
