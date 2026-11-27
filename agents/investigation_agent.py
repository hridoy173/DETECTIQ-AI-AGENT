"""The Investigation Agent.

Workflow:  validate -> PLAN (Gemini picks tools, validated by Pydantic; rules if that fails)
           -> EXECUTE the selected Python tools (a failing tool never stops the others)
           -> GENERATE the report from all tool results.
Every log line is written at the moment the event really happens.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from models import TOOL_DESCRIPTIONS, TOOL_LABELS, ToolPlan
from services import ai_service
from services.case_service import validate_for_investigation
from tools import TOOL_REGISTRY, generate_report
from tools.base import SYSTEM_PROMPT, case_items, case_json
from tools.text_utils import resolve_time

REQUIRED_TOOL = "missing_information_analyzer"


class InvestigationAgent:
    def __init__(self, use_ai: bool = True, progress: Callable[[dict], None] | None = None):
        self.use_ai = use_ai
        self.progress = progress
        self.log: list[dict] = []

    # ---------- logging ----------
    def log_event(self, message: str, level: str = "info") -> None:
        entry = {"time": datetime.now().strftime("%H:%M:%S"), "level": level, "message": message}
        self.log.append(entry)
        if self.progress:
            try:
                self.progress(entry)
            except Exception:  # a UI problem must never break the investigation
                pass

    # ---------- planning ----------
    @staticmethod
    def deterministic_plan(case: dict) -> list[dict]:
        """Rule-based tool selection (used when the AI is unavailable or returns an invalid plan)."""
        n_ev, n_st = len(case.get("evidence", [])), len(case.get("statements", []))
        has_times = any(resolve_time(i["event_time"], i["text"]) for i in case_items(case))
        chosen = []
        if n_ev:
            chosen.append(("evidence_analyzer", f"{n_ev} evidence item(s) exist."))
        if has_times:
            chosen.append(("timeline_generator", "Timestamps were found in the case data."))
        if n_st >= 2 or (n_st >= 1 and n_ev >= 1):
            chosen.append(("contradiction_detector", f"{n_st} statement(s) and {n_ev} evidence item(s) can be compared."))
        if n_ev + n_st >= 2:
            chosen.append(("clue_analyzer", f"{n_ev + n_st} items may be related to each other."))
        chosen.append((REQUIRED_TOOL, "Always run: every case has information gaps."))
        return [{"tool_name": n, "reason": r} for n, r in chosen]

    def _ai_plan(self, case: dict) -> tuple[list[dict], str]:
        tools_text = "\n".join(f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items())
        prompt = (f"TASK:\nYou are the planner of an investigation agent. Choose which tools to run for this case and give "
                  f"a short reason for each. '{REQUIRED_TOOL}' must always be selected.\n\nAVAILABLE TOOLS:\n{tools_text}\n\n"
                  f"CASE DATA (JSON):\n{case_json(case)}")
        plan = ai_service.generate_structured(prompt, ToolPlan, system=SYSTEM_PROMPT)
        return [{"tool_name": s.tool_name, "reason": s.reason} for s in plan.selected_tools], plan.reasoning

    def plan(self, case: dict) -> dict:
        """Returns {'source', 'reasoning', 'selected_tools', 'ai_error'}."""
        self.log_event("Planning started: deciding which tools are needed")
        ai_error, reasoning, source, selected = None, "", "rule_based", None
        if self.use_ai and ai_service.is_available():
            try:
                selected, reasoning = self._ai_plan(case)
                source = "ai"
                self.log_event("AI planning completed (Gemini returned a valid plan)")
            except ai_service.AIError as exc:
                ai_error, source = str(exc), "rule_based_fallback"
                self.log_event(f"AI planning failed ({exc}); using deterministic rules", "warning")
        elif self.use_ai:
            ai_error = "AI not available (no valid API key or AI disabled after an earlier error)."
            self.log_event("AI planning unavailable; using deterministic tool-selection rules", "warning")
        else:
            self.log_event("AI disabled by the user; using deterministic tool-selection rules")

        if selected is not None:   # validate the AI plan: unique tools, required tool present, known order
            names = {s["tool_name"] for s in selected}
            if REQUIRED_TOOL not in names:
                selected.append({"tool_name": REQUIRED_TOOL, "reason": "Always run (added by the agent: required tool)."})
                self.log_event(f"{TOOL_LABELS[REQUIRED_TOOL]} was added by the agent because it is always required")
            selected = list({s["tool_name"]: s for s in reversed(selected)}.values())
            selected.sort(key=lambda s: list(TOOL_REGISTRY).index(s["tool_name"]))
        else:
            selected = self.deterministic_plan(case)
        for s in selected:
            self.log_event(f"{TOOL_LABELS[s['tool_name']]} selected - {s['reason']}")
        return {"source": source, "reasoning": reasoning, "selected_tools": selected, "ai_error": ai_error}

    # ---------- execution ----------
    def _run_tool(self, name: str, case: dict) -> dict:
        label = TOOL_LABELS[name]
        self.log_event(f"Executing {label}")
        started = time.perf_counter()
        try:
            result = TOOL_REGISTRY[name](case, use_ai=self.use_ai)
            result["status"], result["error"] = "success", None
            level = "warning" if result.get("mode") == "rule_based_fallback" else "info"
            note = f" - AI failed ({result['ai_error']}); rule-based fallback used" if level == "warning" else ""
            self.log_event(f"{label} completed in {time.perf_counter() - started:.2f}s [{result['mode']}]{note}", level)
        except Exception as exc:  # isolate failures: other tools continue
            result = {"tool": name, "mode": "none", "ai_error": None, "data": {}, "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}"}
            self.log_event(f"{label} FAILED: {result['error']}", "error")
        result["duration_seconds"] = round(time.perf_counter() - started, 3)
        return result

    def run(self, case: dict) -> dict:
        """Run a full investigation. Always returns a dict; never raises for tool/AI problems."""
        ai_service.reset_circuit()
        self.log_event(f"Investigation initialized for {case.get('case_number', 'case')}")
        errors, warnings = validate_for_investigation(case)
        if errors:
            for e in errors:
                self.log_event(e, "error")
            return {"status": "failed", "plan": None, "tool_results": {}, "report": None, "log": self.log, "errors": errors}
        self.log_event(f"Case information validated ({len(case['evidence'])} evidence, {len(case['statements'])} statements)")
        for w in warnings:
            self.log_event(w, "warning")

        plan = self.plan(case)
        results: dict[str, dict] = {}
        for sel in plan["selected_tools"]:
            results[sel["tool_name"]] = self._run_tool(sel["tool_name"], case)
        ok = sum(r["status"] == "success" for r in results.values())
        self.log_event(f"Tools execution completed ({ok} succeeded, {len(results) - ok} failed)",
                       "info" if ok == len(results) else "warning")

        self.log_event("Report generation started")
        try:
            report = generate_report(case, results, use_ai=self.use_ai)
            report["status"], report["error"] = "success", None
            self.log_event(f"Final report generated [{report['mode']}]")
        except Exception as exc:
            report = {"tool": "report_generator", "mode": "none", "data": {"markdown": ""}, "status": "failed",
                      "error": f"{type(exc).__name__}: {exc}", "ai_error": None}
            self.log_event(f"Report generation FAILED: {report['error']}", "error")

        status = "failed" if report["status"] == "failed" or ok == 0 else \
            "completed" if ok == len(results) else "completed_with_errors"
        return {"status": status, "plan": plan, "tool_results": results, "report": report, "log": self.log, "errors": []}
