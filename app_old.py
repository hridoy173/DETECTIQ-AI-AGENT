"""DetectIQ - Streamlit entry point.  Run with:  streamlit run app.py"""
from datetime import date

import streamlit as st
from pydantic import BaseModel

import config
import database
from components.case_cards import render_case_card
from components.dashboard import render_dashboard
from components.results_view import render_run_results, report_downloads
from components.sidebar import goto, render_sidebar
from components.theme import badge, inject_css
from services import ai_service, case_service, investigation_service

st.set_page_config(page_title="DetectIQ — AI Investigation Agent", page_icon="🕵️", layout="wide")


@st.cache_resource
def _init_database() -> bool:
    database.init_db()
    return True


def flash(kind: str, text: str) -> None:
    st.session_state["flash"] = (kind, text)


def show_flash() -> None:
    message = st.session_state.pop("flash", None)
    if message:
        getattr(st, message[0])(message[1])


# =====================================================================  Cases
def page_cases() -> None:
    st.title("Cases")
    c1, c2 = st.columns([3, 1])
    search = c1.text_input("Search", placeholder="Search by title, case number or description", label_visibility="collapsed")
    status = c2.selectbox("Status", ["All"] + case_service.STATUSES, label_visibility="collapsed")
    cases = case_service.list_cases(search, status)
    st.caption(f"{len(cases)} case(s)")
    if not cases:
        st.info("No cases match. Create one on 'New Investigation' or load the demo case from the Dashboard.")
    for case in cases:
        action = render_case_card(case, confirming=st.session_state.get("confirm_delete") == case["id"])
        if action == "open":
            goto("Investigation Workspace", case["id"])
            st.rerun()
        elif action == "ask_delete":
            st.session_state["confirm_delete"] = case["id"]
            st.rerun()
        elif action == "cancel_delete":
            st.session_state.pop("confirm_delete", None)
            st.rerun()
        elif action == "confirm_delete":
            case_service.delete_case(case["id"])
            st.session_state.pop("confirm_delete", None)
            flash("success", f"Deleted {case['case_number']}.")
            st.rerun()


# =====================================================================  New investigation
def _bump(key: str, delta: int) -> None:
    st.session_state[key] = max(0, st.session_state[key] + delta)


def _reset_form() -> None:
    st.session_state["form_v"] += 1
    st.session_state["ev_count"], st.session_state["st_count"] = 1, 1


def _load_demo_and_open() -> None:
    goto("Investigation Workspace", case_service.load_demo_case())
    flash("success", "Demo case loaded. Click 'Run Investigation' to start the agent.")


