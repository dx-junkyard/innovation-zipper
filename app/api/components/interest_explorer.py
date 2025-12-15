import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient

class InterestExplorer:
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/interest_exploration.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def explore(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_response(prompt)

        result = {
            "bot_message": "...",
            "suggested_mode": "discovery"
        }

        if response:
            if "bot_message" in response:
                result["bot_message"] = response["bot_message"]
            if "suggested_next_mode" in response:
                 # "discovery" 以外が提案された場合、その意図を保持する
                 result["suggested_mode"] = response["suggested_next_mode"]

        return result

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        history = context.get("dialog_history", [])
        recent_history = history[-10:] if history else []
        history_str = "\n".join([f"{msg.get('role')}: {msg.get('content')}" for msg in recent_history])
        current_profile = json.dumps(context.get("interest_profile", {}), ensure_ascii=False, indent=2)

        return f"{self.base_prompt}\n\nInterest Profile:\n{current_profile}\n\nRecent Conversation:\n{history_str}"
