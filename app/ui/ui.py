import logging
import os
import requests
import json
import streamlit as st

from line_login import ensure_login

logger = logging.getLogger(__name__)


class ChatUI:
    """Main chat UI handling text and voice input."""

    API_URL = os.environ.get("API_URL", "http://api:8000/api/v1/user-message-stream")

    @staticmethod
    def call_api_stream(text: str):
        payload = {"message": text}
        if "user_id" in st.session_state:
            payload["user_id"] = st.session_state["user_id"]

        try:
            with requests.post(ChatUI.API_URL, json=payload, stream=True) as resp:
                resp.raise_for_status()
                yield from resp.iter_lines()
        except Exception as e:
            st.error(f"送信エラー: {e}")
            yield None

    def _format_message(self, text: str) -> str:
        """
        Streamlitのmarkdown表示用にテキストを整形する。
        改行コードを末尾スペース2つ+改行に変換して、強制的に改行させる。
        """
        if not text:
            return ""
        return text.replace("\n", "  \n")

    def render_chat(self):
        if "messages" not in st.session_state:
            st.session_state.messages = [
                {"role": "assistant", "content": "こんにちは！何かお困りのことはありますか？"}
            ]

        # Audio handling removed as it is out of scope for this update
        if "last_audio" in st.session_state:
            st.session_state.pop("last_audio")

        for m in st.session_state.messages:
            with st.chat_message("user" if m["role"] == "user" else "ai"):
                st.markdown(self._format_message(m["content"]))

        prompt = st.chat_input("メッセージを入力...")

        if prompt:
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(self._format_message(prompt))

            with st.chat_message("ai"):
                status_placeholder = st.status("処理を開始します...", expanded=True)
                reply_text = ""
                try:
                    for line in self.call_api_stream(prompt):
                        if not line: continue
                        data = json.loads(line)
                        if data["type"] == "progress":
                            status_placeholder.write(data["message"])
                            status_placeholder.update(label=data["message"])
                        elif data["type"] == "result":
                            reply_text = data["message"]
                            if "interest_profile" in data:
                                st.session_state.current_profile = data["interest_profile"]
                            status_placeholder.update(label="完了しました！", state="complete", expanded=False)
                except Exception as e:
                    import traceback
                    logger.error(f"Stream error: {e}")
                    logger.error(traceback.format_exc())
                    reply_text = f"エラーが発生しました: {e}"

                st.markdown(self._format_message(reply_text))

            st.session_state.messages.append({"role": "assistant", "content": reply_text})

    def render_topic_deep_dive(self, topic: str):
        """選択されたカテゴリーに関するまとめと問いかけを表示する"""
        with st.expander(f"📌 {topic} についての深掘り", expanded=True):
            with st.spinner("思考を整理しています..."):
                api_url = self.API_URL.replace("/user-message-stream", "/topic-deep-dive")
                payload = {
                    "topic": topic,
                    "user_id": st.session_state.get("user_id", "")
                }

                try:
                    resp = requests.post(api_url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()

                    st.info(f"**これまでのまとめ**\n\n{data.get('summary', '（生成できませんでした）')}")
                    st.success(f"**Next Question**\n\n{data.get('question', '（生成できませんでした）')}")

                except Exception as e:
                    st.error(f"エラーが発生しました: {e}")

                if st.button("閉じる"):
                    st.session_state.show_topic_info = False
                    st.rerun()

    def run(self):
        st.set_page_config(page_title="AI チャットアプリ", page_icon="🤖")
        ensure_login()

        # ページ切り替えロジック
        page = st.sidebar.radio("Menu", ["Chat", "Dashboard"])

        # サイドバー：関連カテゴリーボタンの表示
        st.sidebar.markdown("---")
        st.sidebar.subheader("関連カテゴリー")

        # 興味プロファイルから上位3つのトピックを取得
        profile = st.session_state.get("current_profile", {})
        topics = profile.get("topics", [])[:3]

        for topic in topics:
            if st.sidebar.button(f"🔍 {topic}", use_container_width=True):
                st.session_state.selected_topic = topic
                st.session_state.show_topic_info = True

        # --- File Upload Section ---
        st.sidebar.markdown("---")
        st.sidebar.subheader("📂 資料アップロード")
        uploaded_file = st.sidebar.file_uploader("PDFファイル", type=["pdf"])
        if uploaded_file is not None:
            file_title = st.sidebar.text_input("タイトル", value=uploaded_file.name)
            if st.sidebar.button("アップロード"):
                with st.spinner("アップロード中..."):
                    files = {"file": (uploaded_file.name, uploaded_file, "application/pdf")}
                    data = {"user_id": st.session_state.get("user_id"), "title": file_title}
                    upload_url = self.API_URL.replace("/user-message-stream", "/user-files/upload")
                    try:
                        resp = requests.post(upload_url, data=data, files=files)
                        if resp.status_code == 200:
                            st.sidebar.success("アップロード完了！")
                        else:
                            st.sidebar.error(f"エラー: {resp.text}")
                    except Exception as e:
                        st.sidebar.error(f"通信エラー: {e}")

        if page == "Chat":
            # トピックが選択されている場合は、チャット欄の上部に「まとめと質問」を表示
            if st.session_state.get("show_topic_info"):
                self.render_topic_deep_dive(st.session_state.selected_topic)
            self.render_chat()
        else:
            from dashboard import show_dashboard
            show_dashboard()


def main():
    ChatUI().run()


if __name__ == "__main__":
    main()
