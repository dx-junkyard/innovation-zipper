import streamlit as st
import requests
import os
import graphviz
import json
from streamlit_agraph import agraph, Node, Edge, Config

# --- 設定読み込み部分の修正 ---
try:
    from config import settings
except ImportError:
    class MockSettings:
        S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://minio:9000")
        S3_PUBLIC_ENDPOINT_URL = os.environ.get("S3_PUBLIC_ENDPOINT_URL", "http://localhost:9000")
    settings = MockSettings()

# 環境変数からベースURLを正しく取得するロジックに変更
# API_BASE_URLが設定されていればそれを使い、なければAPI_URLから推測を試みる
ENV_API_URL = os.environ.get("API_URL", "http://api:8000/api/v1/chat/stream")
ENV_API_BASE_URL = os.environ.get("API_BASE_URL")

def get_base_url():
    """Helper to get base API URL"""
    if ENV_API_BASE_URL:
        return ENV_API_BASE_URL

    # フォールバック: API_URLから不要なパスを取り除く
    base = ENV_API_URL
    for suffix in ["/chat/stream", "/user-message"]:
        if base.endswith(suffix):
            base = base[:-len(suffix)]
            break

    if base.endswith('/'):
        base = base[:-1]
    return base

# グローバル変数として保持
BASE_URL = get_base_url()
# ---------------------------

