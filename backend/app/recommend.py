"""POST /policies/recommend — rank policies for a NEW purchase by simulating likely claims through the engine.

Everything here is computed by code (engine + a transparent rubric). No LLM call is made.
"""
from __future__ import annotations

from typing import Optional

from . import engine, store
from .present import inr
from .schemas import Bill, Category, ClaimFacts, CoverageModel

DEFAULT_RENT = 3000.0
# Illustrative defaults: (hospital days, linked charges, medicines & implants) in rupees.
DEFAULT_BILLS = {
    "appendectomy": (3, 85000, 30000), "cataract": (1, 40000, 10000), "hernia": (2, 70000, 20000),
    "joint_replacement": (5, 250000, 250000), "maternity": (3, 70000, 15000), "cosmetic": (1, 60000, 5000),
    "dental": (1, 30000, 5000), "infertility": (1, 120000, 30000), "accident_trauma": (4, 150000, 50000),
    "other": (3, 80000, 20000),
}
RUBRIC = [
    "70 pts: simulated payout ÷ billed, summed over the claims you listed (each run as a NEW policy, so waiting periods apply)",
    "10 pts: shorter waiting periods (longest of PED / specified-illness waits that apply to your plan, capped at 48 months)",
    "10 pts: lower co-payment (conditional co-payments count half)",
    "5 pts: room-rent cap vs your preferred room (full marks if the room is within the cap)",
    "5 pts: fewer listed exclusions (capped at 30)",
]
DISCLAIMER = ("This compares coverage terms for the claims you listed. It is not financial advice and does not consider premiums "
              "unless you entered them.")


def _cat(name: str) -> tuple[Category, bool]:
    try:
        return Category(name), True
    except ValueError:
        return Category.other, False


def _bill_for(cat: Category, total: Optional[float], rent: float) -> tuple[Bill, int, float]:
    days, linked, meds = DEFAULT_BILLS.get(cat.value, DEFAULT_BILLS["other"])
    if total is None:
        room = rent * days
        return Bill(room=room, linked=linked, meds_implants=meds), days, room + linked + meds
    room = min(rent * days, total)
    rest = max(total - room, 0)
    return Bill(room=room, linked=rest * 0.75, meds_implants=rest * 0.25), days, total


def _wait_months(cov: CoverageModel, plan: Optional[str]) -> int:
    if cov.waiting_plans and plan not in cov.waiting_plans:
        return 0
    ms = [w.months for w in cov.specific_waits] + ([cov.waiting_ped.months] if cov.waiting_ped else [])
    return max(ms, default=0)


def _score(cov: CoverageModel, plan: Optional[str], ratio: float, si: float, rent: float) -> tuple[int, dict]:
    pay = 70 * ratio
    wait = 10 * (1 - min(_wait_months(cov, plan), 48) / 48)
    cp = cov.copay
    cpay = 10.0
    if cp and cp.percent > 0:
        pct = min(cp.percent, 30) / (2 if cp.applies_when != "always" else 1)
        cpay = 10 * (1 - pct / 30)
    cap_pts = 5.0
    rr = cov.room_rent
    if rr and rr.kind in ("percent_si", "fixed"):
        cap = si * rr.value / 100 if rr.kind == "percent_si" else rr.value
        if rent > cap > 0:
            cap_pts = 5 * cap / rent
    excl = 5 * (1 - min(len(cov.exclusions), 30) / 30)
    parts = {"payout": round(pay, 1), "waiting": round(wait, 1), "copay": round(cpay, 1), "room_cap": round(cap_pts, 1), "exclusions": round(excl, 1)}
    return round(sum(parts.values())), parts


def _reasons(cov: CoverageModel, plan: Optional[str], results: list[dict], si: float, rent: float) -> list[dict]:
    out = []

    def add(text, c):
        out.append({"text": text, "clause": c.clause if c else "—", "page": (c.page or None) if c else None,
                    "quote": c.quote if c else "", "verified": bool(c and c.verified)})

    rr, pr = cov.room_rent, cov.proportionate
    if rr and rr.kind in ("percent_si", "fixed"):
        cap = si * rr.value / 100 if rr.kind == "percent_si" else rr.value
        txt = f"Room cap is {inr(cap)}/day ({rr.value:g}% of your sum insured)" if rr.kind == "percent_si" else f"Room cap is {inr(cap)}/day"
        if pr and pr.applies:
            txt += " with proportionate payment on associated charges" + (f" — your preferred room ({inr(rent)}/day) exceeds it" if rent > cap else "")
        add(txt, pr if (pr and pr.applies and rent > cap) else rr)
    if cov.waiting_plans and plan not in cov.waiting_plans:
        add(f"Waiting periods do not apply to the {plan} plan", cov.waiting_ped or cov.waiting_initial)
    else:
        blocked = [r for r in results if r["verdict"] == "NOT_COVERED" and r.get("note")]
        for r in blocked[:2]:
            c = next((w for w in cov.specific_waits if w.category.value == r["category"]), None) or cov.waiting_ped or cov.waiting_initial
            add(f"{r['category'].replace('_', ' ').title()}: {r['note']}", c)
    if cov.copay and cov.copay.percent > 0:
        add(f"{cov.copay.percent:g}% co-payment" + (f" ({cov.copay.condition})" if cov.copay.condition else ""), cov.copay)
    elif cov.copay:
        add("No co-payment", cov.copay)
    return out[:5]


