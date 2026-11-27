"""Tool registry: the agent looks tools up here by name."""
from tools import (clue_analyzer, contradiction_detector, evidence_analyzer, missing_information_analyzer,
                   report_generator, timeline_generator)

# Order here = execution order. The report generator is separate because it runs last, on all results.
TOOL_REGISTRY = {
    "evidence_analyzer": evidence_analyzer.run,
    "timeline_generator": timeline_generator.run,
    "contradiction_detector": contradiction_detector.run,
    "clue_analyzer": clue_analyzer.run,
    "missing_information_analyzer": missing_information_analyzer.run,
}
generate_report = report_generator.run
