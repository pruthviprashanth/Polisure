"""Ingest every PDF in data/library/ plus data/policy.pdf and data/policy_b.pdf.

Sequential and paced (all LLM calls go through the shared client); already-ingested PDFs are skipped, so the
script is resumable. Prints each policy's computable flag. Use --dry-run to list files only.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import config, llm, store  # noqa: E402


def main() -> None:
    files = [config.DATA / "policy.pdf", config.DATA / "policy_b.pdf"] + sorted(config.LIBRARY.glob("*.pdf"))
    files = [f for f in files if f.exists()]
    if "--dry-run" in sys.argv:
        print(*files, sep="\n")
        return
    for f in files:
        try:
            m, cached, _ = store.ingest(f.read_bytes(), source=f)
        except store.NotAPdf as e:
            print(f"SKIP {f.name}: {e}")
            continue
        except llm.LLMUnavailable as e:
            print(f"STOP at {f.name}: {e}\nRe-run to resume (finished policies are cached).")
            return
        print(f"{'cached' if cached else 'ingested'}: {f.name} -> {m.policy_id} {m.name!r} computable={m.computable}"
              + (f" ({m.computable_note[:90]})" if m.computable_note else ""))
    print(f"live calls today: {llm.total_live_calls()}")


if __name__ == "__main__":
    main()
