import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient
from config import MODEL_INTEREST_EXPLORATION

class InterestExplorer:
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/interest_exploration.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def explore(self, context: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_response(prompt, model=MODEL_INTEREST_EXPLORATION)

        result = {
            "bot_message": "...",
            "suggested_mode": "discovery",
            "analysis_log": {}
        }

        if response:
            if "bot_message" in response:
                result["bot_message"] = response["bot_message"]
            if "suggested_next_mode" in response:
                 # "discovery" 以外が提案された場合、その意図を保持する
                 result["suggested_mode"] = response["suggested_next_mode"]
            if "analysis_log" in response:
                result["analysis_log"] = response["analysis_log"]

        return result

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        conversation_summary = context.get("interest_profile", {}).get("conversation_summary", "")
        # Fallback to recent messages if summary is empty, or just use what we have.
        # But per instructions, we should perform the switch.
        # We also need the current message? The user instructions said:
        # "直近1〜2件のやり取りと、上記の「まとめ」のみを送信する構成"
        
        history = context.get("dialog_history", [])
        recent_history = history[-2:] if history else []
        recent_msgs_str = "\n".join([f"{msg.get('role')}: {msg.get('message')}" for msg in recent_history])

        current_profile = json.dumps(context.get("interest_profile", {}), ensure_ascii=False, indent=2)

        return f"{self.base_prompt}\n\nInterest Profile:\n{current_profile}\n\nConversation Summary:\n{conversation_summary}\n\nRecent Messages:\n{recent_msgs_str}"
