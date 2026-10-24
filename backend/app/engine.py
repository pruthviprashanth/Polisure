"""Deterministic claim engine. No LLM, Decimal only. Every step appends to the trace."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from .schemas import Category, ClaimFacts, CoverageModel, Cite, Citation, TraceStep

D = Decimal
BUCKETS = ("room", "linked", "meds_implants", "other")


def dec(x) -> Decimal:
    return D(str(x if x is not None else 0))


def rupees(x: Decimal) -> int:
    return int(x.quantize(D("1"), rounding=ROUND_HALF_UP))


def derive_plan(cov: CoverageModel, age: Optional[int]) -> Optional[str]:
    if age is None or not cov.plans:
        return None
    for b in cov.plans:
        if b.min_age <= age <= b.max_age:
            return b.plan
    return None


@dataclass
class EngineResult:
    verdict: str
    billed: int
    payout: Optional[int]
    trace: list[TraceStep] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    abstain_reason: Optional[str] = None
    plan: Optional[str] = None
    room_cap_per_day: Optional[int] = None
    blocked: Optional[dict] = None  # {"kind": "waiting_initial|ped|specific", "months_needed": n}


class _Run:
    def __init__(self, cov: CoverageModel, facts: ClaimFacts):
        self.cov, self.f = cov, facts
        self.trace: list[TraceStep] = []
        self.cites: dict[tuple, Citation] = {}
        self.used_unverified: list[str] = []

    def use(self, c: Optional[Cite]) -> tuple[str, Optional[int]]:
        if c is None:
            return "—", None
        key = (c.clause, c.page)
        if key not in self.cites:
            self.cites[key] = Citation(clause=c.clause or "—", page=c.page or None, quote=c.quote, verified=c.verified)
        if not c.verified:
            self.used_unverified.append(c.clause or c.quote[:40])
        return c.clause or "—", c.page or None

    def add(self, step, label, before, after, cite: Optional[Cite] = None):
        clause, page = self.use(cite) if cite else ("—", None)
        self.trace.append(TraceStep(step=step, label=label, before=rupees(before) if before is not None else None,
                                    after=rupees(after) if after is not None else None, clause=clause, page=page))

    def finish(self, verdict, billed, payout, reason=None, plan=None, cap=None, blocked=None) -> EngineResult:
        if self.used_unverified and verdict != "NEEDS_REVIEW":
            verdict, payout = "NEEDS_REVIEW", None
            reason = "A policy rule used for this estimate could not be verified against the document text (" + \
                     ", ".join(sorted(set(self.used_unverified))) + ")."
            blocked = None
        return EngineResult(verdict=verdict, billed=rupees(billed), payout=None if payout is None else rupees(payout),
                            trace=self.trace, citations=list(self.cites.values()), abstain_reason=reason,
                            plan=plan, room_cap_per_day=None if cap is None else rupees(cap), blocked=blocked)


def _kw(k: str, text: str) -> bool:
    return bool(k) and re.search(r"\b" + re.escape(k.lower()) + r"\b", text) is not None


def _match(cat: Category, keywords: list[str], f: ClaimFacts, text: str) -> bool:
    if cat not in (Category.other, Category.unknown) and cat == f.category:
        return True
    cname = f.category.value.replace("_", " ")
    return any(_kw(k, text) or (f.category not in (Category.other, Category.unknown) and k.lower() == cname) for k in keywords)


def _applies(plan: Optional[str], plans: list[str]) -> bool:
    return not plans or (plan is not None and plan in plans)


def run(cov: CoverageModel, facts: ClaimFacts) -> EngineResult:
    r = _Run(cov, facts)
    f = facts
    bill = {k: dec(getattr(f.bill, k)) for k in BUCKETS}
    billed = sum(bill.values(), D(0))
    si = dec(f.sum_insured)
    plan = f.plan or derive_plan(cov, f.insured_age)

    def review(reason, cap=None):
        return r.finish("NEEDS_REVIEW", billed, None, reason, plan, cap)

    if not cov.computable:
        return review(cov.computable_note or "This policy's structure cannot be computed exactly by the engine.")
    if f.sum_insured is None or si <= 0:
        return review("Sum insured is unknown.")
    if billed <= 0:
        return review("No bill amounts were provided.")
    if f.category == Category.unknown:
        return review("The diagnosis could not be mapped to a known category.")
    if f.policy_age_months is None:
        return review("Policy age (months since first policy) is unknown.")
    if cov.plans:
        if plan is None:
            return review("The insured age is outside the policy's entry-age bands, so the plan cannot be determined.")
    age_m = f.policy_age_months
    waiting_on = _applies(plan, cov.waiting_plans)

    # 1. initial waiting period
    wi = cov.waiting_initial
    if waiting_on and wi and wi.days > 0 and not f.is_accident and age_m * 30 < wi.days:
        r.add("waiting_initial", f"Initial waiting period of {wi.days} days not over (policy age {age_m} month(s))", billed, D(0), wi)
        return r.finish("NOT_COVERED", billed, D(0), plan=plan,
                        blocked={"kind": "waiting_initial", "months_needed": -(-wi.days // 30)})

    # 2. exclusions
    text = f"{f.diagnosis_text} {f.procedure}".lower()
    for ex in cov.exclusions:
        hit = (ex.category not in (Category.other, Category.unknown) and ex.category == f.category) or \
              any(_kw(k, text) for k in ex.keywords)
        if hit:
            if f.is_accident and "accident" in (ex.quote + ex.text).lower():
                return review("The matching exclusion has an accident exception, so the outcome needs a human check.")
            r.add("exclusion", f"Excluded: {ex.text or ex.category.value}", billed, D(0), ex)
            return r.finish("NOT_COVERED", billed, D(0), plan=plan)

    # 3. pre-existing disease
    wp = cov.waiting_ped
    if waiting_on and wp and wp.months > 0 and not f.is_accident and age_m < wp.months:
        if f.ped is None:
            return review("Whether the condition is pre-existing is unknown, and a pre-existing-disease waiting period still applies.")
        if f.ped:
            r.add("waiting_ped", f"Pre-existing disease waiting period of {wp.months} months not over (policy age {age_m})", billed, D(0), wp)
            return r.finish("NOT_COVERED", billed, D(0), plan=plan, blocked={"kind": "ped", "months_needed": wp.months})

    # 4. specific-illness waiting
    if waiting_on and not f.is_accident:
        for sw in cov.specific_waits:
            if _match(sw.category, sw.keywords, f, text) and age_m < sw.months:
                r.add("waiting_specific", f"{sw.label or sw.category.value}: {sw.months}-month waiting period not over (policy age {age_m})", billed, D(0), sw)
                return r.finish("NOT_COVERED", billed, D(0), plan=plan,
                                blocked={"kind": "specific", "months_needed": sw.months})

    # unsupported structure
    if f.icu_days and f.icu_days > 0:
        return review("An ICU stay was reported; ICU limits are not modelled by this estimator.")
    if cov.unmodeled_terms:
        return review("This policy has terms the estimator cannot compute exactly: " + "; ".join(cov.unmodeled_terms[:3]))

    # steps 5-8 in deduction order
    cur = billed
    scale = D(1)
    rr, prop = cov.room_rent, cov.proportionate
    cap_day: Optional[Decimal] = None
    if rr and rr.kind == "percent_si":
        cap_day = si * dec(rr.value) / 100
    elif rr and rr.kind == "fixed":
        cap_day = dec(rr.value)
    elif rr is None or rr.kind == "unknown":
        return review("The policy's room-rent rule could not be read.")

    order = [s for s in (cov.deduction_order or []) if s in ("sublimit", "room_rent", "copay", "sum_insured")]
    for s in ("sublimit", "room_rent", "copay", "sum_insured"):
        if s not in order:
            order.append(s)

    for step in order:
        if step == "sublimit":
            sl = next((s for s in cov.sublimits if _match(s.category, s.keywords, f, text)), None)
            if sl and _applies(plan, cov.sublimit_plans):
                caps = []
                if sl.pct_si is not None:
                    caps.append(si * dec(sl.pct_si) / 100)
                if sl.limit_inr is not None:
                    caps.append(dec(sl.limit_inr))
                if caps:
                    cap = min(caps) * (f.units if sl.per == "eye" else 1)
                    new = min(cur, cap)
                    r.add("sublimit", f"Sub-limit for {sl.label or sl.category.value}: capped at ₹{rupees(cap):,}", cur, new, sl)
                    if cur > 0:
                        scale = scale * new / cur
                    cur = new
        elif step == "room_rent" and cap_day is not None:
            days = f.days
            rent = dec(f.room_rent_per_day) if f.room_rent_per_day else (bill["room"] / days if days else None)
            if rent is None or rent <= 0 or not days:
                if bill["room"] > 0:
                    return review("Room rent per day or number of days is unknown.", cap_day)
                continue
            clause_cite = rr
            if rent > cap_day:
                ratio = cap_day / rent
                eligible = cap_day * days
                room_after = min(bill["room"], eligible) * scale
                r.add("room_rent", f"Room: {days} day(s) × ₹{rupees(cap_day):,} cap (actual ₹{rupees(rent):,}/day)",
                      bill["room"] * scale, room_after, clause_cite)
                reduction = bill["room"] * scale - room_after
                prop_buckets = prop.applies_to if prop and prop.applies else []
                for b in ("linked", "meds_implants", "other"):
                    if bill[b] <= 0:
                        continue
                    if b in prop_buckets:
                        after = bill[b] * scale * ratio
                        r.add("proportionate" if b == "linked" else f"proportionate_{b}",
                              f"{'Associated charges' if b == 'linked' else b} × {(ratio * 100).quantize(D('0.1'))}% (cap ÷ actual)",
                              bill[b] * scale, after, prop)
                        reduction += bill[b] * scale - after
                    elif b == "meds_implants":
                        r.add("meds_implants", "Medicines & implants (not reduced)", bill[b] * scale, bill[b] * scale)
                cur = cur - reduction
            else:
                r.add("room_rent", f"Room ₹{rupees(rent):,}/day is within the ₹{rupees(cap_day):,}/day cap", bill["room"] * scale, bill["room"] * scale, rr)
        elif step == "copay":
            cp = cov.copay
            if cp and cp.percent > 0:
                if cp.applies_when == "non_network":
                    if f.network_hospital is None:
                        return review("Co-payment applies only at non-network hospitals; whether the hospital is in the network is unknown.", cap_day)
                    apply = f.network_hospital is False
                elif cp.applies_when == "other":
                    return review("A conditional co-payment applies that the estimator cannot evaluate.", cap_day)
                else:
                    apply = True
                if apply:
                    new = cur * (100 - dec(cp.percent)) / 100
                    r.add("copay", f"Co-payment {cp.percent:g}%", cur, new, cp)
                    cur = new
        elif step == "sum_insured":
            remaining = dec(f.remaining_sum_insured) if f.remaining_sum_insured is not None else si
            if cur > remaining:
                r.add("sum_insured", f"Capped at remaining sum insured ₹{rupees(remaining):,}", cur, remaining)
                cur = remaining

    payout = D(rupees(cur))
    r.add("total", "Payable", billed, payout)
    verdict = "NOT_COVERED" if payout <= 0 else ("COVERED" if payout >= D(rupees(billed)) else "PARTIAL")
    return r.finish(verdict, billed, payout, plan=plan, cap=cap_day)
