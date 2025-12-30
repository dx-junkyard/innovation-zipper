import logging
import asyncio
import json
import os
import redis
import pypdf
import uuid
from typing import Dict, Any, Optional

from app.core.celery_app import celery_app
from app.api.workflow import WorkflowManager
from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.state_manager import StateManager
from app.api.components.knowledge_manager import KnowledgeManager
from app.api.components.topic_client import TopicClient
from config import MODEL_CAPTURE_FILTERING, MODEL_HOT_CACHE

logger = logging.getLogger(__name__)

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

        # --- Topic Service Integration ---
        try:
            topic_client = TopicClient()
            predicted_category = topic_client.predict_category(message)
            if predicted_category:
                logger.info(f"Topic Service predicted: {predicted_category}")
                # Override or fallback the category
                final_state["interest_profile"]["current_category"] = predicted_category
        except Exception as e:
            logger.warning(f"Topic prediction failed: {e}")
        # ---------------------------------

        # 5. Save Results

        # --- Knowledge Graph Update Logic ---
        try:
            # Update User Interest (Current Category)
            profile = final_state.get("interest_profile", {})
            current_category = profile.get("current_category")

            if current_category:
                logger.info(f"Updating KG with category: {current_category}")
                knowledge_manager.graph_manager.add_user_interest(
                    user_id=user_id,
                    concept_name=current_category,
                    confidence=0.9,
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
        repo.insert_message(user_id, "ai", bot_message)

        logger.info(f"Workflow task completed for user_id={user_id}. Bot message: {bot_message[:50]}...")

        # --- Trigger Hot Cache Generation ---
        generate_hot_cache_task.delay(user_id)

        return {
            "status": "success",
            "bot_message": bot_message,
            "task_id": run_workflow_task.request.id
        }

    except Exception as e:
        logger.error(f"Error in workflow task for user_id={user_id}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@celery_app.task(name="process_document_task")
def process_document_task(user_id: str, file_path: str, title: str, file_id: str):
    """
    Background task to process uploaded documents (PDF).
    Extracts text, chunks it, and saves it to KnowledgeManager with metadata.
    """
    try:
        print(f"Starting process_document_task for {file_path}")
        km = KnowledgeManager()

        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            return {"status": "error", "message": "File not found"}

        text_content = ""
        try:
            reader = pypdf.PdfReader(file_path)
            for page in reader.pages:
                text_content += page.extract_text() + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
            return {"status": "error", "message": f"PDF reading failed: {str(e)}"}

        if not text_content.strip():
             return {"status": "error", "message": "No text content extracted"}

        # Simple Chunking (can be improved with LangChain RecursiveCharacterTextSplitter later)
        chunk_size = 1000
        overlap = 100
        chunks = []
        for i in range(0, len(text_content), chunk_size - overlap):
            chunks.append(text_content[i:i + chunk_size])

        # Infer category using TopicClient
        try:
            topic_client = TopicClient()
            # Use first 1000 chars for prediction
            predicted_category = topic_client.predict_category(text_content[:1000])
        except Exception as e:
            print(f"Topic prediction failed for document: {e}")
            predicted_category = None

        # Fallback if prediction fails or returns None
        final_category = predicted_category if predicted_category else "Uncategorized"

        success_count = 0
        for i, chunk in enumerate(chunks):
            # Add to Knowledge Base with Metadata
            meta = {
                "file_id": file_id,
                "title": title,
                "chunk_index": i,
                "source": "uploaded_file"
            }

            # Using 'user_stated' or 'user_hypothesis' type?
            # Files are usually "external info" but for RAG purposes we treat them as private memory for now.
            if km.add_user_memory(
                user_id=user_id,
                content=chunk,
                memory_type="document_chunk",
                category=final_category,
                meta=meta
            ):
                success_count += 1

        print(f"Processed {success_count} chunks for {title}")
        return {"status": "completed", "chunks_processed": success_count}

    except Exception as e:
        print(f"Task failed: {e}")
        return {"status": "failed", "error": str(e)}

@celery_app.task(name="process_capture_task")
def process_capture_task(payload: Dict[str, Any]):
    """
    Background task to process browser captures.
    Filters content (Filter Agent) and saves important knowledge.
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

        # 1. Check Duplicates (KnowledgeBase level)
        if knowledge_manager.is_duplicate_content(content):
            logger.info(f"Duplicate content skipped: {url}")
            return {"status": "skipped", "reason": "duplicate"}

        # 2. Filter Agent (LLM Classification)
        # Load prompt
        prompt_path = os.path.join(os.path.dirname(__file__), "../static/prompts/content_filtering.txt")
        try:
            with open(prompt_path, "r") as f:
                prompt_template = f.read()
        except FileNotFoundError:
            # Fallback if file not found
            prompt_template = "Classify content: {content}. Return JSON {{category: 'Interest'|'Operation'|'Notification'}}"

        prompt = prompt_template.replace("{content}", content[:2000]) # Limit content for token efficiency

        classification_res = ai_client.generate_json(prompt, model=MODEL_CAPTURE_FILTERING)

        category = classification_res.get("category", "Notification")
        reason = classification_res.get("reason", "")

        logger.info(f"Capture classified as: {category} ({reason})")

        # 3. Action based on Category
        if category == "Interest":
            # Save to SQL (Raw Log)
            capture_id = repo.save_captured_page(
                user_id=user_id,
                url=url,
                title=title,
                content=content,
                screenshot_url=screenshot_url
            )

            # Save to Knowledge Base (Vector/Graph)
            # Determine visibility/type
            visibility = "private"
            trusted_domains = [".go.jp", ".ac.jp"]
            if any(url.endswith(d) or f"{d}/" in url for d in trusted_domains):
                visibility = "public"

            summary = f"Title: {title}\nURL: {url}\n\n{content[:1000]}"
            meta = {"source_url": url, "title": title, "capture_id": capture_id}

            if visibility == "public":
                knowledge_manager.add_shared_fact(summary, "webhook_capture", meta)
            else:
                # --- Topic Service Integration for Capture ---
                category_for_memory = "CapturedInterest"
                try:
                    topic_client = TopicClient()
                    pred = topic_client.predict_category(content[:500]) # Use first 500 chars
                    if pred:
                        category_for_memory = pred
                except:
                    pass
                # ---------------------------------------------

                knowledge_manager.add_user_memory(
                    user_id=user_id,
                    content=summary,
                    memory_type="user_hypothesis",
                    category=category_for_memory,
                    meta=meta
                )

            logger.info(f"Saved 'Interest' content for user {user_id}")

            # Trigger Hot Cache update because knowledge changed
            generate_hot_cache_task.delay(user_id)

        else:
            logger.info(f"Skipping storage for category: {category}")
            # We do NOT save to SQL or KB for Operation/Notification

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
                    results = knowledge_manager.qdrant_client.search(
                        collection_name=knowledge_manager.collection_name,
                        query_vector=embedding,
                        limit=3,
                        query_filter=None # We could filter by user_id here but keeping it broad for context
                    )
                    memories = [point.payload.get("content", "") for point in results if point.payload]
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
