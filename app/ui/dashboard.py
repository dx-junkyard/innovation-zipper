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

def fetch_neighbors(user_id, node_id):
    """ノードの隣接情報を取得"""
    try:
        base_url = get_base_url()
        target_url = f"{base_url}/dashboard/knowledge-graph/neighbors"

        resp = requests.get(target_url, params={"user_id": user_id, "node_id": node_id})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"隣接データ取得エラー: {e}")
        return {"nodes": [], "edges": []}

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

def merge_graph_data(current_nodes, current_edges, new_data, node_styles):
    """既存のグラフデータに新しいデータをマージするヘルパー関数"""
    existing_ids = {n.id for n in current_nodes}
    existing_edges = {(e.source, e.target) for e in current_edges}

    # ノードのマージ
    for n in new_data.get("nodes", []):
        if n["id"] not in existing_ids:
            node_type = n.get("type", "Concept")
            style = node_styles.get(node_type, node_styles["Concept"])

            # APIからの色指定があれば優先
            color = n.get("color") or style["color"]
            size = n.get("size") or style["size"]

            # Nodeオブジェクト作成
            # 注: agraphのNodeはkwargsを受け入れてJS側に渡すことがあるが、
            # Py側でのアクセスには限界があるため、識別子はid等に頼る。
            # ここではtypeを保持するためにkwargsとして渡す。
            current_nodes.append(Node(
                id=n["id"],
                label=n["label"],
                size=size,
                color=color,
                symbolType=style.get("symbolType", "circle"),
                title=n.get("label"), # hover
                type=node_type # カスタム属性として保持
            ))
            existing_ids.add(n["id"])

    # エッジのマージ
    for e in new_data.get("edges", []):
        if (e["source"], e["target"]) not in existing_edges:
            current_edges.append(Edge(
                source=e["source"],
                target=e["target"],
                label=e.get("label", ""),
                color="#BDC3C7"
            ))
            existing_edges.add((e["source"], e["target"]))

    return current_nodes, current_edges

def render_graph_view():
    st.subheader("Explore your Interest Graph")
    user_id = st.session_state.get("user_id")

    # ノードスタイルの定義
    NODE_STYLES = {
        "Concept": {"color": "#5DADE2", "size": 25, "symbolType": "circle"},  # Blue
        "Category": {"color": "#5DADE2", "size": 25, "symbolType": "circle"}, # Alias
        "Keyword": {"color": "#82E0AA", "size": 15, "symbolType": "diamond"}, # Green
        "Hypothesis": {"color": "#E74C3C", "size": 20, "symbolType": "triangle"}, # Red
        "User": {"color": "#F1C40F", "size": 30, "symbolType": "star"},       # Yellow
        "Document": {"color": "#95A5A6", "size": 20, "symbolType": "square"}  # Gray
    }

    # 1. Session Stateの初期化
    if "graph_nodes" not in st.session_state:
        st.session_state["graph_nodes"] = []
        st.session_state["graph_edges"] = []
        st.session_state["expanded_nodes"] = set() # 展開済みノード管理

        # 初期データのロード (Hub一覧)
        init_data = fetch_knowledge_graph(user_id)
        if init_data:
            st.session_state["graph_nodes"], st.session_state["graph_edges"] = merge_graph_data(
                [], [], init_data, NODE_STYLES
            )

    # 2. グラフ描画
    config = Config(
        width="100%",
        height=600,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#F7A7A6",
        collapsible=False,
        node={"labelProperty": "label"},
        link={"labelProperty": "type", "renderLabel": False}
    )

    st.caption("ノードをクリックして詳細を確認できます。")

    # keyを指定して状態を維持
    # Note: 環境によっては key 引数がエラーになる場合があるため削除
    selected_node_id = agraph(
        nodes=st.session_state["graph_nodes"],
        edges=st.session_state["graph_edges"],
        config=config
    )

    # 3. インタラクション処理
    if selected_node_id:
        # 選択されたノードオブジェクトを探す
        # Nodeオブジェクトの属性にアクセスする
        selected_node = next((n for n in st.session_state["graph_nodes"] if n.id == selected_node_id), None)

        if selected_node:
            # agraphのNodeクラスがkwargsを__dict__に入れると仮定
            # もし入らない場合はデフォルト値
            node_type = getattr(selected_node, "type", "Concept")

            # --- ACTION PANEL ---
            with st.sidebar:
                st.header(f"Selected: {selected_node.label}")
                st.markdown(f"Type: **{node_type}**")

                # A. Hubの場合: 展開/収納
                if node_type in ["Concept", "Category"]:
                    if selected_node_id in st.session_state["expanded_nodes"]:
                        st.success("展開済み (Expanded)")
                    else:
                        if st.button("📡 関連情報を展開する (Expand)", key=f"expand_{selected_node_id}"):
                            with st.spinner("関連情報を取得中..."):
                                # APIを叩いてデータを取得
                                neighbors = fetch_neighbors(user_id, selected_node_id)

                                # データをマージ
                                st.session_state["graph_nodes"], st.session_state["graph_edges"] = merge_graph_data(
                                    st.session_state["graph_nodes"],
                                    st.session_state["graph_edges"],
                                    neighbors,
                                    NODE_STYLES
                                )

                                # 展開済みフラグを立てる
                                st.session_state["expanded_nodes"].add(selected_node_id)
                                st.rerun() # 再描画して新しいノードを表示

                # B. Leafの場合: 詳細表示
                elif node_type == "Hypothesis":
                    st.info("仮説の詳細情報はチャットで確認できます。")

                st.divider()
                # 共通: 構造分解ボタン
                if st.button("🧪 構造分解する", key=f"analyze_{selected_node_id}"):
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
        render_graph_view()

    with tab2:
        render_innovation_history_tab()
