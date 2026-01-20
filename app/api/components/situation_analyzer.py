import json
import logging
import numpy as np
from pathlib import Path
from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate
from app.api.ai_client import AIClient
from app.api.state_manager import StateManager
from config import MODEL_SITUATION_ANALYSIS

logger = logging.getLogger(__name__)

class SituationAnalyzer:
    """
    状況整理コンポーネント。
    static/prompts/situation_analysis.txt で定義されたプロンプトを使用して、
    ユーザーの発話と会話履歴をもとに、住民プロファイルとサービスニーズを更新する。
    また、ベクトル類似度による没入度判定を行う。
    """

    ANCHOR_TEXTS_HIGH = [
        "詳細に分析して", "構造的な欠陥は？", "具体例を挙げて比較して",
        "論理的な整合性は？", "メカニズムを解説して", "プロトコルを作成して",
        "専門的な視点での考察"
    ]

    ANCHOR_TEXTS_LOW = [
        "これなに？", "教えて", "簡単に", "要約して",
        "知りたい", "短くまとめて", "ざっくり言うと"
    ]

    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
        # プロンプトファイルのパス解決
        prompt_path = Path(__file__).resolve().parents[3] / "static/prompts/situation_analysis.txt"
        self.prompt_template = PromptTemplate.from_file(prompt_path)

        # アンカーベクトルの初期化
        self.high_immersion_vectors = self._embed_anchors(self.ANCHOR_TEXTS_HIGH)
        # Low immersion vectors are currently not used for score calculation but kept for potential future use
        self.low_immersion_vectors = self._embed_anchors(self.ANCHOR_TEXTS_LOW)

    def _embed_anchors(self, texts: List[str]) -> List[np.ndarray]:
        vectors = []
        for text in texts:
            vec = self.ai_client.get_embedding(text)
            if vec:
                vectors.append(np.array(vec))
        return vectors

    def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        現状の分析を実行する。
        1. 没入度の判定 (Immersion Analysis)
        2. LLMによる状況分析 (Situation Analysis)

        Args:
            context (Dict[str, Any]): 現在の会話コンテキスト

        Returns:
            Dict[str, Any]: 更新されたコンテキスト
        """
        user_message = context.get("user_message", "")

        # 1. 没入度判定
        immersion_result = self._calculate_immersion(user_message)
        context["immersion_score"] = immersion_result["score"]
        context["mode"] = immersion_result["mode"]

        logger.info(f"Immersion Analysis: Score={immersion_result['score']:.2f}, Mode={immersion_result['mode']}")

        # 2. LLM分析
        prompt = self._create_prompt(context)

        # Use generic generate_response instead of analyze_interaction
        analysis_result = self.ai_client.generate_response(prompt, model=MODEL_SITUATION_ANALYSIS, force_json=True)

        if analysis_result:
            normalized_analysis = StateManager.normalize_analysis(analysis_result)
            if normalized_analysis:
                context["interest_profile"] = normalized_analysis["interest_profile"]
                context["active_hypotheses"] = normalized_analysis["active_hypotheses"]

            # Save updated conversation summary if present
            if "conversation_summary" in analysis_result:
                summary = analysis_result["conversation_summary"]
                # Save to interest_profile.context for persistence
                if "context" not in context["interest_profile"]:
                    context["interest_profile"]["context"] = {}
                context["interest_profile"]["context"]["conversation_summary"] = summary
                
                # Also keep in top level context if needed by workflow explicitly
                context["conversation_summary"] = summary

        return context

    def _calculate_immersion(self, text: str) -> Dict[str, Any]:
        """
        ユーザー発話の没入度を計算する。
        Deep Dive系アンカーとの最大類似度をスコアとする。

        Returns:
            Dict: { "score": float, "mode": str }
        """
        if not text or not self.high_immersion_vectors:
            return {"score": 0.0, "mode": "explorer"}

        target_vec = self.ai_client.get_embedding(text)
        if not target_vec:
            return {"score": 0.0, "mode": "explorer"}

        target_vec_np = np.array(target_vec)

        # Cosine Similarity Calculation
        # sim(A, B) = dot(A, B) / (norm(A) * norm(B))
        # Assuming OpenAI embeddings are normalized, but recalculating to be safe

        target_norm = np.linalg.norm(target_vec_np)
        if target_norm == 0:
            return {"score": 0.0, "mode": "explorer"}

        max_score = 0.0

        for anchor_vec in self.high_immersion_vectors:
            anchor_norm = np.linalg.norm(anchor_vec)
            if anchor_norm == 0:
                continue

            dot_product = np.dot(target_vec_np, anchor_vec)
            similarity = dot_product / (target_norm * anchor_norm)

            if similarity > max_score:
                max_score = similarity

        # Determine Mode
        mode = "deep_dive" if max_score >= 0.6 else "explorer"

        return {"score": float(max_score), "mode": mode}

    def _create_prompt(self, context: Dict[str, Any]) -> str:
        """
        LLMへのプロンプトを作成する。
        """
        current_state = {
            "interest_profile": context.get("interest_profile", {}),
            "active_hypotheses": context.get("active_hypotheses", {})
        }

        state_dump = json.dumps(current_state, ensure_ascii=False, indent=2)
        
        # Retrieve summary from interest_profile (primary persistence)
        conversation_summary = context.get("interest_profile", {}).get("context", {}).get("conversation_summary", "")
        # Fallback to top level if missing
        if not conversation_summary:
            conversation_summary = context.get("conversation_summary", "")
            
        latest_user_message = context.get("user_message", "")

        # Capture page context
        captured_page = context.get("captured_page", {}) or {}
        page_title = captured_page.get("title", "No page detected")
        page_url = captured_page.get("url", "")
        page_content = captured_page.get("content", "")[:1000] # Limit content length

        # Get last AI message from history
        history = context.get("dialog_history", [])
        last_ai_message = "（会話開始）"
        for msg in reversed(history):
            if msg.get("role") == "assistant" or msg.get("role") == "ai":
                last_ai_message = msg.get("content", "") or msg.get("message", "")
                break

        return self.prompt_template.format(
            current_state=state_dump,
            page_title=page_title,
            page_url=page_url,
            page_content=page_content,
            conversation_summary=conversation_summary,
            last_ai_message=last_ai_message,
            latest_user_message=latest_user_message
        )
