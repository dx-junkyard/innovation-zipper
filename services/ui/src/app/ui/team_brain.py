"""
Team Brain UI

3階層ナレッジプラットフォームのStreamlit UI
- 1階: 思考の私有地 (Private Layer)
- 2階: 情報の関所 (Gateway Layer)
- 3階: 共創の広場 (Public Layer)
"""

import json
import logging
import os
import requests
import streamlit as st
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

API_BASE_URL = os.environ.get("API_URL", "http://api:8000").rstrip("/api/v1/chat/stream")
if API_BASE_URL.endswith("/api/v1/chat/stream"):
    API_BASE_URL = API_BASE_URL.replace("/api/v1/chat/stream", "")
TEAM_BRAIN_API = f"{API_BASE_URL}/api/v1/team-brain"


def get_user_id() -> str:
    """Get current user ID from session."""
    return st.session_state.get("user_id", "")


def api_call(endpoint: str, method: str = "GET", data: Dict = None) -> Dict:
    """Make API call to Team Brain endpoints."""
    url = f"{TEAM_BRAIN_API}/{endpoint}"
    try:
        if method == "GET":
            resp = requests.get(url, params=data)
        else:
            resp = requests.post(url, json=data)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"API call failed: {e}")
        return {"error": str(e)}


def show_team_brain_dashboard():
    """
    Team Brain メインダッシュボード
    """
    st.title("Team Brain")
    st.caption("仮説の共創と検証の循環")

    user_id = get_user_id()
    if not user_id:
        st.warning("ログインしてください")
        return

    # タブで機能を分ける
    tab1, tab2, tab3, tab4 = st.tabs([
        "思考の私有地",
        "情報の関所",
        "共創の広場",
        "集合知RAG"
    ])

    with tab1:
        render_private_layer(user_id)

    with tab2:
        render_gateway_layer(user_id)

    with tab3:
        render_public_layer(user_id)

    with tab4:
        render_collective_wisdom(user_id)


# =============================================================================
# 1階: 思考の私有地 (Private Layer)
# =============================================================================

def render_private_layer(user_id: str):
    """1階: 思考の私有地"""
    st.header("思考の私有地")
    st.caption("経験の言語化と仮説の構造化")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("経験から仮説を生成")
        with st.form("incubate_form"):
            experience = st.text_area(
                "今日の経験やメモを入力してください",
                placeholder="今日、Aという対応をしたらBという反応があった...",
                height=150
            )
            auto_score = st.checkbox("自動スコアリング", value=True)
            check_sharing = st.checkbox("共有サジェストをチェック", value=True)
            submitted = st.form_submit_button("仮説を生成")

            if submitted and experience:
                with st.spinner("仮説を生成しています..."):
                    result = api_call("hypotheses/incubate", "POST", {
                        "user_id": user_id,
                        "experience": experience,
                        "auto_score": auto_score,
                        "check_sharing": check_sharing
                    })

                    if result.get("success"):
                        st.success("仮説が生成されました！")

                        # 構造化された仮説を表示
                        hypothesis = result.get("structured_hypothesis", {})
                        st.markdown("### 構造化された仮説")
                        st.info(hypothesis.get("statement", ""))

                        with st.expander("詳細を見る"):
                            st.json(hypothesis)

                        # 推論の根拠
                        if result.get("reasoning"):
                            st.markdown("**推論の根拠:**")
                            st.write(result["reasoning"])

                        # ブラッシュアップの提案
                        suggestions = result.get("refinement_suggestions", [])
                        if suggestions:
                            st.markdown("**ブラッシュアップの提案:**")
                            for s in suggestions:
                                st.write(f"- {s}")

                        # 品質スコア
                        if result.get("quality_score"):
                            render_quality_score(result["quality_score"])

                        # 共有サジェスト
                        if result.get("sharing_suggestion"):
                            render_sharing_suggestion(result["sharing_suggestion"])

                    else:
                        st.error(result.get("error", "仮説の生成に失敗しました"))

    with col2:
        st.subheader("私の仮説一覧")

        # フィルター
        status_filter = st.selectbox(
            "ステータス",
            ["すべて", "DRAFT", "PROPOSED", "SHARED"]
        )
        verification_filter = st.selectbox(
            "検証状態",
            ["すべて", "UNVERIFIED", "IN_PROGRESS", "VALIDATED", "FAILED"]
        )

        params = {"user_id": user_id, "limit": 20}
        if status_filter != "すべて":
            params["status"] = status_filter
        if verification_filter != "すべて":
            params["verification_state"] = verification_filter

        result = api_call("hypotheses/my", "GET", params)
        hypotheses = result.get("hypotheses", [])

        if not hypotheses:
            st.info("まだ仮説がありません。経験を入力して仮説を生成しましょう！")
        else:
            for h in hypotheses:
                render_hypothesis_card(h, user_id, editable=True)


