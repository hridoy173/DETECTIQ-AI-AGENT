"""Sidebar navigation and the goto() helper used by buttons on other pages."""
import streamlit as st

import config

PAGES = ["Dashboard", "Cases", "New Investigation", "Investigation Workspace", "Reports", "Settings / About"]


def goto(page: str, case_id: int | None = None) -> None:
    """Button callback: switch page (and optionally pre-select a case)."""
    st.session_state["nav"] = page
    if case_id is not None:
        st.session_state["selected_case_id"] = case_id
        st.session_state["ws_case"] = case_id


def render_sidebar() -> str:
    with st.sidebar:
        st.markdown('<div class="brand">Detect<span>IQ</span></div><div class="tagline">AI Investigation Agent</div>', unsafe_allow_html=True)
        st.radio("Navigation", PAGES, key="nav", label_visibility="collapsed")
        st.divider()
        if config.ai_configured():
            st.caption(f"🟢 Gemini AI ready · `{config.get_model()}`")
        else:
            st.caption("🟡 No API key: rule-based mode.\nAdd GEMINI_API_KEY to `.env` for AI.")
        st.caption("Educational simulation · fictional cases only")
    return st.session_state["nav"]
