"""Verify FastAPI app.openapi() matches the committed openapi.json snapshot (C1)."""
import json
import os

from app.main import app

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SNAPSHOT_PATH = os.path.join(PROJECT_ROOT, "frontend", "src", "api", "openapi.json")


def test_openapi_matches_committed_snapshot():
    assert os.path.exists(SNAPSHOT_PATH), f"OpenAPI snapshot not found at {SNAPSHOT_PATH}"

    with open(SNAPSHOT_PATH, "r", encoding="utf-8") as f:
        committed_schema = json.load(f)

    # Serialize and re-parse app.openapi() to normalize json types
    current_schema = json.loads(json.dumps(app.openapi()))

    assert current_schema == committed_schema, (
        "OpenAPI schema has drifted from frontend/src/api/openapi.json snapshot. "
        "Run `python scripts/export_openapi.py` to regenerate."
    )
