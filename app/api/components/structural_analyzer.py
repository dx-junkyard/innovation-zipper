import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient

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
        response = self.ai_client.generate_response(prompt)

        if response and "structural_analysis" in response:
            context["structural_analysis"] = response["structural_analysis"]

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        user_message = context.get("user_message", "")
        dialog_history = context.get("dialog_history", [])

        # 単純な履歴の結合
        history_str = "\n".join([f"{msg.get('role')}: {msg.get('content')}" for msg in dialog_history])

        return f"{self.base_prompt}\n\nContext:\nHistory:\n{history_str}\nUser Message:\n{user_message}"
