"""Tool 6 - Investigation Report Generator.

Combines every tool result into a 13-section Markdown report. Every section carries a label so the reader can
tell user-supplied facts from automated analysis, inference and unknowns. The short narrative (key findings and
the neutral assessment) is written by Gemini when available, otherwise by a template.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from models import ReportNarrative, TOOL_LABELS
from services import ai_service
from tools.base import SYSTEM_PROMPT, case_items, make_result
from tools.text_utils import resolve_time

USER, AUTO, INFER, UNKNOWN = ("**[User-supplied]**", "**[Automated analysis]**", "**[Inference]**", "**[Unknown]**")
UNSAFE_RE = re.compile(r"\bguilty\b|\bculprit\b|\b(is|was) the (thief|perpetrator)\b|\bconvict", re.I)


def _cell(value) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _table(headers: list[str], rows: list[list]) -> str:
    if not rows:
        return "_None._\n"
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def _bullets(values: list[str]) -> str:
    return "\n".join(f"- {v}" for v in values) + "\n" if values else "_None._\n"


def _data(results: dict, name: str):
    res = results.get(name)
    return res["data"] if res and res.get("status") == "success" else None


def _unavailable(results: dict, name: str) -> str:
    res = results.get(name)
    if not res:
        return f"_{TOOL_LABELS[name]} was not run for this investigation._\n"
    return f"_{TOOL_LABELS[name]} failed: {res.get('error')}._\n"


def _mode(results: dict, name: str) -> str:
    res = results.get(name) or {}
    return "AI analysis (Gemini)" if res.get("mode") == "ai" else "rule-based analysis"


# ---------------- narrative ----------------
def _fallback_narrative(case: dict, results: dict) -> ReportNarrative:
    findings = []
    timeline = _data(results, "timeline_generator")
    if timeline and timeline["events"]:
        ev = timeline["events"]
        findings.append(f"{len(ev)} timed events were found, from {ev[0]['time_display']} to {ev[-1]['time_display']}.")
        if timeline["gaps"]:
            findings.append(f"{len(timeline['gaps'])} gap(s) of {15}+ minutes with no recorded events were found.")
    contra = _data(results, "contradiction_detector")
    if contra:
        findings.append(f"Contradiction check: {len(contra['contradictions'])} confirmed, {len(contra['possible_inconsistencies'])} possible, "
                        f"{len(contra['unclear_information'])} unclear relation(s), {len(contra['unverified_claims'])} uncorroborated claim(s).")
    clues = _data(results, "clue_analyzer")
    if clues:
        findings.append(f"{len(clues['relationships'])} relationship(s) between items were identified "
                        f"({sum(r['directness'] == 'direct' for r in clues['relationships'])} direct, the rest inferred).")
    missing = _data(results, "missing_information_analyzer")
    if missing:
        high = [m["item"] for m in missing["missing_items"] if m["priority"] == "high"]
        findings.append(f"{len(missing['missing_items'])} information gap(s) found; high priority: {'; '.join(high[:3]) or 'none'}.")
    if not findings:
        findings.append("No tool produced findings; see the limitations section.")
    assessment = ("The supplied information is incomplete and mostly unverified, so no conclusion about what happened or who "
                  "was involved can be drawn. The relationships and gaps above point to where to look next; they are leads, "
                  "not facts. This report does not attribute responsibility to any person.")
    return ReportNarrative(key_findings=findings, neutral_assessment=assessment)


def _narrative(case: dict, results: dict, use_ai: bool) -> tuple[ReportNarrative, str, str | None]:
    if use_ai and ai_service.is_available():
        summary = {name: res["data"] for name, res in results.items() if res.get("status") == "success"}
        prompt = ("TASK:\nWrite key_findings (3-6 short bullet strings) and a neutral_assessment (3-5 sentences) for the "
                  "investigation report. Base them ONLY on the tool results. State uncertainty. Do not name anyone as "
                  "guilty or as a suspect; do not present inferences as facts.\n\nCASE: " + case["title"] +
                  "\n\nTOOL RESULTS (JSON):\n" + json.dumps(summary, ensure_ascii=False)[:24000])
        try:
            narrative = ai_service.generate_structured(prompt, ReportNarrative, system=SYSTEM_PROMPT)
            text = " ".join(narrative.key_findings) + " " + narrative.neutral_assessment
            if UNSAFE_RE.search(text):
                return _fallback_narrative(case, results), "rule_based_fallback", "AI text was rejected by the neutrality check."
            return narrative, "ai", None
        except ai_service.AIError as exc:
            return _fallback_narrative(case, results), "rule_based_fallback", str(exc)
    return _fallback_narrative(case, results), "rule_based", None


# ---------------- sections ----------------
def _statement_section(case: dict, results: dict) -> str:
    if not case.get("statements"):
        return f"{UNKNOWN} No witness statements were supplied.\n"
    clues = _data(results, "clue_analyzer")
    contra = _data(results, "contradiction_detector")
    out = [f"{USER} statements as supplied; {AUTO} notes below.\n"]
    for st in case["statements"]:
        label, mention = st["witness_label"], resolve_time(st.get("event_time", ""), st["statement"])
        out.append(f"**{label}** — \"{st['statement']}\"  \n"
                   f"Time referred to: {mention.display + ' (' + mention.certainty + ')' if mention else 'not stated'}"
                   + (f" · Source notes: {st['source_notes']}" if st.get("source_notes") else ""))
        notes = []
        if clues:
            notes += [f"Related to {r['related_item'] if r['source_item'] == label else r['source_item']}: {r['relationship']} ({r['directness']}, {r['confidence']})"
                      for r in clues["relationships"] if label in (r["source_item"], r["related_item"])][:4]
        if contra:
            for group in ("contradictions", "possible_inconsistencies", "unclear_information"):
                notes += [f"{group.replace('_', ' ').title()}: {f['description']}" for f in contra[group] if label in f["items"]]
        out.append(_bullets(notes) if notes else "_No related findings._\n")
    return "\n".join(out)


def _contradiction_section(results: dict) -> str:
    data = _data(results, "contradiction_detector")
    if not data:
        return _unavailable(results, "contradiction_detector")
    out = [f"{AUTO} ({_mode(results, 'contradiction_detector')}). {data['explanation']}\n"]
    for title, key in (("Confirmed contradictions", "contradictions"), ("Possible inconsistencies", "possible_inconsistencies"),
                       ("Unclear information (not treated as contradictions)", "unclear_information"),
                       ("Unverified / uncorroborated claims", "unverified_claims")):
        out.append(f"**{title}**\n")
        out.append(_bullets([f"{', '.join(f['items'])}: {f['description']} — {f['explanation']}" for f in data[key]]))
    return "\n".join(out)


def build_markdown(case: dict, results: dict, narrative: ReportNarrative, narrative_mode: str) -> str:
    ev_data, timeline = _data(results, "evidence_analyzer"), _data(results, "timeline_generator")
    clues, missing = _data(results, "clue_analyzer"), _data(results, "missing_information_analyzer")
    ran = [f"{TOOL_LABELS[n]} ({r.get('mode', '?')}{', ' + r['status'] if r.get('status') != 'success' else ''})" for n, r in results.items()]
    limitations = [
        "This is an educational simulation on fictional data. It is decision support, not a finding of fact.",
        "Only information typed into the case was analysed; nothing was independently verified.",
        "AI and rule-based analysis can miss context or misread wording. Inferences must be checked by a human.",
        "Times without AM/PM or with 'approximately' are treated as uncertain.",
    ]
    limitations += [f"{TOOL_LABELS[n]} failed and is missing from this report: {r.get('error')}" for n, r in results.items() if r.get("status") != "success"]
    limitations += [f"{TOOL_LABELS[n]}: AI was not used ({r['ai_error']})" for n, r in results.items() if r.get("ai_error")]

    p = [f"# Investigation Report — {case['title']}", "",
         f"_Generated {datetime.now():%Y-%m-%d %H:%M} by DetectIQ (educational simulation)._", "",
         f"**How to read this report:** {USER} = typed in by the user · {AUTO} = produced by tools/AI from that input · "
         f"{INFER} = reasoning that is not confirmed · {UNKNOWN} = information not available. "
         "Nothing labelled analysis or inference is verified evidence.", "",
         "## 1. Case Overview", f"{USER}\n", _table(["Field", "Value"], [
             ["Case number", case["case_number"]], ["Title", case["title"]], ["Incident type", case["incident_type"]],
             ["Location", case.get("location") or "Unknown"], ["Incident date", case.get("incident_date") or "Unknown"],
             ["Status", case["status"]]]), "",
         "## 2. Incident Summary", f"{USER} {case['description']}", "",
         "## 3. Investigation Objective",
         f"{AUTO} Establish what can and cannot be determined from the supplied evidence and statements about "
         f"\"{case['title']}\", identify conflicts and gaps, and suggest next steps. The objective is not to assign blame.", "",
         "## 4. Evidence Overview"]
    if ev_data:
        p.append(f"{AUTO} ({_mode(results, 'evidence_analyzer')})\n")
        p.append(_table(["ID", "Category", "Summary", "Relevance", "Limitations"],
                        [[i["evidence_id"], i["category"], i["summary"], i["relevance"], "; ".join(i["limitations"] + i["unverifiable"])]
                         for i in ev_data["items"]]))
    elif case.get("evidence"):
        p.append(f"{USER} (analysis unavailable)\n" + _unavailable(results, "evidence_analyzer"))
        p.append(_table(["ID", "Type", "Title"], [[e["evidence_number"], e["evidence_type"], e["title"]] for e in case["evidence"]]))
    else:
        p.append(f"{UNKNOWN} No evidence was supplied.\n")
    p += ["", "## 5. Key Findings", f"{AUTO} ({narrative_mode.replace('_', ' ')})\n", _bullets(narrative.key_findings), "",
          "## 6. Timeline"]
    if timeline:
        p.append(f"{AUTO} Times come from the user's text; none were invented.\n")
        p.append(_table(["Time", "Event", "Source", "Certainty", "Notes"],
                        [[e["time_display"], e["event"], f"{e['source']} ({e['source_type']})", e["certainty"], e["notes"]] for e in timeline["events"]]))
        if timeline["gaps"]:
            p.append(f"{UNKNOWN} Gaps with no recorded events:\n")
            p.append(_bullets([f"{g['from']} → {g['to']} ({g['minutes']} min), between {g['between'][0]} and {g['between'][1]}" for g in timeline["gaps"]]))
        if timeline["untimed_items"]:
            p.append(f"{UNKNOWN} Items with no usable time: {', '.join(u['source'] for u in timeline['untimed_items'])}\n")
        p += [f"_{w}_\n" for w in timeline["warnings"]]
    else:
        p.append(_unavailable(results, "timeline_generator"))
    p += ["", "## 7. Witness Statement Analysis", _statement_section(case, results), "",
          "## 8. Contradictions and Inconsistencies", _contradiction_section(results), "",
          "## 9. Evidence Relationships"]
    if clues:
        p.append(f"{AUTO} ({_mode(results, 'clue_analyzer')}). 'Direct' = both items state the shared element; 'inferred' = {INFER} based on closeness or sequence.\n")
        p.append(_table(["Item", "Related item", "Relationship", "Type", "Confidence", "Basis"],
                        [[r["source_item"], r["related_item"], r["relationship"], r["relationship_type"], r["confidence"], r["directness"]] for r in clues["relationships"]]))
        p.append(_bullets([f"{r['source_item']} ↔ {r['related_item']}: {r['explanation']}" for r in clues["relationships"]]))
    else:
        p.append(_unavailable(results, "clue_analyzer"))
    p += ["", "## 10. Missing Information"]
    if missing:
        p.append(f"{UNKNOWN} ({_mode(results, 'missing_information_analyzer')})\n")
        p.append(_table(["Priority", "Missing item", "Why it matters"], [[m["priority"], m["item"], m["why_it_matters"]] for m in missing["missing_items"]]))
        p += ["", "## 11. Recommended Next Investigative Steps", _bullets(missing["next_steps"])]
    else:
        p += [_unavailable(results, "missing_information_analyzer"), "", "## 11. Recommended Next Investigative Steps", "_Unavailable._\n"]
    p += ["", "## 12. Limitations", _bullets(limitations), "",
          "## 13. Final Neutral Assessment", f"{AUTO} {narrative.neutral_assessment}\n",
          f"_Tools run: {', '.join(ran)}._"]
    return "\n".join(p)


def run(case: dict, results: dict | None = None, use_ai: bool = True) -> dict:
    """Build the report from the other tools' results (the agent passes them in)."""
    results = results or {}
    narrative, mode, ai_error = _narrative(case, results, use_ai)
    markdown = build_markdown(case, results, narrative, mode)
    return make_result("report_generator", {"markdown": markdown, "key_findings": narrative.key_findings,
                                            "neutral_assessment": narrative.neutral_assessment}, mode, ai_error)
