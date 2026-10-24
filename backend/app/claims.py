"""/claims/check orchestration: facts (once) -> engine per policy -> counterfactuals -> explanation -> comparison."""
from __future__ import annotations

from typing import Optional

from . import engine, explain, facts as factsmod, llm
from .present import inr
from .schemas import ClaimFacts, Counterfactual, CoverageModel, Profile, Verdict

CONF_MIN = 0.5
USE_LLM_EXPLAIN = True  # the eval harness turns this off to save live calls
COMBINED_NOTE = ("Indemnity policies can often be claimed together up to the actual loss; the second insurer pays against the "
                 "balance. Estimate only — confirm each insurer's other-insurance clause.")


class UnknownPolicy(Exception):
    pass


def meta(provs: list[str]) -> dict:
    provs = [p for p in dict.fromkeys(p for p in provs if p)]
    return {"cached": bool(provs) and all(p == "cache" for p in provs), "providers_used": provs or ["cache"], "model_note": None}


def _label_blocked(kind: str) -> str:
    return {"waiting_initial": "initial", "ped": "pre-existing disease", "specific": "specified-illness"}.get(kind, kind)


def counterfactuals(cov: CoverageModel, f: ClaimFacts, res: engine.EngineResult) -> list[Counterfactual]:
    if res.verdict == "NEEDS_REVIEW" or res.payout is None:
        return []
    base, out = res.payout, []

    def add(change: str, f2: ClaimFacts) -> None:
        r2 = engine.run(cov, f2, best_case=True)
        if r2.payout is not None and r2.verdict != "NEEDS_REVIEW" and r2.payout != base:
            out.append(Counterfactual(change=change, new_payout=r2.payout, delta=r2.payout - base))

    cap = res.room_cap_per_day
    if cap and f.room_rent_per_day and f.days and f.room_rent_per_day > cap:
        f2 = f.model_copy(deep=True, update={"room_rent_per_day": cap})
        f2.bill.room = cap * f.days
        add(f"Choose a room within {inr(cap)}/day", f2)
    if res.blocked:
        months = res.blocked["months_needed"]
        add(f"If the {_label_blocked(res.blocked['kind'])} waiting period were over ({months} months of cover)",
            f.model_copy(update={"policy_age_months": months}))
        if res.blocked["kind"] == "ped":
            add("If the condition were not pre-existing", f.model_copy(update={"ped": False}))
    return out


def _verdict_for(cov: CoverageModel, f: ClaimFacts, low_conf: bool) -> tuple[Verdict, engine.EngineResult]:
    f = f.model_copy(update={"plan": engine.derive_plan(cov, f.insured_age)})
    if low_conf:
        res = engine.EngineResult("NEEDS_REVIEW", 0, None, abstain_reason="The incident description was too unclear to read reliably.")
    else:
        res = engine.run(cov, f, best_case=True)
    v = Verdict(verdict=res.verdict, billed=res.billed, payout=res.payout, trace=res.trace, citations=res.citations,
                abstain_reason=res.abstain_reason, estimate_quality=res.quality, assumptions=res.assumptions)
    if v.verdict == "NEEDS_REVIEW" and not v.abstain_reason:
        v.abstain_reason = "The estimate could not be made reliably."
    v.counterfactuals = counterfactuals(cov, f, res)
    return v, res


def _questions(covs: list[CoverageModel], f: ClaimFacts) -> list[dict]:
    fields = list(f.missing)
    if f.policy_age_months is None:
        fields.append("policy_age_months")
    if f.ped is None and not f.is_accident:
        for c in covs:
            plan = engine.derive_plan(c, f.insured_age)
            if (c.computable or c.estimate_quality == "best_case") and c.waiting_ped and c.waiting_ped.months > (f.policy_age_months or 0) and \
                    (not c.waiting_plans or plan in c.waiting_plans):
                fields.append("ped")
                break
    if f.network_hospital is None and any((c.computable or c.estimate_quality == "best_case") and c.copay and c.copay.applies_when == "non_network" and c.copay.percent > 0 for c in covs):
        fields.append("network_hospital")
    return [factsmod.question(x) for x in dict.fromkeys(fields)]


def _combined(ordered: list[tuple[CoverageModel, Verdict]], billed: int) -> Optional[dict]:
    payers = [(c, v) for c, v in ordered if v.verdict != "NEEDS_REVIEW" and (v.payout or 0) > 0]
    if len(payers) < 2:
        return None
    remaining, split = billed, []
    for c, v in payers:
        pay = min(remaining, v.payout)
        split.append({"policy_id": c.policy_id, "payout": pay})
        remaining -= pay
    note = COMBINED_NOTE + (" Includes best-case estimates, so the true total may be lower." if any(v.estimate_quality == "best_case" for _, v in payers) else "")
    return {"possible": True, "total_payout": sum(s["payout"] for s in split), "split": split, "note": note}


