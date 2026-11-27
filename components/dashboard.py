"""Dashboard page content."""
import plotly.express as px
import streamlit as st

from components.sidebar import goto
from components.theme import badge
from services import case_service


def _style(fig):
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(l=10, r=10, t=40, b=10), height=300)
    return fig


def _load_demo() -> None:
    goto("Investigation Workspace", case_service.load_demo_case())


def render_dashboard() -> None:
    stats = case_service.get_stats()
    cols = st.columns(5)
    for col, (label, key) in zip(cols, [("Total cases", "total_cases"), ("Active investigations", "active"), ("Completed", "completed"),
                                         ("Total evidence", "total_evidence"), ("Investigation runs", "total_runs")]):
        col.metric(label, stats[key])

    st.subheader("Quick actions")
    a, b, c, _ = st.columns([1.3, 1.3, 1.3, 2])
    a.button("➕ New investigation", on_click=goto, args=("New Investigation",), type="primary")
    b.button("📂 Load demo case", on_click=_load_demo)
    c.button("📄 View reports", on_click=goto, args=("Reports",))

    left, right = st.columns(2)
    with left:
        if stats["by_status"]:
            fig = px.pie(names=list(stats["by_status"]), values=list(stats["by_status"].values()), hole=0.55, title="Cases by status",
                         color_discrete_sequence=["#4C8BF5", "#7EE2A8", "#F5B84C", "#FF8C8C"])
            st.plotly_chart(_style(fig))
        else:
            st.info("No cases yet. Create one or load the demo case.")
    with right:
        if stats["evidence_by_type"]:
            fig = px.bar(x=list(stats["evidence_by_type"]), y=list(stats["evidence_by_type"].values()), title="Evidence by type",
                         labels={"x": "", "y": "Items"}, color_discrete_sequence=["#4C8BF5"])
            st.plotly_chart(_style(fig))
        else:
            st.info("No evidence recorded yet.")

    left, right = st.columns(2)
    with left:
        st.subheader("Recent cases")
        recent = case_service.list_cases()[:5]
        for case in recent:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"**{case['title']}**  \n<span class='muted'>{case['case_number']} · {case['created_at'][:16]}</span>", unsafe_allow_html=True)
                c2.markdown(badge(case["status"]), unsafe_allow_html=True)
                st.button("Open workspace", key=f"dash_open_{case['id']}", on_click=goto, args=("Investigation Workspace", case["id"]))
        if not recent:
            st.caption("Nothing here yet.")
    with right:
        st.subheader("Recent investigation activity")
        for run in stats["recent_runs"]:
            st.markdown(f"**{run['case_number']}** · run #{run['run_number']} · {badge(run['execution_status'])}  \n"
                        f"<span class='muted'>{run['title']} · {run['started_at'][:16]}</span>", unsafe_allow_html=True)
        if not stats["recent_runs"]:
            st.caption("No investigations have been run yet.")
