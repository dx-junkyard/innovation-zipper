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

# Use the same API_URL default as ui.py and derive the base endpoint for
# additional API calls such as user registration.
API_URL = os.getenv("API_URL", "http://api:8000/api/v1/user-message")
API_BASE_URL = API_URL.rsplit("/", 1)[0]
logger.info("Using API base URL: %s", API_BASE_URL)

LINE_CLIENT_ID = os.getenv("LINE_CHANNEL_ID")
LINE_CLIENT_SECRET = os.getenv("LINE_CHANNEL_SECRET")
LINE_REDIRECT_URI = os.getenv("LINE_REDIRECT_URI", "http://localhost:8080")

AUTH_URL = "https://access.line.me/oauth2/v2.1/authorize"
TOKEN_URL = "https://api.line.me/oauth2/v2.1/token"
PROFILE_URL = "https://api.line.me/v2/profile"


def _login_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": LINE_CLIENT_ID,
        "redirect_uri": LINE_REDIRECT_URI,
        "scope": "profile openid",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _exchange_code(code: str) -> dict:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": LINE_REDIRECT_URI,
        "client_id": LINE_CLIENT_ID,
        "client_secret": LINE_CLIENT_SECRET,
    }
    resp = requests.post(TOKEN_URL, data=data)
    resp.raise_for_status()
    return resp.json()


def _fetch_profile(access_token: str) -> dict:
    resp = requests.get(PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"})
    resp.raise_for_status()
    return resp.json()


def ensure_login() -> None:
    """Ensure user has logged in via LINE. Stops execution if not."""
    if "line_access_token" in st.session_state:
        logger.debug("Already logged in")
        return

    params = st.query_params.to_dict()
    logger.info("Received query params: %s", params)
    if "code" in params:
        code = params["code"]
        state = params.get("state")
        logger.info("LINE callback params - code: %s, state: %s", code, state)

        if state not in _VALID_STATES:
            logger.warning(
                "OAuth state mismatch or expired. returned=%s valid_states=%s",
                state,
                list(_VALID_STATES),
            )
            st.error("State mismatch. Please try again.")
            st.stop()

        _VALID_STATES.discard(state)
        try:
            token_data = _exchange_code(code)
            st.session_state["line_access_token"] = token_data["access_token"]
            st.session_state["line_id_token"] = token_data.get("id_token")
            profile = _fetch_profile(token_data["access_token"])
            st.session_state["line_profile"] = profile
            try:
                register_url = f"{API_BASE_URL}/users"
                payload = {"line_user_id": profile.get("userId")}
                logger.debug("POST %s payload=%s", register_url, payload)
                resp = requests.post(register_url, json=payload)
                resp.raise_for_status()
                st.session_state["user_id"] = resp.json().get("user_id")
            except Exception as exc:
                logger.exception("Failed to register user")
            # remove query params
            st.query_params.clear()
            logger.info("LINE login successful")
            return
        except Exception as exc:
            st.error(f"Login failed: {exc}")
            logger.error("Failed to exchange LINE code: %s", exc)
            st.stop()

    state = secrets.token_hex(16)
    _VALID_STATES.add(state)
    logger.info("Generated OAuth state: %s", state)
    login_url = _login_url(state)
    logger.info("Login URL: %s", login_url)
    st.markdown(f"[LINE Login]({login_url})")
    st.stop()
