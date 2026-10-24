import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile

os.environ["LLM_MODE"] = "mock"
os.environ["POLISURE_CACHE"] = tempfile.mkdtemp(prefix="polisure_test_cache_")
