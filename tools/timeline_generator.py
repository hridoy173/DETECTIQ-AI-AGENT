"""Tool 2 - Timeline Generator (fully deterministic: it never invents a timestamp)."""
from tools.base import case_items, make_result
from tools.text_utils import parse_event_time, sentence_times

GAP_MINUTES = 15
KIND_LABELS = {"incident_description": "incident description", "evidence": "evidence", "witness_statement": "witness statement"}


def _event(mention, certainty, text, item, notes):
    return {
        "time": mention.hhmm, "time_display": mention.display, "minutes": mention.minutes,
        "event": text[:240], "source": item["id"], "source_type": KIND_LABELS[item["kind"]],
        "certainty": certainty, "notes": "; ".join(n for n in notes if n),
    }


def _notes(certainty, item, extra=""):
    note = {"ambiguous": "No AM/PM given - time is ambiguous", "approximate": "Approximate time",
            "range": "Boundary of a time window; exact time of the event is unknown"}.get(certainty, "")
    return [note, extra, f"Source note: {item['source_note']}" if item["source_note"] else ""]


def build_timeline(case: dict) -> dict:
    events, untimed, seen = [], [], set()
    for item in case_items(case):
        given = parse_event_time(item["event_time"])
        before = len(events)
        if given:
            key = (item["id"], given.minutes)
            seen.add(key)
            label = f"{item['title']}: {item['text']}" if item["kind"] == "evidence" else item["text"]
            cert = given.certainty
            for _, ts in sentence_times(item["text"]):
                for t in ts:
                    if t.minutes == given.minutes and cert == "exact" and t.certainty != "exact":
                        cert = t.certainty
            events.append(_event(given, cert, label, item, _notes(cert, item, "Time taken from the event-time field")))
        for sentence, times in sentence_times(item["text"]):
            for t in times:
                key = (item["id"], t.minutes)
                if key in seen:
                    continue
                seen.add(key)
                events.append(_event(t, t.certainty, sentence, item, _notes(t.certainty, item)))
        if len(events) == before:
            untimed.append({"source": item["id"], "source_type": KIND_LABELS[item["kind"]], "text": item["text"][:200]})

    events.sort(key=lambda e: e["minutes"])
    gaps = []
    for a, b in zip(events, events[1:]):
        if b["minutes"] - a["minutes"] >= GAP_MINUTES:
            gaps.append({"from": a["time_display"], "to": b["time_display"], "minutes": b["minutes"] - a["minutes"],
                         "between": [a["source"], b["source"]]})
    warnings = []
    if not events:
        warnings.append("No usable timestamps were found, so no timeline could be built.")
    if any(e["certainty"] == "ambiguous" for e in events):
        warnings.append("Some times have no AM/PM and are ambiguous; they are shown as written (24-hour reading).")
    return {"events": events, "gaps": gaps, "untimed_items": untimed, "warnings": warnings}


def run(case: dict, use_ai: bool = True) -> dict:
    return make_result("timeline_generator", build_timeline(case))
