"""Incident text (+ profile, bill, answers) -> ClaimFacts and follow-up questions."""
from __future__ import annotations

import re
from typing import Any, Optional

from pydantic import BaseModel, Field

from . import llm
from .schemas import Bill, Category, ClaimFacts, Profile

SYSTEM = """You extract structured facts from a policyholder's description of a hospital claim. Output only what the text states; leave unknown things null/0. Never guess amounts.
- category: one of appendectomy, cataract, hernia, joint_replacement (knee/hip/joint replacement), maternity (childbirth/pregnancy), cosmetic, dental, infertility (IVF etc.), accident_trauma (injury from an accident), other (a real condition not in the list), unknown (cannot tell).
- is_accident: true only if the text says the cause was an accident/injury event. is_planned: true for planned/elective admission.
- days: number of nights/days in hospital. room_rent_per_day: room charge per day in rupees. icu_days: days in ICU (0 if none).
- Amounts are rupees. Convert '1.6 lakh' to 160000, '25k' to 25000.
- bill_total: the total bill if stated. bill_room / bill_linked (doctor, surgeon, OT, investigations, nursing and other room-category-linked charges) / bill_meds_implants (medicines, implants, stents, consumables) / bill_other: only if the text itemises them.
- units: number of eyes (cataract) or joints; default 1.
- network_hospital: true/false only if stated (cashless/network vs non-network), else null.
- ped: true/false only if the text says the condition was or was not pre-existing/known before the policy, else null.
- policy_age_months: months since the policy first started, only if stated.
- confidence 0..1: how sure you are about category and the numbers."""


class FactsLLM(BaseModel):
    diagnosis_text: str = ""
    category: Category = Category.unknown
    procedure: str = ""
    is_accident: bool = False
    is_planned: bool = False
    days: Optional[int] = None
    icu_days: int = 0
    units: int = 1
    room_rent_per_day: Optional[float] = None
    bill_total: Optional[float] = None
    bill_room: Optional[float] = None
    bill_linked: Optional[float] = None
    bill_meds_implants: Optional[float] = None
    bill_other: Optional[float] = None
    network_hospital: Optional[bool] = None
    ped: Optional[bool] = None
    policy_age_months: Optional[int] = None
    confidence: float = Field(0.0, ge=0, le=1)


# ---------------------------------------------------------------- mock extractor (heuristic, mock mode only)
def _money(s: str) -> Optional[float]:
    m = re.search(r"(?:₹|rs\.?|inr)?\s*([\d][\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|k|crore)?", s, re.I)
    if not m:
        return None
    v = float(m.group(1).replace(",", ""))
    u = (m.group(2) or "").lower()
    if u.startswith("l"):
        v *= 100000
    elif u == "k":
        v *= 1000
    elif u == "crore":
        v *= 10000000
    return v


_CATS = [("appendectomy", r"append"), ("cataract", r"cataract"), ("hernia", r"hernia"),
         ("joint_replacement", r"(knee|hip|joint)\s+replacement|arthroplasty"), ("maternity", r"deliver|childbirth|pregnan|caesarean|c-section"),
         ("cosmetic", r"cosmetic|plastic surgery|rhinoplasty|liposuction"), ("dental", r"dental|tooth|root canal"),
         ("infertility", r"infertil|\bivf\b"), ("accident_trauma", r"accident|fracture|road traffic|injur")]


def mock_facts(system: str, user: str) -> dict:
    t = user.lower()
    cat, conf = "unknown", 0.3
    for name, pat in _CATS:
        if re.search(pat, t):
            cat, conf = name, 0.85
            break
    if cat == "unknown" and re.search(r"fever|dengue|typhoid|pneumonia|infection|surgery|stone|fracture", t):
        cat, conf = "other", 0.7
    d = {"diagnosis_text": user[:120], "category": cat, "confidence": conf,
         "is_accident": bool(re.search(r"accident|road traffic|fell|fall ", t)), "is_planned": "planned" in t or "elective" in t}
    m = re.search(r"(\d+)\s*(?:days?|nights?)", t)
    if m:
        d["days"] = int(m.group(1))
    m = re.search(r"(?:₹|rs\.?)\s*([\d,]+)\s*(?:/|per)\s*(?:day|night)", t)
    if m:
        d["room_rent_per_day"] = float(m.group(1).replace(",", ""))
    m = re.search(r"(?:total|bill)[^.\d₹]{0,30}(?:₹|rs\.?)?\s*([\d.,]+\s*(?:lakhs?|lacs?|k)?)", t)
    if m:
        v = _money(m.group(1))
        if v and v >= 1000:
            d["bill_total"] = v
    if re.search(r"non[- ]network", t):
        d["network_hospital"] = False
    elif re.search(r"\bcashless\b|\bnetwork hospital", t):
        d["network_hospital"] = True
    if re.search(r"pre-?existing|known (?:diabet|hypert)|for years", t):
        d["ped"] = True
    return d


llm.register_mock("facts", mock_facts)


