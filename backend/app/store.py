"""JSON-file policy store and ingestion (PDF bytes -> cached CoverageModel)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from . import config, extraction
from .schemas import CoverageModel


# Friendly names for the bundled sample PDFs (the LLM-read title is often generic, e.g. 'Health Insurance Policy Retail').
SAMPLE_NAMES = {"policy.pdf": "United India Individual Health Insurance Policy (sample)",
                "policy_b.pdf": "SBI General Health Insurance Policy - Retail (sample)",
                "sbi_arogya_premier.pdf": "SBI General Arogya Premier Policy",
                "sbi_arogya_sanjeevani.pdf": "SBI General Arogya Sanjeevani Policy",
                "sbi_arogya_plus.pdf": "SBI General Arogya Plus Policy",
                "super_health_insurance.pdf": "SBI General Super Health Insurance Policy",
                "star_health_assure.pdf": "Star Health Assure Insurance Policy",
                "new_india_mediclaim.pdf": "New India Mediclaim Policy"}


class NotAPdf(Exception):
    pass


def _path(policy_id: str) -> Path:
    return config.POLICY_DIR / f"{policy_id}.json"


def load(policy_id: str) -> Optional[CoverageModel]:
    p = _path(policy_id)
    if not policy_id.isalnum() or not p.exists():
        return None
    return CoverageModel.model_validate(json.loads(p.read_text(encoding="utf-8")))


def save(m: CoverageModel) -> None:
    _path(m.policy_id).write_text(m.model_dump_json(indent=1), encoding="utf-8")


def list_all() -> list[CoverageModel]:
    out = []
    for p in sorted(config.POLICY_DIR.glob("*.json")):
        try:
            out.append(CoverageModel.model_validate(json.loads(p.read_text(encoding="utf-8"))))
        except Exception:
            continue
    return out


def is_catalog(m: CoverageModel) -> bool:
    """Catalog = the bundled policies (data/policy*.pdf and data/library/*.pdf), as opposed to a user's own upload."""
    return m.pdf_path.startswith("data/") and not m.pdf_path.startswith("data/cache/")


def pdf_file(m: CoverageModel) -> Optional[Path]:
    if not m.pdf_path:
        return None
    p = (config.ROOT / m.pdf_path).resolve()
    if config.ROOT.resolve() not in p.parents or not p.exists():
        return None
    return p


def _rel(p: Path) -> str:
    return p.resolve().relative_to(config.ROOT.resolve()).as_posix()


def ingest(pdf_bytes: bytes, source: Optional[Path] = None, purpose: str = "coverage") -> tuple[CoverageModel, bool, list[str]]:
    """Returns (model, from_cache, providers_used). Raises NotAPdf / llm.LLMUnavailable."""
    if not pdf_bytes.startswith(b"%PDF"):
        raise NotAPdf("The uploaded file is not a PDF.")
    try:
        pages = extraction.read_pages(pdf_bytes)
    except Exception:
        raise NotAPdf("The PDF could not be opened.") from None
    if sum(len(p.strip()) for p in pages) < 200:
        raise NotAPdf("The PDF has no text layer (scanned PDFs are not supported).")
    pid = extraction.pdf_id(pdf_bytes)
    existing = load(pid)
    if existing is not None and not (existing.source_providers == ["mock"] and config.llm_mode() != "mock"):
        return existing, True, ["cache"]
    if source is not None:
        rel = _rel(source)
    else:
        dest = config.PDF_DIR / f"{pid}.pdf"
        dest.write_bytes(pdf_bytes)
        rel = _rel(dest)
    ext, provs = extraction.extract_coverage(pages, purpose=purpose)
    model = extraction.finalize(ext, pages, pid, rel, provs)
    if source is not None and source.parent in (config.DATA, config.LIBRARY) and source.name in SAMPLE_NAMES:
        model.name = SAMPLE_NAMES[source.name]
    save(model)
    return model, False, provs
