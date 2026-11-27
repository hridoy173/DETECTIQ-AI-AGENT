# DetectIQ — AI Investigation Agent

An AI-powered **investigation and evidence-analysis agent** for fictional cases.
It is **not a chatbot**: it plans which tools to use, runs real Python tools, combines their results and
writes a structured report. Built as an Artificial Intelligence course project.

> **Educational simulation.** DetectIQ never declares anyone guilty. Use fictional cases only.

## Objectives
- Build a genuine tool-using AI agent (plan → act → combine → report).
- Use structured, validated LLM output instead of fragile text parsing.
- Keep the agent working when the AI fails (deterministic fallback).
- Be transparent: every tool, reason, result and log line is shown to the user.

## AI concepts demonstrated
Agent architecture · tool selection / planning · structured outputs (Pydantic schemas) · retries and graceful
fallback · rule-based vs. LLM reasoning · uncertainty handling · responsible-AI guardrails · persistence.

## Features
Dashboard with charts · case management (search, filter, delete with confirmation) · dynamic case form ·
5 analysis tools + report generator · interactive Plotly timeline · live agent activity log · saved runs and
reports · export as Markdown / TXT / print-friendly HTML (print to PDF) · one-click demo case.

## Technology stack
Python 3.11+ · Streamlit · Google Gemini API (`google-genai`) · SQLite · Plotly · Pandas · Pydantic · python-dotenv.

## Architecture
```
User input → validation → PLAN (Gemini → ToolPlan schema; rules if it fails)
          → EXECUTE selected tools (a crash in one tool does not stop the others)
          → REPORT (all results combined) → SAVE (SQLite) → DISPLAY
```
```
app.py                     Streamlit pages
agents/investigation_agent.py   the agent: plan, execute, log, report
tools/                     evidence_analyzer, timeline_generator, contradiction_detector,
                           clue_analyzer, missing_information_analyzer, report_generator
                           (text_utils.py = time/place parsing, base.py = "AI first, rules as backup")
services/                  ai_service (Gemini), case_service (CRUD), investigation_service (run + save/load)
components/                sidebar, dashboard, case cards, timeline, results view, theme
database.py  models.py  config.py      schema · Pydantic models · settings
tests/                     24 tests (no real API calls)
```
Each tool returns `{"tool", "mode", "ai_error", "data"}`. `mode` is `ai`, `rule_based` or `rule_based_fallback`,
so you can always see whether Gemini or plain Python produced a result. The Timeline Generator is fully deterministic.

## Installation (Windows)
```bat
cd DetectIQ
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
(macOS/Linux: `source .venv/bin/activate` and `cp .env.example .env`.)

## Gemini API setup
1. Create a free key at <https://aistudio.google.com/apikey>.
2. Open `.env` and set `GEMINI_API_KEY=your key`. Optionally change `GEMINI_MODEL` (default `gemini-2.5-flash`;
   use any model your key supports — no code change needed).
3. Never share or commit `.env` (it is in `.gitignore`).

**No key?** The app still works in rule-based mode. Add a key to enable AI planning, AI analysis and the AI-written summary.
Use *Settings / About → Test Gemini connection* to verify your setup.

## Run
```bat
streamlit run app.py
```
Open the URL shown (usually http://localhost:8501). The database is created automatically in `data/detectiq.db`.

## Demo instructions
1. Dashboard → **Load demo case** (Missing Laptop — University Computer Lab).
2. Click **Run Investigation** and watch the live log.
3. Open the tabs: *Tool selection* (why each tool was chosen), *Timeline*, *Contradictions*, *Relationships*, *Missing info*, *Report*.
4. Reports page → download the report. Restart the app: everything is still there.

## Example case
Laptop last confirmed on a desk at 2:10 PM (E001); a witness saw a person leave with a backpack at ~2:35 PM (E002);
lab reportedly empty at ~2:45 PM (E003); statements W001–W003 at 2:20, 2:30 and 2:45 PM.
Expected behaviour: **no** confirmed contradiction; W001/W002 flagged as *unclear* (not shown to be the same person);
CCTV, verification, identity of "someone" and the time the loss was noticed listed as missing information.

## Testing
```bat
python -m pytest -q
```
Covers the database, case CRUD, validation, time parsing, timeline sorting, contradiction rules, tool selection,
tool execution, report saving, restart persistence, failing tools, invalid AI JSON, quota errors and the neutrality guard.
AI paths are tested with a fake model, so tests are free.

## Screenshots
_Add your screenshots here (Dashboard, Workspace, Timeline, Report)._

## Limitations
- Rule-based logic only understands simple wording (e.g. "empty", "left", "someone") and clock times; Gemini adds semantic understanding but can be wrong.
- Times without AM/PM are marked ambiguous; only times of day are handled (not full dates).
- PDF export is done through the print-friendly HTML (browser → Print → Save as PDF), not a built-in PDF writer.
- English text only. Fictional/educational use only. Not legal or forensic software.

## Future improvements
Multi-day timelines, file/image evidence, a relationship graph, a built-in PDF writer, user accounts, multi-language support.

## Academic conclusion
DetectIQ shows that a useful AI agent is more than one model call: it combines planning, real tools, validation,
fallbacks and transparency, and it keeps a human in charge by labelling facts, analysis, inference and unknowns.
