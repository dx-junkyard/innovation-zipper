import json
import logging
from pathlib import Path
from typing import Dict, Any, Tuple
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient
from config import MODEL_RESPONSE_PLANNING, MODEL_FAST, MODEL_SMART

logger = logging.getLogger(__name__)

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
        # Determine Mode and settings
        mode = context.get("mode", "explorer") # Default to explorer if missing

        # Default settings
        model_to_use = MODEL_RESPONSE_PLANNING # Default fallback
        system_instruction = ""

        if mode == "explorer":
            # Explorer Mode settings
            model_to_use = MODEL_FAST
            system_instruction = (
                "【システム指示】\n"
                "・簡潔に答えてください。\n"
                "・詳細は省き、ユーザーが興味を持ちそうなポイントを短く提示してください。\n"
                "・レスポンスの速さを優先します。\n"
                "・500文字以内で回答してください。\n"
            )
            logger.info("ResponsePlanner: Using Explorer Mode (Fast/Concise)")

        elif mode == "deep_dive":
            # Deep Dive Mode settings
            model_to_use = MODEL_SMART
            system_instruction = (
                "【システム指示】\n"
                "・専門家として振る舞ってください。\n"
                "・マークダウンを用いて構造化された長文レポートを作成してください。\n"
                "・多角的な視点、背景、構造分析を含めてじっくり解説してください。\n"
                "・文字数制限はありません。\n"
            )
            logger.info("ResponsePlanner: Using Deep Dive Mode (Smart/Detailed)")

        # Create base prompt
        base_prompt = self._create_prompt(context)

        # Inject system instruction at the beginning
        final_prompt = f"{system_instruction}\n\n{base_prompt}"

        result = self.ai_client.generate_response(final_prompt, model=model_to_use)

        bot_message = None
        if result:
            # コンテキストへの保存（既存）
            if isinstance(result, dict):
                context["response_plan"] = result
            else:
                context["response_plan"] = {"message": str(result)}

            # 【修正箇所】bot_message への代入を追加
            if isinstance(result, str):
                bot_message = result
            elif isinstance(result, dict):
                # 辞書からメッセージを抽出（キーの揺らぎを吸収）
                bot_message = (
                    result.get("message") or
                    result.get("answer") or
                    result.get("content") or
                    json.dumps(result, ensure_ascii=False) # 見つからなければJSON全体を文字列化
                )

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
