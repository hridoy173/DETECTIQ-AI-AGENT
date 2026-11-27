"""Pydantic models. They validate everything the AI returns, so we never trust raw text."""
from typing import Literal

from pydantic import BaseModel

ToolName = Literal[
    "evidence_analyzer",
    "timeline_generator",
    "contradiction_detector",
    "clue_analyzer",
    "missing_information_analyzer",
]
Level = Literal["high", "medium", "low"]

TOOL_LABELS = {
    "evidence_analyzer": "Evidence Analyzer",
    "timeline_generator": "Timeline Generator",
    "contradiction_detector": "Contradiction Detector",
    "clue_analyzer": "Clue Relationship Analyzer",
    "missing_information_analyzer": "Missing Information Analyzer",
    "report_generator": "Investigation Report Generator",
}

TOOL_DESCRIPTIONS = {
    "evidence_analyzer": "Extracts facts, times, locations, objects and limitations from each evidence item. Use when evidence exists.",
    "timeline_generator": "Builds a chronological timeline from any timestamps in the case. Use when timestamps exist.",
    "contradiction_detector": "Compares statements with each other and with evidence. Use when there are several statements or statements plus evidence.",
    "clue_analyzer": "Finds connections between evidence items and statements. Use when there are several items.",
    "missing_information_analyzer": "Lists missing information and next steps. ALWAYS use.",
}


# ---- Agent planning ----
class ToolSelection(BaseModel):
    tool_name: ToolName
    reason: str


class ToolPlan(BaseModel):
    selected_tools: list[ToolSelection]
    reasoning: str


# ---- Evidence Analyzer ----
class EvidenceItemAnalysis(BaseModel):
    evidence_id: str
    summary: str
    category: str
    facts: list[str]
    times: list[str]
    locations: list[str]
    objects: list[str]
    relevance: Level
    limitations: list[str]
    unverifiable: list[str]


class EvidenceAnalysis(BaseModel):
    items: list[EvidenceItemAnalysis]


# ---- Contradiction Detector ----
class Finding(BaseModel):
    items: list[str]
    description: str
    explanation: str


class ContradictionAnalysis(BaseModel):
    contradictions: list[Finding]
    possible_inconsistencies: list[Finding]
    unverified_claims: list[Finding]
    unclear_information: list[Finding]
    explanation: str


# ---- Clue Relationship Analyzer ----
class Relationship(BaseModel):
    source_item: str
    related_item: str
    relationship: str
    explanation: str
    relationship_type: str
    confidence: Level
    directness: Literal["direct", "inferred"]


class ClueAnalysis(BaseModel):
    relationships: list[Relationship]


# ---- Missing Information Analyzer ----
class MissingItem(BaseModel):
    item: str
    why_it_matters: str
    priority: Level
    suggested_step: str


class MissingAnalysis(BaseModel):
    missing_items: list[MissingItem]
    next_steps: list[str]


# ---- Report narrative (written by AI, or by a template if AI is unavailable) ----
class ReportNarrative(BaseModel):
    key_findings: list[str]
    neutral_assessment: str
