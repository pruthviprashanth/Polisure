"""Pure metric computation for the evaluation report (no I/O, no LLM)."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

VERDICTS = ["COVERED", "PARTIAL", "NOT_COVERED", "NEEDS_REVIEW"]


def clause_key(c: str) -> str:
    """Loose clause identity: lowercase alphanumerics of the last three dot/space segments."""
    parts = [p for p in re.split(r"[.\s()]+", c.lower()) if p]
    return "".join(re.sub(r"[^a-z0-9]", "", p) for p in parts[-3:])


def payout_ok(exp: Optional[float], pred: Optional[float]) -> bool:
    if exp is None or pred is None:
        return False
    return abs(exp - pred) <= max(1.0, 0.01 * abs(exp))


def compute(rows: list[dict]) -> dict:
    """rows: expected_verdict, expected_payout, should_abstain, pred_verdict, pred_payout,
    cited (list[str]), expected_clauses (list[str]), quotes_total, quotes_verified."""
    n = len(rows)
    if n == 0:
        return {}
    conf = defaultdict(lambda: defaultdict(int))
    correct = 0
    abs_err, abs_n, within = [], 0, 0
    exact_n = 0
    for r in rows:
        conf[r["expected_verdict"]][r["pred_verdict"]] += 1
        correct += r["expected_verdict"] == r["pred_verdict"]
        if r["expected_payout"] is not None:
            exact_n += 1
            if r["pred_payout"] is not None:
                abs_err.append(abs(r["expected_payout"] - r["pred_payout"]))
                within += payout_ok(r["expected_payout"], r["pred_payout"])
    pred_abs = [r for r in rows if r["pred_verdict"] == "NEEDS_REVIEW"]
    should = [r for r in rows if r["should_abstain"]]
    confident = [r for r in rows if r["pred_verdict"] != "NEEDS_REVIEW"]
    wrong = [r for r in confident if r["pred_verdict"] != r["expected_verdict"]
             or (r["expected_payout"] is not None and not payout_ok(r["expected_payout"], r["pred_payout"]))]
    cite_rows = [r for r in rows if r["expected_clauses"]]
    cite_ok = sum(1 for r in cite_rows if {clause_key(c) for c in r["cited"]} & {clause_key(c) for c in r["expected_clauses"]})
    qt = sum(r["quotes_total"] for r in rows)
    qv = sum(r["quotes_verified"] for r in rows)
    return {
        "verdict_accuracy": round(correct / n, 4),
        "payout_mae_inr": round(sum(abs_err) / len(abs_err), 1) if abs_err else None,
        "payout_within_1_pct": round(within / exact_n, 4) if exact_n else None,
        "citation_correctness": round(cite_ok / len(cite_rows), 4) if cite_rows else None,
        "quote_verified_pct": round(qv / qt, 4) if qt else None,
        "extraction_accuracy": None,
        "abstention_precision": round(sum(1 for r in pred_abs if r["should_abstain"]) / len(pred_abs), 4) if pred_abs else None,
        "abstention_recall": round(sum(1 for r in should if r["pred_verdict"] == "NEEDS_REVIEW") / len(should), 4) if should else None,
        "confident_wrong_rate": round(len(wrong) / len(confident), 4) if confident else None,
    }, {k: dict(v) for k, v in conf.items()}
