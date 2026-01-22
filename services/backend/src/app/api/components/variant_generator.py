import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient
from config import MODEL_INNOVATION_SYNTHESIS

class VariantGenerator:
    """
    亜種生成を行うコンポーネント。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[2] / "static/prompts/variant_generation.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        構造分解された要素から亜種を生成する。
        """
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_response(prompt, model=MODEL_INNOVATION_SYNTHESIS)

        if response and "idea_variants" in response:
            context["idea_variants"] = response["idea_variants"]

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        structural_analysis = context.get("structural_analysis", {})
        analysis_str = json.dumps(structural_analysis, ensure_ascii=False, indent=2)

        return f"{self.base_prompt}\n\nStructural Analysis:\n{analysis_str}"
