"""Tool 1 - Evidence Analyzer: facts, times, places, objects, relevance and limitations per evidence item."""
import re

from models import EvidenceAnalysis, EvidenceItemAnalysis
from tools.base import run_ai_or_fallback
from tools.text_utils import is_verified, extract_locations, extract_objects, resolve_time, sentence_times, split_sentences, extract_times

TASK = (
    "Analyze EACH evidence item. For every item return: evidence_id (the evidence_number), a one-sentence "
    "summary, category, facts (only things literally stated), times mentioned, locations, objects, relevance "
    "(high/medium/low to the incident), limitations (reliability weaknesses) and unverifiable (claims that "
    "cannot be verified from the data). Do not invent facts."
)
CATEGORIES = {"witness": "Testimonial", "observation": "Observation", "document": "Document", "log": "Record/Log",
              "cctv": "Video/Digital", "photo": "Video/Digital", "physical": "Physical", "digital": "Video/Digital"}
HEARSAY_RE = re.compile(r"\b(reported|reportedly|allegedly|appeared|seemed|approximately|around|about)\b", re.I)


def _category(evidence_type: str) -> str:
    lowered = (evidence_type or "").lower()
    for key, label in CATEGORIES.items():
        if key in lowered:
            return label
    return evidence_type.title() or "Uncategorized"


def analyze_rule_based(case: dict) -> EvidenceAnalysis:
    incident_objects = set(extract_objects(case.get("description", "")))
    items = []
    for ev in case.get("evidence", []):
        text, notes = ev["description"], ev.get("reliability_notes", "")
        mention = resolve_time(ev.get("event_time", ""), text)
        times = list(dict.fromkeys(
            [t.display for _, ts in sentence_times(text) for t in ts] + ([mention.display] if mention else [])))
        objects, locations = extract_objects(text), extract_locations(text)

        facts = split_sentences(text)[:6]
        if mention:
            facts.append(f"Event time recorded: {mention.display} ({mention.certainty})")
        limitations, unverifiable = [], []
        if not ev.get("source"):
            limitations.append("Source of this evidence is not specified.")
        if not mention:
            limitations.append("No time is recorded for this evidence.")
        elif mention.certainty != "exact":
            limitations.append(f"The time is {mention.certainty}, not exact.")
        if HEARSAY_RE.search(text):
            limitations.append("Wording suggests a report or approximation rather than a direct, exact observation.")
        if notes:
            limitations.append(f"Reliability note from user: {notes}")
        if not is_verified(notes + " " + ev.get("source", "")):
            unverifiable.append("Not independently verified in the supplied data.")

        score = (1 if mention else 0) + (1 if incident_objects & set(objects) else 0) \
            + (1 if extract_locations(case.get("description", "")) and set(locations) & set(extract_locations(case["description"])) else 0)
        items.append(EvidenceItemAnalysis(
            evidence_id=ev["evidence_number"], summary=(split_sentences(text) or [text])[0][:200],
            category=_category(ev.get("evidence_type", "")), facts=facts, times=times, locations=locations,
            objects=objects, relevance="high" if score >= 2 else "medium" if score == 1 else "low",
            limitations=limitations, unverifiable=unverifiable))
    return EvidenceAnalysis(items=items)


def run(case: dict, use_ai: bool = True) -> dict:
    return run_ai_or_fallback("evidence_analyzer", case, TASK, EvidenceAnalysis, analyze_rule_based, use_ai)
