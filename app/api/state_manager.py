from copy import deepcopy
from typing import Any, Dict, List, Optional

class StateManager:
    DEFAULT_INTEREST_PROFILE: Dict[str, Any] = {
        "topics": [], # Topics of interest (e.g. "Tax Law", "Gardening")
        "current_category": None, # Current session category (e.g. "Technology", "Business")
        "categorized_interests": {}, # Dictionary of topics by category
        "context": {
            "current_page": None, # URL or title of the page they are looking at
            "browsing_history_summary": None,
            "conversation_summary": "",
        },
        "intent": {
            "goal": None, # What they are trying to achieve
            "depth": "beginner", # beginner, intermediate, expert
        },
        "preferences": {
            "response_style": "detailed",
            "verification_method": "scientific",
        }
    }

    DEFAULT_ACTIVE_HYPOTHESES: Dict[str, Any] = {
        "list": [], # List of hypotheses
        "current_focus": None, # ID of the hypothesis currently being verified
        "verification_status": {}, # Status of each hypothesis
    }

    @staticmethod
    def deep_merge(default: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        辞書を再帰的にマージする。

        Args:
            default (Dict[str, Any]): デフォルト値の辞書
            updates (Dict[str, Any]): 更新値の辞書

        Returns:
            Dict[str, Any]: マージされた辞書
        """
        result = deepcopy(default)
        if not isinstance(updates, dict):
            return result
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = StateManager.deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @classmethod
    def get_state_with_defaults(cls, stored_state: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        保存された状態にデフォルト値を適用して取得する。

        Args:
            stored_state (Optional[Dict[str, Any]]): 保存された状態

        Returns:
            Dict[str, Any]: デフォルト値が適用された状態
        """
        interest_updates = (stored_state or {}).get("interest_profile", {})
        hypotheses_updates = (stored_state or {}).get("active_hypotheses", {})
        interest_profile = cls.deep_merge(cls.DEFAULT_INTEREST_PROFILE, interest_updates)
        active_hypotheses = cls.deep_merge(cls.DEFAULT_ACTIVE_HYPOTHESES, hypotheses_updates)
        return {
            "interest_profile": interest_profile,
            "active_hypotheses": active_hypotheses,
        }

    @classmethod
    def normalize_analysis(cls, analysis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        分析結果を正規化し、デフォルト構造に合わせる。

        Args:
            analysis (Dict[str, Any]): 分析結果

        Returns:
            Optional[Dict[str, Any]]: 正規化された分析結果、またはNone
        """
        interest_profile = analysis.get("interest_profile")
        active_hypotheses = analysis.get("active_hypotheses")

        if isinstance(interest_profile, dict) and isinstance(active_hypotheses, dict):
            normalized_interest = cls.deep_merge(cls.DEFAULT_INTEREST_PROFILE, interest_profile)
            normalized_hypotheses = cls.deep_merge(cls.DEFAULT_ACTIVE_HYPOTHESES, active_hypotheses)
            normalized_analysis = {**analysis}
            normalized_analysis["interest_profile"] = normalized_interest
            normalized_analysis["active_hypotheses"] = normalized_hypotheses
            return normalized_analysis
        return None

    @classmethod
    def init_conversation_context(
        cls,
        user_message: str,
        dialog_history: List[Dict[str, Any]],
        interest_profile: Dict[str, Any],
        active_hypotheses: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        会話コンテキストを初期化する。

        Args:
            user_message (str): ユーザーのメッセージ
            dialog_history (List[Dict[str, Any]]): 会話履歴
            interest_profile (Dict[str, Any]): 興味プロファイル
            active_hypotheses (Dict[str, Any]): アクティブな仮説

        Returns:
            Dict[str, Any]: 初期化されたコンテキスト
        """
        return {
            "user_message": user_message,
            "dialog_history": dialog_history,
            "interest_profile": cls.deep_merge(cls.DEFAULT_INTEREST_PROFILE, interest_profile),
            "active_hypotheses": cls.deep_merge(cls.DEFAULT_ACTIVE_HYPOTHESES, active_hypotheses),
            "captured_page": None, # Will be populated if available
            "hypotheses": [],
            "retrieval_evidence": {},
            "conversation_summary": "",
            "bot_message": None
        }
