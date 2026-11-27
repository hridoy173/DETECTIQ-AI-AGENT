"""Sidebar navigation and the goto() helper used by buttons on other pages."""
import streamlit as st

import config

PAGES = ["Dashboard", "Cases", "New Investigation", "Investigation Workspace", "Reports", "Settings / About"]


def goto(page: str, case_id: int | None = None) -> None:
    """Request a page change. Safe to call from a button callback OR directly in page code.
    The change is applied at the very start of the next run (apply_pending_nav), before the sidebar radio exists."""
    st.session_state["_pending_nav"] = (page, case_id)


def apply_pending_nav() -> None:
    """Call once at the top of main(), BEFORE render_sidebar()."""
    pending = st.session_state.pop("_pending_nav", None)
    if pending:
        page, case_id = pending
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
