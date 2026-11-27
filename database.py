"""SQLite setup: schema, connections (with foreign keys ON) and a safe transaction helper."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import config


class DatabaseError(Exception):
    """Raised when a database operation fails."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_number   TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL CHECK (length(trim(title)) > 0),
    incident_type TEXT NOT NULL,
    description   TEXT NOT NULL CHECK (length(trim(description)) > 0),
    location      TEXT NOT NULL DEFAULT '',
    incident_date TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'New'
                  CHECK (status IN ('New', 'In Progress', 'Completed', 'Failed')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS evidence (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id           INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    evidence_number   TEXT NOT NULL,
    evidence_type     TEXT NOT NULL,
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    event_time        TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL DEFAULT '',
    reliability_notes TEXT NOT NULL DEFAULT '',
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (case_id, evidence_number)
);

CREATE TABLE IF NOT EXISTS witness_statements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id       INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    witness_label TEXT NOT NULL,
    statement     TEXT NOT NULL,
    event_time    TEXT NOT NULL DEFAULT '',
    source_notes  TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS investigation_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id          INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    run_number       INTEGER NOT NULL,
    selected_tools   TEXT NOT NULL DEFAULT '{}',   -- JSON: the agent's plan
    execution_status TEXT NOT NULL DEFAULT 'running'
                     CHECK (execution_status IN ('running', 'completed', 'completed_with_errors', 'failed')),
    summary          TEXT NOT NULL DEFAULT '',
    activity_log     TEXT NOT NULL DEFAULT '[]',   -- JSON: real agent log (extra column)
    started_at       TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    completed_at     TEXT,
    UNIQUE (case_id, run_number)
);

CREATE TABLE IF NOT EXISTS investigation_tool_results (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    investigation_run_id INTEGER NOT NULL REFERENCES investigation_runs(id) ON DELETE CASCADE,
    tool_name            TEXT NOT NULL,
    input_data           TEXT NOT NULL DEFAULT '{}',
    output_data          TEXT NOT NULL DEFAULT '{}',
    execution_status     TEXT NOT NULL CHECK (execution_status IN ('success', 'failed')),
    error_message        TEXT,
    created_at           TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS investigation_reports (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id              INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
    investigation_run_id INTEGER NOT NULL REFERENCES investigation_runs(id) ON DELETE CASCADE,
    report_content       TEXT NOT NULL,
    report_format        TEXT NOT NULL DEFAULT 'markdown',
    created_at           TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_case   ON evidence(case_id);
CREATE INDEX IF NOT EXISTS idx_witness_case    ON witness_statements(case_id);
CREATE INDEX IF NOT EXISTS idx_runs_case       ON investigation_runs(case_id);
CREATE INDEX IF NOT EXISTS idx_toolres_run     ON investigation_tool_results(investigation_run_id);
CREATE INDEX IF NOT EXISTS idx_reports_case    ON investigation_reports(case_id);
CREATE INDEX IF NOT EXISTS idx_cases_status    ON cases(status);
"""


def get_connection() -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement turned on."""
    path = Path(config.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db_session():
    """Run a block in one transaction: commit on success, roll back on error."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        raise DatabaseError(str(exc)) from exc
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Create all tables if they do not exist yet (safe to call on every start)."""
    with db_session() as conn:
        conn.executescript(SCHEMA)
