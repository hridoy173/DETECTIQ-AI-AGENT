"""Tool 5 - Missing Information Analyzer: what is unknown, why it matters, and what to do next."""
import re

from models import MissingAnalysis, MissingItem
from tools.base import case_items, run_ai_or_fallback
from tools.text_utils import is_verified, resolve_time

TASK = (
    "List useful information that is MISSING from this case (e.g. CCTV availability, whether a witness saw the event "
    "personally, independent verification, other witnesses, exact times). For each: item, why_it_matters, priority "
    "(high/medium/low), suggested_step. Then give next_steps: practical, ordered investigative actions."
)
ORDER = {"high": 0, "medium": 1, "low": 2}
RECORD_RE = re.compile(r"\b(cctv|camera|video|footage|access log|swipe|badge log|sign-in)\b", re.I)
FIRST_PERSON_RE = re.compile(r"\b(I|my|me|we)\b")
UNNAMED_RE = re.compile(r"\b(someone|somebody|a person|a man|a woman|unknown)\b", re.I)


def analyze_rule_based(case: dict) -> MissingAnalysis:
    found: list[MissingItem] = []

    def add(item, why, priority, step):
        found.append(MissingItem(item=item, why_it_matters=why, priority=priority, suggested_step=step))

    evidence, statements = case.get("evidence", []), case.get("statements", [])
    all_text = " ".join(i["text"] + " " + i["source_note"] for i in case_items(case))

    if not evidence:
        add("No evidence items were supplied", "Without evidence, statements cannot be checked against anything.", "high",
            "Collect and record available evidence (objects, logs, photos, reports).")
    if not statements:
        add("No witness statements were supplied", "Statements give perspectives that can be compared.", "high",
            "Interview people who were present and record their statements.")
    if not case.get("location"):
        add("Incident location is not recorded", "Locations are needed to compare claims.", "medium", "Record the exact location.")
    if not RECORD_RE.search(all_text):
        add("Whether CCTV footage or access logs exist", "Recorded footage or logs are independent of human memory.", "high",
            "Ask whether CCTV, door-access or sign-in records exist for the location and time window.")
    for ev in evidence:
        if not resolve_time(ev.get("event_time", ""), ev["description"]):
            add(f"Exact time for {ev['evidence_number']}", "An item without a time cannot be placed on the timeline.", "medium",
                f"Find out when {ev['evidence_number']} was observed or recorded.")
        if not ev.get("source"):
            add(f"Source of {ev['evidence_number']}", "Unknown origin limits how far the item can be trusted.", "medium",
                f"Record who provided {ev['evidence_number']} and how.")
    unverified = [e["evidence_number"] for e in evidence
                  if not is_verified(e.get("reliability_notes", "") + " " + e.get("source", ""))]
    if unverified:
        add(f"Independent verification of {', '.join(unverified)}", "Nothing in the data shows these items were independently confirmed.",
            "high", "Check each item against a second, independent source.")
    for st in statements:
        if not FIRST_PERSON_RE.search(st["statement"]):
            add(f"Whether {st['witness_label']} personally observed the event", "The statement is not phrased as a first-hand observation.",
                "medium", f"Ask {st['witness_label']} whether they saw this themselves or heard it from someone.")
        if not resolve_time(st.get("event_time", ""), st["statement"]):
            add(f"Time referred to by {st['witness_label']}", "Without a time the statement cannot be compared.", "medium",
                f"Ask {st['witness_label']} when this happened.")
    if len(statements) < 5:
        add("Other witnesses who were present", f"Only {len(statements)} statement(s) available; more perspectives could confirm or challenge them.",
            "medium", "Identify everyone who was present and who else could have seen something.")
    if UNNAMED_RE.search(all_text):
        add("Identity of persons described only as 'someone' / 'a person'", "Unnamed people cannot be linked across items.", "high",
            "Ask witnesses for descriptions or other details that could establish who is meant (without assuming guilt).")
    if re.search(r"\b(missing|stolen|lost|damaged)\b", case.get("description", ""), re.I) and \
            not re.search(r"\b(discovered|noticed (it )?missing|found missing|reported missing at)\b", all_text, re.I):
        add("When and by whom the problem was first noticed", "Defines the end of the time window under investigation.", "high",
            "Record who first noticed the problem, when, and what they saw.")

    found.sort(key=lambda m: ORDER[m.priority])
    steps = list(dict.fromkeys(m.suggested_step for m in found))
    return MissingAnalysis(missing_items=found, next_steps=steps)


def run(case: dict, use_ai: bool = True) -> dict:
    return run_ai_or_fallback("missing_information_analyzer", case, TASK, MissingAnalysis, analyze_rule_based, use_ai)
