"""Small, deterministic text helpers shared by the tools (times, places, objects, claim types)."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TimeMention:
    minutes: int      # minutes after midnight
    text: str         # the text it was found in
    certainty: str    # exact | approximate | ambiguous | range

    @property
    def hhmm(self) -> str:
        return f"{self.minutes // 60:02d}:{self.minutes % 60:02d}"

    @property
    def display(self) -> str:
        hour, minute = divmod(self.minutes, 60)
        return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


_MERIDIEM_RE = re.compile(r"(?<![\w:])(\d{1,2})(?::([0-5]\d))?\s*([apAP])(?:\.[mM]\.|[mM])(?!\w)")
_24H_RE = re.compile(r"(?<![\w:])([01]?\d|2[0-3]):([0-5]\d)(?![\w:])")
_APPROX_RE = re.compile(r"(approximately|approx\.?|around|about|roughly|circa|~)\s*$", re.I)


def _approx_before(text: str, start: int) -> bool:
    return bool(_APPROX_RE.search(text[max(0, start - 20):start]))


def extract_times(text: str) -> list[TimeMention]:
    """Find clock times such as '2:10 PM', '14:35' or 'around 2 pm'. Never invents a time."""
    found: list[tuple[int, TimeMention]] = []
    spans: list[tuple[int, int]] = []
    for m in _MERIDIEM_RE.finditer(text or ""):
        hour, minute = int(m.group(1)), int(m.group(2) or 0)
        if not 1 <= hour <= 12:
            continue
        minutes = ((hour % 12) + (12 if m.group(3).lower() == "p" else 0)) * 60 + minute
        certainty = "approximate" if _approx_before(text, m.start()) else "exact"
        found.append((m.start(), TimeMention(minutes, m.group(0).strip(), certainty)))
        spans.append((m.start(), m.end()))
    for m in _24H_RE.finditer(text or ""):
        if any(s <= m.start() < e for s, e in spans):
            continue
        hour, minute = int(m.group(1)), int(m.group(2))
        if 1 <= hour <= 12:
            certainty = "ambiguous"   # "2:20" without AM/PM could be morning or afternoon
        elif _approx_before(text, m.start()):
            certainty = "approximate"
        else:
            certainty = "exact"
        found.append((m.start(), TimeMention(hour * 60 + minute, m.group(0), certainty)))
    found.sort(key=lambda pair: pair[0])
    return [mention for _, mention in found]


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text or "") if s.strip()]


def sentence_times(text: str) -> list[tuple[str, list[TimeMention]]]:
    """Sentences that contain times. 'between X and Y' marks both times as a range."""
    result = []
    for sentence in split_sentences(text):
        times = extract_times(sentence)
        if len(times) >= 2 and re.search(r"\b(between|from)\b", sentence, re.I):
            times = [TimeMention(t.minutes, t.text, "range") for t in times]
        if times:
            result.append((sentence, times))
    return result


def parse_event_time(value: str | None) -> TimeMention | None:
    """Read the optional 'event time' form field. Returns None if empty or unreadable."""
    value = (value or "").strip()
    times = extract_times(value) if value else []
    return times[0] if times else None


def resolve_time(event_time: str | None, text: str) -> TimeMention | None:
    """Best single time for an item: the event-time field first, else the first time in its text.
    If the text says the same time is 'approximately', keep that weaker certainty."""
    given = parse_event_time(event_time)
    in_text = [t for _, ts in sentence_times(text) for t in ts]
    if given:
        same = [t for t in in_text if t.minutes == given.minutes]
        if same and given.certainty == "exact" and same[0].certainty != "exact":
            return TimeMention(given.minutes, given.text, same[0].certainty)
        return given
    return in_text[0] if in_text else None


# ---------------- places, objects, claim types ----------------
PLACE_WORDS = {
    "laboratory": "laboratory", "lab": "laboratory", "room": "room", "office": "office",
    "library": "library", "hallway": "hallway", "corridor": "hallway", "lobby": "lobby",
    "classroom": "classroom", "entrance": "entrance", "building": "building",
    "parking": "parking", "cafeteria": "cafeteria", "warehouse": "warehouse",
}
OBJECT_WORDS = {
    "laptop": "laptop", "backpack": "backpack", "bag": "bag", "phone": "phone",
    "wallet": "wallet", "key": "key", "keys": "key", "camera": "camera", "tablet": "tablet",
    "charger": "charger", "desk": "desk", "door": "door", "window": "window",
    "badge": "badge", "notebook": "notebook", "monitor": "monitor", "cctv": "cctv",
}
_LOC_RE = re.compile(r"\b(?:in|on|at|near|inside|outside|from)\s+(?:the|a|an)\s+((?:[A-Za-z][A-Za-z-]*\s*){1,4})", re.I)
_LOC_STOP = {"at", "around", "between", "when", "with", "and", "was", "is", "as", "i", "checked", "during",
             "approximately", "about", "by", "after", "before", "reported", "reportedly", "while", "that", "for", "to"}


def place_nouns(text: str) -> set[str]:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return {PLACE_WORDS[w] for w in words if w in PLACE_WORDS}


def extract_objects(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", (text or "").lower())
    return list(dict.fromkeys(OBJECT_WORDS[w] for w in words if w in OBJECT_WORDS))


def extract_locations(text: str) -> list[str]:
    """Places named in the text: prepositional phrases ('on the laboratory desk') plus place nouns."""
    locations: list[str] = []
    for m in _LOC_RE.finditer(text or ""):
        words = []
        for word in m.group(1).split():
            if word.lower() in _LOC_STOP:
                break
            words.append(word.lower())
        if words:
            locations.append(" ".join(words))
    locations.extend(sorted(place_nouns(text)))
    return list(dict.fromkeys(locations))


EMPTY_RE = re.compile(r"\b(empty|nobody|no one|deserted|vacant)\b", re.I)
DEPART_RE = re.compile(r"\b(left|leave|leaving|exit(?:ed)?|walked out|departed)\b", re.I)
PRESENCE_RE = re.compile(r"\b(someone|somebody|a person|a man|a woman|person|people|present|still in|was in|were in)\b", re.I)


def is_empty_claim(text: str) -> bool:
    return bool(EMPTY_RE.search(text or ""))


def is_departure_claim(text: str) -> bool:
    return bool(DEPART_RE.search(text or ""))


def is_presence_claim(text: str) -> bool:
    return bool(PRESENCE_RE.search(text or "")) and not is_empty_claim(text)


_VERIFIED_RE = re.compile(r"\b(verified|confirmed by|cross-checked|corroborated)\b", re.I)
_NEGATED_RE = re.compile(r"\b(not|no|un|never|without|isn't|wasn't|hasn't)\b[^.;]{0,30}\b(verified|confirmed|corroborated)", re.I)


def is_verified(text: str) -> bool:
    """True if the text says something was verified (and does not say 'not verified')."""
    return bool(_VERIFIED_RE.search(text or "")) and not _NEGATED_RE.search(text or "")
