"""Gold checks for coverage-extraction accuracy.

If data/gold_coverage.json exists it is used (format: {"checks": [{"name": str, "path": "room_rent.value", "equals": 1}]}).
Otherwise the built-in checks below are used; they encode facts stated in the task brief and verified by the team against
the policy text (policy A = United India prospectus, policy B = SBI General retail wording).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POLICY_A = [
    ("room_rent.kind", "room_rent.kind", "percent_si"), ("room_rent.value", "room_rent.value", 1),
    ("icu_rent", "room_rent.icu_value", 2), ("proportionate.applies", "proportionate.applies", True),
    ("copay.percent", "copay.percent", 0), ("waiting_initial.days", "waiting_initial.days", 30),
    ("waiting_ped.months", "waiting_ped.months", 48),
    ("cataract wait 24", "specific:cataract", 24), ("hernia wait 24", "specific:hernia", 24),
    ("joint replacement wait 48", "specific:joint_replacement", 48),
    ("cataract sublimit pct", "sublimit:cataract.pct_si", 25), ("cataract sublimit inr", "sublimit:cataract.limit_inr", 40000),
    ("cataract per eye", "sublimit:cataract.per", "eye"),
    ("hernia sublimit pct", "sublimit:hernia.pct_si", 25), ("hernia sublimit inr", "sublimit:hernia.limit_inr", 100000),
    ("waiting applies Gold", "waiting_plans.has:Gold", True), ("waiting not Platinum", "waiting_plans.has:Platinum", False),
    ("maternity excluded", "exclusion:maternity", True), ("cosmetic excluded", "exclusion:cosmetic", True),
    ("computable", "computable", True),
]
POLICY_B = [
    ("room_rent.kind", "room_rent.kind", "percent_si"), ("room_rent.value", "room_rent.value", 1),
    ("icu_rent", "room_rent.icu_value", 2), ("copay.percent", "copay.percent", 10),
    ("copay non-network only", "copay.applies_when", "non_network"),
    ("waiting_initial.days", "waiting_initial.days", 30), ("waiting_ped.months", "waiting_ped.months", 48),
    ("cataract sublimit pct", "sublimit:cataract.pct_si", 15), ("cataract sublimit inr", "sublimit:cataract.limit_inr", 25000),
    ("cataract per eye", "sublimit:cataract.per", "eye"),
    ("flagged not computable", "computable", False),
]


def _get(model, path: str) -> Any:
    if path.startswith("specific:"):
        for w in model.specific_waits:
            if w.category.value == path.split(":")[1]:
                return w.months
        return None
    if path.startswith("sublimit:"):
        cat, attr = path.split(":")[1].split(".")
        for s in model.sublimits:
            if s.category.value == cat:
                return getattr(s, attr)
        return None
    if path.startswith("exclusion:"):
        return any(e.category.value == path.split(":")[1] for e in model.exclusions)
    if path.startswith("waiting_plans.has:"):
        return path.split(":")[1] in model.waiting_plans
    obj: Any = model
    for part in path.split("."):
        obj = getattr(obj, part, None) if obj is not None else None
    return obj


def score(model, which: str, gold_file: Path | None = None) -> dict:
    if gold_file and gold_file.exists():
        checks = [(c["name"], c["path"], c["equals"]) for c in json.loads(gold_file.read_text(encoding="utf-8"))["checks"]]
        source = "data/gold_coverage.json"
    else:
        checks = POLICY_A if which == "A" else POLICY_B
        source = "built-in checks from facts stated in the task brief"
    results = []
    for name, path, expect in checks:
        got = _get(model, path)
        ok = (got == expect) or (isinstance(expect, (int, float)) and isinstance(got, (int, float)) and not isinstance(got, bool)
                                 and float(got) == float(expect))
        results.append({"check": name, "expected": expect, "got": got, "ok": bool(ok)})
    return {"accuracy": round(sum(r["ok"] for r in results) / len(results), 4), "n_checks": len(results),
            "gold_source": source, "failures": [r for r in results if not r["ok"]]}
