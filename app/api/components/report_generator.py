import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient

class ReportGenerator:
    """
    レポート生成を行うコンポーネント。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/report_generation.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        これまでの情報をまとめてレポートを生成する。
        """
        prompt = self._create_prompt(context)
        # Note: Report generation might return a long string.
        # AIClient.generate_response is expected to return a Dict parsed from JSON.
        # But report_generation.txt instruction says "Markdown形式のレポートを作成します"
        # And usually we expect JSON response because of AIClient implementation.
        # I should probably ask for a JSON wrapper like {"report_content": "..."} in the prompt?
        # But the instruction was just "Markdown形式のレポートを作成します".
        # However, looking at the other prompts provided by user, they have "出力フォーマット: { ... }".
        # The report prompt says "セクション: ...". It doesn't explicitly define JSON output format.
        # But AIClient expects JSON.
        # I will wrap the prompt to request JSON wrapper if AIClient is strict.
        # Let's check AIClient implementation details later if needed.
        # For now, I'll rely on AIClient enforcing JSON if configured so.
        # But to be safe, I will append an instruction to wrap it in JSON.

        # Actually, let's look at `ai_client.py`.
        # I'll check if it strictly expects JSON.

        response = self.ai_client.generate_response(prompt)

        # Assuming the AI returns something like {"report": "markdown content"} or similar if I asked for it.
        # Since I can't change the prompt file content (it was specified by user),
        # I will handle the response.
        # If the user prompt didn't ask for JSON, AIClient might fail if it tries to parse JSON.
        # However, the user said "AIClient enforces a JSON object response format".
        # So the model IS trained/instructed to return JSON?
        # Or maybe I should append "Output as JSON: { 'report': '...' }" to the prompt.

        if response:
             # If response is a dict, we look for some key or just dump it?
             # If the prompt didn't specify JSON keys, the LLM might choose any key.
             # I'll try to find a likely key or just take the whole thing.
             if isinstance(response, dict):
                 # Try to find a string value that looks like the report
                 report_content = response.get("report") or response.get("content") or response.get("markdown") or str(response)
                 context["bot_message"] = report_content
             else:
                 context["bot_message"] = str(response)

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        history = context.get("dialog_history", [])
        structural_analysis = context.get("structural_analysis", {})
        innovation_hypotheses = context.get("innovation_hypotheses", [])

        data = {
            "history": history,
            "structural_analysis": structural_analysis,
            "innovation_hypotheses": innovation_hypotheses
        }
        data_str = json.dumps(data, ensure_ascii=False, indent=2)

        return f"{self.base_prompt}\n\nData:\n{data_str}\n\nIMPORTANT: Please output the result as a JSON object with a key 'report' containing the Markdown text."
