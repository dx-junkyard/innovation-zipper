import json
from pathlib import Path
from typing import Dict, Any
from app.api.ai_client import AIClient
from config import MODEL_INNOVATION_SYNTHESIS

class InnovationSynthesizer:
    """
    仮説構築を行うコンポーネント。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/innovation_synthesis.txt"
        with open(prompt_path, "r", encoding="utf-8") as f:
            self.base_prompt = f.read()

    def synthesize(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        亜種を結合して仮説を構築する。
        """
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_response(prompt, model=MODEL_INNOVATION_SYNTHESIS)

        if response:
            if "innovation_hypotheses" in response:
                context["innovation_hypotheses"] = response["innovation_hypotheses"]
            if "bot_message" in response:
                context["bot_message"] = response["bot_message"]

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        idea_variants = context.get("idea_variants", {})
        # 構造分析の結果もコンテキストに追加
        structural_analysis = context.get("structural_analysis", {})
        
        variants_str = json.dumps(idea_variants, ensure_ascii=False, indent=2)
        analysis_str = json.dumps(structural_analysis, ensure_ascii=False, indent=2)

        return f"{self.base_prompt}\n\nOriginal Structure:\n{analysis_str}\n\nIdea Variants:\n{variants_str}"
