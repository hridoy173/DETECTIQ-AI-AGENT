"""Shows the saved results of one investigation run (used right after a run and when reopening old runs)."""
import re

import markdown as md
import pandas as pd
import streamlit as st

from components.theme import badge
from components.timeline_view import render_timeline
from models import TOOL_LABELS

LEVEL_ICON = {"info": "•", "warning": "⚠️", "error": "❌"}
PRINT_CSS = ("body{font-family:Segoe UI,Arial,sans-serif;max-width:850px;margin:2rem auto;padding:0 1rem;color:#111;line-height:1.5}"
             "table{border-collapse:collapse;width:100%;font-size:0.85rem;margin:0.5rem 0}th,td{border:1px solid #999;padding:4px 6px;text-align:left;vertical-align:top}"
             "th{background:#eee}h1,h2{border-bottom:1px solid #ccc;padding-bottom:4px}@media print{.noprint{display:none}}")


def report_to_txt(markdown_text: str) -> str:
    text = re.sub(r"\*\*|__", "", markdown_text)
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    return re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", text)


def report_to_html(markdown_text: str, title: str) -> str:
    body = md.markdown(markdown_text, extensions=["tables"])
    return (f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title><style>{PRINT_CSS}</style></head><body>"
            f"<button class='noprint' onclick='window.print()'>Print / Save as PDF</button>{body}</body></html>")


def report_downloads(markdown_text: str, base_name: str, key: str) -> None:
    c1, c2, c3 = st.columns(3)
    c1.download_button("⬇ Markdown (.md)", markdown_text, f"{base_name}.md", "text/markdown", key=f"{key}_md")
    c2.download_button("⬇ Text (.txt)", report_to_txt(markdown_text), f"{base_name}.txt", "text/plain", key=f"{key}_txt")
    c3.download_button("🖨 Print-friendly (.html)", report_to_html(markdown_text, base_name), f"{base_name}.html", "text/html", key=f"{key}_html")
    st.caption("Open the .html file in your browser and press Print to save it as PDF.")


def _mode_note(res: dict) -> None:
    mode = res.get("mode")
    if mode == "ai":
        st.caption("🤖 Produced by Gemini AI (validated against a schema).")
    elif mode == "rule_based_fallback":
        st.warning(f"AI failed, rule-based fallback used. Reason: {res.get('ai_error')}")
    elif mode == "rule_based":
        st.caption("⚙️ Produced by rule-based Python logic" + (f" ({res['ai_error']})" if res.get("ai_error") else "."))


def _unavailable(results: dict, name: str):
    res = results.get(name)
    if res is None:
        st.info(f"{TOOL_LABELS[name]} was not selected for this run.")
    else:
        st.error(f"{TOOL_LABELS[name]} failed: {res.get('error')}")
    return None


def _ok(results: dict, name: str):
    res = results.get(name)
    if res and res["status"] == "success":
        _mode_note(res)
        return res["data"]
    return _unavailable(results, name)


