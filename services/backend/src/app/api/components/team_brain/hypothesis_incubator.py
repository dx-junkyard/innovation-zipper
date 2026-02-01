"""
Hypothesis Incubator (FR-103)

1階: 思考の私有地 (Private Layer)
経験の言語化と仮説の構造化を行うコンポーネント。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.prompts import PromptTemplate

from app.api.ai_client import AIClient
from app.api.db import DBClient
from config import MODEL_HYPOTHESIS_GENERATION

logger = logging.getLogger(__name__)


class HypothesisIncubator:
    """
    仮説形成アシスタント（Hypothesis Incubator）

    ユーザーの雑多なメモや日報（経験）から、因果関係や法則性を抽出して
    「仮説」として構造化する。

    プロセス:
    1. ユーザーが経験を入力
    2. AIが仮説として再定義・構造化して提示
    3. ユーザーと共に仮説のブラッシュアップを行う
    """

    def __init__(self, ai_client: AIClient, db_client: Optional[DBClient] = None):
        self.ai_client = ai_client
        self.db_client = db_client or DBClient()

        # プロンプトファイルの読み込み
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/hypothesis_incubator.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def incubate(
        self,
        user_id: str,
        experience: str,
        interest_profile: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        経験から仮説を生成する。

        Args:
            user_id: ユーザーID
            experience: ユーザーの経験・メモ
            interest_profile: ユーザーの興味プロファイル

        Returns:
            構造化された仮説と関連情報
        """
        # 既存の仮説を取得
        existing_hypotheses = self.db_client.get_user_hypotheses(
            user_id, status="DRAFT", limit=10
        )

        # プロンプトの作成
        prompt = self._create_prompt(
            experience,
            existing_hypotheses,
            interest_profile or {}
        )

        # AIによる仮説生成
        result = self.ai_client.generate_response(
            prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            logger.warning("Failed to generate hypothesis from AI")
            return {
                "success": False,
                "error": "AI response generation failed"
            }

        # 仮説をデータベースに保存
        structured_hypothesis = result.get("structured_hypothesis", {})
        hypothesis_id = self._save_hypothesis(
            user_id,
            structured_hypothesis,
            experience
        )

        return {
            "success": True,
            "hypothesis_id": hypothesis_id,
            "structured_hypothesis": structured_hypothesis,
            "reasoning": result.get("reasoning", ""),
            "refinement_suggestions": result.get("refinement_suggestions", [])
        }

    def refine(
        self,
        user_id: str,
        hypothesis_id: str,
        feedback: str
    ) -> Dict[str, Any]:
        """
        仮説をブラッシュアップする（壁打ち）。

        Args:
            user_id: ユーザーID
            hypothesis_id: 仮説ID
            feedback: ユーザーからのフィードバック

        Returns:
            更新された仮説
        """
        # 既存の仮説を取得
        hypothesis = self.db_client.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return {"success": False, "error": "Hypothesis not found"}

        if hypothesis.get("origin_user_id") != user_id:
            return {"success": False, "error": "Unauthorized"}

        # 壁打ち用のプロンプト
        refinement_prompt = f"""
あなたは仮説形成アシスタントです。以下の仮説に対するユーザーのフィードバックを踏まえて、仮説をブラッシュアップしてください。

## 現在の仮説
{json.dumps(hypothesis.get('content', ''), ensure_ascii=False)}

## ユーザーのフィードバック
{feedback}

## タスク
フィードバックを反映して、仮説を改善してください。

## 出力形式
以下のJSON形式で出力してください：
```json
{{
  "refined_hypothesis": {{
    "statement": "改善された仮説の本文",
    "action": "具体的なアクション",
    "target": "対象となる条件・属性",
    "expected_outcome": "期待される結果",
    "confidence": "low/medium/high",
    "tags": ["タグ1", "タグ2"]
  }},
  "changes_summary": "変更点の要約",
  "next_refinement_suggestions": ["次に検討すべき点"]
}}
```
"""
        result = self.ai_client.generate_response(
            refinement_prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            return {"success": False, "error": "AI response generation failed"}

        # 仮説を更新
        refined = result.get("refined_hypothesis", {})
        content = json.dumps(refined, ensure_ascii=False)
        tags = refined.get("tags", [])

        self.db_client.update_hypothesis(
            hypothesis_id,
            user_id,
            content=content,
            tags=tags
        )

        return {
            "success": True,
            "hypothesis_id": hypothesis_id,
            "refined_hypothesis": refined,
            "changes_summary": result.get("changes_summary", ""),
            "next_refinement_suggestions": result.get("next_refinement_suggestions", [])
        }

    def _create_prompt(
        self,
        experience: str,
        existing_hypotheses: List[Dict[str, Any]],
        interest_profile: Dict[str, Any]
    ) -> str:
        """プロンプトを作成する。"""
        hypotheses_text = ""
        for h in existing_hypotheses[:5]:  # 最新5件
            hypotheses_text += f"- {h.get('content', '')}\n"

        return self.prompt_template.format(
            user_experience=experience,
            existing_hypotheses=hypotheses_text or "（なし）",
            interest_profile=json.dumps(interest_profile, ensure_ascii=False, indent=2)
        )

    def _save_hypothesis(
        self,
        user_id: str,
        structured_hypothesis: Dict[str, Any],
        original_experience: str
    ) -> Optional[str]:
        """仮説をデータベースに保存する。"""
        content = json.dumps(structured_hypothesis, ensure_ascii=False)
        tags = structured_hypothesis.get("tags", [])

        return self.db_client.create_hypothesis(
            user_id=user_id,
            content=content,
            original_experience=original_experience,
            tags=tags
        )

    def get_user_hypotheses(
        self,
        user_id: str,
        status: Optional[str] = None,
        verification_state: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """ユーザーの仮説一覧を取得する。"""
        hypotheses = self.db_client.get_user_hypotheses(
            user_id, status, verification_state, limit
        )

        # コンテンツをパース
        for h in hypotheses:
            if h.get("content"):
                try:
                    h["content_parsed"] = json.loads(h["content"])
                except json.JSONDecodeError:
                    h["content_parsed"] = {"statement": h["content"]}

        return hypotheses
