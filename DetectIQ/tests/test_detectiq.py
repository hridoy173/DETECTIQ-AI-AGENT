"""DetectIQ tests. No test calls the real Gemini API."""
import json
import sqlite3

import pytest

import config
import database
from agents.investigation_agent import InvestigationAgent
from models import ToolPlan
from services import ai_service, case_service, investigation_service
from tools import TOOL_REGISTRY
from tools import contradiction_detector, timeline_generator
from tools.text_utils import extract_times, parse_event_time

BASE = {"title": "T", "incident_type": "Other", "description": "Something happened at 1:00 PM.", "location": "Lab", "incident_date": "2026-01-01"}


# ---------- database ----------
def test_database_initializes_with_all_tables():
    with database.db_session() as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cases", "evidence", "witness_statements", "investigation_runs",
            "investigation_tool_results", "investigation_reports"} <= names


def test_foreign_keys_enforced():
    with pytest.raises(database.DatabaseError):
        with database.db_session() as conn:
            conn.execute("INSERT INTO evidence (case_id, evidence_number, evidence_type, title, description) VALUES (999,'E001','x','t','d')")


# ---------- cases ----------
def test_create_case_with_evidence_and_statements():
    cid = case_service.create_case(BASE, [{"title": "a", "description": "b", "evidence_type": "Observation"}],
                                   [{"witness_label": "W1", "statement": "I saw it."}])
    case = case_service.get_case(cid)
    assert case["case_number"].startswith("CASE-") and case["status"] == "New"
    assert case["evidence"][0]["evidence_number"] == "E001"
    assert case["statements"][0]["witness_label"] == "W1"
    assert len(case_service.list_cases()) == 1


def test_invalid_input_is_rejected():
    with pytest.raises(ValueError):
        case_service.create_case({**BASE, "title": " "})
    errors = case_service.validate_case_input(BASE, [{"title": "x", "description": "y", "event_time": "banana"}], [])
    assert any("could not read the time" in e for e in errors)


def test_search_filter_and_delete_cascades():
    a = case_service.create_case({**BASE, "title": "Alpha laptop"}, [{"title": "a", "description": "b"}])
    case_service.create_case({**BASE, "title": "Beta"})
    assert [c["title"] for c in case_service.list_cases(search="alpha")] == ["Alpha laptop"]
    case_service.set_status(a, "Completed")
    assert len(case_service.list_cases(status="Completed")) == 1
    case_service.delete_case(a)
    with database.db_session() as conn:
        assert conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0] == 0


def test_demo_case_loads_once():
    first, second = case_service.load_demo_case(), case_service.load_demo_case()
    assert first == second
    case = case_service.get_case(first)
    assert len(case["evidence"]) == 3 and len(case["statements"]) == 3


# ---------- time parsing / timeline ----------
def test_time_extraction():
    assert extract_times("at 2:10 PM")[0].hhmm == "14:10"
    assert extract_times("approximately 2:35 pm")[0].certainty == "approximate"
    assert extract_times("I left at 2:20")[0].certainty == "ambiguous"
    assert extract_times("12:05 AM")[0].hhmm == "00:05"
    assert extract_times("no times here") == []
    assert parse_event_time("approx 14:35").certainty == "approximate"


def test_timeline_sorted_and_never_invents(demo_case):
    data = timeline_generator.build_timeline(demo_case)
    minutes = [e["minutes"] for e in data["events"]]
    assert minutes == sorted(minutes) and len(minutes) >= 6
    case = {**BASE, "description": "Nothing with a clock here.", "evidence": [{"evidence_number": "E001", "title": "t", "description": "A bag.", "evidence_type": "x"}], "statements": []}
    empty = timeline_generator.build_timeline(case)
    assert empty["events"] == [] and empty["warnings"] and len(empty["untimed_items"]) == 2


