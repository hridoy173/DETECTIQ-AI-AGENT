"""Dark navy theme (CSS) and small HTML helpers."""
import html

import streamlit as st

CSS = """
<style>
.block-container {padding-top: 2rem; padding-bottom: 3rem; max-width: 1250px;}
[data-testid="stSidebar"] {background: #0A101D; border-right: 1px solid #1B2740;}
h1, h2, h3 {letter-spacing: -0.01em;}
h1 {font-weight: 700;}
div[data-testid="stMetric"] {background: #111B2E; border: 1px solid #1F2F4D; border-radius: 12px; padding: 14px 18px;}
div[data-testid="stMetricValue"] {color: #7FB0FF;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-color: #1F2F4D !important; border-radius: 12px;}
.stButton > button[kind="primary"] {background: #2F6FED; border: 0;}
.stButton > button {border-radius: 8px;}
.badge {display:inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 600; border: 1px solid #2B3F66; color:#BBD2FF; background:#14233F;}
.badge-completed {color:#7EE2A8; border-color:#1F6B47; background:#0F2A20;}
.badge-failed {color:#FF9B9B; border-color:#7A2B2B; background:#2B1414;}
.badge-progress {color:#FFD27E; border-color:#7A5E1F; background:#2B2210;}
.brand {font-size: 1.35rem; font-weight: 700; color:#E6EDF7;}
.brand span {color:#4C8BF5;}
.tagline {color:#8FA3C4; font-size: 0.8rem; margin-bottom: 1rem;}
.muted {color:#8FA3C4;}
.logline {font-family: ui-monospace, Consolas, monospace; font-size: 0.85rem; padding: 2px 0;}
@media (max-width: 700px) {.block-container {padding-left: 1rem; padding-right: 1rem;}}
</style>
"""

STATUS_CLASS = {"Completed": "badge-completed", "completed": "badge-completed", "Failed": "badge-failed", "failed": "badge-failed",
                "In Progress": "badge-progress", "running": "badge-progress", "completed_with_errors": "badge-progress"}


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge(text: str) -> str:
    """HTML for a small status pill (text is escaped)."""
    return f'<span class="badge {STATUS_CLASS.get(text, "")}">{html.escape(text.replace("_", " "))}</span>'
