"""Create, read, update and delete cases, evidence and witness statements."""
from __future__ import annotations

from datetime import date, datetime

from database import db_session
from tools.text_utils import parse_event_time

STATUSES = ["New", "In Progress", "Completed", "Failed"]
INCIDENT_TYPES = ["Theft / Missing Item", "Vandalism", "Unauthorized Access", "Fraud (simulated)",
                  "Accident", "Policy Violation", "Other"]
EVIDENCE_TYPES = ["Observation", "Witness Report", "Physical Item", "Document", "Digital Record / Log",
                  "Photo / Video", "Other"]

DEMO_TITLE = "Missing Laptop — University Computer Lab"
DEMO_CASE = {
    "title": DEMO_TITLE, "incident_type": "Theft / Missing Item", "location": "University Computer Laboratory",
    "incident_date": date.today().isoformat(),
    "description": ("A laptop was reported missing from a university computer laboratory between 2:00 PM and 3:00 PM. "
                    "Several people were present in the laboratory during this period. The available information is "
                    "incomplete and requires further analysis."),
}
DEMO_EVIDENCE = [
    {"evidence_type": "Observation", "title": "Laptop last confirmed on desk", "event_time": "14:10",
     "description": "The laptop was last confirmed on a laboratory desk at 2:10 PM.", "source": "Lab observation",
     "reliability_notes": "Not independently verified."},
    {"evidence_type": "Witness Report", "title": "Person leaving with a backpack", "event_time": "approx 14:35",
     "description": "A witness reported seeing a person leave the laboratory with a backpack at approximately 2:35 PM.",
     "source": "Witness report", "reliability_notes": "Identity of the person is unknown."},
    {"evidence_type": "Observation", "title": "Laboratory appeared empty", "event_time": "approx 14:45",
     "description": "The laboratory was reportedly empty at approximately 2:45 PM.", "source": "Reported observation",
     "reliability_notes": ""},
]
DEMO_STATEMENTS = [
    {"witness_label": "W001", "statement": "I left the laboratory at 2:20 PM.", "event_time": "", "source_notes": "First-hand"},
    {"witness_label": "W002", "statement": "I noticed someone near the desk around 2:30 PM.", "event_time": "", "source_notes": "First-hand"},
    {"witness_label": "W003", "statement": "The laboratory appeared empty when I checked at 2:45 PM.", "event_time": "", "source_notes": "First-hand"},
]


def _s(value) -> str:
    return (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value))


def validate_case_input(case: dict, evidence: list[dict], statements: list[dict]) -> list[str]:
    """Return a list of human-readable problems (empty list = valid)."""
    errors = []
    if not _s(case.get("title")):
        errors.append("Case title is required.")
    elif len(_s(case["title"])) > 200:
        errors.append("Case title must be 200 characters or fewer.")
    if not _s(case.get("incident_type")):
        errors.append("Incident type is required.")
    if not _s(case.get("description")):
        errors.append("Incident description is required.")
    for i, ev in enumerate(evidence, 1):
        if not _s(ev.get("title")) or not _s(ev.get("description")):
            errors.append(f"Evidence {i}: title and description are required.")
        if _s(ev.get("event_time")) and not parse_event_time(ev["event_time"]):
            errors.append(f"Evidence {i}: could not read the time '{ev['event_time']}' (try 14:35 or 2:35 PM).")
    for i, st in enumerate(statements, 1):
        if not _s(st.get("witness_label")) or not _s(st.get("statement")):
            errors.append(f"Statement {i}: witness label and statement are required.")
        if _s(st.get("event_time")) and not parse_event_time(st["event_time"]):
            errors.append(f"Statement {i}: could not read the time '{st['event_time']}' (try 14:35 or 2:35 PM).")
    return errors


def validate_for_investigation(case: dict) -> tuple[list[str], list[str]]:
    """(errors, warnings) for running the agent. Errors block the run; warnings do not."""
    errors, warnings = [], []
    if not case.get("evidence") and not case.get("statements"):
        errors.append("The case has no evidence and no witness statements. Add at least one before investigating.")
    else:
        if not case.get("evidence"):
            warnings.append("No evidence items - analysis will rely on statements only.")
        if not case.get("statements"):
            warnings.append("No witness statements - analysis will rely on evidence only.")
    if not (case.get("description") or "").strip():
        errors.append("The case has no incident description.")
    return errors, warnings


