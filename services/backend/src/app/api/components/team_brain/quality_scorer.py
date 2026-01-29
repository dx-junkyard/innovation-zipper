"""
Hypothesis Quality Scorer (FR-201)

2階: 情報の関所 (Gateway Layer)
仮説の「筋の良さ」を評価するコンポーネント。
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


class HypothesisQualityScorer:
    """
    仮説品質スコアリング（Hypothesis Quality Scoring）

    Gatewayエージェントとして、1階で生成された仮説に対し
    「新規性」「具体性」「組織への影響度」を自動評価する。

    判定ロジック:
    - 既存のナレッジと重複していない
    - 具体的アクションを含む
    - 他のメンバーにも応用可能
    → 「筋が良い（High Potential）」と判定
    """

    # スコアの重み付け
    WEIGHT_NOVELTY = 0.30
    WEIGHT_SPECIFICITY = 0.30
    WEIGHT_IMPACT = 0.40

    # High Potential判定の閾値
    THRESHOLD_OVERALL = 0.6
    THRESHOLD_NOVELTY = 0.4
    THRESHOLD_SPECIFICITY = 0.5
    THRESHOLD_IMPACT = 0.5

    def __init__(self, ai_client: AIClient, db_client: Optional[DBClient] = None):
        self.ai_client = ai_client
        self.db_client = db_client or DBClient()

        # プロンプトファイルの読み込み
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/hypothesis_quality_scoring.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def score(
        self,
        hypothesis_id: str,
        existing_knowledge: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        仮説の品質をスコアリングする。

        Args:
            hypothesis_id: 仮説ID
            existing_knowledge: 比較対象の既存ナレッジ（オプション）

        Returns:
            スコアリング結果
        """
        # 仮説を取得
        hypothesis = self.db_client.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return {"success": False, "error": "Hypothesis not found"}

        # 既存ナレッジの取得（指定がなければ共有仮説を検索）
        if existing_knowledge is None:
            existing_knowledge = self._get_related_knowledge(hypothesis)

        # プロンプトの作成
        prompt = self._create_prompt(hypothesis, existing_knowledge)

        # AIによるスコアリング
        result = self.ai_client.generate_response(
            prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            logger.warning("Failed to score hypothesis")
            return {"success": False, "error": "AI scoring failed"}

        # スコアの抽出と検証
        scores = self._extract_and_validate_scores(result)

        # High Potential判定
        is_high_potential = self._determine_high_potential(scores)
        scores["is_high_potential"] = is_high_potential

        # スコアをデータベースに保存
        self._save_scores(hypothesis_id, scores, result)

        return {
            "success": True,
            "hypothesis_id": hypothesis_id,
            "scores": scores,
            "rationale": result.get("scoring_rationale", {}),
            "improvement_suggestions": result.get("improvement_suggestions", [])
        }

    def batch_score(
        self,
        user_id: str,
        status: str = "DRAFT"
    ) -> List[Dict[str, Any]]:
        """
        ユーザーの複数仮説をバッチスコアリングする。

        Args:
            user_id: ユーザーID
            status: 対象とする仮説のステータス

        Returns:
            スコアリング結果のリスト
        """
        hypotheses = self.db_client.get_user_hypotheses(
            user_id, status=status, limit=20
        )

        results = []
        for h in hypotheses:
            # 既にスコアリング済みかチェック
            if h.get("quality_score"):
                results.append({
                    "hypothesis_id": h["id"],
                    "already_scored": True,
                    "scores": h["quality_score"]
                })
                continue

            result = self.score(h["id"])
            results.append(result)

        return results

    def get_high_potential_hypotheses(
        self,
        user_id: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """筋が良いと判定された仮説を取得する。"""
        return self.db_client.get_high_potential_hypotheses(user_id, limit)

    def _get_related_knowledge(
        self,
        hypothesis: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """仮説に関連する既存ナレッジを取得する。"""
        # コンテンツからキーワードを抽出
        content = hypothesis.get("content", "")
        try:
            parsed = json.loads(content)
            keywords = []
            if parsed.get("statement"):
                keywords.extend(parsed["statement"].split()[:5])
            if parsed.get("tags"):
                keywords.extend(parsed["tags"])
        except json.JSONDecodeError:
            keywords = content.split()[:5]

        if not keywords:
            return []

        # 共有仮説を検索
        return self.db_client.search_hypotheses_for_rag(
            keywords=keywords,
            exclude_user_id=hypothesis.get("origin_user_id"),
            limit=limit
        )

    def _create_prompt(
        self,
        hypothesis: Dict[str, Any],
        existing_knowledge: List[Dict[str, Any]]
    ) -> str:
        """スコアリング用プロンプトを作成する。"""
        knowledge_text = ""
        for k in existing_knowledge[:5]:
            knowledge_text += f"- {k.get('content', '')}\n"
            if k.get("verification_summary"):
                knowledge_text += f"  検証状況: {k['verification_summary']}\n"

        return self.prompt_template.format(
            hypothesis_content=hypothesis.get("content", ""),
            existing_knowledge=knowledge_text or "（関連するナレッジなし）"
        )

    def _extract_and_validate_scores(
        self,
        result: Dict[str, Any]
    ) -> Dict[str, float]:
        """スコアを抽出して検証する。"""
        def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
            return max(min_val, min(max_val, value))

        novelty = clamp(float(result.get("novelty_score", 0.5)))
        specificity = clamp(float(result.get("specificity_score", 0.5)))
        impact = clamp(float(result.get("impact_score", 0.5)))

        # 加重平均で総合スコアを計算
        overall = (
            novelty * self.WEIGHT_NOVELTY +
            specificity * self.WEIGHT_SPECIFICITY +
            impact * self.WEIGHT_IMPACT
        )

        return {
            "novelty_score": round(novelty, 2),
            "specificity_score": round(specificity, 2),
            "impact_score": round(impact, 2),
            "overall_score": round(overall, 2)
        }

    def _determine_high_potential(self, scores: Dict[str, float]) -> bool:
        """High Potential（筋が良い）かどうかを判定する。"""
        return (
            scores["overall_score"] >= self.THRESHOLD_OVERALL and
            scores["novelty_score"] >= self.THRESHOLD_NOVELTY and
            scores["specificity_score"] >= self.THRESHOLD_SPECIFICITY and
            scores["impact_score"] >= self.THRESHOLD_IMPACT
        )

    def _save_scores(
        self,
        hypothesis_id: str,
        scores: Dict[str, Any],
        result: Dict[str, Any]
    ) -> None:
        """スコアをデータベースに保存する。"""
        rationale = result.get("scoring_rationale", {})
        rationale_text = json.dumps(rationale, ensure_ascii=False) if isinstance(rationale, dict) else str(rationale)

        self.db_client.save_quality_score(
            hypothesis_id=hypothesis_id,
            novelty_score=scores["novelty_score"],
            specificity_score=scores["specificity_score"],
            impact_score=scores["impact_score"],
            overall_score=scores["overall_score"],
            is_high_potential=scores["is_high_potential"],
            scoring_rationale=rationale_text
        )
