"""Runs the agent for a saved case and stores / loads everything in SQLite."""
from __future__ import annotations

import json
from typing import Callable

import config
from agents.investigation_agent import InvestigationAgent
from database import db_session
from models import TOOL_LABELS
from services import case_service


def _snapshot(case: dict) -> str:
    """Compact copy of the input given to the tools (stored as input_data)."""
    return json.dumps({"case_number": case["case_number"], "evidence": len(case["evidence"]),
                       "statements": len(case["statements"]), "description": case["description"]}, ensure_ascii=False)


def _write_report_file(case: dict, run_number: int, markdown: str) -> None:
    try:
        config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (config.REPORTS_DIR / f"{case['case_number']}_run{run_number}.md").write_text(markdown, encoding="utf-8")
    except OSError:
        pass  # the database copy is the source of truth


def run_investigation(case_id: int, progress: Callable[[dict], None] | None = None, use_ai: bool = True) -> dict:
    """Validate -> create run -> agent -> save results/report -> update case status.
    Returns {'ok', 'run_id', 'status', 'errors'}."""
    case = case_service.get_case(case_id)
    if not case:
        return {"ok": False, "run_id": None, "status": "failed", "errors": ["Case not found."]}
    errors, _ = case_service.validate_for_investigation(case)
    if errors:
        return {"ok": False, "run_id": None, "status": "failed", "errors": errors}

    with db_session() as conn:
        run_number = conn.execute("SELECT COALESCE(MAX(run_number), 0) + 1 FROM investigation_runs WHERE case_id = ?",
                                  (case_id,)).fetchone()[0]
        run_id = conn.execute("INSERT INTO investigation_runs (case_id, run_number) VALUES (?, ?)", (case_id, run_number)).lastrowid
    case_service.set_status(case_id, "In Progress")

    case["status"] = "In Progress"
    agent = InvestigationAgent(use_ai=use_ai, progress=progress)
    try:
        outcome = agent.run(case)
        _save(case, run_id, run_number, outcome)
        agent.log_event("Investigation saved to the database")
        _save_log(run_id, agent.log)
        case_service.set_status(case_id, "Failed" if outcome["status"] == "failed" else "Completed")
        return {"ok": outcome["status"] != "failed", "run_id": run_id, "status": outcome["status"], "errors": []}
    except Exception as exc:   # e.g. database error while saving: record it, never crash the UI
        agent.log_event(f"Investigation could not be completed: {type(exc).__name__}: {exc}", "error")
        try:
            with db_session() as conn:
                conn.execute("UPDATE investigation_runs SET execution_status='failed', summary=?, activity_log=?, "
                             "completed_at=datetime('now','localtime') WHERE id=?", (str(exc), json.dumps(agent.log), run_id))
            case_service.set_status(case_id, "Failed")
        except Exception:
            pass
        return {"ok": False, "run_id": run_id, "status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}


def _save(case: dict, run_id: int, run_number: int, outcome: dict) -> None:
    tool_results = dict(outcome["tool_results"])
    if outcome["report"]:
        tool_results["report_generator"] = outcome["report"]
    succeeded = sum(r["status"] == "success" for r in tool_results.values())
    summary = (f"{len(outcome['tool_results'])} tools selected ({outcome['plan']['source'].replace('_', ' ')} planning); "
               f"{succeeded}/{len(tool_results)} steps succeeded.")
    with db_session() as conn:
        for name, res in tool_results.items():
            conn.execute(
                "INSERT INTO investigation_tool_results (investigation_run_id, tool_name, input_data, output_data, execution_status, error_message) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, name, _snapshot(case), json.dumps({k: v for k, v in res.items() if k != "error"}, ensure_ascii=False),
                 res["status"], res.get("error")))
        markdown = (outcome["report"] or {}).get("data", {}).get("markdown")
        if markdown:
            conn.execute("INSERT INTO investigation_reports (case_id, investigation_run_id, report_content, report_format) "
                         "VALUES (?, ?, ?, 'markdown')", (case["id"], run_id, markdown))
        conn.execute("UPDATE investigation_runs SET selected_tools=?, execution_status=?, summary=?, "
                     "completed_at=datetime('now','localtime') WHERE id=?",
                     (json.dumps(outcome["plan"], ensure_ascii=False), outcome["status"], summary, run_id))
    if markdown:
        _write_report_file(case, run_number, markdown)


def _save_log(run_id: int, log: list[dict]) -> None:
    with db_session() as conn:
        conn.execute("UPDATE investigation_runs SET activity_log=? WHERE id=?", (json.dumps(log), run_id))


# ---------------- loading previous results ----------------
def list_runs(case_id: int) -> list[dict]:
    with db_session() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT id, run_number, execution_status, summary, started_at, completed_at FROM investigation_runs "
            "WHERE case_id = ? ORDER BY run_number DESC", (case_id,))]


def get_run_details(run_id: int) -> dict | None:
    """Everything saved for one run: plan, log, per-tool results and the report."""
    with db_session() as conn:
        run = conn.execute("SELECT * FROM investigation_runs WHERE id = ?", (run_id,)).fetchone()
        if not run:
            return None
        results = {}
        for r in conn.execute("SELECT * FROM investigation_tool_results WHERE investigation_run_id = ? ORDER BY id", (run_id,)):
            out = json.loads(r["output_data"] or "{}")
            out.update({"status": r["execution_status"], "error": r["error_message"]})
            results[r["tool_name"]] = out
        report = conn.execute("SELECT * FROM investigation_reports WHERE investigation_run_id = ?", (run_id,)).fetchone()
    return {"run": dict(run), "plan": json.loads(run["selected_tools"] or "{}"), "log": json.loads(run["activity_log"] or "[]"),
            "tool_results": results, "report": dict(report) if report else None}


def list_reports() -> list[dict]:
    with db_session() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT p.id, p.created_at, p.case_id, p.investigation_run_id, c.title, c.case_number, r.run_number "
            "FROM investigation_reports p JOIN cases c ON c.id = p.case_id JOIN investigation_runs r ON r.id = p.investigation_run_id "
            "ORDER BY p.created_at DESC, p.id DESC")]


def get_report(report_id: int) -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM investigation_reports WHERE id = ?", (report_id,)).fetchone()
    return dict(row) if row else None
