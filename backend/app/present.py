"""Code-built presentation of a CoverageModel: summary items, gap report, ₹ formatting. No LLM."""
from __future__ import annotations

from typing import Optional

from . import engine
from .schemas import Category, Cite, CoverageModel


def inr(x) -> str:
    """Indian digit grouping: 500000 -> ₹5,00,000."""
    n = int(round(float(x)))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts + [tail])
    return ("-" if n < 0 else "") + "₹" + s


def _item(key, label, summary, c: Optional[Cite]) -> dict:
    return {"key": key, "label": label, "summary": summary, "clause": c.clause if c else "—",
            "page": (c.page or None) if c else None, "quote": c.quote if c else "", "verified": bool(c and c.verified)}


def _plans(plans: list[str]) -> str:
    return f" ({' & '.join(plans)} plans only)" if plans else ""


def summary_items(m: CoverageModel) -> list[dict]:
    out = []
    rr = m.room_rent
    if rr:
        if rr.kind == "percent_si":
            s = f"{rr.value:g}% of sum insured per day"
            if rr.icu_value:
                s += f" (ICU {rr.icu_value:g}%)"
        elif rr.kind == "fixed":
            s = f"{inr(rr.value)} per day"
        elif rr.kind == "any":
            s = "No daily room-rent cap"
        else:
            s = "Room-rent rule not clear"
        if not rr.computable:
            s += " — depends on hospital tariff / entitled category"
        out.append(_item("room_rent", "Room rent", s, rr))
        if rr.icu_value:
            out.append(_item("icu_rent", "ICU rent", f"{rr.icu_value:g}% of sum insured per day", rr))
    p = m.proportionate
    if p:
        s = ("If the room exceeds the cap, associated expenses are paid in the same proportion"
             if p.applies else "No proportionate reduction")
        out.append(_item("proportionate", "Proportionate payment", s, p))
    c = m.copay
    if c:
        s = "Not applicable" if c.percent == 0 else f"{c.percent:g}% co-payment" + (f" ({c.condition})" if c.condition else "")
        out.append(_item("copay", "Co-payment", s, c))
    wp = _plans(m.waiting_plans)
    if m.waiting_initial and m.waiting_initial.days:
        out.append(_item("waiting_initial", "Initial waiting period", f"{m.waiting_initial.days} days{wp}", m.waiting_initial))
    if m.waiting_ped and m.waiting_ped.months:
        out.append(_item("waiting_ped", "Pre-existing disease waiting", f"{m.waiting_ped.months} months{wp}", m.waiting_ped))
    if m.specific_waits:
        by = {}
        for w in m.specific_waits:
            by.setdefault(w.months, []).append(w.label or w.category.value)
        txt = "; ".join(f"{mo} months: {', '.join(names)}" for mo, names in sorted(by.items()))
        out.append(_item("waiting_specific", "Specified-illness waiting", txt + wp, m.specific_waits[0]))
    for sl in m.sublimits:
        bits = []
        if sl.pct_si is not None:
            bits.append(f"{sl.pct_si:g}% of sum insured")
        if sl.limit_inr is not None:
            bits.append(inr(sl.limit_inr))
        txt = " or ".join(bits) + (" (whichever is less)" if len(bits) == 2 else "") + (f" per {sl.per}" if sl.per != "claim" else "")
        key = "sublimit_" + (sl.label or sl.category.value).lower().replace(" ", "_").replace("&", "and")
        out.append(_item(key, f"Sub-limit: {sl.label or sl.category.value}", txt + _plans(m.sublimit_plans), sl))
    for i, ex in enumerate(m.exclusions[:25], 1):
        out.append(_item(f"exclusion_{i}", "Exclusion", ex.text or ex.category.value, ex))
    return out


