
def ensure_login():
    import streamlit as st
    st.session_state["user_id"] = "test-user-id"
    st.session_state["line_access_token"] = "mock-token"
