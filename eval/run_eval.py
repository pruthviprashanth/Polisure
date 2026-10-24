"""Evaluation harness.

  python eval/run_eval.py --engine-only               # no LLM, always safe
  python eval/run_eval.py --e2e [--split dev|test|all] [--limit N] [--baseline] [--cross]

End-to-end and baseline runs are paced (via the shared LLM client), sequential, resumable
(eval/results/*.json) and cached: re-running makes zero API calls for finished scenarios.
Writes eval/report.json (+ eval/report.md). Scenarios are authored by the team.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "eval"))

from pydantic import BaseModel  # noqa: E402

from app import claims, config, engine, extraction, facts as factsmod, llm, store  # noqa: E402
from app.schemas import Bill, Category, ClaimFacts  # noqa: E402
import gold  # noqa: E402
import metrics  # noqa: E402

RESULTS = ROOT / "eval" / "results"
DEFAULT_PROFILE = {"insured_age": 45, "sum_insured": 500000}


def load_scenarios(split: str) -> tuple[list[dict], bool]:
    real = ROOT / "data" / "scenarios.csv"
    path, sample = (real, False) if real.exists() else (ROOT / "data" / "scenarios.sample.csv", True)
    with open(path, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    if split != "all":
        rows = [r for r in rows if (r.get("split") or "dev") == split]
    return rows, sample


def num(x):
    try:
        return float(str(x).replace(",", "")) if str(x).strip() != "" else None
    except ValueError:
        return None


def ped_of(x):
    return {"y": True, "yes": True, "true": True, "n": False, "no": False, "false": False}.get(str(x).strip().lower())


def profile_of(r: dict) -> dict:
    return {"insured_age": int(num(r.get("insured_age")) or DEFAULT_PROFILE["insured_age"]),
            "sum_insured": num(r.get("sum_insured")) or DEFAULT_PROFILE["sum_insured"],
            "ped": ped_of(r.get("ped")), "policy_age_months": int(num(r.get("policy_age_months")) or 0),
            "preferred_room_rent_per_day": num(r.get("room_rent_per_day"))}


def bill_of(r: dict) -> dict:
    return {"room": num(r.get("bill_room")) or 0, "linked": num(r.get("bill_linked")) or 0,
            "meds_implants": num(r.get("bill_meds_implants")) or 0, "other": num(r.get("bill_other")) or 0}


def row_result(r: dict, verdict: str, payout, citations: list[dict]) -> dict:
    exp_p = num(r.get("expected_payout_inr"))
    return {"id": r["id"], "expected_verdict": r["expected_verdict"], "expected_payout": exp_p,
            "should_abstain": str(r.get("should_abstain", "0")).strip() in ("1", "true", "True", "yes"),
            "pred_verdict": verdict, "pred_payout": payout,
            "cited": [c["clause"] for c in citations],
            "expected_clauses": [c.strip() for c in str(r.get("expected_clauses") or "").split(";") if c.strip() and c.strip() != "—"],
            "quotes_total": len(citations), "quotes_verified": sum(1 for c in citations if c.get("verified"))}


# ------------------------------------------------------------------ engine-only
def run_engine_only(cov, rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        cat = r.get("category") or factsmod.mock_facts("", r["incident_text"])["category"]
        p = profile_of(r)
        f = ClaimFacts(category=Category(cat), insured_age=p["insured_age"], sum_insured=p["sum_insured"],
                       policy_age_months=p["policy_age_months"], ped=p["ped"], days=int(num(r.get("days")) or 0) or None,
                       room_rent_per_day=num(r.get("room_rent_per_day")), is_accident=cat == "accident_trauma",
                       bill=Bill(**bill_of(r)), confidence=1.0)
        res = engine.run(cov, f)
        out.append(row_result(r, res.verdict, res.payout, [c.model_dump() for c in res.citations]))
    return out


# ------------------------------------------------------------------ end-to-end
def _rhash(r: dict, pid: str, kind: str) -> str:
    return hashlib.sha256(json.dumps([r, pid, kind, llm.PROMPT_VERSION], sort_keys=True).encode()).hexdigest()[:16]


def _cached_result(kind: str, r: dict, pid: str, compute):
    RESULTS.mkdir(parents=True, exist_ok=True)
    p = RESULTS / f"{kind}_{r['id']}_{_rhash(r, pid, kind)}.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8")), True
    res = compute()
    p.write_text(json.dumps(res), encoding="utf-8")
    return res, False


def run_e2e(pid: str, rows: list[dict]) -> tuple[list[dict], int]:
    claims.USE_LLM_EXPLAIN = False
    out, fresh = [], 0

    def one(r):
        resp = claims.check([pid], profile_of(r), r["incident_text"], bill_of(r), {}, store.load)
        if resp["status"] == "needs_info":
            return {"verdict": "NEEDS_REVIEW", "payout": None, "citations": [], "asked": [q["field"] for q in resp["questions"]]}
        v = resp["verdict"]
        return {"verdict": v["verdict"], "payout": v["payout"], "citations": v["citations"]}

    for r in rows:
        try:
            res, hit = _cached_result("e2e", r, pid, lambda: one(r))
        except llm.LLMUnavailable as e:
            print(f"[eval] LLM unavailable at {r['id']}: {e}; stopping (re-run to resume)")
            break
        fresh += 0 if hit else 1
        out.append(row_result(r, res["verdict"], res["payout"], res["citations"]))
        print(f"[eval] e2e {r['id']}: {res['verdict']} {res['payout']} (expected {r['expected_verdict']} {r.get('expected_payout_inr')})")
    return out, fresh


# ------------------------------------------------------------------ baseline
class BaselineOut(BaseModel):
    verdict: str
    payout_inr: float | None = None
    reason: str = ""


BASE_SYS = ("You are a health-insurance claims assessor. Given the policy text, the policyholder profile and the claim, decide the "
            "likely insurer decision. verdict is one of COVERED, PARTIAL, NOT_COVERED, NEEDS_REVIEW (use NEEDS_REVIEW if the "
            "information is insufficient). payout_inr is the amount the insurer would pay in rupees (null for NEEDS_REVIEW).")


def run_baseline(pid: str, rows: list[dict]) -> tuple[list[dict], int]:
    cov = store.load(pid)
    pages = extraction.read_pages((config.ROOT / cov.pdf_path).read_bytes())
    policy_text = extraction.pages_text(pages)
    out, fresh = [], 0

    def one(r):
        user = (f"POLICY TEXT:\n{policy_text}\n\nPROFILE: {json.dumps(profile_of(r))}\n\nINCIDENT: {r['incident_text']}\n"
                f"ITEMISED BILL (rupees): {json.dumps(bill_of(r))}\nRoom rent per day: {r.get('room_rent_per_day')}, days: {r.get('days')}")
        o, _ = llm.extract(BaselineOut, BASE_SYS, user, can_fallback=False, purpose="baseline", max_out=600)
        v = o.verdict if o.verdict in metrics.VERDICTS else "NEEDS_REVIEW"
        return {"verdict": v, "payout": None if o.payout_inr is None else round(o.payout_inr), "citations": []}

    for r in rows:
        try:
            res, hit = _cached_result("baseline", r, pid, lambda: one(r))
        except llm.LLMUnavailable as e:
            print(f"[eval] baseline unavailable at {r['id']}: {e}; stopping (re-run to resume)")
            break
        fresh += 0 if hit else 1
        out.append(row_result(r, res["verdict"], res["payout"], []))
        print(f"[eval] baseline {r['id']}: {res['verdict']} {res['payout']}")
    return out, fresh


# ------------------------------------------------------------------ report
def write_report(report: dict) -> None:
    (ROOT / "eval" / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    m = report["metrics"]
    md = [f"# PoliSure evaluation report", f"Generated {report['generated_at']} — policy: {report['policy']} — "
          f"{report['n_scenarios']} scenarios, split `{report['split']}`, mode `{report['mode']}`", "",
          f"> {report['scenarios_note']}", "", "## Pipeline metrics", "| metric | value |", "|---|---|"]
    md += [f"| {k} | {v} |" for k, v in m.items()]
    if report.get("baseline"):
        md += ["", "## Plain-LLM baseline (same scenarios)", "| metric | value |", "|---|---|"]
        md += [f"| {k} | {v} |" for k, v in report["baseline"].items()]
    if report.get("cross_policy_extraction"):
        md += ["", "## Cross-policy extraction"] + [f"- {c['policy']}: {c['extraction_accuracy']} ({c.get('note', '')})" for c in report["cross_policy_extraction"]]
    md += ["", "## Confusion (expected → predicted)", "```", json.dumps(report["confusion"], indent=1), "```"]
    (ROOT / "eval" / "report.md").write_text("\n".join(md), encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-only", action="store_true")
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--cross", action="store_true", help="cross-policy extraction test on data/policy_b.pdf (cached model only)")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    if not (a.engine_only or a.e2e or a.baseline or a.cross):
        a.engine_only = True

    rows, sample = load_scenarios(a.split)
    if a.limit:
        rows = rows[:a.limit]
    pid = extraction.pdf_id((ROOT / "data" / "policy.pdf").read_bytes())
    cov = store.load(pid)
    if cov is None:
        sys.exit("policy.pdf has no cached coverage model; run the backend ingest first.")

    mode_label = "engine-only"
    pipeline_rows = run_engine_only(cov, rows)
    fresh = 0
    if a.e2e:
        mode_label = "end-to-end"
        pipeline_rows, fresh = run_e2e(pid, rows)
        if config.llm_mode() == "mock":
            mode_label = "end-to-end (MOCK LLM - plumbing only)"
    if not pipeline_rows:
        sys.exit("no results")
    m, conf = metrics.compute(pipeline_rows)
    ex = gold.score(cov, "A", ROOT / "data" / "gold_coverage.json")
    m["extraction_accuracy"] = ex["accuracy"]

    base = None
    if a.baseline:
        brows, bfresh = run_baseline(pid, rows)
        fresh += bfresh
        if brows:
            bm, _ = metrics.compute(brows)
            base = {"verdict_accuracy": bm["verdict_accuracy"], "payout_mae_inr": bm["payout_mae_inr"],
                    "abstention_recall": bm["abstention_recall"], "n_scored": len(brows),
                    "note": "plain LLM (policy text + incident -> JSON), same scenarios"}
    cross = []
    if a.cross:
        pb = extraction.pdf_id((ROOT / "data" / "policy_b.pdf").read_bytes())
        covb = store.load(pb)
        if covb:
            sb = gold.score(covb, "B", ROOT / "data" / "gold_coverage_b.json")
            cross.append({"policy": "SBI General Health Insurance - Retail (data/policy_b.pdf)", "extraction_accuracy": sb["accuracy"],
                          "n_checks": sb["n_checks"], "note": sb["gold_source"], "failures": sb["failures"]})

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": mode_label,
        "models": {"gemini": config.env("GEMINI_MODEL"), "groq": config.env("GROQ_MODEL")},
        "policy": "United India IHIP prospectus", "n_scenarios": len(pipeline_rows), "split": a.split,
        "scenarios_note": ("PLUMBING-ONLY SAMPLE scenarios (data/scenarios.sample.csv) - NOT real labels; metrics below are not evidence of accuracy."
                           if sample else "Authored by the team; drafted with AI assistance and verified against the policy."),
        "metrics": m, "confusion": conf, "baseline": base, "cross_policy_extraction": cross,
        "extraction_failures": ex["failures"],
        "notes": ["citation_correctness compares clause ids loosely (last segments, alphanumerics)",
                  "confident_wrong_rate = wrong or off-by->1% predictions among non-abstained predictions",
                  "end-to-end: a needs_info response counts as a NEEDS_REVIEW (abstention) prediction"],
        "live_calls_this_run": fresh,
    }
    write_report(report)
    print(json.dumps(report["metrics"], indent=1))
    print(f"fresh scenario computations this run: {fresh}; total live calls today: {llm.total_live_calls()}")


if __name__ == "__main__":
    main()