def page_new_investigation() -> None:
    st.title("New Investigation")
    st.caption("Fictional, educational cases only. Do not enter real personal data or real accusations.")
    st.button("📂 Load demo case (Missing Laptop)", on_click=_load_demo_and_open)
    v = st.session_state["form_v"]

    st.subheader("Case information")
    title = st.text_input("Case title *", key=f"title_{v}")
    c1, c2, c3 = st.columns(3)
    incident_type = c1.selectbox("Incident type *", case_service.INCIDENT_TYPES, key=f"type_{v}")
    location = c2.text_input("Location", key=f"loc_{v}")
    incident_date = c3.date_input("Incident date", value=date.today(), key=f"date_{v}")
    description = st.text_area("Incident description *", height=110, key=f"desc_{v}")

    st.subheader("Evidence")
    st.caption("Event time is optional: write it like 14:35, 2:35 PM or 'approx 2:35 PM'. Leave blank if unknown - it will not be invented.")
    for i in range(st.session_state["ev_count"]):
        with st.expander(f"Evidence {i + 1}  (will be E{i + 1:03d})", expanded=True):
            a, b = st.columns(2)
            a.text_input("Evidence title", key=f"evt_{v}_{i}")
            b.selectbox("Evidence type", case_service.EVIDENCE_TYPES, key=f"evtype_{v}_{i}")
            st.text_area("Evidence description", height=80, key=f"evd_{v}_{i}")
            a, b, c = st.columns(3)
            a.text_input("Event time (optional)", key=f"evtime_{v}_{i}")
            b.text_input("Source (optional)", key=f"evsrc_{v}_{i}")
            c.text_input("Reliability notes (optional)", key=f"evrel_{v}_{i}")
    a, b, _ = st.columns([1, 1, 4])
    a.button("➕ Add evidence", on_click=_bump, args=("ev_count", 1))
    b.button("➖ Remove last", on_click=_bump, args=("ev_count", -1), key="rm_ev")

    st.subheader("Witness statements")
    for i in range(st.session_state["st_count"]):
        with st.expander(f"Statement {i + 1}", expanded=True):
            a, b = st.columns([1, 3])
            a.text_input("Witness label", value=f"W{i + 1:03d}", key=f"wl_{v}_{i}")
            b.text_area("Statement", height=70, key=f"ws_{v}_{i}")
            a, b = st.columns(2)
            a.text_input("Event time (optional)", key=f"wt_{v}_{i}")
            b.text_input("Source notes (optional)", key=f"wn_{v}_{i}")
    a, b, _ = st.columns([1, 1, 4])
    a.button("➕ Add statement", on_click=_bump, args=("st_count", 1))
    b.button("➖ Remove last", on_click=_bump, args=("st_count", -1), key="rm_st")

    st.divider()
    if st.button("Create case", type="primary"):
        g = st.session_state.get
        evidence, statements = [], []
        for i in range(st.session_state["ev_count"]):
            row = {"title": g(f"evt_{v}_{i}", ""), "evidence_type": g(f"evtype_{v}_{i}", "Other"), "description": g(f"evd_{v}_{i}", ""),
                   "event_time": g(f"evtime_{v}_{i}", ""), "source": g(f"evsrc_{v}_{i}", ""), "reliability_notes": g(f"evrel_{v}_{i}", "")}
            if any(row[k].strip() for k in ("title", "description", "event_time", "source", "reliability_notes")):
                evidence.append(row)
        for i in range(st.session_state["st_count"]):
            row = {"witness_label": g(f"wl_{v}_{i}", ""), "statement": g(f"ws_{v}_{i}", ""), "event_time": g(f"wt_{v}_{i}", ""), "source_notes": g(f"wn_{v}_{i}", "")}
            if any(row[k].strip() for k in ("statement", "event_time", "source_notes")):
                statements.append(row)
        case = {"title": title, "incident_type": incident_type, "description": description, "location": location,
                "incident_date": incident_date.isoformat()}
        errors = case_service.validate_case_input(case, evidence, statements)
        if errors:
            for e in errors:
                st.error(e)
        else:
            try:
                case_id = case_service.create_case(case, evidence, statements)
            except Exception as exc:
                st.error(f"Could not save the case: {exc}")
            else:
                st.session_state["last_created"] = case_id
                flash("success", f"Case created with {len(evidence)} evidence item(s) and {len(statements)} statement(s).")
                _reset_form()
                st.rerun()
    if st.session_state.get("last_created"):
        st.button("Open the new case in the Investigation Workspace →", on_click=goto, args=("Investigation Workspace", st.session_state["last_created"]))


# =====================================================================  Workspace
def _log_line(entry: dict) -> None:
    icon = {"info": "•", "warning": "⚠️", "error": "❌"}.get(entry["level"], "•")
    st.write(f"`[{entry['time']}]` {icon} {entry['message']}")


def page_workspace() -> None:
    st.title("Investigation Workspace")
    cases = case_service.list_cases()
    if not cases:
        st.info("There are no cases yet.")
        st.button("📂 Load demo case", on_click=_load_demo_and_open)
        return
    ids = [c["id"] for c in cases]
    by_id = {c["id"]: c for c in cases}
    if st.session_state.get("ws_case") not in ids:
        st.session_state["ws_case"] = st.session_state["selected_case_id"] if st.session_state.get("selected_case_id") in ids else ids[0]
    case_id = st.selectbox("Select case", ids, key="ws_case", format_func=lambda i: f"{by_id[i]['case_number']} — {by_id[i]['title']}")
    st.session_state["selected_case_id"] = case_id
    case = case_service.get_case(case_id)

    st.markdown(f"### {case['title']} {badge(case['status'])}", unsafe_allow_html=True)
    a, b, c = st.columns(3)
    a.markdown(f"**Case number**  \n{case['case_number']}")
    b.markdown(f"**Type / location**  \n{case['incident_type']} · {case['location'] or 'unknown'}")
    c.markdown(f"**Incident date**  \n{case['incident_date'] or 'unknown'}")
    st.write(case["description"])

    left, right = st.columns(2)
    with left:
        st.markdown(f"**Evidence ({len(case['evidence'])})**")
        for ev in case["evidence"]:
            with st.expander(f"{ev['evidence_number']} · {ev['title']}"):
                st.write(ev["description"])
                st.caption(f"Type: {ev['evidence_type']} · Time: {ev['event_time'] or 'not given'} · Source: {ev['source'] or 'not given'}"
                           + (f" · Notes: {ev['reliability_notes']}" if ev["reliability_notes"] else ""))
        if not case["evidence"]:
            st.caption("No evidence supplied.")
    with right:
        st.markdown(f"**Witness statements ({len(case['statements'])})**")
        for s in case["statements"]:
            with st.expander(f"{s['witness_label']}"):
                st.write(f"“{s['statement']}”")
                st.caption(f"Time: {s['event_time'] or 'in text / not given'}" + (f" · Notes: {s['source_notes']}" if s["source_notes"] else ""))
        if not case["statements"]:
            st.caption("No statements supplied.")

    st.divider()
    ai_ready = config.ai_configured()
    use_ai = st.toggle("Use Gemini AI for planning and analysis", value=ai_ready, disabled=not ai_ready,
                       help="Turn off to run the rule-based version only. Disabled when no API key is configured.")
    if not ai_ready:
        st.caption("No Gemini API key found - the agent will use deterministic rules. See Settings / About.")
    if st.button("🔍 Run Investigation", type="primary"):
        with st.status("Investigation agent is running...", expanded=True) as status:
            outcome = investigation_service.run_investigation(case_id, progress=_log_line, use_ai=use_ai)
            status.update(label="Investigation finished" if outcome["ok"] else "Investigation could not be completed",
                          state="complete" if outcome["ok"] else "error")
        if outcome["errors"]:
            for e in outcome["errors"]:
                st.error(e)
        if outcome["run_id"]:
            st.session_state[f"run_sel_{case_id}"] = outcome["run_id"]
            flash("success" if outcome["ok"] else "warning", f"Run finished with status: {outcome['status'].replace('_', ' ')}.")
            st.rerun()
        return

    runs = investigation_service.list_runs(case_id)
    if not runs:
        st.info("No investigation has been run for this case yet. Click **Run Investigation**.")
        return
    run_ids = [r["id"] for r in runs]
    if st.session_state.get(f"run_sel_{case_id}") not in run_ids:
        st.session_state[f"run_sel_{case_id}"] = run_ids[0]
    run_map = {r["id"]: r for r in runs}
    run_id = st.selectbox("Investigation run", run_ids, key=f"run_sel_{case_id}",
                          format_func=lambda i: f"Run #{run_map[i]['run_number']} · {run_map[i]['started_at']} · {run_map[i]['execution_status']}")
    details = investigation_service.get_run_details(run_id)
    render_run_results(details, case)


