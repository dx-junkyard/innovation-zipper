"""
Sharing Suggester (FR-202)

2階: 情報の関所 (Gateway Layer)
共有サジェストと承認フローを管理するコンポーネント。
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


class SharingSuggester:
    """
    共有サジェストと承認フロー（Suggestion & Approval）

    トリガー:
    - 「筋が良い」と判定された仮説が生まれた際
    - 検証ステータスが「検証済」になった際

    アクション:
    - AIがユーザーに共有を提案
    - 匿名化ドラフトをプレビュー
    - ユーザーが最終修正・承認を行って3階へ送信
    """

    def __init__(self, ai_client: AIClient, db_client: Optional[DBClient] = None):
        self.ai_client = ai_client
        self.db_client = db_client or DBClient()

        # プロンプトファイルの読み込み
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/sharing_suggestion.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def check_and_suggest(
        self,
        hypothesis_id: str,
        user_id: str,
        trigger: str = "quality_check"
    ) -> Dict[str, Any]:
        """
        仮説の共有を提案するかどうかをチェックする。

        Args:
            hypothesis_id: 仮説ID
            user_id: ユーザーID
            trigger: トリガー種別 (quality_check, verification_complete)

        Returns:
            提案結果
        """
        # 仮説を取得
        hypothesis = self.db_client.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return {"success": False, "error": "Hypothesis not found"}

        if hypothesis.get("origin_user_id") != user_id:
            return {"success": False, "error": "Unauthorized"}

        # 既に共有済みの場合はスキップ
        if hypothesis.get("status") == "SHARED":
            return {
                "success": True,
                "should_suggest": False,
                "reason": "Already shared"
            }

        # 品質スコアと検証状況を確認
        quality_score = hypothesis.get("quality_score", {})
        verification_state = hypothesis.get("verification_state", "UNVERIFIED")

        # 提案条件のチェック
        should_check = self._should_suggest(
            quality_score,
            verification_state,
            trigger
        )

        if not should_check:
            return {
                "success": True,
                "should_suggest": False,
                "reason": "Does not meet suggestion criteria"
            }

        # AIによる提案生成
        prompt = self._create_prompt(hypothesis, quality_score, verification_state)
        result = self.ai_client.generate_response(
            prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            return {"success": False, "error": "AI suggestion generation failed"}

        should_suggest = result.get("should_suggest", False)

        if should_suggest:
            # サジェストをデータベースに保存
            suggestion_id = self._save_suggestion(
                hypothesis_id,
                user_id,
                result
            )

            return {
                "success": True,
                "should_suggest": True,
                "suggestion_id": suggestion_id,
                "suggestion_reason": result.get("suggestion_reason", ""),
                "user_message": result.get("user_message", ""),
                "anonymized_draft": result.get("anonymized_draft", {}),
                "target_audience": result.get("target_audience", []),
                "sharing_benefits": result.get("sharing_benefits", [])
            }
        else:
            return {
                "success": True,
                "should_suggest": False,
                "reason": result.get("suggestion_reason", "Does not meet sharing criteria")
            }

    def get_pending_suggestions(self, user_id: str) -> List[Dict[str, Any]]:
        """保留中の共有サジェストを取得する。"""
        return self.db_client.get_pending_suggestions(user_id)

    def respond_to_suggestion(
        self,
        suggestion_id: int,
        user_id: str,
        action: str,
        edited_content: Optional[str] = None,
        team_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        共有サジェストに応答する。

        Args:
            suggestion_id: サジェストID
            user_id: ユーザーID
            action: アクション (accept, reject, edit)
            edited_content: 編集内容（edit時）
            team_id: 共有先チームID（オプション）

        Returns:
            応答結果
        """
        # サジェストの情報を取得（pending状態のもの）
        pending = self.db_client.get_pending_suggestions(user_id)
        suggestion = next(
            (s for s in pending if s.get("id") == suggestion_id),
            None
        )

        if not suggestion:
            return {"success": False, "error": "Suggestion not found or already processed"}

        hypothesis_id = suggestion.get("hypothesis_id")

        if action == "accept":
            # そのまま共有
            status = "ACCEPTED"
            self.db_client.respond_to_suggestion(suggestion_id, user_id, status)
            self.db_client.share_hypothesis(hypothesis_id, user_id, team_id)

            return {
                "success": True,
                "action": "shared",
                "hypothesis_id": hypothesis_id
            }

        elif action == "edit":
            # 編集して共有
            if not edited_content:
                return {"success": False, "error": "Edited content required"}

            status = "EDITED"
            self.db_client.respond_to_suggestion(
                suggestion_id, user_id, status, edited_content
            )
            # 仮説のコンテンツを更新して共有
            self.db_client.update_hypothesis(
                hypothesis_id, user_id, content=edited_content
            )
            self.db_client.share_hypothesis(hypothesis_id, user_id, team_id)

            return {
                "success": True,
                "action": "edited_and_shared",
                "hypothesis_id": hypothesis_id
            }

        elif action == "reject":
            # 共有を拒否
            status = "REJECTED"
            self.db_client.respond_to_suggestion(suggestion_id, user_id, status)

            return {
                "success": True,
                "action": "rejected",
                "hypothesis_id": hypothesis_id
            }

        else:
            return {"success": False, "error": f"Unknown action: {action}"}

    def _should_suggest(
        self,
        quality_score: Dict[str, Any],
        verification_state: str,
        trigger: str
    ) -> bool:
        """提案すべきかどうかを判定する。"""
        # 品質スコアが高い場合
        if trigger == "quality_check":
            is_high_potential = quality_score.get("is_high_potential", False)
            overall_score = quality_score.get("overall", 0)
            return is_high_potential or overall_score >= 0.6

        # 検証完了時
        if trigger == "verification_complete":
            return verification_state in ["VALIDATED", "FAILED"]

        return False

    def _create_prompt(
        self,
        hypothesis: Dict[str, Any],
        quality_score: Dict[str, Any],
        verification_state: str
    ) -> str:
        """サジェスト用プロンプトを作成する。"""
        return self.prompt_template.format(
            hypothesis=json.dumps(hypothesis.get("content", ""), ensure_ascii=False),
            quality_score=json.dumps(quality_score, ensure_ascii=False, indent=2),
            verification_state=verification_state
        )

    def _save_suggestion(
        self,
        hypothesis_id: str,
        user_id: str,
        result: Dict[str, Any]
    ) -> Optional[int]:
        """サジェストをデータベースに保存する。"""
        anonymized_draft = result.get("anonymized_draft", {})
        draft_content = json.dumps(anonymized_draft, ensure_ascii=False)

        return self.db_client.create_sharing_suggestion(
            hypothesis_id=hypothesis_id,
            user_id=user_id,
            suggestion_reason=result.get("suggestion_reason", ""),
            draft_content=draft_content
        )