def test_timeline_gap_detected():
    case = {**BASE, "description": "x", "evidence": [
        {"evidence_number": "E001", "title": "a", "description": "Seen.", "event_time": "10:00", "evidence_type": "x"},
        {"evidence_number": "E002", "title": "b", "description": "Seen.", "event_time": "11:00", "evidence_type": "x"}], "statements": []}
    assert timeline_generator.build_timeline(case)["gaps"][0]["minutes"] == 60


# ---------- contradiction detector ----------
def test_demo_statements_not_treated_as_contradiction(demo_case):
    data = contradiction_detector.detect_rule_based(demo_case).model_dump()
    assert data["contradictions"] == []
    assert any(set(f["items"]) == {"W001", "W002"} for f in data["unclear_information"])


def test_confirmed_contradiction_requires_same_exact_time_and_place():
    def mk(t_empty, t_pres):
        return {**BASE, "evidence": [], "statements": [
            {"witness_label": "A", "statement": f"The laboratory was empty at {t_empty}.", "event_time": ""},
            {"witness_label": "B", "statement": f"I saw someone in the laboratory at {t_pres}.", "event_time": ""}]}
    assert len(contradiction_detector.detect_rule_based(mk("2:45 PM", "2:45 PM")).contradictions) == 1
    close = contradiction_detector.detect_rule_based(mk("2:45 PM", "2:50 PM"))
    assert close.contradictions == [] and len(close.possible_inconsistencies) == 1
    far = contradiction_detector.detect_rule_based(mk("2:45 PM", "3:30 PM"))
    assert far.contradictions == [] and far.possible_inconsistencies == []


# ---------- every tool, empty case ----------
def test_all_tools_survive_empty_case():
    empty = {**BASE, "evidence": [], "statements": []}
    for name, fn in TOOL_REGISTRY.items():
        assert fn(empty, use_ai=False)["data"] is not None, name


def test_tools_return_structured_results(demo_case):
    for name, fn in TOOL_REGISTRY.items():
        result = fn(demo_case, use_ai=False)
        assert {"tool", "mode", "data"} <= set(result) and isinstance(result["data"], dict)
    assert "CCTV" in json.dumps(TOOL_REGISTRY["missing_information_analyzer"](demo_case, use_ai=False)["data"])


# ---------- agent ----------
def test_deterministic_plan_rules(demo_case):
    names = [s["tool_name"] for s in InvestigationAgent.deterministic_plan(demo_case)]
    assert names == ["evidence_analyzer", "timeline_generator", "contradiction_detector", "clue_analyzer", "missing_information_analyzer"]
    only_statement = {**BASE, "description": "No time words.", "evidence": [], "statements": [{"witness_label": "W", "statement": "I saw a bag."}]}
    assert [s["tool_name"] for s in InvestigationAgent.deterministic_plan(only_statement)] == ["missing_information_analyzer"]   # one lone statement: nothing to compare


def test_full_investigation_saved_and_reloaded(demo_case):
    out = investigation_service.run_investigation(demo_case["id"], use_ai=False)
    assert out["ok"] and out["status"] == "completed"
    details = investigation_service.get_run_details(out["run_id"])
    assert set(details["tool_results"]) >= {"evidence_analyzer", "timeline_generator", "contradiction_detector",
                                            "clue_analyzer", "missing_information_analyzer", "report_generator"}
    assert details["report"]["report_content"].startswith("# Investigation Report")
    assert "guilty" not in details["report"]["report_content"].lower()
    assert any("Investigation saved" in e["message"] for e in details["log"])
    assert case_service.get_case(demo_case["id"])["status"] == "Completed"
    assert len(investigation_service.list_reports()) == 1
    assert list(config.REPORTS_DIR.glob("*.md"))


def test_run_numbers_increment(demo_case):
    investigation_service.run_investigation(demo_case["id"], use_ai=False)
    investigation_service.run_investigation(demo_case["id"], use_ai=False)
    assert [r["run_number"] for r in investigation_service.list_runs(demo_case["id"])] == [2, 1]


