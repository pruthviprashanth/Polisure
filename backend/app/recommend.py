"""POST /policies/recommend — rank policies for a NEW purchase by simulating likely claims through the engine.

Everything here is computed by code (engine + a transparent rubric). No LLM call is made.
"""
from __future__ import annotations

from typing import Optional

from . import engine, store
from .present import inr
from .schemas import Bill, Category, ClaimFacts, CoverageModel, RoomRentRule

DEFAULT_RENT = 3000.0
# Illustrative defaults: (hospital days, linked charges, medicines & implants) in rupees.
DEFAULT_BILLS = {
    "appendectomy": (3, 85000, 30000), "cataract": (1, 40000, 10000), "hernia": (2, 70000, 20000),
    "joint_replacement": (5, 250000, 250000), "maternity": (3, 70000, 15000), "cosmetic": (1, 60000, 5000),
    "dental": (1, 30000, 5000), "infertility": (1, 120000, 30000), "accident_trauma": (4, 150000, 50000),
    "other": (3, 80000, 20000),
}
TERMS_RUBRIC = [
    "50 pts: share of your likely claims that are NOT blocked by a waiting period or exclusion at your claim timing",
    "20 pts: shorter waiting periods (longest PED / specified-illness wait, capped at 48 months)",
    "20 pts: lower co-payment (conditional co-payments count half)",
    "10 pts: fewer listed exclusions (capped at 30)",
    "Payouts are NOT simulated for these policies (their room-rent or other limits cannot be computed from the wording), so this is a terms-only comparison",
]
RUBRIC = [
    "70 pts: simulated payout ÷ billed, summed over the claims you listed (each run at your chosen claim timing after buying, so waiting periods apply)",
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
              policy_ids: Optional[list[str]], claim_after_months: int = 1) -> dict:
    si = float(profile.get("sum_insured") or 500000)
    age = profile.get("insured_age")
    rent = float(profile.get("preferred_room_rent_per_day") or DEFAULT_RENT)
    ped = profile.get("ped")
    assumed_bills = {k: float(v) for k, v in (assumed_bills or {}).items() if v is not None}
    annual_premiums = annual_premiums or {}
    claims_list = [c for c in dict.fromkeys(likely_claims or [])] or ["appendectomy", "cataract", "hernia"]
    pols = [store.load(p) for p in policy_ids] if policy_ids else [m for m in store.list_all() if store.is_catalog(m)]
    pols = [p for p in pols if p is not None]

    assumptions = [
        f"Each claim is simulated as if made {claim_after_months} month(s) after buying the policy, so waiting periods longer than that apply"
        + (" (the initial 30-day wait has passed)" if claim_after_months >= 1 else " (inside the initial waiting period)"),
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

    ranked_ok, ranked_bad, ranked_terms = [], [], []
    for cov in pols:
        plan = engine.derive_plan(cov, age)
        item = {"policy_id": cov.policy_id, "name": cov.name, "computable": cov.computable, "score": None,
                "scenario_results": [], "reasons": [], "premium_note": None, "eligible": True, "ineligible_reason": None,
                "terms_score": None}
        if cov.plans and age is not None and plan is None:
            lo, hi = min(b.min_age for b in cov.plans), max(b.max_age for b in cov.plans)
            reason = f"Not available at age {age}: this policy's entry ages are {lo}-{hi}."
            item.update(eligible=False, ineligible_reason=reason,
                        reasons=[{"text": reason, "clause": "—", "page": None, "quote": "", "verified": False}])
            ranked_bad.append(item)
            continue
        if not cov.computable:
            _terms_only(item, cov, plan, claims_list, assumed_bills, age, si, rent, ped, claim_after_months)
            ranked_terms.append(item)
            continue
        tot_bill = tot_pay = 0.0
        for name in claims_list:
            cat, _ = _cat(name)
            bill, days, billed = _bill_for(cat, assumed_bills.get(name), rent)
            f = ClaimFacts(category=cat, insured_age=age, sum_insured=si, policy_age_months=claim_after_months,
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
    ranked_terms.sort(key=lambda x: (-(x["terms_score"] or 0), x["name"]))
    ranked_bad.sort(key=lambda x: x["name"])  # ineligible by age, last
    best_terms = ranked_terms[0]["policy_id"] if ranked_terms else None
    return {"ranked": ranked_ok + ranked_terms + ranked_bad, "best_terms_policy_id": best_terms,
            "terms_rubric": TERMS_RUBRIC, "best_policy_id": best["policy_id"] if best else None, "why": why,
            "assumptions": assumptions, "score_rubric": RUBRIC, "disclaimer": DISCLAIMER,
            "meta": {"cached": True, "providers_used": ["cache"], "model_note": None}}


TYPICAL = ["appendectomy", "cataract", "hernia", "joint_replacement", "maternity"]


def typical_claims(cov: CoverageModel, age: Optional[int], si: Optional[float], ped: Optional[bool],
                   rent: Optional[float], policy_age_months: int) -> list[dict]:
    """What a few typical claims would pay on this policy for this profile (illustrative bill sizes)."""
    if not cov.computable or not si:
        return []
    out = []
    for name in TYPICAL:
        cat = Category(name)
        bill, days, billed = _bill_for(cat, None, rent or DEFAULT_RENT)
        f = ClaimFacts(category=cat, insured_age=age, sum_insured=si, policy_age_months=policy_age_months,
                       ped=bool(ped) if ped is not None else False, days=days, room_rent_per_day=rent or DEFAULT_RENT,
                       bill=bill, confidence=1.0)
        res = engine.run(cov, f)
        out.append({"category": name, "billed": int(round(billed)), "payout": res.payout or 0, "verdict": res.verdict})
    return out


def _terms_only(item: dict, cov: CoverageModel, plan: Optional[str], claims_list: list[str], assumed_bills: dict,
                age: Optional[int], si: float, rent: float, ped: Optional[bool], months: int = 1) -> None:
    """Compare a policy whose payouts cannot be computed on the rules we can read: waiting periods, exclusions, co-pay."""
    # Run only the gates (waiting periods / exclusions): neutralise the parts of the structure that block a payout.
    probe = cov.model_copy(deep=True)
    probe.computable, probe.computable_note, probe.unmodeled_terms = True, None, []
    probe.room_rent = RoomRentRule(kind="any", clause=(cov.room_rent.clause if cov.room_rent else ""), page=(cov.room_rent.page if cov.room_rent else 0),
                                   quote=(cov.room_rent.quote if cov.room_rent else ""), verified=True)
    blocked = 0
    for name in claims_list:
        cat, _ = _cat(name)
        bill, days, billed = _bill_for(cat, assumed_bills.get(name), rent)
        f = ClaimFacts(category=cat, insured_age=age, sum_insured=si, policy_age_months=months, ped=bool(ped) if ped is not None else False,
                       days=days, room_rent_per_day=rent, is_accident=cat == Category.accident_trauma, bill=bill, confidence=1.0)
        res = engine.run(probe, f)
        row = {"category": name, "billed": int(round(billed)), "payout": None}
        if res.verdict == "NOT_COVERED":
            blocked += 1
            row.update(verdict="NOT_COVERED", note=(res.trace[0].label if res.trace else "excluded"))
        else:
            row.update(verdict="NEEDS_REVIEW", note="Not blocked by waiting periods or exclusions; payout not computed for this policy")
        item["scenario_results"].append(row)
    n = max(len(claims_list), 1)
    wait = 20 * (1 - min(_wait_months(cov, plan), 48) / 48)
    cp = cov.copay
    cpay = 20.0
    if cp and cp.percent > 0:
        pct = min(cp.percent, 30) / (2 if cp.applies_when != "always" else 1)
        cpay = 20 * (1 - pct / 30)
    excl = 10 * (1 - min(len(cov.exclusions), 30) / 30)
    claims_pts = 50 * (1 - blocked / n)
    item["terms_score"] = round(claims_pts + wait + cpay + excl)
    item["terms_breakdown"] = {"claims_not_blocked": round(claims_pts, 1), "waiting": round(wait, 1), "copay": round(cpay, 1), "exclusions": round(excl, 1)}
    c = cov.room_rent
    item["reasons"] = [{"text": "Payouts cannot be computed exactly for this policy: " + (cov.computable_note or ""),
                        "clause": c.clause if c else "—", "page": (c.page or None) if c else None,
                        "quote": c.quote if c else "", "verified": bool(c and c.verified)}]
    if cp and cp.percent > 0:
        item["reasons"].append({"text": f"{cp.percent:g}% co-payment" + (f" ({cp.condition})" if cp.condition else ""), "clause": cp.clause or "—",
                                "page": cp.page or None, "quote": cp.quote, "verified": bool(cp.verified)})
    for r_ in item["scenario_results"]:
        if r_["verdict"] == "NOT_COVERED":
            w = next((w for w in cov.specific_waits if w.category.value == r_["category"]), None) or cov.waiting_initial or cov.waiting_ped
            item["reasons"].append({"text": f"{r_['category'].replace('_', ' ').title()}: {r_['note']}", "clause": w.clause if w else "—",
                                    "page": (w.page or None) if w else None, "quote": w.quote if w else "", "verified": bool(w and w.verified)})
    item["reasons"] = item["reasons"][:5]
