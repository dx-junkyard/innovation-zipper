import streamlit as st
import requests
import os
import graphviz
import json
from streamlit_agraph import agraph, Node, Edge, Config

API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")

def get_base_url():
    """Helper to get base API URL"""
    base_url = API_URL.split('/user-message')[0]
    if base_url.endswith('/'):
        base_url = base_url[:-1]
    return base_url

def fetch_innovation_history(user_id):
    """APIからイノベーション履歴を取得"""
    try:
        base_url = get_base_url()
        target_url = f"{base_url}/dashboard/innovations"

        resp = requests.get(target_url, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json().get("history", [])
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return []

def fetch_knowledge_graph(user_id):
    """APIからナレッジグラフデータを取得"""
    try:
        base_url = get_base_url()
        target_url = f"{base_url}/dashboard/knowledge-graph"

        resp = requests.get(target_url, params={"user_id": user_id, "limit": 15})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # Silent error is better here as we can show 'collecting data' message in UI
        print(f"Graph fetch error: {e}")
        return None

def render_innovation_zipper(analysis_data):
    """構造分解データをGraphvizでジッパー状に可視化"""

    struct = analysis_data.get("structural_analysis", {})
    variants = analysis_data.get("idea_variants", {})
    hypotheses = analysis_data.get("innovation_hypotheses", [])

    # Graphvizオブジェクト作成 (左から右へ流れるレイアウト)
    graph = graphviz.Digraph()
    graph.attr(rankdir='LR', splines='ortho')
    graph.attr('node', shape='box', style='rounded,filled', fontname='IPAGothic') # 日本語フォント対応が必要な場合あり

    # 1. 現状構造 (Current Reality) - 青系
    with graph.subgraph(name='cluster_0') as c:
        c.attr(label='Current Structure (分解)', style='dashed', color='blue')
        c.attr('node', fillcolor='#E6F3FF', color='blue')

        # 主要な要素をノード化
        if struct.get("agent"):
            c.node('S_Agent', f"主体\n{struct['agent']}")
        if struct.get("pain"):
            c.node('S_Pain', f"痛点\n{struct['pain']}")
        if struct.get("structural_constraints"):
            c.node('S_Const', f"制約\n{struct['structural_constraints']}")
        if struct.get("system_loop"):
            c.node('S_Loop', f"悪循環\n{struct['system_loop']}")

    # 2. 亜種 (Variants/Leap) - 黄/緑系
    # ここで「飛躍」を表現。構造ノードから派生させる。
    with graph.subgraph(name='cluster_1') as c:
        c.attr(label='Variants (飛躍)', style='dashed', color='green')
        c.attr('node', fillcolor='#E8F5E9', color='green')

        # Agent Variants
        for i, v in enumerate(variants.get("agent_variants", [])[:3]): # 多すぎると見づらいので制限
            node_id = f"V_Agent_{i}"
            c.node(node_id, v)
            graph.edge('S_Agent', node_id, style='dashed') # 構造からの派生線

        # Constraint/Mechanism Variants
        # variant_generatorの出力キーに合わせてマッピング
        # ここでは便宜上 constraint_variants を S_Const に紐付け
        for i, v in enumerate(variants.get("constraint_variants", [])[:3]):
            node_id = f"V_Const_{i}"
            c.node(node_id, v)
            if struct.get("structural_constraints"):
                graph.edge('S_Const', node_id, style='dashed')

    # 3. 統合仮説 (Synthesis/New Reality) - 赤/オレンジ系
    # ジッパーが閉じる部分。複数の亜種から1つの仮説へ収束するイメージ。
    with graph.subgraph(name='cluster_2') as c:
        c.attr(label='Innovation Hypotheses (再結合)', style='bold', color='red')
        c.attr('node', fillcolor='#FFEBEE', color='red', shape='note')

        for i, h in enumerate(hypotheses):
            h_id = f"H_{i}"
            label = f"{h.get('title')}\n\nLogic: {h.get('logic')}"
            c.node(h_id, label)

            # 全てのVariantから仮説へ線を引くと線が多すぎるため、
            # 視覚的には「Variantsの集合」から「仮説」へ収束するように見せる透明な中間ノードを使う手もあるが、
            # シンプルに代表的なVariantから繋ぐか、ダミーエッジにする。

            # ここでは「強制結合」を表現するため、ランダムまたは全てのVariantグループから矢印を集める
            if variants.get("agent_variants"):
                graph.edge(f"V_Agent_0", h_id, color='gray')
            if variants.get("constraint_variants"):
                graph.edge(f"V_Const_0", h_id, color='gray')

    st.graphviz_chart(graph)

def render_knowledge_explorer():
    st.subheader("Explore your Interest Graph")

    user_id = st.session_state.get("user_id")
    data = fetch_knowledge_graph(user_id)

    if not data or not data.get("nodes"):
        st.info("まだ十分な知識データがありません。チャットで興味のある話題について話しかけてみてください。")
        return

    # agraph用データ変換
    nodes = []
    edges = []

    for n in data["nodes"]:
        nodes.append(Node(
            id=n["id"],
            label=n["label"],
            size=n["size"],
            color=n.get("color", "#5DADE2"),
            symbolType="circle"
        ))

    for e in data.get("edges", []):
        edges.append(Edge(
            source=e["source"],
            target=e["target"],
            label=e.get("label", ""),  # 関係名を表示
            type="STRAIGHT",           # 線を直線に
            color="#CCCCCC"            # 薄いグレーで見やすく
        ))

    config = Config(
        width=700,
        height=500,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False
    )

    # グラフ描画とクリックイベントの取得
    st.caption("ノードをクリックして詳細を確認し、分析を開始できます。")
    selected_node_id = agraph(nodes=nodes, edges=edges, config=config, key="knowledge_graph_view")

    if selected_node_id:
        st.divider()
        st.info(f"Selected Topic: **{selected_node_id}**")

        col1, col2 = st.columns([1, 2])
        with col1:
            if st.button("🧪 このテーマを構造分解する", use_container_width=True):
                # UIのタブをチャットに切り替えるトリガー（ui.py側で制御が必要だが、ここではsession_stateにセット）
                # ui.py handles navigation based on sidebar inputs usually.
                # Since we are inside the dashboard component, we might need a way to signal navigation.
                # Assuming simple instruction for now as per plan.

                # Copy to clipboard or set internal state for Chat input
                st.session_state["prefill_message"] = f"「{selected_node_id}」について構造分解して、イノベーションの機会を探してください。"
                st.success(f"『{selected_node_id}』の分析準備が整いました。チャット画面へ移動して送信してください。")

def render_innovation_history_tab():
    history = fetch_innovation_history(st.session_state["user_id"])

    if not history:
        st.info("まだイノベーションモードの記録がありません。「課題解決」や「ブレスト」と話しかけてみてください。")
        return

    # セレクターで過去のセッションを選択
    options = {f"{item['created_at']} (ID: {item['id']})": item for item in history}
    selected_time = st.selectbox("履歴を選択", list(options.keys()))

    if selected_time:
        target_data = options[selected_time]["data"]

        st.subheader("Innovation Zipper Visualization")
        st.caption("構造分解(左) → 強制発想(中) → 再結合(右)")

        render_innovation_zipper(target_data)

        # 詳細テキスト表示
        with st.expander("詳細データを見る"):
            st.json(target_data)

def show_dashboard():
    st.header("Dashboard 🧠")

    if "user_id" not in st.session_state:
        st.warning("ログインしてください")
        return

    # タブの作成
    tab1, tab2 = st.tabs(["🔭 Knowledge Explorer", "🧬 Innovation History"])

    with tab1:
        render_knowledge_explorer()

    with tab2:
        render_innovation_history_tab()