def test_data_survives_restart(demo_case):
    out = investigation_service.run_investigation(demo_case["id"], use_ai=False)
    # "Restart": brand-new connections and init_db on the existing file.
    database.init_db()
    raw = sqlite3.connect(config.DB_PATH)
    assert raw.execute("SELECT COUNT(*) FROM investigation_reports").fetchone()[0] == 1
    raw.close()
    assert investigation_service.get_run_details(out["run_id"])["run"]["execution_status"] == "completed"


def test_empty_case_blocked_without_run():
    cid = case_service.create_case(BASE)
    out = investigation_service.run_investigation(cid, use_ai=False)
    assert not out["ok"] and out["errors"] and investigation_service.list_runs(cid) == []


def test_failing_tool_does_not_stop_others(demo_case, monkeypatch):
    def boom(case, use_ai=True):
        raise RuntimeError("simulated tool crash")
    monkeypatch.setitem(TOOL_REGISTRY, "timeline_generator", boom)
    outcome = InvestigationAgent(use_ai=False).run(demo_case)
    assert outcome["status"] == "completed_with_errors"
    assert outcome["tool_results"]["timeline_generator"]["status"] == "failed"
    assert outcome["tool_results"]["clue_analyzer"]["status"] == "success"
    assert "simulated tool crash" in outcome["report"]["data"]["markdown"]


# ---------- AI paths (fake model) ----------
def _fake_ai(monkeypatch, handler):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-tests")
    monkeypatch.setattr(ai_service, "_call_model", handler)


def test_ai_plan_is_validated_and_required_tool_added(demo_case, monkeypatch):
    plan = {"selected_tools": [{"tool_name": "timeline_generator", "reason": "times exist"}], "reasoning": "test"}
    def handler(prompt, system, schema):
        if schema is ToolPlan:
            return json.dumps(plan)
        raise RuntimeError("503 unavailable")   # tools then fall back
    _fake_ai(monkeypatch, handler)
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: None)
    outcome = InvestigationAgent().run(demo_case)
    assert outcome["plan"]["source"] == "ai"
    assert set(outcome["tool_results"]) == {"timeline_generator", "missing_information_analyzer"}
    assert outcome["status"] == "completed"


def test_invalid_ai_json_falls_back_to_rules(demo_case, monkeypatch):
    _fake_ai(monkeypatch, lambda prompt, system, schema: "this is not json")
    monkeypatch.setattr(ai_service.time, "sleep", lambda s: None)
    outcome = InvestigationAgent().run(demo_case)
    assert outcome["plan"]["source"] == "rule_based_fallback"
    assert outcome["status"] == "completed"
    ai_tools = [r for n, r in outcome["tool_results"].items() if n != "timeline_generator"]   # timeline is deterministic
    assert all(r["mode"] == "rule_based_fallback" for r in ai_tools)


def test_quota_error_trips_circuit_breaker(demo_case, monkeypatch):
    calls = []
    def handler(prompt, system, schema):
        calls.append(1)
        raise Exception("429 RESOURCE_EXHAUSTED quota exceeded")
    _fake_ai(monkeypatch, handler)
    outcome = InvestigationAgent().run(demo_case)
    assert len(calls) == 1                       # only the first call hit the API
    assert outcome["status"] == "completed"      # investigation still finished
    assert "quota" in (outcome["plan"]["ai_error"] or "").lower()


def test_ai_report_guard_rejects_guilt_language(demo_case, monkeypatch):
    from models import ReportNarrative
    from tools import report_generator
    _fake_ai(monkeypatch, lambda p, s, schema: ReportNarrative(key_findings=["W001 is guilty."], neutral_assessment="ok").model_dump_json())
    result = report_generator.run(demo_case, {}, use_ai=True)
    assert result["mode"] == "rule_based_fallback" and "guilty" not in result["data"]["markdown"].lower().replace("assigned guilt", "")


def test_missing_api_key_message():
    with pytest.raises(ai_service.AIUnavailableError):
        ai_service.generate_structured("hi", ToolPlan)