def check(policy_ids: list[str], profile: dict, incident_text: str, bill: Optional[dict], answers: Optional[dict],
          load) -> dict:
    covs = []
    for pid in policy_ids:
        c = load(pid)
        if c is None:
            raise UnknownPolicy(pid)
        covs.append(c)
    prof = Profile(**(profile or {}))
    f, prov = factsmod.build_facts(incident_text, prof, bill, answers)
    provs = [prov]

    qs = _questions(covs, f)
    asked = set((answers or {}).keys()) | {"bill." + k for k in (bill or {})}
    qs = [q for q in qs if q["field"] not in asked]
    if qs:
        return {"status": "needs_info", "questions": qs, "meta": meta(provs)}

    low = f.confidence < CONF_MIN
    results = [(c, *_verdict_for(c, f, low)) for c in covs]

    # rank: computable policies with a payout, best first
    def key(r):
        c, v, _ = r
        # exact estimates rank above best-case upper bounds (they are not directly comparable), then by payout
        return (0 if v.verdict != "NEEDS_REVIEW" else 1, 0 if v.estimate_quality == "exact" else 1, -(v.payout or 0))

    ranked = sorted(results, key=key)
    best_c, best_v, _ = ranked[0]
    recommended = best_c.policy_id if best_v.verdict != "NEEDS_REVIEW" else None

    for c, v, _ in results:
        if c.policy_id == best_c.policy_id:
            if USE_LLM_EXPLAIN:
                why, steps, p = explain.explain(v)
                provs.append(p)
            else:
                why, steps = explain.template(v)
        else:
            why, steps = explain.template(v)
        if v.estimate_quality == "best_case" and v.verdict != "NEEDS_REVIEW":
            why = ("Best-case estimate (an upper bound, assuming " + "; ".join(v.assumptions) + "). ") + why
            steps = ["Check the room-rent limit and any co-payment in your policy schedule, or enter the limit under More details to refine this"] + steps
        v.why, v.next_steps = why, steps
    if recommended is None and len(covs) > 1:
        best_v.next_steps = ["Ask each insurer or TPA to confirm coverage for this claim"] + best_v.next_steps

    out = {"status": "done", "verdict": best_v.model_dump(), "meta": meta(provs)}
    if len(covs) >= 2:
        reason = _reason(ranked, recommended)
        out["comparison"] = {
            "results": [{"policy_id": c.policy_id, "name": c.name, "computable": c.computable, "estimate_quality": v.estimate_quality if v.verdict != "NEEDS_REVIEW" else c.estimate_quality, "verdict": v.model_dump()}
                        for c, v, _ in results],
            "recommended_policy_id": recommended,
            "recommendation_reason": reason,
            "combined": _combined([(c, v) for c, v, _ in ranked], best_v.billed or 0) if recommended else None,
        }
    return out


def _reason(ranked, recommended: Optional[str]) -> str:
    if recommended is None:
        return ("None of these policies could be computed reliably for this claim (see each result). "
                "Ask the insurers to confirm coverage.")
    (c1, v1, _), (c2, v2, _) = ranked[0], ranked[1]
    if (v1.payout or 0) == 0 and v1.verdict != "NEEDS_REVIEW":
        return "None of the policies that could be computed is estimated to pay for this claim."
    if v2.verdict == "NEEDS_REVIEW":
        return f"Only {c1.name} could be computed for this claim; the other policy needs manual review."
    if v1.estimate_quality == "exact" and v2.estimate_quality == "best_case":
        return (f"{c1.name} is an exact estimate ({inr(v1.payout)}). {c2.name} is only a best case of up to {inr(v2.payout)} "
                "(it assumes your room is within its limit), so the two are not directly comparable. Enter your room limit to refine it.")
    diff = (v1.payout or 0) - (v2.payout or 0)
    tail = " Both are best-case estimates." if v1.estimate_quality == "best_case" else ""
    if diff == 0:
        return f"Both policies are estimated to pay the same ({inr(v1.payout)}); the first listed is shown.{tail}"
    return f"Pays {inr(diff)} more than the alternative for this claim ({inr(v1.payout)} vs {inr(v2.payout)}).{tail}"
