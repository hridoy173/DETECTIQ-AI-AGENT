"""Case card used on the Cases page."""
import streamlit as st

from components.theme import badge


def render_case_card(case: dict, confirming: bool) -> str | None:
    """Draw one card. Returns the action clicked: open | ask_delete | confirm_delete | cancel_delete | None."""
    action = None
    key = f"case_{case['id']}"
    with st.container(border=True):
        left, right = st.columns([4, 1])
        left.markdown(f"**{case['title']}**  \n<span class='muted'>{case['case_number']} · {case['incident_type']} · "
                      f"{case['location'] or 'location unknown'} · created {case['created_at'][:16]}</span>", unsafe_allow_html=True)
        right.markdown(badge(case["status"]), unsafe_allow_html=True)
        st.caption(f"{case['evidence_count']} evidence · {case['statement_count']} statements · {case['run_count']} investigation run(s)")
        with st.expander("View case details"):
            st.write(case["description"])
            st.caption(f"Incident date: {case['incident_date'] or 'unknown'} · Last updated: {case['updated_at']}")
        if confirming:
            st.warning("Delete this case and ALL its evidence, statements, runs and reports? This cannot be undone.")
            c1, c2, _ = st.columns([1, 1, 3])
            if c1.button("Yes, delete", key=f"{key}_yes", type="primary"):
                action = "confirm_delete"
            if c2.button("Cancel", key=f"{key}_no"):
                action = "cancel_delete"
        else:
            c1, c2, _ = st.columns([1, 1, 4])
            if c1.button("Open", key=f"{key}_open", type="primary"):
                action = "open"
            if c2.button("Delete", key=f"{key}_del"):
                action = "ask_delete"
    return action
