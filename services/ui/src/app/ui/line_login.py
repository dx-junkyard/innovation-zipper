import os
import secrets
from urllib.parse import urlencode

import logging
import requests
import streamlit as st
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store generated OAuth state values so we can validate callbacks even when the
# Streamlit session is recreated after redirect.  Using an in-memory set keeps
# the implementation simple for a single-user environment.
_VALID_STATES: set[str] = set()

load_dotenv()

# API endpoints (internal container communication)
API_URL = os.getenv("API_URL", "http://api:8000/api/v1/user-message")
API_BASE_URL = os.getenv("API_BASE_URL", "http://api:8000/api/v1")

# Public API URL for browser redirects
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", "http://localhost:8086")

logger.info("Using API base URL: %s", API_BASE_URL)
logger.info("Using API public URL: %s", API_PUBLIC_URL)

LINE_CLIENT_ID = os.getenv("LINE_CHANNEL_ID")
# LINE_REDIRECT_URI now points to Backend's callback endpoint (public URL)
LINE_REDIRECT_URI = os.getenv("LINE_REDIRECT_URI", "http://localhost:8086/api/v1/auth/callback")

AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"


def _login_url(state: str) -> str:
    """Generate LINE OAuth login URL that redirects to Backend callback."""
    params = {
        "response_type": "code",
        "client_id": LINE_CLIENT_ID,
        "redirect_uri": LINE_REDIRECT_URI,
        "scope": "profile openid",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _verify_auth_token(token: str) -> dict:
    """Verify auth token with Backend API to get user info."""
    try:
        verify_url = f"{API_BASE_URL}/auth/verify-token"
        resp = requests.get(verify_url, params={"token": token})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Failed to verify auth token: {e}")
        return {"valid": False}


def ensure_login() -> None:
    """Ensure user has logged in via LINE. Stops execution if not."""
    # Already logged in
    if "user_id" in st.session_state and st.session_state.get("user_id"):
        logger.debug("Already logged in as user: %s", st.session_state.get("user_id"))
        return

    params = st.query_params.to_dict()
    logger.info("Received query params: %s", params)

    # Check for auth_token from Backend callback redirect
    if "auth_token" in params:
        auth_token = params["auth_token"]
        logger.info("Processing auth_token from Backend callback")

        # Verify token with Backend
        token_info = _verify_auth_token(auth_token)

        if token_info.get("valid"):
            # Login successful - restore session state
            st.session_state["user_id"] = token_info.get("user_id")
            st.session_state["line_user_id"] = token_info.get("line_user_id")
            st.session_state["line_profile"] = {
                "userId": token_info.get("line_user_id"),
                "displayName": token_info.get("display_name", "")
            }
            # Set a flag to indicate authenticated via new flow
            st.session_state["authenticated"] = True

            # Clear URL params
            st.query_params.clear()
            logger.info("LINE login successful via Backend callback for user: %s", token_info.get("user_id"))
            return
        else:
            logger.warning("Invalid or expired auth_token")
            st.query_params.clear()
            st.error("認証トークンが無効または期限切れです。再度ログインしてください。")
            # Don't stop - show login button

    # Check for auth_error from Backend callback
    if "auth_error" in params:
        error_type = params["auth_error"]
        st.query_params.clear()
        error_messages = {
            "server_config": "サーバー設定エラーが発生しました。管理者にお問い合わせください。",
            "token_exchange": "LINE認証中にエラーが発生しました。再度お試しください。",
            "profile_fetch": "プロフィール取得に失敗しました。再度お試しください。"
        }
        st.error(error_messages.get(error_type, "認証エラーが発生しました。"))
        # Don't stop - show login button

    # Generate new OAuth state and show login button
    state = secrets.token_hex(16)
    _VALID_STATES.add(state)
    logger.info("Generated OAuth state: %s", state)
    login_url = _login_url(state)
    logger.info("Login URL: %s", login_url)
    st.link_button("LINE Login", login_url)
    st.stop()
