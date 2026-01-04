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

def fetch_all_user_contents(user_id):
    """APIからユーザーの全コンテンツ（ファイル、Webクリップ）を取得"""
    try:
        base_url = get_base_url()
        target_url = f"{base_url}/user-contents"

        resp = requests.get(target_url, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json().get("contents", [])
    except Exception as e:
        st.error(f"コンテンツ取得エラー: {e}")
        return []

def send_content_feedback(user_id, content_id, content_type, new_category, text_to_learn=None):
    """コンテンツのカテゴリフィードバックを送信"""
    try:
        base_url = get_base_url()
        target_url = f"{base_url}/feedback/content"

        payload = {
            "user_id": user_id,
            "content_id": content_id,
            "content_type": content_type,
            "new_category": new_category,
            "text_to_learn": text_to_learn
        }
        resp = requests.post(target_url, json=payload)
        resp.raise_for_status()
        return True
    except Exception as e:
        st.error(f"フィードバック送信エラー: {e}")
        return False

def render_data_management_tab():
    st.subheader("🗃️ Knowledge Gardening (データ管理・育成)")
    user_id = st.session_state.get("user_id")

    # リロードボタン
    if st.button("🔄 データを更新"):
        st.rerun()

    contents = fetch_all_user_contents(user_id)

    if not contents:
        st.info("まだ登録されたコンテンツがありません。")
        return

    # Header
    cols = st.columns([3, 2, 2, 2])
    cols[0].markdown("**タイトル / ソース**")
    cols[1].markdown("**現在のカテゴリ**")
    cols[2].markdown("**修正**")
    cols[3].markdown("**アクション**")

    for idx, item in enumerate(contents):
        with st.container():
            cols = st.columns([3, 2, 2, 2])

            # 1. Title & Source
            icon = "📄" if item['type'] == 'file' else "🌐"
            source_display = item['source']
            if len(source_display) > 30:
                source_display = source_display[:27] + "..."

            cols[0].markdown(f"{icon} **{item['title']}**\n\n<span style='color:gray; font-size:0.8em'>{source_display}</span>", unsafe_allow_html=True)

            # 2. Current Category
            is_verified = item.get("is_verified", False)
            status_icon = "✅" if is_verified else "❓"
            cols[1].markdown(f"{status_icon} {item.get('category', 'Uncategorized')}")

            # 3. Modification
            new_cat = cols[2].text_input("新しいカテゴリ", value=item.get('category', ''), key=f"cat_{item['id']}_{item['type']}")

            # 4. Action
            if cols[3].button("学習・更新", key=f"btn_{item['id']}_{item['type']}"):
                if new_cat and new_cat != item.get('category'):
                    text_to_learn = f"{item['title']} {item['source']}"

                    if send_content_feedback(user_id, item['id'], item['type'], new_cat, text_to_learn):
                        st.success(f"更新しました: {new_cat}")
                        st.rerun()
                else:
                    st.warning("カテゴリを変更してください。")

            st.divider()

def render_innovation_zipper(analysis_data):
    """構造分解データをGraphvizでジッパー状に可視化"""

    struct = analysis_data.get("structural_analysis", {})
    variants = analysis_data.get("idea_variants", {})
    hypotheses = analysis_data.get("innovation_hypotheses", [])

    graph = graphviz.Digraph()
    graph.attr(rankdir='LR', splines='ortho')
    graph.attr('node', shape='box', style='rounded,filled', fontname='IPAGothic')

    # 1. 現状構造 (Current Reality)
    with graph.subgraph(name='cluster_0') as c:
        c.attr(label='Current Structure (分解)', style='dashed', color='blue')
        c.attr('node', fillcolor='#E6F3FF', color='blue')

        if struct.get("agent"):
            c.node('S_Agent', f"主体\n{struct['agent']}")
        if struct.get("pain"):
            c.node('S_Pain', f"痛点\n{struct['pain']}")
        if struct.get("structural_constraints"):
            c.node('S_Const', f"制約\n{struct['structural_constraints']}")
        if struct.get("system_loop"):
            c.node('S_Loop', f"悪循環\n{struct['system_loop']}")

    # 2. 亜種 (Variants/Leap)
    with graph.subgraph(name='cluster_1') as c:
        c.attr(label='Variants (飛躍)', style='dashed', color='green')
        c.attr('node', fillcolor='#E8F5E9', color='green')

        for i, v in enumerate(variants.get("agent_variants", [])[:3]):
            node_id = f"V_Agent_{i}"
            c.node(node_id, v)
            graph.edge('S_Agent', node_id, style='dashed')

        for i, v in enumerate(variants.get("constraint_variants", [])[:3]):
            node_id = f"V_Const_{i}"
            c.node(node_id, v)
            if struct.get("structural_constraints"):
                graph.edge('S_Const', node_id, style='dashed')

    # 3. 統合仮説 (Synthesis/New Reality)
    with graph.subgraph(name='cluster_2') as c:
        c.attr(label='Innovation Hypotheses (再結合)', style='bold', color='red')
        c.attr('node', fillcolor='#FFEBEE', color='red', shape='note')

        for i, h in enumerate(hypotheses):
            h_id = f"H_{i}"
            label = f"{h.get('title')}\n\nLogic: {h.get('logic')}"
            c.node(h_id, label)

            if variants.get("agent_variants"):
                graph.edge(f"V_Agent_0", h_id, color='gray')
            if variants.get("constraint_variants"):
                graph.edge(f"V_Const_0", h_id, color='gray')

    st.graphviz_chart(graph)

def merge_graph_data(current_nodes, current_edges, new_data, node_styles):
    """既存のグラフデータに新しいデータをマージするヘルパー関数"""
    existing_ids = {n.id for n in current_nodes}
    existing_edges = {(e.source, e.target) for e in current_edges}

    for n in new_data.get("nodes", []):
        if n["id"] not in existing_ids:
            node_type = n.get("type", "Concept")
            style = node_styles.get(node_type, node_styles["Concept"])

            color = n.get("color") or style["color"]
            size = n.get("size") or style["size"]

            current_nodes.append(Node(
                id=n["id"],
                label=n["label"],
                size=size,
                color=color,
                shape=style.get("shape", "dot"),
                title=n.get("label"),
                type=node_type,
                properties=n.get("properties", {})
            ))
            existing_ids.add(n["id"])

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
        "Concept": {"color": "#5DADE2", "size": 25, "shape": "dot"},       # symbolType -> shape
        "Category": {"color": "#5DADE2", "size": 25, "shape": "dot"},
        "Keyword": {"color": "#82E0AA", "size": 15, "shape": "diamond"},
        "Hypothesis": {"color": "#E74C3C", "size": 20, "shape": "triangle"},
        "User": {"color": "#F1C40F", "size": 30, "shape": "star"},
        "Document": {"color": "#95A5A6", "size": 20, "shape": "box"}
    }

    # 1. Session Stateの初期化
    if "graph_nodes" not in st.session_state:
        st.session_state["graph_nodes"] = []
        st.session_state["graph_edges"] = []
        st.session_state["expanded_nodes"] = set()

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

    selected_node_id = agraph(
        nodes=st.session_state["graph_nodes"],
        edges=st.session_state["graph_edges"],
        config=config
    )

    # 3. インタラクション処理
    if selected_node_id:
        # 選択されたノードオブジェクトを探す
        selected_node = next((n for n in st.session_state["graph_nodes"] if n.id == selected_node_id), None)

        # ★重要: 以下のブロックは selected_node が存在する場合のみ実行されるようにインデントされています
        if selected_node:
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
                                neighbors = fetch_neighbors(user_id, selected_node_id)
                                st.session_state["graph_nodes"], st.session_state["graph_edges"] = merge_graph_data(
                                    st.session_state["graph_nodes"],
                                    st.session_state["graph_edges"],
                                    neighbors,
                                    NODE_STYLES
                                )
                                st.session_state["expanded_nodes"].add(selected_node_id)
                                st.rerun()

                # B. Leafの場合: 詳細表示
                elif node_type == "Hypothesis":
                    props = getattr(selected_node, "properties", {})
                    st.markdown("### 📝 仮説の内容")
                    st.info(props.get("text", "詳細テキストがありません"))
                    if "logic" in props:
                        st.markdown(f"**ロジック:** {props['logic']}")

                elif node_type == "Document":
                    props = getattr(selected_node, "properties", {})
                    st.markdown(f"### 📄 {props.get('title', 'ドキュメント')}")
                    if "summary" in props:
                        st.caption(props["summary"])
                    if "url" in props:
                        st.link_button("🔗 元記事を開く", props["url"])

                st.divider()
                if st.button("🧪 構造分解する", key=f"analyze_{selected_node_id}"):
                    st.session_state["prefill_message"] = f"「{selected_node_id}」について構造分解して、イノベーションの機会を探してください。"
                    st.success(f"『{selected_node_id}』の分析準備が整いました。チャット画面へ移動して送信してください。")

def render_innovation_history_tab():
    history = fetch_innovation_history(st.session_state["user_id"])

    if not history:
        st.info("まだイノベーションモードの記録がありません。「課題解決」や「ブレスト」と話しかけてみてください。")
        return

    options = {f"{item['created_at']} (ID: {item['id']})": item for item in history}
    selected_time = st.selectbox("履歴を選択", list(options.keys()))

    if selected_time:
        target_data = options[selected_time]["data"]

        st.subheader("Innovation Zipper Visualization")
        st.caption("構造分解(左) → 強制発想(中) → 再結合(右)")

        render_innovation_zipper(target_data)

        with st.expander("詳細データを見る"):
            st.json(target_data)

def show_dashboard():
    st.header("Dashboard 🧠")

    if "user_id" not in st.session_state:
        st.warning("ログインしてください")
        return

    tab1, tab2, tab3 = st.tabs(["🔭 Knowledge Explorer", "🧬 Innovation History", "🗃️ Data Management"])

    with tab1:
        render_graph_view()

    with tab2:
        render_innovation_history_tab()

    with tab3:
        render_data_management_tab()