def render_hypothesis_card(hypothesis: Dict, user_id: str, editable: bool = False):
    """仮説カードを表示"""
    content = hypothesis.get("content", "")
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        parsed = {"statement": content}

    status = hypothesis.get("status", "DRAFT")
    verification = hypothesis.get("verification_state", "UNVERIFIED")

    # ステータスバッジの色
    status_colors = {
        "DRAFT": "gray",
        "PROPOSED": "orange",
        "SHARED": "green"
    }
    verification_colors = {
        "UNVERIFIED": "gray",
        "IN_PROGRESS": "blue",
        "VALIDATED": "green",
        "FAILED": "red"
    }

    with st.container():
        st.markdown(f"""
        <div style="border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                <span style="background-color: {status_colors.get(status, 'gray')}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{status}</span>
                <span style="background-color: {verification_colors.get(verification, 'gray')}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{verification}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown(f"**{parsed.get('statement', content)[:200]}**")

        if parsed.get("tags"):
            st.caption(" ".join([f"#{t}" for t in parsed["tags"]]))

        # 品質スコア
        quality = hypothesis.get("quality_score")
        if quality:
            cols = st.columns(4)
            with cols[0]:
                st.metric("新規性", f"{quality.get('novelty', 0):.2f}")
            with cols[1]:
                st.metric("具体性", f"{quality.get('specificity', 0):.2f}")
            with cols[2]:
                st.metric("影響度", f"{quality.get('impact', 0):.2f}")
            with cols[3]:
                st.metric("総合", f"{quality.get('overall', 0):.2f}")

        # 検証ステータス更新（編集可能な場合）
        if editable and status == "DRAFT":
            with st.expander("検証ステータスを更新"):
                new_state = st.selectbox(
                    "新しい検証状態",
                    ["UNVERIFIED", "IN_PROGRESS", "VALIDATED", "FAILED"],
                    key=f"state_{hypothesis.get('id')}"
                )
                notes = st.text_input("メモ", key=f"notes_{hypothesis.get('id')}")

                if st.button("更新", key=f"update_{hypothesis.get('id')}"):
                    result = api_call("hypotheses/verification-state", "POST", {
                        "user_id": user_id,
                        "hypothesis_id": hypothesis.get("id"),
                        "verification_state": new_state,
                        "notes": notes
                    })
                    if result.get("success"):
                        st.success("更新しました")
                        st.rerun()
                    else:
                        st.error(result.get("error", "更新に失敗しました"))

        st.markdown("---")


def render_quality_score(score: Dict):
    """品質スコアを表示"""
    st.markdown("### 品質スコア")
    cols = st.columns(4)
    with cols[0]:
        st.metric("新規性", f"{score.get('novelty_score', 0):.2f}")
    with cols[1]:
        st.metric("具体性", f"{score.get('specificity_score', 0):.2f}")
    with cols[2]:
        st.metric("影響度", f"{score.get('impact_score', 0):.2f}")
    with cols[3]:
        is_high = "High Potential" if score.get("is_high_potential") else "-"
        st.metric("総合", f"{score.get('overall_score', 0):.2f}", delta=is_high)


def render_sharing_suggestion(suggestion: Dict):
    """共有サジェストを表示"""
    st.markdown("---")
    st.markdown("### 共有のご提案")
    st.info(suggestion.get("message", "この仮説はチームにとって有益な知見になりそうです。"))

    if suggestion.get("benefits"):
        st.markdown("**共有のメリット:**")
        for b in suggestion["benefits"]:
            st.write(f"- {b}")


# =============================================================================
# 2階: 情報の関所 (Gateway Layer)
# =============================================================================

def render_gateway_layer(user_id: str):
    """2階: 情報の関所"""
    st.header("情報の関所")
    st.caption("「筋の良い仮説」の選別と共有サジェスト")

    # 保留中のサジェストを表示
    st.subheader("保留中の共有サジェスト")

    result = api_call("suggestions/pending", "GET", {"user_id": user_id})
    suggestions = result.get("suggestions", [])

    if not suggestions:
        st.info("現在、保留中の共有サジェストはありません")
    else:
        for s in suggestions:
            with st.container():
                st.markdown(f"### 仮説: {s.get('hypothesis_content', '')[:100]}...")
                st.write(f"**提案理由:** {s.get('suggestion_reason', '')}")

                # 匿名化ドラフトのプレビュー
                with st.expander("匿名化ドラフトをプレビュー"):
                    try:
                        draft = json.loads(s.get("draft_content", "{}"))
                        st.json(draft)
                    except json.JSONDecodeError:
                        st.text(s.get("draft_content", ""))

                col1, col2, col3 = st.columns(3)

                with col1:
                    if st.button("承認して共有", key=f"accept_{s.get('id')}"):
                        result = api_call("suggestions/respond", "POST", {
                            "suggestion_id": s.get("id"),
                            "user_id": user_id,
                            "action": "accept"
                        })
                        if result.get("success"):
                            st.success("共有しました！")
                            st.rerun()

                with col2:
                    if st.button("編集して共有", key=f"edit_{s.get('id')}"):
                        st.session_state[f"editing_{s.get('id')}"] = True

                with col3:
                    if st.button("拒否", key=f"reject_{s.get('id')}"):
                        result = api_call("suggestions/respond", "POST", {
                            "suggestion_id": s.get("id"),
                            "user_id": user_id,
                            "action": "reject"
                        })
                        if result.get("success"):
                            st.info("サジェストを拒否しました")
                            st.rerun()

                # 編集モード
                if st.session_state.get(f"editing_{s.get('id')}"):
                    edited = st.text_area(
                        "内容を編集",
                        value=s.get("draft_content", ""),
                        key=f"edited_content_{s.get('id')}"
                    )
                    if st.button("編集を確定して共有", key=f"submit_edit_{s.get('id')}"):
                        result = api_call("suggestions/respond", "POST", {
                            "suggestion_id": s.get("id"),
                            "user_id": user_id,
                            "action": "edit",
                            "edited_content": edited
                        })
                        if result.get("success"):
                            st.success("編集して共有しました！")
                            st.session_state[f"editing_{s.get('id')}"] = False
                            st.rerun()

                st.markdown("---")


# =============================================================================
# 3階: 共創の広場 (Public Layer)
# =============================================================================

def render_public_layer(user_id: str):
    """3階: 共創の広場"""
    st.header("共創の広場")
    st.caption("集合知としての仮説バンク")

    # フィルター
    col1, col2 = st.columns(2)
    with col1:
        verification_filter = st.selectbox(
            "検証状態でフィルター",
            ["すべて", "VALIDATED", "FAILED", "IN_PROGRESS", "UNVERIFIED"],
            key="public_verification_filter"
        )
    with col2:
        limit = st.slider("表示件数", 10, 100, 50)

    params = {"limit": limit}
    if verification_filter != "すべて":
        params["verification_state"] = verification_filter

    result = api_call("hypotheses/shared", "GET", params)
    hypotheses = result.get("hypotheses", [])

    if not hypotheses:
        st.info("まだ共有された仮説がありません")
    else:
        for h in hypotheses:
            render_shared_hypothesis_card(h, user_id)


def render_shared_hypothesis_card(hypothesis: Dict, user_id: str):
    """共有された仮説カードを表示"""
    content = hypothesis.get("content", "")
    try:
        parsed = json.loads(content) if isinstance(content, str) else content
    except json.JSONDecodeError:
        parsed = {"statement": content}

    verification = hypothesis.get("verification_state", "UNVERIFIED")
    total_v = hypothesis.get("total_verifications", 0)
    success_c = hypothesis.get("success_count", 0)
    failure_c = hypothesis.get("failure_count", 0)

    with st.container():
        st.markdown(f"### {parsed.get('statement', content)[:150]}...")

        # 検証サマリー
        cols = st.columns(4)
        with cols[0]:
            st.metric("検証状態", verification)
        with cols[1]:
            st.metric("総検証回数", total_v)
        with cols[2]:
            st.metric("成功", success_c)
        with cols[3]:
            st.metric("失敗", failure_c)

        # 検証結果を追加
        with st.expander("検証結果を追加する"):
            new_result = st.selectbox(
                "検証結果",
                ["SUCCESS", "FAILURE", "PARTIAL", "INCONCLUSIVE"],
                key=f"verify_result_{hypothesis.get('id')}"
            )
            conditions = st.text_input(
                "検証条件",
                key=f"verify_conditions_{hypothesis.get('id')}"
            )
            notes = st.text_area(
                "メモ",
                key=f"verify_notes_{hypothesis.get('id')}"
            )

            if st.button("検証結果を追加", key=f"add_verify_{hypothesis.get('id')}"):
                result = api_call("hypotheses/verify", "POST", {
                    "user_id": user_id,
                    "hypothesis_id": hypothesis.get("id"),
                    "verification_result": new_result,
                    "conditions": conditions,
                    "notes": notes
                })
                if result.get("success"):
                    st.success("検証結果を追加しました！")
                    st.rerun()
                else:
                    st.error(result.get("error", "追加に失敗しました"))

        # 検証履歴を表示
        with st.expander("検証履歴を見る"):
            verifications = api_call(
                f"hypotheses/{hypothesis.get('id')}/verifications",
                "GET"
            )

            if verifications.get("success"):
                v_list = verifications.get("verifications", [])
                if v_list:
                    for v in v_list:
                        result_color = {
                            "SUCCESS": "green",
                            "FAILURE": "red",
                            "PARTIAL": "orange",
                            "INCONCLUSIVE": "gray"
                        }.get(v.get("verification_result"), "gray")

                        st.markdown(f"""
                        <div style="border-left: 4px solid {result_color}; padding-left: 12px; margin-bottom: 8px;">
                            <strong>{v.get('verification_result')}</strong>
                            {f" - {v.get('team_name')}" if v.get('team_name') else ""}
                            <br><small>{v.get('conditions', '')}</small>
                            <br><small style="color: gray;">{v.get('notes', '')}</small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("まだ検証結果がありません")

        st.markdown("---")


# =============================================================================
# 循環型RAG (Cross-Layer RAG)
# =============================================================================

def render_collective_wisdom(user_id: str):
    """循環型RAG: 集合知を活用した思考支援"""
    st.header("集合知RAG")
    st.caption("他者の検証結果を自考に活かす")

    st.subheader("あなたの思考を入力")
    thought = st.text_area(
        "試そうと思っていること、検討していることを入力してください",
        placeholder="Xという方法を試そうと思う...",
        height=100
    )

    if st.button("集合知を検索", disabled=not thought):
        with st.spinner("関連する検証結果を検索しています..."):
            result = api_call("think", "POST", {
                "user_id": user_id,
                "thought": thought
            })

            if result.get("success"):
                if result.get("has_relevant_info"):
                    # アドバイスタイプに応じた表示
                    advice_type = result.get("advice_type", "information")

                    if advice_type == "warning":
                        st.warning(f"⚠️ {result.get('main_message', '')}")
                    elif advice_type == "recommendation":
                        st.success(f"✅ {result.get('main_message', '')}")
                    else:
                        st.info(f"ℹ️ {result.get('main_message', '')}")

                    # 関連仮説のサマリー
                    summaries = result.get("related_hypotheses_summary", [])
                    if summaries:
                        st.subheader("関連する仮説と検証結果")
                        for s in summaries:
                            status_icon = {
                                "VALIDATED": "✅",
                                "FAILED": "❌",
                                "IN_PROGRESS": "🔄",
                                "UNVERIFIED": "❓"
                            }.get(s.get("status"), "❓")

                            st.markdown(f"""
                            **{status_icon} {s.get('summary', '')}**
                            - 関連性: {s.get('relevance', '')}
                            - 検証サマリー: {s.get('verification_summary', 'なし')}
                            """)

                    # 推奨アクション
                    actions = result.get("suggested_actions", [])
                    if actions:
                        st.subheader("推奨アクション")
                        for a in actions:
                            st.write(f"- {a}")

                    # 差分検証の機会
                    diff_opp = result.get("differential_opportunity", {})
                    if diff_opp.get("exists"):
                        st.subheader("差分検証の機会")
                        st.info(diff_opp.get("description", ""))

                else:
                    st.info("関連する検証済み仮説は見つかりませんでした。新しい仮説として登録することをお勧めします。")
            else:
                st.error(result.get("error", "検索に失敗しました"))

    # 差分検証セクション
    st.markdown("---")
    st.subheader("差分検証を提案する")
    st.caption("既存の仮説に対して、新しい条件での検証を提案")

    with st.form("differential_form"):
        hypothesis_id = st.text_input("参照する仮説ID")
        new_conditions = st.text_area(
            "新しい検証条件",
            placeholder="別の条件で検証したい場合、その条件を記述してください"
        )
        submitted = st.form_submit_button("差分検証を提案")

        if submitted and hypothesis_id and new_conditions:
            with st.spinner("提案を分析しています..."):
                result = api_call("differential/suggest", "POST", {
                    "user_id": user_id,
                    "hypothesis_id": hypothesis_id,
                    "new_conditions": new_conditions
                })

                if result.get("success"):
                    if result.get("should_verify"):
                        st.success("この差分検証は価値があります！")
                        st.write(f"**価値評価:** {result.get('verification_value', '')}")
                        st.write(f"**根拠:** {result.get('rationale', '')}")

                        if result.get("expected_insights"):
                            st.write("**期待される知見:**")
                            for i in result["expected_insights"]:
                                st.write(f"- {i}")
                    else:
                        st.warning("類似の条件での検証が既に行われています")
                else:
                    st.error(result.get("error", "提案の分析に失敗しました"))
