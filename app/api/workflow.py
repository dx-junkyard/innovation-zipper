from typing import TypedDict, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
import json

from app.api.components.situation_analyzer import SituationAnalyzer
from app.api.components.hypothesis_generator import HypothesisGenerator
from app.api.components.rag_manager import RAGManager
from app.api.components.response_planner import ResponsePlanner
from app.api.components.knowledge_manager import KnowledgeManager
from app.api.ai_client import AIClient

class GraphState(TypedDict):
    """
    グラフの状態を保持する型定義。

    Attributes:
        user_id: ユーザーID (for saving memory)
        user_message (str): ユーザーからのメッセージ
        dialog_history (List[Dict[str, Any]]): 会話履歴
        interest_profile (Dict[str, Any]): 興味プロファイル
        active_hypotheses (Dict[str, Any]): アクティブな仮説
        hypotheses (Optional[List[Dict[str, Any]]]): 生成された仮説のリスト
        retrieval_evidence (Optional[Dict[str, Any]]): RAGによる検索結果
        response_plan (Optional[Dict[str, Any]]): 応答計画
        bot_message (Optional[str]): 最終的なボットの応答メッセージ
        captured_page: Optional[Dict[str, Any]]
    """
    user_id: str
    user_message: str
    dialog_history: List[Dict[str, Any]]
    interest_profile: Dict[str, Any]
    active_hypotheses: Dict[str, Any]
    hypotheses: Optional[List[Dict[str, Any]]]
    retrieval_evidence: Optional[Dict[str, Any]]
    response_plan: Optional[Dict[str, Any]]
    bot_message: Optional[str]
    captured_page: Optional[Dict[str, Any]]

class WorkflowManager:
    """
    LangGraphを使用した対話フローの管理クラス。
    """
    def __init__(self, ai_client: AIClient):
        self.situation_analyzer = SituationAnalyzer(ai_client)
        self.hypothesis_generator = HypothesisGenerator(ai_client)
        self.rag_manager = RAGManager(ai_client)
        self.response_planner = ResponsePlanner(ai_client)
        self.knowledge_manager = KnowledgeManager()
        self.graph = self._build_graph()

    def _build_graph(self):
        """
        ステートグラフを構築してコンパイルする。
        """
        workflow = StateGraph(GraphState)

        # ノードの定義
        workflow.add_node("situation_analysis", self._situation_analysis_node)
        workflow.add_node("hypothesis_generation", self._hypothesis_generation_node)
        workflow.add_node("rag_retrieval", self._rag_retrieval_node)
        workflow.add_node("response_planning", self._response_planning_node)

        # エッジの定義
        workflow.set_entry_point("situation_analysis")
        workflow.add_edge("situation_analysis", "hypothesis_generation")

        # 条件付きエッジ: RAGが必要かどうかで分岐
        workflow.add_conditional_edges(
            "hypothesis_generation",
            self._check_rag_needed,
            {
                "continue": "rag_retrieval",
                "skip": "response_planning"
            }
        )

        workflow.add_edge("rag_retrieval", "response_planning")
        workflow.add_edge("response_planning", END)

        return workflow.compile()

    def invoke(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        ワークフローを実行する。

        Args:
            initial_state (Dict[str, Any]): 初期状態

        Returns:
            Dict[str, Any]: 実行後の最終状態
        """
        return self.graph.invoke(initial_state)

    # ノード関数
    def _situation_analysis_node(self, state: GraphState) -> Dict[str, Any]:
        """状況整理ノード"""
        updated_context = self.situation_analyzer.analyze(state.copy())

        # Memory Consolidation (Synchronous for now)
        user_id = state.get("user_id")
        if user_id:
            interest_profile = updated_context.get("interest_profile")
            if interest_profile:
                # Store important interest topics as user memory
                topics = interest_profile.get("topics", [])
                intent_goal = interest_profile.get("intent", {}).get("goal")

                if intent_goal:
                     self.knowledge_manager.add_user_memory(
                        user_id=user_id,
                        content=f"User Goal: {intent_goal}",
                        memory_type="ai_insight",
                        meta={"source": "situation_analysis"}
                    )

                # We could loop topics too, but let's keep it simple for now to avoid spamming vector DB

        return {
            "interest_profile": updated_context["interest_profile"],
            "active_hypotheses": updated_context["active_hypotheses"]
        }

    def _hypothesis_generation_node(self, state: GraphState) -> Dict[str, Any]:
        """仮説生成ノード"""
        updated_context = self.hypothesis_generator.generate(state.copy())
        return {
            "hypotheses": updated_context.get("hypotheses")
        }

    def _rag_retrieval_node(self, state: GraphState) -> Dict[str, Any]:
        """情報検索ノード"""
        updated_context = self.rag_manager.retrieve_knowledge(state.copy())
        return {
            "retrieval_evidence": updated_context.get("retrieval_evidence")
        }

    def _response_planning_node(self, state: GraphState) -> Dict[str, Any]:
        """応答設計ノード"""
        updated_context, bot_message = self.response_planner.plan_response(state.copy())
        return {
            "response_plan": updated_context.get("response_plan"),
            "bot_message": bot_message
        }

    # 条件付きエッジ関数
    def _check_rag_needed(self, state: GraphState) -> str:
        """RAG検索が必要かどうかを判定する"""
        hypotheses = state.get("hypotheses", [])
        # Safe check ensuring h is a dict
        if hypotheses and any(isinstance(h, dict) and h.get("should_call_rag", False) for h in hypotheses):
            return "continue"
        return "skip"
