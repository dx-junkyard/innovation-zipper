import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient
from config import MODEL_STRUCTURAL_ANALYSIS

class StructuralAnalyzer:
    """
    課題の構造分解を行うコンポーネント。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/structural_analysis.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        ユーザーの課題を構造分解する。
        """
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_response(prompt, model=MODEL_STRUCTURAL_ANALYSIS)

        if response and "structural_analysis" in response:
            context["structural_analysis"] = response["structural_analysis"]

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        user_message = context.get("user_message", "")
        conversation_summary = context.get("interest_profile", {}).get("conversation_summary", "")
        
        # Also include recent history for immediate context if needed, but instructions emphasize summary.
        # "直近1〜2件のやり取りと、上記の「まとめ」のみを送信する構成"
        dialog_history = context.get("dialog_history", [])
        recent_history = dialog_history[-2:] if dialog_history else []
        recent_msgs_str = "\n".join([f"{msg.get('role')}: {msg.get('message')}" for msg in recent_history])

        return f"{self.base_prompt}\n\nContext:\nConversation Summary:\n{conversation_summary}\n\nRecent Messages:\n{recent_msgs_str}\n\nUser Message:\n{user_message}"