def gaps(m: CoverageModel, age: Optional[int], si: Optional[float], ped: Optional[bool], rent: Optional[float],
         policy_age_months: int = 0) -> tuple[Optional[str], list[dict]]:
    plan = engine.derive_plan(m, age)
    out: list[dict] = []

    def add(sev, title, detail, c: Optional[Cite]):
        out.append({"severity": sev, "title": title, "detail": detail, "clause": c.clause if c else "—",
                    "page": (c.page or None) if c else None, "quote": c.quote if c else "",
                    "verified": bool(c and c.verified)})

    if not m.computable:
        add("high", "Payouts for this policy cannot be computed exactly", m.computable_note or "", m.room_rent)
    if m.plans and age is not None and plan is None:
        add("info", "Age is outside the policy's entry bands", f"Age {age} does not fall in any plan band, so plan-specific rules are unclear.", None)
    rr, pr = m.room_rent, m.proportionate
    if rr and si and rr.kind in ("percent_si", "fixed"):
        cap = si * rr.value / 100 if rr.kind == "percent_si" else rr.value
        if rent and rent > cap:
            ratio = cap / rent
            if pr and pr.applies:
                buckets = " and ".join(b.replace("_", "/") for b in pr.applies_to) or "associated"
                add("high", "Your preferred room exceeds the cap",
                    f"Room cap is {inr(cap)}/day ({rr.value:g}% of {inr(si)}). At {inr(rent)}/day, {buckets} charges are reduced to {ratio * 100:.1f}%.", pr)
            else:
                add("medium", "Your preferred room exceeds the cap",
                    f"Room cap is {inr(cap)}/day; you would pay the difference of {inr(rent - cap)}/day.", rr)
        elif rent:
            add("info", "Preferred room is within the cap", f"Room cap is {inr(cap)}/day and your preferred room is {inr(rent)}/day.", rr)
        else:
            add("info", "Room-rent cap", f"Room cap is {inr(cap)}/day for your sum insured.", rr)
    wait_on = (not m.waiting_plans) or (plan in m.waiting_plans)
    if wait_on:
        if m.waiting_ped and m.waiting_ped.months:
            if ped is True:
                rem = max(0, m.waiting_ped.months - policy_age_months)
                add("high" if rem else "info", "Pre-existing conditions have a waiting period",
                    f"Pre-existing diseases are not covered for {m.waiting_ped.months} months of continuous cover; about {rem} month(s) remain.", m.waiting_ped)
            elif ped is None:
                add("medium", "Pre-existing disease waiting period applies",
                    f"If you have a pre-existing condition it is excluded for {m.waiting_ped.months} months.", m.waiting_ped)
        if m.waiting_initial and m.waiting_initial.days:
            add("info", "Initial waiting period", f"Illness claims in the first {m.waiting_initial.days} days are not covered (accidents are).", m.waiting_initial)
        by = {}
        for w in m.specific_waits:
            by.setdefault(w.months, []).append(w)
        for mo, ws in sorted(by.items()):
            labels = [w.label or w.category.value for w in ws]
            names = ", ".join(labels[:3]) + (f" and {len(labels) - 3} more" if len(labels) > 3 else "")
            add("medium", f"{names} have a {mo}-month waiting period",
                f"Not covered until {mo} months of continuous cover (accidents excepted): {'; '.join(labels)}.", ws[0])
    if m.sublimits and ((not m.sublimit_plans) or (plan in m.sublimit_plans)):
        for sl in m.sublimits:
            bits = []
            if si and sl.pct_si is not None:
                bits.append(si * sl.pct_si / 100)
            if sl.limit_inr is not None:
                bits.append(sl.limit_inr)
            if bits:
                add("medium", f"{sl.label or sl.category.value} is capped", f"Payable up to {inr(min(bits))}" + (f" per {sl.per}" if sl.per != "claim" else "") + ".", sl)
    if m.copay and m.copay.percent > 0:
        add("medium", f"{m.copay.percent:g}% co-payment" + (f" ({m.copay.condition})" if m.copay.condition else ""),
            "You pay this share of each eligible claim.", m.copay)
    if m.exclusions:
        names = ", ".join(sorted({e.text or e.category.value for e in m.exclusions[:6]}))
        add("info", "Notable exclusions", f"Not covered, for example: {names}.", m.exclusions[0])
    order = {"high": 0, "medium": 1, "info": 2}
    out.sort(key=lambda g: order[g["severity"]])
    return plan, out


def gap_metrics(m: CoverageModel, age: Optional[int], si: Optional[float], rent: Optional[float],
                policy_age_months: int = 0) -> dict:
    """Numbers behind the gap report, for charts (all computed in code from the coverage model)."""
    plan = engine.derive_plan(m, age)
    out: dict = {"room": None, "waiting": [], "sublimits": [], "policy_age_months": policy_age_months}
    rr, pr = m.room_rent, m.proportionate
    if rr and si and rr.kind in ("percent_si", "fixed"):
        cap = si * rr.value / 100 if rr.kind == "percent_si" else rr.value
        pct = 100.0
        if rent and rent > cap and pr and pr.applies:
            pct = round(cap / rent * 100, 1)
        out["room"] = {"cap_per_day": round(cap), "preferred_per_day": round(rent) if rent else None, "payable_pct": pct,
                       "proportionate": bool(pr and pr.applies)}
    if (not m.waiting_plans) or (plan in m.waiting_plans):
        if m.waiting_initial and m.waiting_initial.days:
            out["waiting"].append({"label": "Initial waiting", "months": round(m.waiting_initial.days / 30, 1)})
        if m.waiting_ped and m.waiting_ped.months:
            out["waiting"].append({"label": "Pre-existing diseases", "months": m.waiting_ped.months})
        by: dict[int, list] = {}
        for w in m.specific_waits:
            by.setdefault(w.months, []).append(w.label or w.category.value)
        for mo, names in sorted(by.items()):
            out["waiting"].append({"label": f"Specified illnesses ({len(names)})", "months": mo, "detail": ", ".join(names)})
    if m.sublimits and ((not m.sublimit_plans) or (plan in m.sublimit_plans)) and si:
        for sl in m.sublimits:
            caps = ([si * sl.pct_si / 100] if sl.pct_si is not None else []) + ([sl.limit_inr] if sl.limit_inr is not None else [])
            if caps:
                out["sublimits"].append({"label": (sl.label or sl.category.value) + (f" (per {sl.per})" if sl.per != "claim" else ""),
                                         "cap_inr": round(min(caps))})
    waits = [w["months"] for w in out["waiting"]]
    out["summary"] = {
        "copay_percent": m.copay.percent if m.copay else 0,
        "copay_condition": m.copay.condition if m.copay else None,
        "exclusions": len(m.exclusions),
        "sublimits": len(out["sublimits"]),
        "longest_wait_months": max(waits, default=0),
        "plan": plan,
    }
    return out

