from typing import TypedDict, Dict, Any, List, Optional
from langgraph.graph import StateGraph, END
import json

# Existing components
from app.api.components.situation_analyzer import SituationAnalyzer
from app.api.components.hypothesis_generator import HypothesisGenerator
from app.api.components.rag_manager import RAGManager
from app.api.components.gap_analyzer import GapAnalyzer
from app.api.components.response_planner import ResponsePlanner
from app.api.components.knowledge_manager import KnowledgeManager
from app.api.ai_client import AIClient
from app.api.components.topic_client import TopicClient

# New components
from app.api.components.intent_router import IntentRouter
from app.api.components.structural_analyzer import StructuralAnalyzer
from app.api.components.variant_generator import VariantGenerator
from app.api.components.innovation_synthesizer import InnovationSynthesizer
from app.api.components.report_generator import ReportGenerator
from app.api.components.interest_explorer import InterestExplorer

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

        # New fields
        mode: str
        structural_analysis: Optional[Dict[str, Any]]
        idea_variants: Optional[Dict[str, Any]]
        innovation_hypotheses: Optional[List[Dict[str, Any]]]
    """
    user_id: str
    user_message: str
    dialog_history: List[Dict[str, Any]]
    interest_profile: Dict[str, Any]
    active_hypotheses: Dict[str, Any]
    hypotheses: Optional[List[Dict[str, Any]]]
    retrieval_evidence: Optional[Dict[str, Any]]
    knowledge_gaps: Optional[List[Dict[str, Any]]]
    response_plan: Optional[Dict[str, Any]]
    bot_message: Optional[str]
    captured_page: Optional[Dict[str, Any]]

    mode: str
    structural_analysis: Optional[Dict[str, Any]]
    idea_variants: Optional[Dict[str, Any]]
    innovation_hypotheses: Optional[List[Dict[str, Any]]]

class WorkflowManager:
    """
    LangGraphを使用した対話フローの管理クラス。
    """
    def __init__(self, ai_client: AIClient):
        # Existing
        self.situation_analyzer = SituationAnalyzer(ai_client)
        self.hypothesis_generator = HypothesisGenerator(ai_client)
        self.rag_manager = RAGManager(ai_client)
        self.gap_analyzer = GapAnalyzer(ai_client)
        self.response_planner = ResponsePlanner(ai_client)
        self.knowledge_manager = KnowledgeManager()

        # New
        self.intent_router = IntentRouter()
        self.structural_analyzer = StructuralAnalyzer(ai_client)
        self.variant_generator = VariantGenerator(ai_client)
        self.innovation_synthesizer = InnovationSynthesizer(ai_client)
        self.report_generator = ReportGenerator(ai_client)
        self.interest_explorer = InterestExplorer(ai_client)

        self.graph = self._build_graph()

    def _build_graph(self):
        """
        ステートグラフを構築してコンパイルする。
        """
        workflow = StateGraph(GraphState)

        # ノードの定義 (Common / Research)
        workflow.add_node("intent_router", self._intent_router_node)
        workflow.add_node("discovery_exploration", self._discovery_exploration_node)
        workflow.add_node("situation_analysis", self._situation_analysis_node)
        workflow.add_node("hypothesis_generation", self._hypothesis_generation_node)
        workflow.add_node("rag_retrieval", self._rag_retrieval_node)
        workflow.add_node("gap_analysis", self._gap_analysis_node)
        workflow.add_node("response_planning", self._response_planning_node)

        # ノードの定義 (Innovation)
        workflow.add_node("structural_analysis", self._structural_analysis_node)
        workflow.add_node("variant_generation", self._variant_generation_node)
        workflow.add_node("innovation_synthesis", self._innovation_synthesis_node)

        # ノードの定義 (Report)
        workflow.add_node("report_generation", self._report_generation_node)

        # エッジの定義
        workflow.set_entry_point("intent_router")

        # Branching based on intent
        workflow.add_conditional_edges(
            "intent_router",
            self._route_intent,
            {
                "discovery": "discovery_exploration",
                "research": "situation_analysis",
                "innovation": "structural_analysis",
                "report": "report_generation"
            }
        )

        # --- Research Flow ---
        workflow.add_edge("situation_analysis", "hypothesis_generation")
        workflow.add_conditional_edges(
            "hypothesis_generation",
            self._check_rag_needed,
            {
                "continue": "rag_retrieval",
                "skip": "response_planning"
            }
        )
        workflow.add_edge("rag_retrieval", "gap_analysis")
        workflow.add_edge("gap_analysis", "response_planning")
        workflow.add_edge("response_planning", END)

        # --- Innovation Flow ---
        workflow.add_edge("structural_analysis", "variant_generation")
        workflow.add_edge("variant_generation", "innovation_synthesis")
        workflow.add_edge("innovation_synthesis", END)

        # --- Report Flow ---
        workflow.add_edge("report_generation", END)

        # --- Discovery Flow ---
        workflow.add_edge("discovery_exploration", END)

        return workflow.compile()

    def invoke(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        ワークフローを実行する。
        """
        return self.graph.invoke(initial_state)

    # --- Node Functions ---

    def _intent_router_node(self, state: GraphState) -> Dict[str, Any]:
        """意図判定ノード (State update only, routing is done by conditional edge)"""
        mode = self.intent_router.route(state.copy())
        return {"mode": mode}

    def _route_intent(self, state: GraphState) -> str:
        """条件付きエッジのためのルーティング関数"""
        return state.get("mode", "discovery")

    def _discovery_exploration_node(self, state: GraphState) -> Dict[str, Any]:
        result = self.interest_explorer.explore(state.copy())
        # AIが遷移を提案した場合、返答にそれを含める。
        # 次のターンのRouterでユーザーの同意があればモードが変わる運用。
        return {
            "bot_message": result["bot_message"],
            "mode": result.get("suggested_mode", "discovery") # 次のターンのデフォルトとして保存
        }

    # Research Nodes
    def _situation_analysis_node(self, state: GraphState) -> Dict[str, Any]:
        """状況整理ノード"""
        updated_context = self.situation_analyzer.analyze(state.copy())

        # Ensure category is valid (not "General" or None) using TopicClient if needed
        interest_profile = updated_context.get("interest_profile", {})
        current_category = interest_profile.get("current_category")

        if not current_category or current_category == "General":
            try:
                topic_client = TopicClient()
                user_msg = state.get("user_message", "")
                if user_msg:
                    predicted_category = topic_client.predict_category(user_msg)
                    if predicted_category:
                        current_category = predicted_category
                        interest_profile["current_category"] = current_category
            except Exception as e:
                print(f"Topic prediction failed in situation analysis: {e}")

            # Fallback if still invalid
            if not current_category or current_category == "General":
                current_category = "Uncategorized"
                interest_profile["current_category"] = current_category

        updated_context["interest_profile"] = interest_profile

        # Memory Consolidation
        user_id = state.get("user_id")
        if user_id:
            intent_goal = interest_profile.get("intent", {}).get("goal")
            if intent_goal:
                 self.knowledge_manager.add_user_memory(
                    user_id=user_id,
                    content=f"User Goal: {intent_goal}",
                    memory_type="ai_insight",
                    category=current_category, # Now guaranteed to be predicted if possible
                    meta={"source": "situation_analysis"}
                )
        return {
            "interest_profile": updated_context["interest_profile"],
            "active_hypotheses": updated_context["active_hypotheses"],
            "conversation_summary": updated_context.get("conversation_summary", "")
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

    def _gap_analysis_node(self, state: GraphState) -> Dict[str, Any]:
        """ギャップ分析ノード"""
        updated_context = self.gap_analyzer.analyze(state.copy())
        return {
            "knowledge_gaps": updated_context.get("knowledge_gaps")
        }

    def _response_planning_node(self, state: GraphState) -> Dict[str, Any]:
        """応答設計ノード"""
        updated_context, bot_message = self.response_planner.plan_response(state.copy())
        return {
            "response_plan": updated_context.get("response_plan"),
            "bot_message": bot_message
        }

    def _check_rag_needed(self, state: GraphState) -> str:
        """RAG検索が必要かどうかを判定する"""
        hypotheses = state.get("hypotheses", [])
        if hypotheses and any(isinstance(h, dict) and h.get("should_call_rag", False) for h in hypotheses):
            return "continue"
        return "skip"

    # Innovation Nodes
    def _structural_analysis_node(self, state: GraphState) -> Dict[str, Any]:
        updated_context = self.structural_analyzer.analyze(state.copy())
        return {"structural_analysis": updated_context.get("structural_analysis")}

    def _variant_generation_node(self, state: GraphState) -> Dict[str, Any]:
        updated_context = self.variant_generator.generate(state.copy())
        return {"idea_variants": updated_context.get("idea_variants")}

    def _innovation_synthesis_node(self, state: GraphState) -> Dict[str, Any]:
        updated_context = self.innovation_synthesizer.synthesize(state.copy())
        return {
            "innovation_hypotheses": updated_context.get("innovation_hypotheses"),
            "bot_message": updated_context.get("bot_message")
        }

    # Report Nodes
    def _report_generation_node(self, state: GraphState) -> Dict[str, Any]:
        updated_context = self.report_generator.generate(state.copy())
        return {"bot_message": updated_context.get("bot_message")}
