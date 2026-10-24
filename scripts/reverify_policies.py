"""Re-apply the deterministic guards to every cached policy model, with NO LLM calls.

For each data/cache/policies/<id>.json: run extraction.clean (guards on LLM output), re-verify every quote against
the PDF page text, recompute the computable flag, apply the friendly sample/library name, and save.
Use after changing the verifier or the guards.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config, extraction, store  # noqa: E402


def main() -> None:
    for m in store.list_all():
        pdf = store.pdf_file(m)
        if pdf is None:
            print(f"SKIP {m.policy_id} {m.name!r}: PDF not found")
            continue
        before = (m.computable, sum(c.verified for c in extraction.iter_cites(m)))
        pages = extraction.read_pages(pdf.read_bytes())
        extraction.clean(m)
        extraction.verify(m, pages)
        extraction.set_computable(m)
        fname = Path(m.pdf_path).name
        if Path(m.pdf_path).parent in (Path("data"), Path("data/library")) and fname in store.SAMPLE_NAMES:
            m.name = store.SAMPLE_NAMES[fname]
        store.save(m)
        after = (m.computable, sum(c.verified for c in extraction.iter_cites(m)))
        print(f"{m.policy_id} {m.name[:48]:48s} computable {before[0]}->{after[0]}  verified quotes {before[1]}->{after[1]}")


if __name__ == "__main__":
    main()
