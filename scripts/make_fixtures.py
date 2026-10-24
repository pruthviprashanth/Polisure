"""Write mock-mode fixtures from the hand-built sample model (no network)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config  # noqa: E402
from app.samples import united_india_extract  # noqa: E402

(config.FIXTURES / "coverage.json").write_text(united_india_extract().model_dump_json(indent=1), encoding="utf-8")
print("wrote", config.FIXTURES / "coverage.json")
