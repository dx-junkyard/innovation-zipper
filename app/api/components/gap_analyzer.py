import json
from pathlib import Path
from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient
from config import MODEL_GAP_ANALYSIS

class GapAnalyzer:
    """
    ギャップ分析コンポーネント。
    RAGの検索結果を分析し、「検証済」「類推可能」「要現場検証」に分類する。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/gap_analysis.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        検索結果のギャップ分析を実行する。
        """
        prompt = self._create_prompt(context)
        response = self.ai_client.generate_json(prompt, model=MODEL_GAP_ANALYSIS)

        knowledge_gaps = []
        if response and isinstance(response, dict) and "knowledge_gaps" in response:
            knowledge_gaps = response["knowledge_gaps"]

        return {"knowledge_gaps": knowledge_gaps}

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        user_goal = context.get("interest_profile", {}).get("intent", {}).get("goal", "Unknown Goal")
        active_hypotheses = json.dumps(context.get("active_hypotheses", {}), ensure_ascii=False)
        retrieval_evidence = json.dumps(context.get("retrieval_evidence", {}), ensure_ascii=False)

        return self.prompt_template.format(
            user_goal=user_goal,
            active_hypotheses=active_hypotheses,
            retrieval_evidence=retrieval_evidence
        )
