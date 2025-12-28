import logging
import asyncio
from typing import Dict, Any, Optional

from app.core.celery_app import celery_app
from app.api.workflow import WorkflowManager
from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.state_manager import StateManager
from app.api.components.knowledge_manager import KnowledgeManager

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
            # active_hypotheses might be a dict with a list 'hypotheses' or just the dict itself depending on structure
            # Based on user snippet: hypotheses = final_state.get("active_hypotheses", {}).get("hypotheses", [])
            hypotheses = hypotheses_data.get("hypotheses", []) if isinstance(hypotheses_data, dict) else []

            if hypotheses:
                logger.info(f"Updating KG with {len(hypotheses)} hypotheses")
                for h in hypotheses:
                    # h might be a dict or string
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

        return {
            "status": "success",
            "bot_message": bot_message,
            "task_id": run_workflow_task.request.id
        }

    except Exception as e:
        logger.error(f"Error in workflow task for user_id={user_id}: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
