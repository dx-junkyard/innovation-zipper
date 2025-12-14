from typing import Dict, Any

class IntentRouter:
    """
    ユーザーの意図を判定してルーティングを行うクラス。
    """
    def route(self, context: Dict[str, Any]) -> str:
        """
        コンテキストに基づいてモードを判定する。

        Args:
            context (Dict[str, Any]): 現在のステート情報

        Returns:
            str: "report", "research", or "innovation"
        """
        user_message = context.get("user_message", "")
        captured_page = context.get("captured_page", {})

        # 1. Report Mode
        if "まとめて" in user_message or "レポート" in user_message:
            return "report"

        # 2. Research Mode
        # captured_page があり「このページ」等の言及があれば
        if captured_page and ("このページ" in user_message or "記事" in user_message):
            return "research"

        # 3. Innovation Mode (Default)
        return "innovation"