def recommend(profile: dict, likely_claims: list[str], assumed_bills: Optional[dict], annual_premiums: Optional[dict],
              policy_ids: Optional[list[str]]) -> dict:
    si = float(profile.get("sum_insured") or 500000)
    age = profile.get("insured_age")
    rent = float(profile.get("preferred_room_rent_per_day") or DEFAULT_RENT)
    ped = profile.get("ped")
    assumed_bills = {k: float(v) for k, v in (assumed_bills or {}).items() if v is not None}
    annual_premiums = annual_premiums or {}
    claims_list = [c for c in dict.fromkeys(likely_claims or [])] or ["appendectomy", "cataract", "hernia"]
    pols = [store.load(p) for p in policy_ids] if policy_ids else store.list_all()
    pols = [p for p in pols if p is not None]

    assumptions = [
        "Each claim is simulated as if the policy were newly bought (policy age 0 months), so waiting periods apply",
        f"Insured age {age if age is not None else 'unknown'}, sum insured {inr(si)}, preferred room {inr(rent)}/day"
        + ("" if profile.get("preferred_room_rent_per_day") else " (default assumed)"),
        "Premiums were not read from the policy documents" + ("; only the premiums you entered are used" if annual_premiums else ""),
    ]
    if ped is None:
        assumptions.append("No pre-existing condition was assumed (profile did not say)")
    unlisted = [c for c in claims_list if not _cat(c)[1]]
    if unlisted:
        assumptions.append("Unrecognised claim types treated as a general illness: " + ", ".join(unlisted))
    defaults = [c for c in claims_list if c not in assumed_bills]
    if defaults:
        assumptions.append("Bill sizes are illustrative for: " + ", ".join(defaults) + " (override with assumed_bills)")

    ranked_ok, ranked_bad = [], []
    for cov in pols:
        plan = engine.derive_plan(cov, age)
        item = {"policy_id": cov.policy_id, "name": cov.name, "computable": cov.computable, "score": None,
                "scenario_results": [], "reasons": [], "premium_note": None}
        if not cov.computable:
            c = cov.room_rent
            item["reasons"] = [{"text": "Payouts cannot be computed exactly for this policy: " + (cov.computable_note or ""),
                                "clause": c.clause if c else "—", "page": (c.page or None) if c else None,
                                "quote": c.quote if c else "", "verified": bool(c and c.verified)}]
            ranked_bad.append(item)
            continue
        tot_bill = tot_pay = 0.0
        for name in claims_list:
            cat, _ = _cat(name)
            bill, days, billed = _bill_for(cat, assumed_bills.get(name), rent)
            f = ClaimFacts(category=cat, insured_age=age, sum_insured=si, policy_age_months=0,
                           ped=bool(ped) if ped is not None else False, days=days, room_rent_per_day=rent,
                           is_accident=cat == Category.accident_trauma, bill=bill, confidence=1.0)
            res = engine.run(cov, f)
            r = {"category": name, "billed": int(round(billed)), "payout": res.payout if res.payout is not None else 0,
                 "verdict": res.verdict}
            if res.blocked:
                r["note"] = {"waiting_initial": "initial waiting period applies to a new policy",
                             "ped": "pre-existing disease waiting period applies",
                             "specific": f"{res.blocked['months_needed']}-month waiting period for a new policy"}[res.blocked["kind"]]
            elif res.verdict == "NOT_COVERED":
                r["note"] = res.trace[0].label if res.trace else "excluded"
            elif res.verdict == "NEEDS_REVIEW":
                r["note"] = res.abstain_reason
            item["scenario_results"].append(r)
            tot_bill += billed
            tot_pay += r["payout"]
        ratio = tot_pay / tot_bill if tot_bill else 0
        item["score"], item["score_breakdown"] = _score(cov, plan, ratio, si, rent)
        item["total_simulated_payout"] = int(round(tot_pay))
        item["reasons"] = _reasons(cov, plan, item["scenario_results"], si, rent)
        prem = annual_premiums.get(cov.policy_id)
        if prem:
            item["premium_note"] = f"{inr(prem)}/yr → simulated payout across your likely claims per ₹ of premium: {tot_pay / float(prem):.2f}"
        ranked_ok.append(item)

    ranked_ok.sort(key=lambda x: (-x["score"], -x["total_simulated_payout"]))
    best = ranked_ok[0] if ranked_ok else None
    if best:
        tb = sum(r["billed"] for r in best["scenario_results"])
        why = (f"Highest score ({best['score']}/100): simulated payout {inr(best['total_simulated_payout'])} of {inr(tb)} billed "
               f"across the claims you listed, given waiting periods for a new policy.")
    else:
        why = "No computable policy was available to compare."
    return {"ranked": ranked_ok + ranked_bad, "best_policy_id": best["policy_id"] if best else None, "why": why,
            "assumptions": assumptions, "score_rubric": RUBRIC, "disclaimer": DISCLAIMER,
            "meta": {"cached": True, "providers_used": ["cache"], "model_note": None}}
