"""
Status-Aware RAG (FR-401, FR-402)

1階⇔3階: 循環型RAG (Cross-Layer RAG)
他者の検証結果を自考に活かすコンポーネント。
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.prompts import PromptTemplate

from app.api.ai_client import AIClient
from app.api.db import DBClient
from app.api.components.rag_manager import RAGManager
from config import MODEL_HYPOTHESIS_GENERATION

logger = logging.getLogger(__name__)


class StatusAwareRAG:
    """
    ステータス考慮型リトリーバル（Status-Aware RAG）

    シナリオ:
    ユーザーが1階で「Xという方法を試そうと思う」と考えた時、
    AIは3階（Public）を検索し、関連する検証結果を踏まえてアドバイスを行う。

    特徴:
    - 単に「似た文書がある」だけでなく、「検証が進んでいるか？」
      「結果はどうだったか？」というメタデータを優先して回答に組み込む
    - 差分分析：他者の検証済み仮説に対し、新たな条件で検証を行った場合、
      その「差分」のみを3階にフィードバックするよう促す
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

        # プロンプトファイルの読み込み
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/status_aware_rag.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

    def retrieve_with_status(
        self,
        user_id: str,
        user_thought: str,
        category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        ユーザーの思考に対して、検証ステータスを考慮した情報を取得する。

        Args:
            user_id: ユーザーID
            user_thought: ユーザーの現在の思考・計画
            category: カテゴリフィルタ（オプション）

        Returns:
            検証ステータスを含む関連情報とアドバイス
        """
        # キーワード抽出
        keywords = self._extract_keywords(user_thought)

        if not keywords:
            return {
                "success": True,
                "has_relevant_info": False,
                "message": "No keywords extracted from thought"
            }

        # 共有仮説を検索（検証ステータス付き）
        related_hypotheses = self.db_client.search_hypotheses_for_rag(
            keywords=keywords,
            exclude_user_id=user_id,
            include_verification_summary=True,
            limit=10
        )

        # ベクトル検索も実行（補助的に）
        vector_results = self.rag_manager.search_by_text(
            query_text=user_thought,
            user_id=user_id,
            category=category,
            limit=5
        )

        if not related_hypotheses and not vector_results:
            return {
                "success": True,
                "has_relevant_info": False,
                "message": "No related information found"
            }

        # AIによるアドバイス生成
        prompt = self._create_prompt(user_thought, related_hypotheses)
        result = self.ai_client.generate_response(
            prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            # AI失敗時は生データを返す
            return {
                "success": True,
                "has_relevant_info": bool(related_hypotheses),
                "related_hypotheses": related_hypotheses,
                "vector_results": vector_results,
                "advice": None
            }

        return {
            "success": True,
            "has_relevant_info": result.get("has_relevant_info", True),
            "advice_type": result.get("advice_type", "information"),
            "main_message": result.get("main_message", ""),
            "related_hypotheses_summary": result.get("related_hypotheses_summary", []),
            "suggested_actions": result.get("suggested_actions", []),
            "differential_opportunity": result.get("differential_opportunity", {}),
            "raw_data": {
                "hypotheses": related_hypotheses,
                "vector_results": vector_results
            }
        }

    def get_verification_context(
        self,
        hypothesis_id: str
    ) -> Dict[str, Any]:
        """
        特定の仮説の検証コンテキストを取得する。

        Args:
            hypothesis_id: 仮説ID

        Returns:
            検証コンテキスト（誰が検証したか、結果はどうだったか）
        """
        hypothesis = self.db_client.get_hypothesis(hypothesis_id)
        if not hypothesis:
            return {"success": False, "error": "Hypothesis not found"}

        verifications = self.db_client.get_hypothesis_verifications(hypothesis_id)

        # 検証サマリーの構築
        summary = {
            "total_verifications": len(verifications),
            "success_count": 0,
            "failure_count": 0,
            "partial_count": 0,
            "inconclusive_count": 0,
            "by_team": {},
            "conditions_tried": []
        }

        for v in verifications:
            result = v.get("verification_result")
            if result == "SUCCESS":
                summary["success_count"] += 1
            elif result == "FAILURE":
                summary["failure_count"] += 1
            elif result == "PARTIAL":
                summary["partial_count"] += 1
            elif result == "INCONCLUSIVE":
                summary["inconclusive_count"] += 1

            team_name = v.get("team_name", "Unknown")
            if team_name not in summary["by_team"]:
                summary["by_team"][team_name] = []
            summary["by_team"][team_name].append({
                "result": result,
                "conditions": v.get("conditions"),
                "notes": v.get("notes"),
                "created_at": v.get("created_at")
            })

            if v.get("conditions"):
                summary["conditions_tried"].append(v["conditions"])

        return {
            "success": True,
            "hypothesis": hypothesis,
            "verification_summary": summary,
            "verifications": verifications
        }

    def suggest_differential_verification(
        self,
        user_id: str,
        hypothesis_id: str,
        new_conditions: str
    ) -> Dict[str, Any]:
        """
        差分検証を提案する（FR-402）。

        Args:
            user_id: ユーザーID
            hypothesis_id: 参照する仮説ID
            new_conditions: 新しい検証条件

        Returns:
            差分検証の提案
        """
        context = self.get_verification_context(hypothesis_id)
        if not context.get("success"):
            return context

        existing_conditions = context["verification_summary"]["conditions_tried"]

        # 新しい条件が既存と重複していないかチェック
        is_novel = self._check_condition_novelty(new_conditions, existing_conditions)

        if not is_novel:
            return {
                "success": True,
                "should_verify": False,
                "reason": "Similar conditions have already been tested",
                "existing_conditions": existing_conditions
            }

        # 差分検証の提案を生成
        prompt = f"""
以下の仮説に対して、新しい条件での差分検証が提案されています。

## 既存の仮説
{json.dumps(context['hypothesis'].get('content', ''), ensure_ascii=False)}

## 既存の検証結果
{json.dumps(context['verification_summary'], ensure_ascii=False, indent=2)}

## 新しい検証条件
{new_conditions}

## タスク
この差分検証の価値を評価し、以下のJSON形式で出力してください：

```json
{{
  "verification_value": "high/medium/low",
  "rationale": "この差分検証が価値がある理由",
  "expected_insights": ["得られる可能性のある知見"],
  "recommended_approach": "推奨されるアプローチ",
  "potential_pitfalls": ["注意すべき点"]
}}
```
"""
        result = self.ai_client.generate_response(
            prompt,
            model=MODEL_HYPOTHESIS_GENERATION
        )

        if not result:
            return {
                "success": True,
                "should_verify": True,
                "conditions_are_novel": True,
                "analysis": None
            }

        return {
            "success": True,
            "should_verify": True,
            "conditions_are_novel": True,
            "verification_value": result.get("verification_value", "medium"),
            "rationale": result.get("rationale", ""),
            "expected_insights": result.get("expected_insights", []),
            "recommended_approach": result.get("recommended_approach", ""),
            "potential_pitfalls": result.get("potential_pitfalls", []),
            "parent_hypothesis_id": hypothesis_id
        }

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
        """
        差分検証結果を記録する（FR-402）。

        Args:
            user_id: ユーザーID
            parent_hypothesis_id: 参照元の仮説ID
            verification_result: 検証結果 (SUCCESS, FAILURE, PARTIAL, INCONCLUSIVE)
            conditions: 検証条件
            notes: 検証メモ
            evidence: 検証の根拠データ
            team_id: チームID

        Returns:
            記録結果
        """
        # 通常の検証を記録
        verification_id = self.db_client.add_verification(
            hypothesis_id=parent_hypothesis_id,
            verifier_user_id=user_id,
            verification_result=verification_result,
            conditions=conditions,
            notes=notes,
            evidence=evidence,
            verifier_team_id=team_id,
            is_differential=True
        )

        if not verification_id:
            return {"success": False, "error": "Failed to record verification"}

        return {
            "success": True,
            "verification_id": verification_id,
            "is_differential": True,
            "parent_hypothesis_id": parent_hypothesis_id,
            "message": "差分検証結果を記録しました。この知見は組織の集合知として蓄積されます。"
        }

    def _extract_keywords(self, text: str) -> List[str]:
        """テキストからキーワードを抽出する。"""
        # シンプルな実装：重要そうな単語を抽出
        # 実際の実装ではNLPを使用することを推奨
        import re

        # 日本語と英語の単語を抽出
        words = re.findall(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+|\w+', text)

        # ストップワードを除去
        stopwords = {'の', 'に', 'は', 'を', 'た', 'が', 'で', 'て', 'と', 'し', 'れ',
                     'さ', 'ある', 'いる', 'も', 'する', 'から', 'な', 'こと', 'として',
                     'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
                     'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                     'would', 'could', 'should', 'may', 'might', 'must', 'shall'}

        keywords = [w for w in words if w.lower() not in stopwords and len(w) > 1]

        # 最大10個のキーワードを返す
        return keywords[:10]

    def _create_prompt(
        self,
        user_thought: str,
        related_hypotheses: List[Dict[str, Any]]
    ) -> str:
        """アドバイス生成用プロンプトを作成する。"""
        hypotheses_text = ""
        for h in related_hypotheses:
            hypotheses_text += f"""
- 仮説: {h.get('content', '')}
  検証状態: {h.get('verification_state', 'UNVERIFIED')}
  検証回数: {h.get('total_verifications', 0)} (成功: {h.get('success_count', 0)}, 失敗: {h.get('failure_count', 0)})
  検証サマリー: {h.get('verification_summary', 'なし')}
"""

        return self.prompt_template.format(
            user_thought=user_thought,
            related_hypotheses=hypotheses_text or "（関連する仮説なし）"
        )

    def _check_condition_novelty(
        self,
        new_conditions: str,
        existing_conditions: List[str]
    ) -> bool:
        """新しい条件が既存と重複していないかチェックする。"""
        if not existing_conditions:
            return True

        # シンプルな類似度チェック
        new_lower = new_conditions.lower()
        for existing in existing_conditions:
            if existing:
                existing_lower = existing.lower()
                # 80%以上の文字が一致する場合は重複とみなす
                common_chars = sum(1 for c in new_lower if c in existing_lower)
                similarity = common_chars / max(len(new_lower), len(existing_lower))
                if similarity > 0.8:
                    return False

        return True
