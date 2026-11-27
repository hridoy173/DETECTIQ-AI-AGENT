"""Shared plumbing for the tools: normalizing case data and 'AI first, rules as backup' execution."""
from __future__ import annotations

import json
from typing import Callable

from pydantic import BaseModel

from services import ai_service

SYSTEM_PROMPT = (
    "You are an analysis module inside DetectIQ, an EDUCATIONAL investigation-support tool that works on "
    "FICTIONAL cases. Rules: use only facts present in the supplied case; never invent times, people, "
    "evidence or locations; never state or imply that any person is guilty; clearly separate direct facts "
    "from inferences; write 'unknown' when information is missing; be concise. Respond only with JSON."
)


def case_items(case: dict) -> list[dict]:
    """Flatten a case into one list of items (incident description, evidence, statements)."""
    items = [{
        "id": "CASE", "kind": "incident_description", "title": case.get("title", ""),
        "text": case.get("description", ""), "event_time": "", "source_note": "", "reliability": "",
    }]
    for ev in case.get("evidence", []):
        items.append({
            "id": ev["evidence_number"], "kind": "evidence", "title": ev["title"],
            "text": ev["description"], "event_time": ev.get("event_time", ""),
            "source_note": ev.get("source", ""), "reliability": ev.get("reliability_notes", ""),
            "evidence_type": ev.get("evidence_type", ""),
        })
    for st in case.get("statements", []):
        items.append({
            "id": st["witness_label"], "kind": "witness_statement", "title": f"Statement of {st['witness_label']}",
            "text": st["statement"], "event_time": st.get("event_time", ""),
            "source_note": st.get("source_notes", ""), "reliability": st.get("source_notes", ""),
        })
    return items


def case_json(case: dict) -> str:
    """Compact JSON of the case for AI prompts."""
    data = {
        "title": case.get("title"), "incident_type": case.get("incident_type"),
        "description": case.get("description"), "location": case.get("location"),
        "incident_date": case.get("incident_date"),
        "evidence": [{k: e.get(k, "") for k in ("evidence_number", "evidence_type", "title", "description",
                                                  "event_time", "source", "reliability_notes")}
                     for e in case.get("evidence", [])],
        "witness_statements": [{k: s.get(k, "") for k in ("witness_label", "statement", "event_time", "source_notes")}
                               for s in case.get("statements", [])],
    }
    return json.dumps(data, ensure_ascii=False, indent=1)


def make_result(tool: str, data: dict, mode: str = "rule_based", ai_error: str | None = None) -> dict:
    """Uniform result wrapper. mode: ai | rule_based | rule_based_fallback."""
    return {"tool": tool, "mode": mode, "ai_error": ai_error, "data": data}


def run_ai_or_fallback(tool: str, case: dict, task: str, schema: type[BaseModel],
                       fallback: Callable[[dict], BaseModel], use_ai: bool = True) -> dict:
    """Try Gemini first (validated by `schema`); if unavailable or invalid, run the rule-based fallback."""
    ai_error = None
    if use_ai and ai_service.is_available():
        prompt = f"TASK:\n{task}\n\nCASE DATA (JSON):\n{case_json(case)}"
        try:
            result = ai_service.generate_structured(prompt, schema, system=SYSTEM_PROMPT)
            return make_result(tool, result.model_dump(), "ai")
        except ai_service.AIError as exc:
            ai_error = str(exc)
            return make_result(tool, fallback(case).model_dump(), "rule_based_fallback", ai_error)
    if use_ai:
        ai_error = "AI not available (no valid API key or AI disabled after an earlier error)."
    return make_result(tool, fallback(case).model_dump(), "rule_based", ai_error)
