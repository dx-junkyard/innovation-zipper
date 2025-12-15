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

        # 1. Report Check
        if any(w in user_message for w in ["まとめて", "レポート", "議事録"]):
            return "report"

        # 2. Research Check (Extension流入)
        if captured_page and any(w in user_message for w in ["このページ", "記事", "読んで"]):
            return "research"

        # 3. Explicit Innovation Check (強い開始意志)
        if any(w in user_message for w in ["課題解決", "アイデア出し", "ブレスト", "構造分解", "仮説"]):
             return "innovation"

        # 4. Default -> Discovery (New!)
        return "discovery"
