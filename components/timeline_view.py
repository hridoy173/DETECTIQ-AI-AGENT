"""Interactive Plotly timeline + table for the Timeline Generator result."""
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

COLORS = {"evidence": "#4C8BF5", "witness statement": "#F5B84C", "incident description": "#9AA9C2"}


def timeline_figure(events: list[dict]) -> go.Figure:
    base = datetime(2000, 1, 1)
    df = pd.DataFrame(events)
    df["when"] = [base + timedelta(minutes=int(m)) for m in df["minutes"]]
    fig = go.Figure()
    for source_type, color in COLORS.items():
        sub = df[df["source_type"] == source_type]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub["when"], y=sub["source"], mode="markers+text", name=source_type, text=sub["time_display"],
            textposition="top center", marker=dict(size=14, color=color, line=dict(width=2, color=color),
                                                   symbol=["circle" if c == "exact" else "circle-open" for c in sub["certainty"]]),
            hovertext=[f"<b>{r.source}</b> · {r.time_display} ({r.certainty})<br>{r.event[:110]}" for r in sub.itertuples()],
            hoverinfo="text"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      height=330 + 12 * df["source"].nunique(), margin=dict(l=10, r=10, t=30, b=10),
                      xaxis=dict(tickformat="%H:%M", title="Time of day", gridcolor="#1F2F4D"),
                      yaxis=dict(title="", type="category", autorange="reversed", gridcolor="#1F2F4D"),
                      legend=dict(orientation="h", y=1.12))
    return fig


def render_timeline(data: dict) -> None:
    events = data.get("events", [])
    for w in data.get("warnings", []):
        st.warning(w)
    if not events:
        st.info("No timestamps were found, so there is no timeline. (Times are never invented.)")
    else:
        st.caption("Filled dot = exact time · hollow dot = approximate, ambiguous or time-window boundary.")
        st.plotly_chart(timeline_figure(events))
        table = pd.DataFrame(events)[["time_display", "event", "source", "source_type", "certainty", "notes"]]
        table.columns = ["Time", "Event", "Source", "Source type", "Certainty", "Notes"]
        st.dataframe(table, hide_index=True)
    if data.get("gaps"):
        st.markdown("**Time gaps (no recorded events):**")
        for g in data["gaps"]:
            st.write(f"• {g['from']} → {g['to']} ({g['minutes']} min), between {g['between'][0]} and {g['between'][1]}")
    if data.get("untimed_items"):
        st.markdown("**Items without a usable time (not placed on the timeline):**")
        for u in data["untimed_items"]:
            st.write(f"• {u['source']} ({u['source_type']}): {u['text']}")
