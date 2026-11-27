import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
import database  # noqa: E402
from services import ai_service  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    """Every test gets its own empty database, its own reports folder and NO real AI."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(config, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    ai_service.reset_circuit()
    database.init_db()
    yield
    ai_service.reset_circuit()


@pytest.fixture
def demo_case():
    from services import case_service
    return case_service.get_case(case_service.load_demo_case())