def render_run_results(details: dict, case: dict) -> None:
    results, run = details["tool_results"], details["run"]
    st.markdown(f"**Run #{run['run_number']}** · {badge(run['execution_status'])} · started {run['started_at']}  \n"
                f"<span class='muted'>{run['summary']}</span>", unsafe_allow_html=True)
    tabs = st.tabs(["Agent activity", "Tool selection", "Evidence", "Timeline", "Contradictions", "Relationships", "Missing info", "Report"])

    with tabs[0]:
        for e in details["log"]:
            st.markdown(f"<div class='logline'>[{e['time']}] {LEVEL_ICON.get(e['level'], '•')} {e['message']}</div>", unsafe_allow_html=True)
    with tabs[1]:
        plan = details["plan"]
        if plan:
            src = {"ai": "Gemini AI (schema-validated)", "rule_based": "deterministic rules", "rule_based_fallback": "deterministic rules (AI failed)"}
            st.markdown(f"**Planner:** {src.get(plan['source'], plan['source'])}")
            if plan.get("ai_error"):
                st.caption(f"AI note: {plan['ai_error']}")
            if plan.get("reasoning"):
                st.info(plan["reasoning"])
            st.dataframe(pd.DataFrame([{"Tool": TOOL_LABELS[s["tool_name"]], "Why it was selected": s["reason"]} for s in plan["selected_tools"]]), hide_index=True)
        st.markdown("**Execution status**")
        rows = [{"Tool": TOOL_LABELS.get(n, n), "Status": r["status"], "Mode": r.get("mode"), "Seconds": r.get("duration_seconds"),
                 "Error": r.get("error") or ""} for n, r in results.items()]
        st.dataframe(pd.DataFrame(rows), hide_index=True)

    with tabs[2]:
        data = _ok(results, "evidence_analyzer")
        for item in (data or {}).get("items", []):
            with st.expander(f"{item['evidence_id']} · {item['category']} · relevance: {item['relevance']}"):
                st.write(item["summary"])
                st.markdown("**Facts stated:**\n" + "\n".join(f"- {f}" for f in item["facts"]))
                st.markdown(f"**Times:** {', '.join(item['times']) or '—'}  \n**Locations:** {', '.join(item['locations']) or '—'}  \n"
                            f"**Objects:** {', '.join(item['objects']) or '—'}")
                st.markdown("**Limitations:**\n" + ("\n".join(f"- {x}" for x in item["limitations"]) or "- none noted"))
                st.markdown("**Cannot be verified:**\n" + ("\n".join(f"- {x}" for x in item["unverifiable"]) or "- none noted"))
        if data is not None and not data["items"]:
            st.info("This case has no evidence items.")
    with tabs[3]:
        data = _ok(results, "timeline_generator")
        if data is not None:
            render_timeline(data)
    with tabs[4]:
        data = _ok(results, "contradiction_detector")
        if data is not None:
            st.write(data["explanation"])
            for title, key, fn in (("Confirmed contradictions", "contradictions", st.error), ("Possible inconsistencies", "possible_inconsistencies", st.warning),
                                   ("Unclear information (not treated as contradictions)", "unclear_information", st.info),
                                   ("Unverified / uncorroborated claims", "unverified_claims", st.info)):
                st.markdown(f"**{title}** ({len(data[key])})")
                for f in data[key]:
                    fn(f"**{', '.join(f['items'])}** — {f['description']}\n\n{f['explanation']}")
    with tabs[5]:
        data = _ok(results, "clue_analyzer")
        if data is not None:
            if not data["relationships"]:
                st.info("No relationships were identified.")
            else:
                df = pd.DataFrame(data["relationships"])[["source_item", "related_item", "relationship", "relationship_type", "confidence", "directness", "explanation"]]
                df.columns = ["Item", "Related item", "Relationship", "Type", "Confidence", "Direct / inferred", "Explanation"]
                st.dataframe(df, hide_index=True)
                st.caption("A relationship is a lead to check, not proof. 'Inferred' links are reasoning, not facts.")
    with tabs[6]:
        data = _ok(results, "missing_information_analyzer")
        if data is not None:
            st.dataframe(pd.DataFrame(data["missing_items"]).rename(columns={"priority": "Priority", "item": "Missing information", "why_it_matters": "Why it matters", "suggested_step": "Suggested step"})
                         [["Priority", "Missing information", "Why it matters", "Suggested step"]] if data["missing_items"] else pd.DataFrame(), hide_index=True)
            st.markdown("**Recommended next steps**")
            for i, step in enumerate(data["next_steps"], 1):
                st.write(f"{i}. {step}")
    with tabs[7]:
        if details["report"]:
            text = details["report"]["report_content"]
            _mode_note(results.get("report_generator", {}))
            report_downloads(text, f"{case['case_number']}_run{run['run_number']}", f"ws_{run['id']}")
            st.divider()
            st.markdown(text)
        else:
            st.error("No report was saved for this run.")
