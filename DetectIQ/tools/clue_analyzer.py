"""Tool 4 - Clue Relationship Analyzer: connections between evidence and statements (direct vs inferred)."""
from itertools import combinations

from models import ClueAnalysis, Relationship
from tools.base import case_items, run_ai_or_fallback
from tools.text_utils import (extract_objects, is_departure_claim, is_empty_claim, place_nouns, resolve_time)

TASK = (
    "Find relationships between evidence items and witness statements (shared times, locations, objects, events). "
    "For each: source_item, related_item, relationship (short), explanation, relationship_type "
    "(temporal/object/sequence/other), confidence (high/medium/low) and directness: 'direct' if both items explicitly "
    "state the shared element, 'inferred' if it is your reasoning. Never assign blame or call anyone a suspect."
)
ORDER = {"high": 0, "medium": 1, "low": 2}


def analyze_rule_based(case: dict) -> ClueAnalysis:
    items = [i for i in case_items(case) if i["kind"] != "incident_description"]
    for i in items:
        i["time"] = resolve_time(i["event_time"], i["text"])
        i["objects"] = set(extract_objects(i["text"]))
        i["places"] = place_nouns(i["text"])
    rows = []
    for a, b in combinations(items, 2):
        place_note = f" Both refer to the {', '.join(sorted(a['places'] & b['places']))}." if a["places"] & b["places"] else ""
        shared = (a["objects"] & b["objects"]) - {"desk"}
        if shared:
            rows.append(Relationship(
                source_item=a["id"], related_item=b["id"], relationship=f"Both mention: {', '.join(sorted(shared))}",
                explanation=f"Both items explicitly mention the same object(s).{place_note} This shows a shared topic, not proof of a link.",
                relationship_type="object", confidence="medium" if len(shared) > 1 else "low", directness="direct"))
        if a["time"] and b["time"]:
            gap = abs(a["time"].minutes - b["time"].minutes)
            if gap <= 10:
                weak = "exact" != a["time"].certainty or "exact" != b["time"].certainty
                rows.append(Relationship(
                    source_item=a["id"], related_item=b["id"], relationship=f"Close in time ({gap} min apart)",
                    explanation=f"{a['id']} is at {a['time'].display} and {b['id']} at {b['time'].display}.{place_note} "
                                "Closeness in time is a hint to look further, not evidence that the items are about the same event.",
                    relationship_type="temporal", confidence="low" if weak or gap > 5 else "medium", directness="inferred"))
        # A reported departure followed shortly by an 'empty' report.
        for x, y in ((a, b), (b, a)):
            if x["time"] and y["time"] and is_departure_claim(x["text"]) and is_empty_claim(y["text"]) \
                    and 0 < y["time"].minutes - x["time"].minutes <= 15:
                rows.append(Relationship(
                    source_item=x["id"], related_item=y["id"], relationship="Reported departure, then reported empty",
                    explanation=f"{x['id']} reports someone leaving at {x['time'].display}; {y['id']} reports the place empty at "
                                f"{y['time'].display}. The departure could explain the emptiness, but that is an inference.",
                    relationship_type="sequence", confidence="low", directness="inferred"))
    rows.sort(key=lambda r: (ORDER[r.confidence], r.source_item))
    return ClueAnalysis(relationships=rows[:30])


def run(case: dict, use_ai: bool = True) -> dict:
    return run_ai_or_fallback("clue_analyzer", case, TASK, ClueAnalysis, analyze_rule_based, use_ai)
