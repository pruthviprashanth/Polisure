"""Paths and environment settings. Keys are read from the environment only and never logged."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CACHE = DATA / "cache"
LLM_CACHE_DIR = CACHE / "llm"
POLICY_DIR = CACHE / "policies"
PDF_DIR = CACHE / "pdfs"
FIXTURES = DATA / "fixtures"
LIBRARY = DATA / "library"

load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def llm_mode() -> str:
    return env("LLM_MODE", "live").lower()


def cache_enabled() -> bool:
    return env("LLM_CACHE", "on").lower() != "off"


for _d in (CACHE, LLM_CACHE_DIR, POLICY_DIR, PDF_DIR, FIXTURES):
    _d.mkdir(parents=True, exist_ok=True)