def fetch_innovation_history(user_id):
    """APIからイノベーション履歴を取得"""
    try:
        # get_base_url() の代わりに BASE_URL を使用
        target_url = f"{BASE_URL}/dashboard/innovations"

        resp = requests.get(target_url, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json().get("history", [])
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return []

def fetch_knowledge_graph(user_id):
    """APIからナレッジグラフデータを取得"""
    try:
        target_url = f"{BASE_URL}/dashboard/knowledge-graph"

        resp = requests.get(target_url, params={"user_id": user_id, "limit": 15})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Graph fetch error: {e}")
        return None

def fetch_neighbors(user_id, node_id):
    """ノードの隣接情報を取得"""
    try:
        target_url = f"{BASE_URL}/dashboard/knowledge-graph/neighbors"

        resp = requests.get(target_url, params={"user_id": user_id, "node_id": node_id})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        st.error(f"隣接データ取得エラー: {e}")
        return {"nodes": [], "edges": []}

def fetch_all_user_contents(user_id):
    """APIからユーザーの全コンテンツ（ファイル、Webクリップ）を取得"""
    try:
        target_url = f"{BASE_URL}/user-contents"

        resp = requests.get(target_url, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json().get("contents", [])
    except Exception as e:
        st.error(f"コンテンツ取得エラー: {e}")
        return []

def send_content_feedback(user_id, content_id, content_type, new_categories, new_keywords=None, text_to_learn=None):
    """コンテンツのカテゴリ・キーワードフィードバックを送信"""
    try:
        target_url = f"{BASE_URL}/feedback/content"

        payload = {
            "user_id": user_id,
            "content_id": content_id,
            "content_type": content_type,
            "new_categories": new_categories,
            "new_keywords": new_keywords,
            "text_to_learn": text_to_learn
        }
        resp = requests.post(target_url, json=payload)
        resp.raise_for_status()
        return True
    except Exception as e:
        st.error(f"フィードバック送信エラー: {e}")
        return False

@st.cache_data
def load_categories():
    """カテゴリ定義を読み込む"""
    try:
        # パス解決のロジックは変更なし
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../topic-service/categories.json'))
        # コンテナ内のパス配置によっては調整が必要だが、現状のマウント設定ならこれで動く可能性が高い
        # もし見つからない場合は /app/topic-service/categories.json を直接指定
        if not os.path.exists(path):
             path = "/app/topic-service/categories.json"

        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        st.error(f"カテゴリ定義の読み込みに失敗しました: {e}")
        return {}

def category_edit_dialog(item, category_data, user_id):
    """カテゴリ編集用ダイアログ"""
    st.write(f"**{item['title']}** のカテゴリを編集")

    current_cats = item.get('category', [])
    if isinstance(current_cats, str):
        current_cats = [current_cats]

    current_keywords = item.get('keywords', [])
    if isinstance(current_keywords, str): # Fallback if API returns string
        current_keywords = [current_keywords]

    st.caption(f"現在のカテゴリ: {', '.join(current_cats)}")

    main_cats = list(category_data.keys())

    # 1. 大カテゴリ選択
    selected_mains = st.multiselect("大カテゴリを選択", main_cats)

    # 2. サブカテゴリ選択 (フィルタリング)
    available_subs = []
    for m in selected_mains:
        subs = category_data[m].get("subcategories", [])
        for s in subs:
            available_subs.append(s["category"])

    selected_subs = st.multiselect("サブカテゴリを選択（最終的なタグになります）", available_subs, default=[])

    st.divider()

    # 3. キーワード編集
    st.markdown("##### 🔑 固有キーワード")
    st.caption("カンマ区切りで入力してください (例: React, マイクロサービス, Docker)")
    keyword_input = st.text_area("キーワード", value=", ".join(current_keywords))

    if st.button("保存して更新"):
        new_keywords = [k.strip() for k in keyword_input.split(",") if k.strip()]
        text_to_learn = f"{item['title']} {item.get('source', '')}"

        if selected_subs or new_keywords:
             if send_content_feedback(user_id, item['id'], item['type'], selected_subs, new_keywords, text_to_learn):
                 st.success("更新しました！")
                 st.rerun()
        else:
            st.warning("カテゴリまたはキーワードを入力してください。")

@st.dialog("カテゴリ編集")
def open_category_dialog(item, category_data, user_id):
    category_edit_dialog(item, category_data, user_id)

def render_data_management_tab():
    st.subheader("🗃️ Knowledge Gardening (データ管理・育成)")
    user_id = st.session_state.get("user_id")
    category_data = load_categories()

    # リロードボタン
    if st.button("🔄 データを更新"):
        st.rerun()

    contents = fetch_all_user_contents(user_id)

    if not contents:
        st.info("まだ登録されたコンテンツがありません。")
        return

    # Header
    cols = st.columns([4, 3, 2])
    cols[0].markdown("**タイトル / ソース**")
    cols[1].markdown("**現在のカテゴリ**")
    cols[2].markdown("**アクション**")

    for idx, item in enumerate(contents):
        with st.container():
            cols = st.columns([4, 3, 2])

            # 1. Title & Source
            icon = "📄" if item['type'] == 'file' else "🌐"
            source_display = item['source']
            if len(source_display) > 30:
                source_display = source_display[:27] + "..."

            cols[0].markdown(f"{icon} **{item['title']}**\n\n<span style='color:gray; font-size:0.8em'>{source_display}</span>", unsafe_allow_html=True)

            # 2. Current Category (Tags) & Keywords
            is_verified = item.get("is_verified", False)
            status_icon = "✅" if is_verified else "❓"

            categories = item.get('category', [])
            if isinstance(categories, str): # Fallback
                categories = [categories]

            keywords = item.get('keywords', [])
            if isinstance(keywords, str):
                keywords = [keywords]

            # Simple badge-like display
            cat_html = " ".join([f"<span style='background-color:#E8F8F5; color:#148F77; padding:2px 8px; border-radius:12px; font-size:0.8em; margin-right:4px;'>{c}</span>" for c in categories])

            # Hashtag style for keywords
            kw_html = " ".join([f"<span style='color:#5D6D7E; font-size:0.8em; margin-right:4px;'>#{k}</span>" for k in keywords])

            cols[1].markdown(f"{status_icon} {cat_html}<br>{kw_html}", unsafe_allow_html=True)

            # 3. Action
            if cols[2].button("編集", key=f"edit_{item['id']}_{item['type']}"):
                open_category_dialog(item, category_data, user_id)

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

def format_node_label(text: str, max_width: int = 15, max_lines: int = 2) -> str:
    if not text:
        return ""
    words = [text[i:i+max_width] for i in range(0, len(text), max_width)]
    if len(words) > max_lines:
        return "\n".join(words[:max_lines]) + "..."
    return "\n".join(words)

def merge_graph_data(current_nodes, current_edges, new_data, node_styles):
    """既存のグラフデータに新しいデータをマージするヘルパー関数"""
    existing_ids = {n.id for n in current_nodes}

    # --- 修正開始: Edgeオブジェクトの属性アクセスを安全に行う ---
    existing_edges = set()
    for e in current_edges:
        # Edgeオブジェクトからsource/targetを取得（存在しない場合はNone）
        s = getattr(e, "source", None)
        t = getattr(e, "target", None)

        # 属性が見つからない場合のフォールバック（__dict__経由など）
        if s is None and hasattr(e, "__dict__"):
             s = e.__dict__.get("source")
             t = e.__dict__.get("target")

        if s and t:
            existing_edges.add((s, t))
    # --- 修正終了 -------------------------------------------

    for n in new_data.get("nodes", []):
        if n["id"] not in existing_ids:
            node_type = n.get("type", "Concept")
            style = node_styles.get(node_type, node_styles["Concept"])

            color = n.get("color") or style["color"]
            size = n.get("size") or style["size"]

            # プロパティから画像URLを取得
            raw_image_url = n.get("properties", {}).get("image")

            # [Fix] 画像URLの検証を厳格化 (文字列かつ http または / で始まるもののみ許可)
            is_valid_image = isinstance(raw_image_url, str) and (raw_image_url.startswith("http") or raw_image_url.startswith("/"))

            if is_valid_image:
                node_shape = "image"
                image_path = raw_image_url
            else:
                node_shape = style.get("shape", "dot")
                image_path = None

            # [Fix] フロントエンドに渡すプロパティのサニタイズ
            safe_properties = n.get("properties", {}).copy()
            if "image" in safe_properties:
                del safe_properties["image"]

            # ノードのパラメータを辞書で構築
            node_config = {
                "id": n["id"],
                "label": format_node_label(n["label"]),
                "size": size,
                "color": color,
                "shape": node_shape,
                "title": n.get("label"),
                "type": node_type,
                "properties": safe_properties
            }

            # 画像がある場合のみ image キーを追加
            if image_path:
                node_config["image"] = image_path

            current_nodes.append(Node(**node_config))
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

def get_file_url(file_id, raw_url=None):
    """Helper to get public file URL"""
    pdf_url = None
    if file_id:
        # Fetch presigned URL from API and convert to public URL
        # BASE_URLを使用
        api_target = f"{BASE_URL}/user-files/{file_id}/content"
        try:
            res = requests.get(api_target)
            if res.status_code == 200:
                data = res.json()
                raw_signed_url = data.get("url")
                if raw_signed_url:
                    pdf_url = raw_signed_url
        except Exception:
            pass
    elif raw_url:
        pdf_url = raw_url
    return pdf_url

def render_graph_view():
    st.subheader("Explore your Interest Graph")
    user_id = st.session_state.get("user_id")

    # ノードスタイルの定義
    NODE_STYLES = {
        "Concept": {"color": "#5DADE2", "size": 25, "shape": "dot"},
        "Category": {"color": "#5DADE2", "size": 25, "shape": "dot"},
        "Keyword": {"color": "#82E0AA", "size": 15, "shape": "diamond"},
        "Hypothesis": {"color": "#E74C3C", "size": 20, "shape": "triangle"},
        "User": {"color": "#F1C40F", "size": 30, "shape": "star"},
        "Document": {"color": "#95A5A6", "size": 20, "shape": "box"}
    }

    # 1. キャッシュの強制クリアと初期化
    if "graph_version" not in st.session_state or st.session_state["graph_version"] != "v2":
        st.session_state["graph_nodes"] = []
        st.session_state["graph_edges"] = []
        st.session_state["expanded_nodes"] = set()
        st.session_state["graph_version"] = "v2"
        st.session_state["last_clicked_node_id"] = None

    if not st.session_state["graph_nodes"]:
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
        groups={},
        node={
            "labelProperty": "label",
            "renderLabel": True,
            "shape": "dot"
        },
        link={"labelProperty": "type", "renderLabel": False}
    )

    st.caption("ノードをクリックして詳細を確認できます。")

    selected_node_id = agraph(
        nodes=st.session_state["graph_nodes"],
        edges=st.session_state["graph_edges"],
        config=config
    )

    # 3. インタラクション処理
    if "last_clicked_node_id" not in st.session_state:
        st.session_state["last_clicked_node_id"] = None

    if selected_node_id:
        # 新しいノードをクリック -> Expand Mode (展開)
        if selected_node_id != st.session_state["last_clicked_node_id"]:
            st.session_state["last_clicked_node_id"] = selected_node_id

            with st.spinner(f"📡 {selected_node_id} の関連情報を展開中..."):
                neighbors = fetch_neighbors(user_id, selected_node_id)
                st.session_state["graph_nodes"], st.session_state["graph_edges"] = merge_graph_data(
                    st.session_state["graph_nodes"],
                    st.session_state["graph_edges"],
                    neighbors,
                    NODE_STYLES
                )
                st.rerun()

        # 選択されたノードオブジェクトを探す
        selected_node = next((n for n in st.session_state["graph_nodes"] if n.id == selected_node_id), None)

        if selected_node:
            node_type = getattr(selected_node, "type", "Concept")

            # Helper to find neighbors in current graph
            current_node_neighbors = []
            for e in st.session_state["graph_edges"]:
                source_id = getattr(e, "source", None) or e.__dict__.get("source")
                target_id = getattr(e, "target", None) or e.__dict__.get("target")

                if source_id == selected_node.id:
                    neighbor = next((n for n in st.session_state["graph_nodes"] if n.id == target_id), None)
                    if neighbor: current_node_neighbors.append(neighbor)
                elif target_id == selected_node.id:
                    neighbor = next((n for n in st.session_state["graph_nodes"] if n.id == source_id), None)
                    if neighbor: current_node_neighbors.append(neighbor)

            # --- ACTION PANEL ---
            with st.sidebar:
                st.header(f"Selected: {selected_node.label}")
                st.markdown(f"Type: **{node_type}**")

                if st.button("🎯 このノードに集中する (Focus)"):
                    with st.spinner(f"🎯 {selected_node_id} に集中しています..."):
                        neighbors = fetch_neighbors(user_id, selected_node_id)
                        st.session_state["graph_nodes"], st.session_state["graph_edges"] = merge_graph_data(
                            [], [], neighbors, NODE_STYLES
                        )
                        st.rerun()

                if node_type in ["Concept", "Category"]:
                    if selected_node_id in st.session_state["expanded_nodes"]:
                        st.success("展開済み (Expanded)")

                elif node_type == "Hypothesis":
                    props = getattr(selected_node, "properties", {})
                    st.markdown("### 📝 仮説の内容")
                    st.info(props.get("text", "詳細テキストがありません"))
                    if "logic" in props:
                        st.markdown(f"**ロジック:** {props['logic']}")

                elif node_type == "Document":
                    props = getattr(selected_node, "properties", {})
                    st.markdown(f"### 📄 {props.get('title', 'ドキュメント')}")

                    file_id = props.get("file_id")
                    raw_url = props.get("url", "")

                    pdf_url = get_file_url(file_id, raw_url)

                    if pdf_url:
                        st.link_button("🔗 ファイルを開く (Open File)", pdf_url)
                        st.markdown(f'<iframe src="{pdf_url}" width="100%" height="600" type="application/pdf"></iframe>', unsafe_allow_html=True)
                    else:
                        st.warning("ファイルURLを取得できませんでした。")

                    if "summary" in props:
                        st.caption(props["summary"])

                    related_kws = [n for n in current_node_neighbors if getattr(n, "type", "") == "Keyword"]
                    if related_kws:
                        st.markdown("**🔑 関連キーワード:**")
                        st.write(", ".join([n.label for n in related_kws]))

                    related_cats = [n for n in current_node_neighbors if getattr(n, "type", "") in ["Concept", "Category"]]
                    if related_cats:
                        st.markdown("**🏷️ 関連カテゴリ:**")
                        st.write(", ".join([n.label for n in related_cats]))

                elif node_type == "Keyword":
                    st.markdown(f"### 🔑 {selected_node.label}")

                    related_docs = [n for n in current_node_neighbors if getattr(n, "type", "") == "Document"]
                    if related_docs:
                        st.markdown("**📂 関連ドキュメント:**")
                        for doc in related_docs:
                            doc_props = getattr(doc, "properties", {})
                            doc_title = doc_props.get("title", doc.label)

                            file_id = doc_props.get("file_id")
                            raw_url = doc_props.get("url", "")
                            doc_url = get_file_url(file_id, raw_url)

                            if doc_url:
                                st.markdown(f"- [{doc_title}]({doc_url})")
                            else:
                                st.write(f"- {doc_title}")

                    related_cats = [n for n in current_node_neighbors if getattr(n, "type", "") in ["Concept", "Category"]]
                    if related_cats:
                        st.markdown("**🏷️ 関連カテゴリ:**")
                        st.write(", ".join([c.label for c in related_cats]))

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
