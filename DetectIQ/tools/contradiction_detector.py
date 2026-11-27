"""Tool 3 - Contradiction Detector.

Rules are conservative: two statements are only a *confirmed* contradiction when they describe the same
place at (almost) the same exact time in opposite ways. Everything weaker is 'possible' or 'unclear'.
"""
from models import ContradictionAnalysis, Finding
from tools.base import case_items, run_ai_or_fallback
from tools.text_utils import is_departure_claim, is_empty_claim, is_presence_claim, place_nouns, resolve_time

TASK = (
    "Compare witness statements with each other and with the evidence. Return: contradictions (CONFIRMED "
    "conflicts only: same person/place/time described incompatibly), possible_inconsistencies, unverified_claims, "
    "unclear_information (statements that look related but where identity or circumstances are not established), "
    "and an overall explanation. Do NOT treat two statements as contradictory unless identities and "
    "circumstances establish a real conflict. Each finding lists the item ids involved."
)
CORROBORATION_WINDOW = 5   # minutes
SAME_MOMENT = 2
CLOSE = 10


def _claims(case: dict) -> list[dict]:
    claims = []
    for item in case_items(case):
        if item["kind"] == "incident_description":
            continue
        mention = resolve_time(item["event_time"], item["text"])
        if not mention:
            continue
        text = item["text"]
        claims.append({**item, "time": mention, "empty": is_empty_claim(text), "left": is_departure_claim(text),
                       "present": is_presence_claim(text), "places": place_nouns(text)})
    return claims


def _desc(c):
    return f"{c['id']} ({c['time'].display}, {c['time'].certainty})"


def detect_rule_based(case: dict) -> ContradictionAnalysis:
    claims = _claims(case)
    contradictions, possible, unverified, unclear = [], [], [], []

    # Rule 1: "empty" vs "someone present" at nearly the same time.
    for empty in (c for c in claims if c["empty"]):
        for pres in (c for c in claims if c["present"] and not c["left"] and c["id"] != empty["id"]):
            gap = abs(empty["time"].minutes - pres["time"].minutes)
            if gap > CLOSE:
                continue
            both_exact = empty["time"].certainty == pres["time"].certainty == "exact"
            same_place = bool(empty["places"] & pres["places"])
            what = f"{_desc(empty)} reports the place empty; {_desc(pres)} reports someone present ({gap} min apart)."
            if gap <= SAME_MOMENT and both_exact and same_place:
                contradictions.append(Finding(items=[empty["id"], pres["id"]], description=what,
                    explanation="Both describe the same place at the same exact time in incompatible ways."))
            else:
                possible.append(Finding(items=[empty["id"], pres["id"]], description=what,
                    explanation="This may be a real conflict, but the times are not identical/exact or the place is not "
                                "clearly the same, so someone could have entered or left in between."))

    # Rule 2: someone says they left; later another item mentions an unnamed person present.
    for left in (c for c in claims if c["left"] and c["kind"] == "witness_statement"):
        for pres in (c for c in claims if c["present"] and not c["left"] and c["id"] != left["id"]
                     and 0 < c["time"].minutes - left["time"].minutes <= 30):
            unclear.append(Finding(items=[left["id"], pres["id"]],
                description=f"{_desc(left)} says they left; {_desc(pres)} mentions a person present {pres['time'].minutes - left['time'].minutes} min later.",
                explanation="Not treated as a contradiction: it is not established that the person seen is the same "
                            "person who left."))

    # Claims no other item supports within a few minutes.
    for c in claims:
        support = [o["id"] for o in claims if o["id"] != c["id"]
                   and abs(o["time"].minutes - c["time"].minutes) <= CORROBORATION_WINDOW]
        if not support:
            unverified.append(Finding(items=[c["id"]], description=f"{_desc(c)}: {c['text'][:140]}",
                explanation=f"No other item gives a time within {CORROBORATION_WINDOW} minutes, so this claim is "
                            "uncorroborated (not necessarily false)."))

    if not claims:
        explanation = "No timed statements or evidence were available, so no comparison was possible."
    else:
        explanation = (f"Compared {len(claims)} timed items. Confirmed contradictions: {len(contradictions)}; possible "
                       f"inconsistencies: {len(possible)}; unclear relations: {len(unclear)}; uncorroborated claims: "
                       f"{len(unverified)}. Rule-based comparison only checks times and simple wording; it cannot judge meaning.")
    return ContradictionAnalysis(contradictions=contradictions, possible_inconsistencies=possible,
                                 unverified_claims=unverified, unclear_information=unclear, explanation=explanation)


def run(case: dict, use_ai: bool = True) -> dict:
    return run_ai_or_fallback("contradiction_detector", case, TASK, ContradictionAnalysis, detect_rule_based, use_ai)