# =====================================================================  Reports
def page_reports() -> None:
    st.title("Reports")
    reports = investigation_service.list_reports()
    if not reports:
        st.info("No reports yet. Run an investigation first.")
        return
    by_id = {r["id"]: r for r in reports}
    rid = st.selectbox("Select a report", list(by_id), format_func=lambda i: f"{by_id[i]['case_number']} · run #{by_id[i]['run_number']} · {by_id[i]['title']} · {by_id[i]['created_at'][:16]}")
    report = investigation_service.get_report(rid)
    report_downloads(report["report_content"], f"{by_id[rid]['case_number']}_run{by_id[rid]['run_number']}", f"rep_{rid}")
    st.divider()
    st.markdown(report["report_content"])


# =====================================================================  Settings / About
def page_settings() -> None:
    st.title("Settings / About")
    st.markdown(f"### {config.APP_FULL_NAME}")
    st.write("DetectIQ is an AI-powered investigation and evidence-analysis agent built for an Artificial Intelligence course. "
             "It analyses *fictional* cases: it selects tools, runs them, combines the results and writes a structured report.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Version", config.APP_VERSION)
    c2.metric("AI provider", "Google Gemini")
    c3.metric("Model", config.get_model())
    c4.metric("API key", "configured" if config.ai_configured() else "not set")
    st.caption("The API key is read from the `.env` file and is never displayed.")

    if config.ai_configured() and st.button("Test Gemini connection"):
        class Ping(BaseModel):
            message: str
        ai_service.reset_circuit()
        try:
            reply = ai_service.generate_structured('Return JSON {"message": "hello"}.', Ping)
            st.success(f"Connection works. Model replied: {reply.message}")
        except ai_service.AIError as exc:
            st.error(str(exc))

    st.subheader("AI limitations")
    st.markdown("- AI can be wrong, miss context or misread wording. Every AI output is validated against a schema, but *validated* does not mean *true*.\n"
                "- Inferences are labelled as inferences and are never evidence.\n"
                "- DetectIQ never declares anyone guilty and must not be used for real accusations.\n"
                "- Without an API key or when the AI fails, the app uses simpler rule-based logic (this is always shown).")
    st.subheader("Academic project information")
    st.write("Concepts demonstrated: tool-using AI agent, planning and tool selection, structured (schema-validated) LLM output, "
             "graceful fallback, human-readable transparency (activity log), persistence and responsible-AI guardrails.")
    st.caption(f"Database file: `{config.DB_PATH}`")


# =====================================================================  main
def main() -> None:
    _init_database()
    inject_css()
    for key, default in {"nav": "Dashboard", "form_v": 0, "ev_count": 1, "st_count": 1}.items():
        st.session_state.setdefault(key, default)
    page = render_sidebar()
    show_flash()
    {"Dashboard": lambda: (st.title("Dashboard"), render_dashboard()), "Cases": page_cases, "New Investigation": page_new_investigation,
     "Investigation Workspace": page_workspace, "Reports": page_reports, "Settings / About": page_settings}[page]()


main()
