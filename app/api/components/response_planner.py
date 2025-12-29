import json
from pathlib import Path
from typing import Dict, Any, Tuple
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient

class ResponsePlanner:
    """
    応答設計コンポーネント。
    分析結果と検索結果をもとに、ユーザーへの応答を計画・生成する。
    """
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        # プロンプトファイルのパス解決 (project_root/static/prompts/response_planning.txt)
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/response_planning.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def plan_response(self, context: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
        """
        応答を計画し、最終的なメッセージを生成する。

        Args:
            context (Dict[str, Any]): 現在の会話コンテキスト

        Returns:
            Tuple[Dict[str, Any], str]: 応答計画が追加されたコンテキストと、ボットのメッセージ
        """
        prompt = self._create_prompt(context)

        result = self.ai_client.generate_response(prompt)

        bot_message = "申し訳ありません、うまく応答を生成できませんでした。"
        if result:
            if isinstance(result, str):
                bot_message = result
            elif isinstance(result, dict):
                 bot_message = result.get("message_text") or result.get("message") or str(result)

        return context, bot_message

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        """
        LLMへのプロンプトを作成する。
        """
        interest_profile_str = json.dumps(context.get('interest_profile', {}), ensure_ascii=False, indent=2)
        active_hypotheses_str = json.dumps(context.get('active_hypotheses', {}), ensure_ascii=False, indent=2)
        hypotheses_str = json.dumps(context.get('hypotheses', []), ensure_ascii=False, indent=2)

        # Format retrieval evidence with tags [MEMORY] / [FACT] and citation
        retrieval_evidence = context.get('retrieval_evidence', {}).get('results', [])
        formatted_evidence = []
        for item in retrieval_evidence:
            source_tag = "[FACT]" if item.get("source_type") == "public_fact" else "[MEMORY]"
            title = item.get("title")
            content = item.get("content", "")[:300] # Truncate for prompt

            citation = f" (Source: {title})" if title else ""
            formatted_evidence.append(f"{source_tag}{citation} {content}")

        retrieval_evidence_str = "\n".join(formatted_evidence)

        captured_page = context.get("captured_page", {}) or {}
        page_title = captured_page.get("title", "No page detected")

        knowledge_gaps_str = json.dumps(context.get('knowledge_gaps', []), ensure_ascii=False, indent=2)

        # Assuming the new prompt uses {user_goal} instead of {interest_profile} directly, or both.
        # The new prompt uses: user_goal, active_hypotheses, retrieval_evidence, knowledge_gaps.
        # Let's map these.

        user_goal = context.get('interest_profile', {}).get('intent', {}).get('goal', 'Unknown Goal')

        return self.prompt_template.format(
            user_goal=user_goal,
            page_title=page_title,
            active_hypotheses=active_hypotheses_str,
            hypotheses=hypotheses_str,
            retrieval_evidence=retrieval_evidence_str,
            knowledge_gaps=knowledge_gaps_str
        )
