import json
from pathlib import Path
from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient
from app.api.state_manager import StateManager

class SituationAnalyzer:
    """
    状況整理コンポーネント。
    static/prompts/situation_analysis.txt で定義されたプロンプトを使用して、
    ユーザーの発話と会話履歴をもとに、住民プロファイルとサービスニーズを更新する。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        # プロンプトファイルのパス解決 (project_root/static/prompts/situation_analysis.txt)
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/situation_analysis.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        現状の分析を実行する。
        static/prompts/situation_analysis.txt で定義されたプロンプトを使用して、
        AIClient経由で分析を行う。

        Args:
            context (Dict[str, Any]): 現在の会話コンテキスト

        Returns:
            Dict[str, Any]: 更新されたコンテキスト
        """
        prompt = self._create_prompt(context)

        # Use generic generate_response instead of analyze_interaction
        analysis_result = self.ai_client.generate_response(prompt)

        if analysis_result:
            normalized_analysis = StateManager.normalize_analysis(analysis_result)
            if normalized_analysis:
                context["interest_profile"] = normalized_analysis["interest_profile"]
                context["active_hypotheses"] = normalized_analysis["active_hypotheses"]

            # Save updated conversation summary if present
            if "conversation_summary" in analysis_result:
                context["conversation_summary"] = analysis_result["conversation_summary"]

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        """
        LLMへのプロンプトを作成する。
        """
        current_state = {
            "interest_profile": context.get("interest_profile", {}),
            "active_hypotheses": context.get("active_hypotheses", {})
        }

        state_dump = json.dumps(current_state, ensure_ascii=False, indent=2)
        conversation_summary = context.get("conversation_summary", "")
        latest_user_message = context.get("user_message", "")

        # Capture page context
        captured_page = context.get("captured_page", {}) or {}
        page_title = captured_page.get("title", "No page detected")
        page_url = captured_page.get("url", "")
        page_content = captured_page.get("content", "")[:1000] # Limit content length

        # Get last AI message from history
        history = context.get("dialog_history", [])
        last_ai_message = "（会話開始）"
        for msg in reversed(history):
            if msg.get("role") == "assistant" or msg.get("role") == "ai":
                last_ai_message = msg.get("content", "") or msg.get("message", "")
                break

        return self.prompt_template.format(
            current_state=state_dump,
            page_title=page_title,
            page_url=page_url,
            page_content=page_content,
            conversation_summary=conversation_summary,
            last_ai_message=last_ai_message,
            latest_user_message=latest_user_message
        )