def create_case(case: dict, evidence: list[dict] | None = None, statements: list[dict] | None = None) -> int:
    """Insert a case with its evidence and statements in one transaction. Returns the new case id."""
    evidence, statements = evidence or [], statements or []
    errors = validate_case_input(case, evidence, statements)
    if errors:
        raise ValueError("\n".join(errors))
    with db_session() as conn:
        next_id = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM cases").fetchone()[0]
        number = f"CASE-{datetime.now().year}-{next_id:04d}"
        cur = conn.execute(
            "INSERT INTO cases (case_number, title, incident_type, description, location, incident_date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (number, _s(case["title"]), _s(case["incident_type"]), _s(case["description"]),
             _s(case.get("location")), _s(case.get("incident_date"))))
        case_id = cur.lastrowid
        for n, ev in enumerate(evidence, 1):
            conn.execute(
                "INSERT INTO evidence (case_id, evidence_number, evidence_type, title, description, event_time, source, "
                "reliability_notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (case_id, f"E{n:03d}", _s(ev.get("evidence_type")) or "Other", _s(ev["title"]), _s(ev["description"]),
                 _s(ev.get("event_time")), _s(ev.get("source")), _s(ev.get("reliability_notes"))))
        for st in statements:
            conn.execute(
                "INSERT INTO witness_statements (case_id, witness_label, statement, event_time, source_notes) "
                "VALUES (?, ?, ?, ?, ?)",
                (case_id, _s(st["witness_label"]), _s(st["statement"]), _s(st.get("event_time")), _s(st.get("source_notes"))))
    return case_id


def get_case(case_id: int) -> dict | None:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        case = dict(row)
        case["evidence"] = [dict(r) for r in conn.execute(
            "SELECT * FROM evidence WHERE case_id = ? ORDER BY evidence_number", (case_id,))]
        case["statements"] = [dict(r) for r in conn.execute(
            "SELECT * FROM witness_statements WHERE case_id = ? ORDER BY id", (case_id,))]
    return case


def list_cases(search: str = "", status: str | None = None) -> list[dict]:
    """All cases (newest first) with evidence/statement/run counts. Optional text search and status filter."""
    sql = ("SELECT c.*, "
           "(SELECT COUNT(*) FROM evidence e WHERE e.case_id = c.id) AS evidence_count, "
           "(SELECT COUNT(*) FROM witness_statements w WHERE w.case_id = c.id) AS statement_count, "
           "(SELECT COUNT(*) FROM investigation_runs r WHERE r.case_id = c.id) AS run_count FROM cases c WHERE 1=1")
    params: list = []
    if search.strip():
        sql += " AND (c.title LIKE ? OR c.case_number LIKE ? OR c.description LIKE ?)"
        params += [f"%{search.strip()}%"] * 3
    if status and status != "All":
        sql += " AND c.status = ?"
        params.append(status)
    sql += " ORDER BY c.created_at DESC, c.id DESC"
    with db_session() as conn:
        return [dict(r) for r in conn.execute(sql, params)]


def set_status(case_id: int, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(f"Invalid status: {status}")
    with db_session() as conn:
        conn.execute("UPDATE cases SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?", (status, case_id))


def delete_case(case_id: int) -> None:
    """Deletes the case and (via ON DELETE CASCADE) its evidence, statements, runs, results and reports."""
    with db_session() as conn:
        conn.execute("DELETE FROM cases WHERE id = ?", (case_id,))


def load_demo_case() -> int:
    """Create the demo case (or return the existing one so it is never duplicated)."""
    with db_session() as conn:
        row = conn.execute("SELECT id FROM cases WHERE title = ?", (DEMO_TITLE,)).fetchone()
    if row:
        return row["id"]
    return create_case(DEMO_CASE, DEMO_EVIDENCE, DEMO_STATEMENTS)


def get_stats() -> dict:
    with db_session() as conn:
        one = lambda sql: conn.execute(sql).fetchone()[0]
        return {
            "total_cases": one("SELECT COUNT(*) FROM cases"),
            "active": one("SELECT COUNT(*) FROM cases WHERE status IN ('New', 'In Progress')"),
            "completed": one("SELECT COUNT(*) FROM cases WHERE status = 'Completed'"),
            "total_evidence": one("SELECT COUNT(*) FROM evidence"),
            "total_runs": one("SELECT COUNT(*) FROM investigation_runs"),
            "by_status": {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM cases GROUP BY status")},
            "evidence_by_type": {r[0]: r[1] for r in conn.execute("SELECT evidence_type, COUNT(*) FROM evidence GROUP BY evidence_type")},
            "recent_runs": [dict(r) for r in conn.execute(
                "SELECT r.id, r.run_number, r.execution_status, r.started_at, c.title, c.case_number, c.id AS case_id "
                "FROM investigation_runs r JOIN cases c ON c.id = r.case_id ORDER BY r.started_at DESC, r.id DESC LIMIT 6")],
        }