# ---------------------------------------------------------------- merge
def _num(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _bool(v: Any) -> Optional[bool]:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        if v.strip().lower() in ("true", "yes", "y"):
            return True
        if v.strip().lower() in ("false", "no", "n"):
            return False
    return None


def build_facts(incident_text: str, profile: Profile, bill_in: Optional[dict], answers: Optional[dict]) -> tuple[ClaimFacts, str]:
    """LLM reads the text; code merges profile, form bill and answers (these win over the text)."""
    obj, prov = llm.extract(FactsLLM, SYSTEM, incident_text, purpose="facts", can_fallback=True, max_out=600, prefer_groq=True)
    ans = dict(answers or {})
    bill_in = dict(bill_in or {})
    for k, v in list(ans.items()):                # dotted answer keys like "bill.meds_implants"
        if k.startswith("bill."):
            bill_in[k[5:]] = v

    bill = {"room": obj.bill_room, "linked": obj.bill_linked, "meds_implants": obj.bill_meds_implants, "other": obj.bill_other}
    for k in bill:
        if _num(bill_in.get(k)) is not None:
            bill[k] = _num(bill_in[k])
    days = _num(ans.get("days")) or obj.days
    # Room rent per day, most reliable source first: an explicit answer, the room charge the user entered
    # in the bill form (÷ days), the rent stated in the text, and only then the profile's preferred rent.
    room_entered = _num(bill_in.get("room"))
    rent = _num(ans.get("room_rent_per_day"))
    if rent is None and room_entered and days:
        rent = room_entered / days
    if rent is None:
        rent = obj.room_rent_per_day
    if rent is None and obj.bill_room and days:
        rent = obj.bill_room / days
    if rent is None:
        rent = profile.preferred_room_rent_per_day
    # a stated total with a known room: remaining split needs the user's meds/implants figure
    total = _num(bill_in.get("total")) or _num(ans.get("bill.total")) or obj.bill_total
    missing: list[str] = []
    if bill["room"] is None and rent and days:
        bill["room"] = rent * days
    if total is not None and bill["linked"] is None:
        if bill["room"] is None:
            missing.append("bill.room")
        if bill["meds_implants"] is None:
            missing.append("bill.meds_implants")
        if not missing:
            bill["linked"] = max(total - sum(v or 0 for k, v in bill.items() if k != "linked"), 0)
    elif total is None:
        missing += [f"bill.{k}" for k in ("room", "linked", "meds_implants") if bill[k] is None]
    ped = _bool(ans.get("ped"))
    if ped is None:
        ped = obj.ped if obj.ped is not None else profile.ped
    age_m = _num(ans.get("policy_age_months"))
    age_m = int(age_m) if age_m is not None else (profile.policy_age_months if profile.policy_age_months is not None else obj.policy_age_months)
    if days is None and (bill["room"] or 0) > 0:
        missing.append("days")
    if rent is None and (bill["room"] or 0) > 0 and days:
        rent = bill["room"] / days
    # Structured form answers beat the LLM's reading of the free text.
    is_accident = _bool(ans.get("is_accident"))
    is_accident = obj.is_accident if is_accident is None else is_accident
    is_planned = _bool(ans.get("is_planned"))
    is_planned = obj.is_planned if is_planned is None else is_planned
    remaining = _num(ans.get("remaining_sum_insured"))
    used = _num(ans.get("sum_insured_used"))
    if remaining is None and used is not None and profile.sum_insured is not None:
        remaining = max(profile.sum_insured - used, 0)
    facts = ClaimFacts(
        diagnosis_text=obj.diagnosis_text, category=obj.category, procedure=obj.procedure,
        is_accident=is_accident, is_planned=is_planned, insured_age=profile.insured_age,
        policy_age_months=age_m, ped=ped, days=int(days) if days else None, icu_days=obj.icu_days,
        units=max(obj.units, 1), network_hospital=_bool(ans.get("network_hospital")) if _bool(ans.get("network_hospital")) is not None else obj.network_hospital,
        room_rent_per_day=rent, room_limit_per_day=_num(ans.get("room_limit_per_day")), bill=Bill(**{k: (v or 0) for k, v in bill.items()}),
        sum_insured=profile.sum_insured, remaining_sum_insured=remaining,
        missing=missing, confidence=obj.confidence)
    return facts, prov


QUESTION_TEXT = {
    "bill.room": ("How much was the room charge in the bill (₹)?", "number"),
    "bill.linked": ("How much were doctor, surgeon, OT and other room-linked charges (₹)?", "number"),
    "bill.meds_implants": ("How much of the bill was medicines and implants (₹)?", "number"),
    "bill.other": ("Any other charges not covered above (₹)?", "number"),
    "days": ("How many days was the patient in hospital?", "number"),
    "room_rent_per_day": ("What was the room rent per day (₹)?", "number"),
    "policy_age_months": ("How many months ago did the first policy with this insurer start?", "number"),
    "ped": ("Was this condition diagnosed or treated before the policy started?", "boolean"),
    "network_hospital": ("Was the hospital in the insurer's cashless network?", "boolean"),
}


def question(field: str) -> dict:
    q, t = QUESTION_TEXT.get(field, (f"Please provide {field}", "number"))
    return {"field": field, "question": q, "type": t}
