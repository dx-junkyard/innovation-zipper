import streamlit as st
import requests
import os
import graphviz
import json

API_URL = os.environ.get("API_URL", "http://api:8000/api/v1")

def fetch_innovation_history(user_id):
    """APIからイノベーション履歴を取得"""
    try:
        # APIエンドポイントのURL構築
        # ui.py defines API_URL as "http://api:8000/api/v1/user-message-stream" usually.
        # We need to extract the base part.
        base_url = API_URL.split('/user-message')[0]
        if base_url.endswith('/'):
            base_url = base_url[:-1]

        target_url = f"{base_url}/dashboard/innovations"

        # Check if we are running in a container network where 'api' host is accessible,
        # or if we need to use localhost (e.g. if running locally outside docker).
        # For now, we trust the env var.

        resp = requests.get(target_url, params={"user_id": user_id})
        resp.raise_for_status()
        return resp.json().get("history", [])
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return []

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

def show_dashboard():
    st.header("Innovation Dashboard 🧬")

    if "user_id" not in st.session_state:
        st.warning("ログインしてください")
        return

    history = fetch_innovation_history(st.session_state["user_id"])

    if not history:
        st.info("まだイノベーションモードの記録がありません。「課題解決」や「ブレスト」と話しかけてみてください。")
        return

    # セレクターで過去のセッションを選択
    # Use formatted string for display
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
