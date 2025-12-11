import json
from pathlib import Path
from typing import Dict, Any
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient

class HypothesisGenerator:
    """
    仮説生成コンポーネント。
    整理された状況情報から、必要なサービス候補群を仮説化する。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        # プロンプトファイルのパス解決 (project_root/static/prompts/hypothesis_generation.txt)
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/hypothesis_generation.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def generate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        現在のコンテキストに基づいて仮説を生成する。

        Args:
            context (Dict[str, Any]): 現在の会話コンテキスト

        Returns:
            Dict[str, Any]: 仮説が追加されたコンテキスト
        """
        prompt = self._create_prompt(context)
        result = self.ai_client.generate_response(prompt)

        # If result is a list, it's likely the hypotheses list itself
        if isinstance(result, list):
             context["hypotheses"] = result
        elif isinstance(result, dict) and "hypotheses" in result:
            context["hypotheses"] = result["hypotheses"]
        else:
            # Fallback if the AI returns something else but maybe parsable
            context["hypotheses"] = result if isinstance(result, list) else []

        return context

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        """
        LLMへのプロンプトを作成する。
        """
        # テンプレートに渡す変数を事前にJSON文字列化
        interest_profile_str = json.dumps(context.get('interest_profile', {}), ensure_ascii=False, indent=2)
        active_hypotheses_str = json.dumps(context.get('active_hypotheses', {}), ensure_ascii=False, indent=2)

        captured_page = context.get("captured_page", {}) or {}
        page_title = captured_page.get("title", "No page detected")
        page_content = captured_page.get("content", "")[:1000]

        return self.prompt_template.format(
            interest_profile=interest_profile_str,
            active_hypotheses=active_hypotheses_str,
            page_title=page_title,
            page_content=page_content
        )