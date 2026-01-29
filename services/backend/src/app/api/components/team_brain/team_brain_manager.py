"""
Team Brain Manager

統合マネージャー：3階層ナレッジプラットフォームを統括する。
"""

import json
import logging
from typing import Any, Dict, List, Optional

from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.components.rag_manager import RAGManager

from .hypothesis_incubator import HypothesisIncubator
from .quality_scorer import HypothesisQualityScorer
from .sharing_suggester import SharingSuggester
from .status_aware_rag import StatusAwareRAG

logger = logging.getLogger(__name__)


class TeamBrainManager:
    """
    Team Brain 統合マネージャー

    3階層ナレッジプラットフォームの全機能を統括：
    - 1階: 思考の私有地 (Private Layer)
    - 2階: 情報の関所 (Gateway Layer)
    - 3階: 共創の広場 (Public Layer)
    """

    def __init__(
        self,
        ai_client: AIClient,
        db_client: Optional[DBClient] = None,
        rag_manager: Optional[RAGManager] = None
    ):
        self.ai_client = ai_client
        self.db_client = db_client or DBClient()
        self.rag_manager = rag_manager or RAGManager(ai_client)

        # コンポーネントの初期化
        self.incubator = HypothesisIncubator(ai_client, self.db_client)
        self.scorer = HypothesisQualityScorer(ai_client, self.db_client)
        self.suggester = SharingSuggester(ai_client, self.db_client)
        self.status_aware_rag = StatusAwareRAG(ai_client, self.db_client, self.rag_manager)

    # =========================================================================
    # 1階: 思考の私有地 (Private Layer)
    # =========================================================================

    def incubate_hypothesis(
        self,
        user_id: str,
        experience: str,
        interest_profile: Optional[Dict[str, Any]] = None,
        auto_score: bool = True,
        check_sharing: bool = True
    ) -> Dict[str, Any]:
        """
        経験から仮説を生成し、オプションでスコアリングと共有チェックを行う。

        Args:
            user_id: ユーザーID
            experience: ユーザーの経験・メモ
            interest_profile: ユーザーの興味プロファイル
            auto_score: 自動スコアリングを行うか
            check_sharing: 共有サジェストをチェックするか

        Returns:
            仮説生成結果と関連情報
        """
        # 1. 仮説の生成（1階）
        incubation_result = self.incubator.incubate(
            user_id, experience, interest_profile
        )

        if not incubation_result.get("success"):
            return incubation_result

        hypothesis_id = incubation_result.get("hypothesis_id")
        result = {
            "success": True,
            "hypothesis_id": hypothesis_id,
            "structured_hypothesis": incubation_result.get("structured_hypothesis"),
            "reasoning": incubation_result.get("reasoning"),
            "refinement_suggestions": incubation_result.get("refinement_suggestions")
        }

        # 2. 品質スコアリング（2階）
        if auto_score and hypothesis_id:
            scoring_result = self.scorer.score(hypothesis_id)
            result["quality_score"] = scoring_result.get("scores", {})
            result["scoring_rationale"] = scoring_result.get("rationale", {})

            # 3. 共有サジェスト（2階）
            if check_sharing and scoring_result.get("success"):
                suggestion_result = self.suggester.check_and_suggest(
                    hypothesis_id, user_id, trigger="quality_check"
                )
                if suggestion_result.get("should_suggest"):
                    result["sharing_suggestion"] = {
                        "suggestion_id": suggestion_result.get("suggestion_id"),
                        "message": suggestion_result.get("user_message"),
                        "anonymized_draft": suggestion_result.get("anonymized_draft"),
                        "benefits": suggestion_result.get("sharing_benefits")
                    }

        return result

    def refine_hypothesis(
        self,
        user_id: str,
        hypothesis_id: str,
        feedback: str
    ) -> Dict[str, Any]:
        """仮説をブラッシュアップする。"""
        return self.incubator.refine(user_id, hypothesis_id, feedback)

    def get_my_hypotheses(
        self,
        user_id: str,
        status: Optional[str] = None,
        verification_state: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """ユーザーの仮説一覧を取得する。"""
        return self.incubator.get_user_hypotheses(
            user_id, status, verification_state, limit
        )

    def update_verification_state(
        self,
        user_id: str,
        hypothesis_id: str,
        verification_state: str,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        仮説の検証ステータスを更新する（FR-104）。

        Args:
            user_id: ユーザーID
            hypothesis_id: 仮説ID
            verification_state: 新しい検証状態 (UNVERIFIED, IN_PROGRESS, VALIDATED, FAILED)
            notes: 検証メモ

        Returns:
            更新結果
        """
        success = self.db_client.update_hypothesis_verification_state(
            hypothesis_id, user_id, verification_state
        )

        if not success:
            return {"success": False, "error": "Failed to update verification state"}

        result = {
            "success": True,
            "hypothesis_id": hypothesis_id,
            "verification_state": verification_state
        }

        # 検証完了時は共有サジェストをチェック
        if verification_state in ["VALIDATED", "FAILED"]:
            suggestion_result = self.suggester.check_and_suggest(
                hypothesis_id, user_id, trigger="verification_complete"
            )
            if suggestion_result.get("should_suggest"):
                result["sharing_suggestion"] = {
                    "suggestion_id": suggestion_result.get("suggestion_id"),
                    "message": suggestion_result.get("user_message"),
                    "anonymized_draft": suggestion_result.get("anonymized_draft"),
                    "benefits": suggestion_result.get("sharing_benefits")
                }

        return result

    # =========================================================================
    # 2階: 情報の関所 (Gateway Layer)
    # =========================================================================

    def score_hypothesis(self, hypothesis_id: str) -> Dict[str, Any]:
        """仮説の品質をスコアリングする。"""
        return self.scorer.score(hypothesis_id)

    def get_pending_suggestions(self, user_id: str) -> List[Dict[str, Any]]:
        """保留中の共有サジェストを取得する。"""
        return self.suggester.get_pending_suggestions(user_id)

    def respond_to_suggestion(
        self,
        suggestion_id: int,
        user_id: str,
        action: str,
        edited_content: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """共有サジェストに応答する。"""
        return self.suggester.respond_to_suggestion(
            suggestion_id, user_id, action, edited_content, team_id
        )

    # =========================================================================
    # 3階: 共創の広場 (Public Layer)
    # =========================================================================

    def get_shared_hypotheses(
        self,
        team_id: Optional[str] = None,
        verification_state: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """共有された仮説バンクを取得する（FR-301）。"""
        hypotheses = self.db_client.get_shared_hypotheses(
            team_id, verification_state, limit
        )

        # コンテンツをパース
        for h in hypotheses:
            if h.get("content"):
                try:
                    h["content_parsed"] = json.loads(h["content"])
                except json.JSONDecodeError:
                    h["content_parsed"] = {"statement": h["content"]}

        return hypotheses

    def add_verification(
        self,
        user_id: str,
        hypothesis_id: str,
        verification_result: str,
        conditions: Optional[str] = None,
        notes: Optional[str] = None,
        evidence: Optional[Dict] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        仮説に検証結果を追加する。

        Args:
            user_id: 検証者のユーザーID
            hypothesis_id: 仮説ID
            verification_result: 検証結果 (SUCCESS, FAILURE, PARTIAL, INCONCLUSIVE)
            conditions: 検証条件
            notes: 検証メモ
            evidence: 検証の根拠データ
            team_id: 検証者のチームID

        Returns:
            追加結果
        """
        verification_id = self.db_client.add_verification(
            hypothesis_id=hypothesis_id,
            verifier_user_id=user_id,
            verification_result=verification_result,
            conditions=conditions,
            notes=notes,
            evidence=evidence,
            verifier_team_id=team_id
        )

        if not verification_id:
            return {"success": False, "error": "Failed to add verification"}

        return {
            "success": True,
            "verification_id": verification_id,
            "hypothesis_id": hypothesis_id,
            "verification_result": verification_result
        }

    def get_hypothesis_verifications(
        self,
        hypothesis_id: str
    ) -> Dict[str, Any]:
        """仮説の検証履歴を取得する。"""
        return self.status_aware_rag.get_verification_context(hypothesis_id)

    # =========================================================================
    # 循環型RAG (Cross-Layer RAG)
    # =========================================================================

    def think_with_collective_wisdom(
        self,
        user_id: str,
        thought: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ユーザーの思考に対して、組織の集合知を活用したアドバイスを提供する（FR-401）。

        Args:
            user_id: ユーザーID
            thought: ユーザーの現在の思考・計画
            category: カテゴリフィルタ

        Returns:
            検証ステータスを考慮したアドバイス
        """
        return self.status_aware_rag.retrieve_with_status(
            user_id, thought, category
        )

    def suggest_differential_verification(
        self,
        user_id: str,
        hypothesis_id: str,
        new_conditions: str
    ) -> Dict[str, Any]:
        """差分検証を提案する（FR-402）。"""
        return self.status_aware_rag.suggest_differential_verification(
            user_id, hypothesis_id, new_conditions
        )

    def record_differential_verification(
        self,
        user_id: str,
        parent_hypothesis_id: str,
        verification_result: str,
        conditions: str,
        notes: Optional[str] = None,
        evidence: Optional[Dict] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """差分検証結果を記録する（FR-402）。"""
        return self.status_aware_rag.record_differential_verification(
            user_id=user_id,
            parent_hypothesis_id=parent_hypothesis_id,
            verification_result=verification_result,
            conditions=conditions,
            notes=notes,
            evidence=evidence,
            team_id=team_id
        )

    # =========================================================================
    # チーム管理
    # =========================================================================

    def create_team(
        self,
        name: str,
        created_by: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """チームを作成する。"""
        team_id = self.db_client.create_team(name, created_by, description)
        if not team_id:
            return {"success": False, "error": "Failed to create team"}

        return {
            "success": True,
            "team_id": team_id,
            "name": name
        }

    def get_my_teams(self, user_id: str) -> List[Dict[str, Any]]:
        """ユーザーが所属するチーム一覧を取得する。"""
        return self.db_client.get_user_teams(user_id)

    def add_team_member(
        self,
        team_id: str,
        user_id: str,
        role: str = "viewer"
    ) -> Dict[str, Any]:
        """チームにメンバーを追加する。"""
        success = self.db_client.add_team_member(team_id, user_id, role)
        if not success:
            return {"success": False, "error": "Failed to add team member"}

        return {
            "success": True,
            "team_id": team_id,
            "user_id": user_id,
            "role": role
        }

    # =========================================================================
    # ダッシュボード用データ
    # =========================================================================

    def get_dashboard_stats(self, user_id: str) -> Dict[str, Any]:
        """ダッシュボード用の統計情報を取得する。"""
        my_hypotheses = self.db_client.get_user_hypotheses(user_id, limit=100)

        stats = {
            "total_hypotheses": len(my_hypotheses),
            "by_status": {
                "DRAFT": 0,
                "PROPOSED": 0,
                "SHARED": 0
            },
            "by_verification_state": {
                "UNVERIFIED": 0,
                "IN_PROGRESS": 0,
                "VALIDATED": 0,
                "FAILED": 0
            },
            "high_potential_count": 0,
            "pending_suggestions": len(self.suggester.get_pending_suggestions(user_id)),
            "teams": self.db_client.get_user_teams(user_id)
        }

        for h in my_hypotheses:
            status = h.get("status", "DRAFT")
            verification = h.get("verification_state", "UNVERIFIED")

            if status in stats["by_status"]:
                stats["by_status"][status] += 1
            if verification in stats["by_verification_state"]:
                stats["by_verification_state"][verification] += 1

            quality = h.get("quality_score", {})
            if quality.get("is_high_potential"):
                stats["high_potential_count"] += 1

        return stats
