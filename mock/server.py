"""Mock PoliSure API (follows CONTRACT.md). No LLM calls, no keys.

Run:  python mock/server.py        (port 8000)

Scenario picking for POST /claims/check, by words in incident_text:
  appendix / appendectomy      -> PARTIAL (room above the 1% cap -> proportionate deduction)
  cataract / hernia            -> NOT_COVERED while policy_age_months < 24 (waiting period), else sub-limit
  knee / hip / joint           -> joint replacement (48-month wait, 70% sub-limit)
  delivery / maternity         -> NOT_COVERED (exclusion)
  unsure / not sure / don't know -> NEEDS_REVIEW (pre-existing status unknown)
  no amounts in the text and no bill -> needs_info (asks for the bill split and PED)
  "llm down"                   -> 503 llm_unavailable
Profile ped=true triggers a follow-up question; ped=null (don't know) -> NEEDS_REVIEW.

Other error cases: uploading a non-PDF -> 400; a file whose name contains "fail" -> 503;
unknown policy id -> 404; GET /mock/settings?no_report=1 makes /eval/latest return 404.
Latency: random 3-8 s on calls that would hit an LLM; env MOCK_LATENCY scales it (0 disables).
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import os
import random
import re
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import (  # noqa: E402
    DEFAULT_BILLS,
    DEMO_ID,
    DISCLAIMER,
    EVAL_REPORT,
    MOCK_META_NOTE,
    POLICIES,
    SBI_ID,
    UI_ID,
    UI_SUMMARY,
)

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = {"latency": float(os.environ.get("MOCK_LATENCY", "1")), "no_report": os.environ.get("MOCK_NO_REPORT") == "1"}
UPLOADS: dict[str, dict] = {}  # policy_id -> {"name", "bytes"}

app = FastAPI(title="PoliSure mock API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def meta(cached: bool = False) -> dict:
    return {"cached": cached, "providers_used": ["cache" if cached else "mock"], "model_note": MOCK_META_NOTE}


def err(status: int, error: str, detail: str | None = None) -> JSONResponse:
    body = {"error": error}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status)


async def think(lo: float = 3, hi: float = 8) -> None:
    if SETTINGS["latency"] > 0:
        await asyncio.sleep(random.uniform(lo, hi) * SETTINGS["latency"])


def r(x) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def inr(n: int) -> str:
    # Indian grouping: 115000 -> 1,15,000
    s = str(abs(int(n)))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        head = re.sub(r"(\d)(?=(\d\d)+$)", r"\1,", head)
        s = f"{head},{tail}"
    return f"₹{s}"


# ---------------------------------------------------------------- policies

def policy_entry(pid: str) -> dict | None:
    if pid in POLICIES:
        return POLICIES[pid]
    if pid in UPLOADS:
        u = UPLOADS[pid]
        return {"policy_id": pid, "name": u["name"], "pages": u["pages"], "summary_items": UI_SUMMARY,
                "computable": True, "computable_note": None, "pdf": None}
    return None


def engine_for(pid: str) -> str:
    return {SBI_ID: "sbi", DEMO_ID: "demo"}.get(pid, "ui")


def policy_body(pid: str, cached: bool) -> dict:
    p = policy_entry(pid)
    m = meta(cached)
    if pid in UPLOADS:
        m["model_note"] = MOCK_META_NOTE + " (summary copied from the sample policy)"
    return {"policy_id": pid, "name": p["name"], "pages": p["pages"],
            "summary_items": copy.deepcopy(p["summary_items"]), "meta": m}


BOOT_ID = hashlib.sha1(str(random.random()).encode()).hexdigest()


@app.get("/session")
async def session():
    return {"boot_id": BOOT_ID}


@app.get("/policies")
async def list_policies():
    out = []
    for pid in list(POLICIES) + list(UPLOADS):
        p = policy_entry(pid)
        out.append({"policy_id": pid, "name": p["name"], "pages": p["pages"],
                    "computable": p["computable"], "computable_note": p["computable_note"]})
    return out


@app.post("/policies")
async def upload_policy(file: UploadFile = File(...)):
    data = await file.read()
    if not data.startswith(b"%PDF"):
        return err(400, "Not a PDF file. Please upload the policy wording as a PDF.")
    if "fail" in (file.filename or "").lower():
        await think(1, 2)
        return err(503, "llm_unavailable", "Mock: simulated provider outage during extraction")
    await think(5, 8)
    digest = hashlib.sha256(data).hexdigest()
    for pid, p in POLICIES.items():
        if p["pdf"] and (ROOT / p["pdf"]).exists():
            if hashlib.sha256((ROOT / p["pdf"]).read_bytes()).hexdigest() == digest:
                return policy_body(pid, cached=False)
    pid = digest[:12]
    pages = max(1, len(re.findall(rb"/Type\s*/Page[^s]", data)))
    UPLOADS[pid] = {"name": Path(file.filename or "Uploaded policy").stem, "bytes": data, "pages": pages}
    return policy_body(pid, cached=False)


@app.get("/policies/{policy_id}")
async def get_policy(policy_id: str):
    if not policy_entry(policy_id):
        return err(404, "unknown_policy")
    await think(0.2, 0.6)
    return policy_body(policy_id, cached=True)


def one_page_pdf(lines: list[str]) -> bytes:
    text = "BT /F1 14 Tf 60 780 Td 18 TL " + " ".join(
        "(" + ln.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") '" for ln in lines) + " ET"
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(text) + text.replace("₹", "Rs. ").replace("–", "-").replace("—", "-").encode("latin-1", "replace") + b"\nendstream",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out


@app.get("/policies/{policy_id}/pdf")
async def get_pdf(policy_id: str):
    p = policy_entry(policy_id)
    if not p:
        return err(404, "unknown_policy")
    if policy_id in UPLOADS:
        data = UPLOADS[policy_id]["bytes"]
    elif p["pdf"] and (ROOT / p["pdf"]).exists():
        data = (ROOT / p["pdf"]).read_bytes()
    else:
        data = one_page_pdf([p["name"], "", "Mock policy document generated by mock/server.py.",
                             *[f"{s['clause']}  {s['label']}: {s['summary']}" for s in p["summary_items"]]])
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": "inline; filename=policy.pdf"})


# ---------------------------------------------------------------- gaps

def plan_for_age(age: int) -> str | None:
    if 18 <= age <= 35:
        return "Platinum"
    if 36 <= age <= 60:
        return "Gold"
    if 61 <= age <= 65:
        return "Senior Citizen"
    return None


def cite(pid: str, key: str) -> dict:
    p = policy_entry(pid)
    for s in p["summary_items"]:
        if s["key"] == key:
            return {"clause": s["clause"], "page": s["page"], "quote": s["quote"], "verified": s["verified"]}
    return {"clause": "—", "page": None, "quote": "", "verified": False}


@app.get("/policies/{policy_id}/gaps")
async def gaps(policy_id: str, insured_age: int, sum_insured: int, preferred_room_rent_per_day: int = 0,
               ped: bool | None = None, policy_age_months: int = 0):
    if not policy_entry(policy_id):
        return err(404, "unknown_policy")
    await think(0.3, 1)
    plan = plan_for_age(insured_age) or "Not eligible"
    out = []
    eng = engine_for(policy_id)
    if eng == "sbi":
        out.append({"severity": "high", "title": "Payouts on this policy depend on the hospital's room tariffs",
                    "detail": POLICIES[SBI_ID]["computable_note"], **cite(policy_id, "proportionate")})
        out.append({"severity": "medium", "title": "10% co-payment at non-network hospitals",
                    "detail": "Use a network hospital to avoid the co-payment.", **cite(policy_id, "copay")})
        return {"plan": "—", "gaps": out, "metrics": empty_metrics(policy_age_months), "meta": meta(True)}
    if eng == "demo":
        out.append({"severity": "medium", "title": "You pay 20% of every claim",
                    "detail": f"On a {inr(100000)} bill you would pay {inr(20000)} yourself.", **cite(policy_id, "copay")})
        out.append({"severity": "info", "title": "No room-rent cap",
                    "detail": "Any room category is paid at actuals (before co-payment).", **cite(policy_id, "room_rent")})
        return {"plan": "—", "gaps": out, "metrics": empty_metrics(policy_age_months), "meta": meta(True)}

    if plan == "Not eligible":
        out.append({"severity": "high", "title": f"Age {insured_age} is outside the plan bands (18–65)",
                    "detail": "The policy's plans are Platinum 18–35, Gold 36–60 and Senior Citizen 61–65.",
                    "clause": "7", "page": 2, "quote": "Sum Insured Options for fresh issuance of policy", "verified": True})
    cap = r(sum_insured * Decimal("0.01"))
    if preferred_room_rent_per_day > cap:
        ratio = Decimal(cap) / Decimal(preferred_room_rent_per_day)
        out.append({"severity": "high", "title": "Your preferred room exceeds the cap",
                    "detail": f"Room cap is {inr(cap)}/day (1% of {inr(sum_insured)}). At {inr(preferred_room_rent_per_day)}/day "
                              f"all associated expenses are reduced to {float(ratio * 100):.1f}%.",
                    **cite(policy_id, "proportionate")})
    else:
        out.append({"severity": "info", "title": "Your preferred room is within the cap",
                    "detail": f"Room cap is {inr(cap)}/day (1% of {inr(sum_insured)}); no proportionate deduction expected.",
                    **cite(policy_id, "room_rent")})
    if plan in ("Gold", "Senior Citizen"):
        out.append({"severity": "medium", "title": "Hernia and cataract have a 24-month waiting period",
                    "detail": f"On the {plan} plan, listed conditions (cataract, hernia, BPH, hydrocele and more) are not paid "
                              "in the first 24 months; joint replacement waits 48 months.",
                    **cite(policy_id, "waiting_specific")})
        cat_lim = min(r(sum_insured * Decimal("0.25")), 40000)
        out.append({"severity": "medium", "title": f"Cataract is capped at {inr(cat_lim)} per eye",
                    "detail": f"25% of sum insured or ₹40,000 per eye, whichever is less, on the {plan} plan.",
                    **cite(policy_id, "sublimit_cataract")})
        if ped is True:
            out.append({"severity": "high", "title": "Pre-existing conditions are excluded for 48 months",
                        "detail": "Claims for a condition you had before the policy started are not paid until 48 months of continuous cover.",
                        **cite(policy_id, "waiting_ped")})
        elif ped is None:
            out.append({"severity": "medium", "title": "Pre-existing conditions: unknown",
                        "detail": "If you had a condition before the policy started, it is excluded for 48 months. Check your medical history.",
                        **cite(policy_id, "waiting_ped")})
    elif plan == "Platinum":
        out.append({"severity": "info", "title": "No waiting periods or sub-limits on the Platinum plan",
                    "detail": "Waiting periods and sub-limits apply only to the Gold and Senior Citizen plans.",
                    **cite(policy_id, "waiting_specific")})
    out.append({"severity": "info", "title": "No co-payment", "detail": "The policy does not apply a co-payment.",
                **cite(policy_id, "copay")})
    metrics = {"room": {"cap_per_day": cap, "preferred_per_day": preferred_room_rent_per_day or None,
                        "payable_pct": round(float(Decimal(cap) / Decimal(preferred_room_rent_per_day) * 100), 1)
                        if preferred_room_rent_per_day > cap else 100.0, "proportionate": True},
               "waiting": [], "sublimits": [], "policy_age_months": policy_age_months}
    if plan in ("Gold", "Senior Citizen"):
        metrics["waiting"] = [{"label": "Initial waiting", "months": 1}, {"label": "Pre-existing diseases", "months": 48},
                              {"label": "Specified illnesses (Table A)", "months": 24},
                              {"label": "Specified illnesses (Table B)", "months": 48}]
        metrics["sublimits"] = [{"label": "Cataract (per eye)", "cap_inr": min(r(sum_insured * Decimal("0.25")), 40000)},
                                {"label": "Hernia & hysterectomy", "cap_inr": min(r(sum_insured * Decimal("0.25")), 100000)},
                                {"label": "Major surgeries", "cap_inr": r(sum_insured * Decimal("0.7"))}]
    gold = plan in ("Gold", "Senior Citizen")
    metrics["summary"] = {"copay_percent": 0, "copay_condition": None, "exclusions": 23, "sublimits": len(metrics["sublimits"]),
                          "longest_wait_months": 48 if gold else 0, "plan": plan}
    metrics["typical_claims"] = [
        {"category": "appendectomy", "billed": 142000, "payout": 142000 if preferred_room_rent_per_day <= cap else 112000,
         "verdict": "COVERED" if preferred_room_rent_per_day <= cap else "PARTIAL"},
        {"category": "cataract", "billed": 50000, "payout": 0 if gold and policy_age_months < 24 else min(40000, 50000),
         "verdict": "NOT_COVERED" if gold and policy_age_months < 24 else "PARTIAL"},
        {"category": "hernia", "billed": 96000, "payout": 0 if gold and policy_age_months < 24 else 96000,
         "verdict": "NOT_COVERED" if gold and policy_age_months < 24 else "COVERED"},
        {"category": "joint_replacement", "billed": 560000, "payout": 0 if gold and policy_age_months < 48 else 350000,
         "verdict": "NOT_COVERED" if gold and policy_age_months < 48 else "PARTIAL"},
        {"category": "maternity", "billed": 95000, "payout": 0, "verdict": "NOT_COVERED"},
    ]
    return {"plan": plan, "gaps": out, "metrics": metrics, "meta": meta(True)}


def empty_metrics(age_m: int) -> dict:
    return {"room": None, "waiting": [], "sublimits": [], "policy_age_months": age_m}


# ---------------------------------------------------------------- claims

def detect_category(text: str) -> str:
    t = text.lower()
    rules = [("cataract", "cataract"), ("hernia", "hernia"), ("knee", "joint_replacement"), ("hip", "joint_replacement"),
             ("joint", "joint_replacement"), ("deliver", "maternity"), ("maternity", "maternity"), ("pregnan", "maternity"),
             ("caesarean", "maternity"), ("cosmetic", "cosmetic"), ("append", "appendectomy")]
    for kw, cat in rules:
        if re.search(r"\b" + kw, t):
            return cat
    return "other"


def is_accident(text: str) -> bool:
    return bool(re.search(r"accident|fractur|injur|\bfell\b", text.lower()))


def is_unsure(text: str) -> bool:
    return bool(re.search(r"unsure|not sure|don'?t know|no idea", text.lower()))


def parse_num(s: str) -> int:
    return int(s.replace(",", ""))


def build_bill(category: str, text: str, bill_in: dict | None, answers: dict) -> tuple[dict, int]:
    d = DEFAULT_BILLS.get(category, DEFAULT_BILLS["other"])
    t = text.lower()
    m = re.search(r"(\d+)\s*(?:days?|nights?)", t)
    days = int(answers.get("days") or (m.group(1) if m else d[4]))
    given = {k: int(v) for k, v in (bill_in or {}).items() if v not in (None, "") and k in DEFAULT_KEYS}
    b = {"room": d[0], "linked": d[1], "meds_implants": d[2], "other": d[3]}
    rent = re.search(r"₹?\s*([\d,]{3,})\s*(?:/|per)\s*day", t)
    if rent:
        b["room"] = parse_num(rent.group(1)) * days
    lakh = re.search(r"₹?\s*([\d.]+)\s*lakh", t)
    plain = re.search(r"(?:bill|total)[^₹\d]{0,20}₹\s*([\d,]{4,})", t)
    total = r(Decimal(lakh.group(1)) * 100000) if lakh else parse_num(plain.group(1)) if plain else None
    b.update({k: v for k, v in given.items() if k == "room"})
    if total is not None:
        # Split what the total leaves over between the fields the user didn't give, in the default proportions.
        missing = [k for k in ("linked", "meds_implants") if k not in given]
        rest = max(total - b["room"] - sum(v for k, v in given.items() if k != "room"), 0)
        weights = {"linked": d[1], "meds_implants": d[2]}
        for i, k in enumerate(missing):
            share = rest if i == len(missing) - 1 else r(Decimal(rest) * weights[k] / sum(weights[m] for m in missing))
            b[k], rest = share, rest - share
    b.update(given)
    return b, max(days, 1)


DEFAULT_KEYS = ("room", "linked", "meds_implants", "other")


SPECIFIC_WAIT = {"cataract": 24, "hernia": 24, "joint_replacement": 48}


def step(name, label, before, after, c):
    return {"step": name, "label": label, "before": before, "after": after, "clause": c["clause"], "page": c["page"]}


NO_CLAUSE = {"clause": "—", "page": None}


def run_ui(pid, profile, cat, accident, ped, bill, days, *, skip_waits=False, skip_initial=False, rent_override=None):
    """Simplified version of the United India rules. Returns (verdict, payout, trace, cites, reason_code)."""
    si = int(profile["sum_insured"])
    pam = int(profile["policy_age_months"])
    plan = plan_for_age(int(profile["insured_age"]))
    billed = sum(bill.values())
    trace, used = [], []

    def deny(name, label, key, code):
        c = cite(pid, key)
        used.append(key)
        trace.append(step(name, label, billed, 0, c))
        trace.append(step("total", "Payable", billed, 0, NO_CLAUSE))
        return "NOT_COVERED", 0, trace, used, code

    if plan is None:
        return "NEEDS_REVIEW", None, [], [], "age"
    waits = plan != "Platinum" and not skip_waits
    if not accident and pam < 1 and not skip_waits and not skip_initial:
        return deny("waiting_initial", f"Illness in the first 30 days of the policy ({pam} months old)", "waiting_initial", "initial")
    if cat == "cosmetic":
        return deny("exclusion", "Cosmetic surgery is excluded", "exclusion_8", "exclusion")
    if cat == "maternity":
        return deny("exclusion", "Maternity / childbirth expenses are excluded", "exclusion_18", "exclusion")
    if waits and ped is True and pam < 48:
        return deny("waiting_ped", f"Pre-existing condition: 48-month wait, policy is {pam} months old", "waiting_ped", "ped")
    if waits and ped is None and pam < 48:
        return "NEEDS_REVIEW", None, [], ["waiting_ped"], "ped_unknown"
    if waits and cat in SPECIFIC_WAIT and not accident and pam < SPECIFIC_WAIT[cat]:
        mo = SPECIFIC_WAIT[cat]
        return deny("waiting_specific", f"{cat.replace('_', ' ').capitalize()}: {mo}-month waiting period, policy is {pam} months old",
                    "waiting_specific", f"wait{mo}")

    room, linked, meds, other = bill["room"], bill["linked"], bill["meds_implants"], bill["other"]
    cap = r(si * Decimal("0.01"))
    rent = Decimal(rent_override if rent_override is not None else Decimal(room) / days)
    if rent_override is not None:
        room = r(rent * days)
    c_room, c_prop = cite(pid, "room_rent"), cite(pid, "proportionate")
    used.append("room_rent")
    if rent > cap:
        ratio = Decimal(cap) / rent
        room_after = cap * days
        linked_after = r(linked * ratio)
        trace.append(step("room_rent", f"Room: {days} days × {inr(cap)} cap (actual {inr(r(rent))}/day)", room, room_after, c_room))
        trace.append(step("proportionate", f"Associated charges × {float(ratio * 100):.1f}% (cap ÷ actual)", linked, linked_after, c_prop))
        used.append("proportionate")
    else:
        room_after, linked_after = room, linked
        trace.append(step("room_rent", f"Room: {days} days at {inr(r(rent))}/day (within {inr(cap)} cap)", room, room, c_room))
        trace.append(step("linked", "Associated charges (not reduced)", linked, linked, NO_CLAUSE))
    trace.append(step("meds_implants", "Medicines & implants (not reduced)", meds, meds, NO_CLAUSE))
    if other:
        trace.append(step("other", "Other charges", other, other, NO_CLAUSE))
    subtotal = room_after + linked_after + meds + other
    lim, key = None, None
    if plan != "Platinum":
        if cat == "cataract":
            lim, key = min(r(si * Decimal("0.25")), 40000), "sublimit_cataract"
        elif cat == "hernia":
            lim, key = min(r(si * Decimal("0.25")), 100000), "sublimit_hernia"
        elif cat == "joint_replacement":
            lim, key = r(si * Decimal("0.70")), "sublimit_major_surgery"
    if lim is not None and subtotal > lim:
        trace.append(step("sublimit", f"{cat.replace('_', ' ').capitalize()} sub-limit {inr(lim)}", subtotal, lim, cite(pid, key)))
        used.append(key)
        subtotal = lim
    if subtotal > si:
        trace.append(step("sum_insured", f"Capped at sum insured {inr(si)}", subtotal, si, NO_CLAUSE))
        subtotal = si
    payout = subtotal
    trace.append(step("total", "Payable", billed, payout, NO_CLAUSE))
    verdict = "NOT_COVERED" if payout == 0 else "COVERED" if payout >= billed else "PARTIAL"
    code = "room" if rent > cap else ("sublimit" if lim is not None and key in used else "ok")
    return verdict, payout, trace, used, code


def run_demo(pid, profile, cat, accident, ped, bill, days, *, skip_waits=False, skip_initial=False, rent_override=None):
    pam = int(profile["policy_age_months"])
    billed = sum(bill.values())
    if rent_override is not None:
        bill = {**bill, "room": r(Decimal(rent_override) * days)}
        billed = sum(bill.values())
    if not accident and pam < 1 and not skip_waits and not skip_initial:
        c = cite(pid, "waiting_initial")
        return "NOT_COVERED", 0, [step("waiting_initial", "Illness in the first 30 days", billed, 0, c),
                                   step("total", "Payable", billed, 0, NO_CLAUSE)], ["waiting_initial"], "initial"
    trace = [step("bill", "Admissible bill (no room cap)", billed, billed, cite(pid, "room_rent"))]
    amount, used = billed, ["room_rent", "copay"]
    if cat == "maternity" and amount > 50000:
        trace.append(step("sublimit", "Maternity sub-limit ₹50,000", amount, 50000, cite(pid, "sublimit_maternity")))
        amount, used = 50000, used + ["sublimit_maternity"]
    after = r(Decimal(amount) * Decimal("0.8"))
    trace.append(step("copay", "Co-payment 20%", amount, after, cite(pid, "copay")))
    trace.append(step("total", "Payable", billed, after, NO_CLAUSE))
    return ("PARTIAL" if after < billed else "COVERED"), after, trace, used, "copay"


def unique_cites(pid: str, keys: list[str]) -> list[dict]:
    seen, out = set(), []
    for k in keys:
        if k not in seen:
            seen.add(k)
            out.append(cite(pid, k))
    return out


def evaluate(pid: str, profile: dict, text: str, bill_in: dict | None, answers: dict, *, skip_initial=False) -> dict:
    p = policy_entry(pid)
    cat = detect_category(text)
    bill, days = build_bill(cat, text, bill_in, answers)
    billed = sum(bill.values())
    if not p["computable"]:
        return {
            "verdict": "NEEDS_REVIEW", "billed": billed, "payout": None,
            "trace": [step("room_rent", "Associated charges depend on the 'entitled' room tariff (not computed)", billed, None,
                           cite(pid, "proportionate"))],
            "citations": unique_cites(pid, ["proportionate", "room_rent"]), "counterfactuals": [],
            "why": "This policy pays associated charges at the rate of the room category you are entitled to, and that "
                   "depends on the hospital's tariff for each room type. We can't compute it from your bill, so we won't guess.",
            "next_steps": ["Ask the hospital's insurance desk for the tariff of your entitled room category",
                           "Request a cashless pre-authorisation estimate from the insurer"],
            "abstain_reason": p["computable_note"], "disclaimer": DISCLAIMER,
        }
    ped = answers["ped"] if "ped" in answers else (None if is_unsure(text) else profile.get("ped"))
    accident = is_accident(text)
    run = run_demo if engine_for(pid) == "demo" else run_ui
    kw = dict(skip_initial=skip_initial)
    verdict, payout, trace, used, code = run(pid, profile, cat, accident, ped, bill, days, **kw)
    cap = r(int(profile["sum_insured"]) * Decimal("0.01"))

    cfs = []

    def cf(change, **extra):
        v2, pay2, *_ = run(pid, profile, cat, accident, extra.pop("ped", ped), bill, days, **{**kw, **extra})
        if pay2 is None:
            return
        cfs.append({"change": change, "new_payout": pay2, "delta": None if payout is None else pay2 - payout})

    if code == "age":
        why = f"Age {profile['insured_age']} is outside this policy's plan bands (18–65), so we can't tell which rules apply."
        steps_ = ["Check the plan on your policy schedule with the insurer"]
        abstain = "The insured's age does not map to a plan (Platinum 18–35, Gold 36–60, Senior Citizen 61–65)."
        return {"verdict": "NEEDS_REVIEW", "billed": billed, "payout": None, "trace": [], "citations": [],
                "counterfactuals": [], "why": why, "next_steps": steps_, "abstain_reason": abstain, "disclaimer": DISCLAIMER}
    if code == "ped_unknown":
        cf("If the condition started after the policy began (not pre-existing)", ped=False)
        cf("If it was diagnosed before the policy started (pre-existing)", ped=True)
        return {
            "verdict": "NEEDS_REVIEW", "billed": billed, "payout": None,
            "trace": [step("waiting_ped", "Pre-existing status unknown: 48-month exclusion may apply", billed, None, cite(pid, "waiting_ped"))],
            "citations": unique_cites(pid, ["waiting_ped"]), "counterfactuals": cfs,
            "why": "Whether this is paid depends on whether the condition existed before the policy started. "
                   "You said you weren't sure, so we won't guess.",
            "next_steps": ["Check old prescriptions or reports for when the condition was first diagnosed",
                           "Ask the treating doctor to note the date of first diagnosis on the discharge summary",
                           "Ask the insurer's TPA to confirm before you rely on this estimate"],
            "abstain_reason": "Pre-existing-disease status is unknown, and it decides whether the 48-month exclusion applies.",
            "disclaimer": DISCLAIMER,
        }
    if code == "room":
        cf(f"Choose a room within {inr(cap)}/day", rent_override=cap)
        why = (f"Your room costs more than the policy's daily cap of {inr(cap)}, so the room is paid at the cap and "
               "associated charges are reduced in the same proportion.")
        steps_ = ["Ask the hospital for an itemised bill",
                  f"Request pre-authorisation for a room within {inr(cap)}/day next time"]
    elif code.startswith("wait"):
        cf(f"If the {code[4:]}-month waiting period had already passed", skip_waits=True)
        why = f"This procedure has a {code[4:]}-month waiting period and your policy is {profile['policy_age_months']} months old, so it is not payable yet."
        steps_ = [f"Plan the procedure after month {code[4:]} of continuous cover if it is medically safe to wait",
                  "If you had earlier continuous cover elsewhere, ask about portability credit"]
    elif code == "ped":
        cf("If the condition was not pre-existing", ped=False)
        why = "The condition existed before the policy started, and pre-existing conditions are excluded for 48 months."
        steps_ = ["Check whether the condition was declared on the proposal form", "Ask the insurer about portability credit"]
    elif code == "initial":
        cf("If the claim were after the 30-day initial waiting period", skip_waits=True)
        why = "Illness claims in the first 30 days of a new policy are excluded."
        steps_ = ["Accidents are covered from day one; illness claims are covered after 30 days"]
    elif code == "exclusion":
        why = "This treatment is on the policy's list of permanent exclusions."
        steps_ = ["Check whether a rider or a different policy covers it"]
    elif code == "copay":
        why = "The policy pays 80% of the admissible bill; you pay a 20% co-payment."
        steps_ = ["Keep all bills and the discharge summary for the reimbursement claim"]
    elif code == "sublimit":
        why = f"The policy caps this procedure at a fixed sub-limit, so the payout is {inr(payout)}."
        steps_ = ["Ask the hospital for a package rate within the sub-limit"]
    else:
        why = "Your room is within the cap and no waiting period or exclusion applies, so the full bill is payable."
        steps_ = ["Submit the itemised bill and discharge summary within the claim deadline"]
    return {"verdict": verdict, "billed": billed, "payout": payout, "trace": trace,
            "citations": unique_cites(pid, used), "counterfactuals": cfs, "why": why, "next_steps": steps_,
            "abstain_reason": None, "disclaimer": DISCLAIMER}


def needs_info(text: str, bill: dict | None, answers: dict, profile: dict) -> list[dict] | None:
    has_bill = bool(bill) and any(v not in (None, "", 0) for v in bill.values())
    qs = []
    if not has_bill and not answers and not re.search(r"\d", text):
        qs += [
            {"field": "bill.room", "question": "What were the total room charges?", "type": "number"},
            {"field": "bill.linked", "question": "How much were doctor, OT, nursing and test charges?", "type": "number"},
            {"field": "bill.meds_implants", "question": "How much of the bill was medicines and implants?", "type": "number"},
        ]
    if profile.get("ped") is True and "ped" not in answers:
        qs.append({"field": "ped", "question": "Was this condition diagnosed before the policy started?", "type": "boolean"})
    return qs or None


@app.post("/claims/check")
async def check_claim(request: Request):
    body = await request.json()
    ids = body.get("policy_ids") or ([body["policy_id"]] if body.get("policy_id") else [])
    if not ids:
        return err(400, "policy_id or policy_ids is required")
    for pid in ids:
        if not policy_entry(pid):
            return err(404, "unknown_policy")
    text = body.get("incident_text") or ""
    profile = body.get("profile") or {}
    answers = body.get("answers") or {}
    bill = body.get("bill")
    await think()
    if "llm down" in text.lower():
        return err(503, "llm_unavailable", "Mock: Gemini quota exhausted and Groq unavailable")
    qs = needs_info(text, bill, answers, profile)
    if qs and any(q["field"].startswith("bill.") for q in qs):
        # Amounts don't matter when the claim is refused or abstained anyway: skip the bill questions.
        probe = evaluate(ids[0], profile, text, None, {**answers, "ped": answers.get("ped", False)})
        if probe["verdict"] in ("NOT_COVERED", "NEEDS_REVIEW") or is_unsure(text):
            qs = [q for q in qs if not q["field"].startswith("bill.")]
    if qs:
        return {"status": "needs_info", "questions": qs, "meta": meta()}

    results = []
    for pid in ids:
        p = policy_entry(pid)
        results.append({"policy_id": pid, "name": p["name"], "computable": p["computable"],
                        "verdict": evaluate(pid, profile, text, bill, answers)})
    resp = {"status": "done", "verdict": results[0]["verdict"], "meta": meta()}
    if len(ids) >= 2:
        resp["comparison"] = compare(results)
        rec = resp["comparison"]["recommended_policy_id"]
        if rec:
            resp["verdict"] = next(x["verdict"] for x in results if x["policy_id"] == rec)
    return resp


def compare(results: list[dict]) -> dict:
    payable = [x for x in results if x["computable"] and x["verdict"]["payout"] is not None]
    payable.sort(key=lambda x: x["verdict"]["payout"], reverse=True)
    if not payable:
        return {"results": results, "recommended_policy_id": None,
                "recommendation_reason": "None of these policies could be computed for this claim; ask each insurer for a pre-authorisation estimate.",
                "combined": None}
    best = payable[0]
    if len(payable) == 1:
        reason = f"Only {best['name']} could be computed for this claim; it pays {inr(best['verdict']['payout'])}."
    else:
        diff = best["verdict"]["payout"] - payable[1]["verdict"]["payout"]
        reason = (f"Pays {inr(diff)} more than {payable[1]['name']} for this claim."
                  if diff > 0 else "Both pay the same for this claim; pick the one with the simpler claim process.")
    combined = None
    positive = [x for x in payable if x["verdict"]["payout"] > 0]
    if len(positive) >= 2:
        billed = best["verdict"]["billed"]
        left, split = billed, []
        for x in positive:
            pay = min(x["verdict"]["payout"], left)
            split.append({"policy_id": x["policy_id"], "payout": pay})
            left -= pay
        combined = {"possible": True, "total_payout": billed - left, "split": split,
                    "note": "Indemnity policies can often be claimed together up to the actual loss; the second insurer pays "
                            "against the balance. Estimate only — confirm each insurer's other-insurance clause."}
    return {"results": results, "recommended_policy_id": best["policy_id"], "recommendation_reason": reason,
            "combined": combined}


# ---------------------------------------------------------------- recommender

RECO_TEXT = {"appendectomy": "appendix surgery, 3 days", "cataract": "cataract surgery, one eye",
             "hernia": "hernia repair, 3 days", "joint_replacement": "knee replacement, 5 days",
             "maternity": "maternity delivery, 3 days"}


@app.post("/policies/recommend")
async def recommend(request: Request):
    body = await request.json()
    profile = dict(body.get("profile") or {})
    claims = body.get("likely_claims") or []
    if not claims:
        return err(400, "likely_claims must not be empty")
    bills = body.get("assumed_bills") or {}
    premiums = body.get("annual_premiums") or {}
    ids = body.get("policy_ids") or list(POLICIES) + list(UPLOADS)
    for pid in ids:
        if not policy_entry(pid):
            return err(404, "unknown_policy")
    await think()
    rent = int(profile.get("preferred_room_rent_per_day") or 0)
    ranked = []
    for pid in ids:
        p = policy_entry(pid)
        if not p["computable"]:
            ranked.append({"policy_id": pid, "name": p["name"], "computable": False, "score": None, "scenario_results": [],
                           "reasons": [{"text": p["computable_note"], **cite(pid, "proportionate")}], "premium_note": None})
            continue
        sr, tot_b, tot_p = [], 0, 0
        for cat in claims:
            d = DEFAULT_BILLS.get(cat, DEFAULT_BILLS["other"])
            days = d[4]
            room = rent * days if rent else d[0]
            linked, meds = d[1], d[2]
            if cat in bills and bills[cat]:
                total = int(bills[cat])
                rest = max(total - room, 0)
                linked = r(Decimal(rest) * Decimal(d[1]) / Decimal(d[1] + d[2]))
                meds = rest - linked
            bill = {"room": room, "linked": linked, "meds_implants": meds, "other": 0}
            v = evaluate(pid, profile, f"{RECO_TEXT.get(cat, cat)}", {k: v for k, v in bill.items()}, {"ped": False},
                         skip_initial=True)
            row = {"category": cat, "billed": v["billed"], "payout": v["payout"], "verdict": v["verdict"]}
            if v["verdict"] == "NOT_COVERED":
                row["note"] = v["trace"][0]["label"] if v["trace"] else v["why"]
            sr.append(row)
            tot_b += v["billed"] or 0
            tot_p += v["payout"] or 0
        score = r(Decimal(100 * tot_p) / Decimal(tot_b)) if tot_b else 0
        if engine_for(pid) == "demo":
            reasons = [{"text": "No room-rent cap, but a 20% co-payment on every claim", **cite(pid, "copay")},
                       {"text": "No specified-disease waiting periods", **cite(pid, "waiting_specific")}]
        else:
            reasons = [{"text": "Room cap is 1% of sum insured per day with proportionate payment", **cite(pid, "proportionate")},
                       {"text": "24-month wait for cataract/hernia and 48 months for joint replacement on a new policy",
                        **cite(pid, "waiting_specific")},
                       {"text": "No co-payment", **cite(pid, "copay")}]
        prem = premiums.get(pid)
        note = (f"{inr(int(prem))}/yr → simulated payout across your likely claims per ₹ of premium: {tot_p / int(prem):.1f}"
                if prem else None)
        part = {"payout": r(Decimal(score) * Decimal("0.7")), "waiting": r(Decimal(score) * Decimal("0.1")),
                "copay": r(Decimal(score) * Decimal("0.1")), "room_cap": r(Decimal(score) * Decimal("0.05"))}
        part["exclusions"] = score - sum(part.values())
        ranked.append({"policy_id": pid, "name": p["name"], "computable": True, "score": score, "scenario_results": sr,
                       "reasons": reasons, "premium_note": note, "score_breakdown": part, "total_simulated_payout": tot_p})
    ranked.sort(key=lambda x: (x["score"] is None, -(x["score"] or 0)))
    best = ranked[0]["policy_id"] if ranked and ranked[0]["score"] is not None else None
    assumptions = [
        "A newly bought policy: claims are simulated in the first policy year, after the 30-day initial wait",
        f"Room charged at your preferred {inr(rent)}/day for a typical stay" if rent else "Room charges from a typical bill",
        "Bill sizes are illustrative (override with your own estimates)" if len(bills) < len(claims) else "Bill sizes are the ones you entered",
        "Premiums were not read from the policy documents" + (" (only the ones you entered are used)" if premiums else ""),
        "Score = simulated payout ÷ simulated bills across your likely claims, × 100",
        "Mock server: fixture rules, not the real engine",
    ]
    return {"ranked": ranked, "best_policy_id": best,
            "why": "Highest simulated payout across the claims you said are likely, given waiting periods for a new policy."
            if best else "No policy could be computed for these claims.",
            "assumptions": assumptions,
            "disclaimer": "This compares coverage terms for the claims you listed. It is not financial advice and does not "
                          "consider premiums unless you entered them.",
            "meta": meta()}


# ---------------------------------------------------------------- eval + mock controls

@app.post("/policies/{policy_id}/ask")
async def ask(policy_id: str, request: Request):
    p = policy_entry(policy_id)
    if not p:
        return err(404, "unknown_policy")
    body = await request.json()
    q = str(body.get("question", "")).strip()
    if not q:
        return err(400, "question is required")
    await think(0.5, 1.5)
    ql = q.lower()
    if any(w in ql for w in ("how much", "will i get", "payout", "estimate")):
        return {"answer": "I can explain the rules, but only the claim estimator computes payouts. Use the What happened screen.",
                "citations": [], "needs_calculation": True, "out_of_scope": False, "note": None, "meta": meta()}
    words = set(re.findall(r"[a-z]{4,}", ql))
    best, score = None, 0
    for it in p["summary_items"]:
        sc = len(words & set(re.findall(r"[a-z]{4,}", (it["label"] + " " + it["summary"]).lower())))
        if sc > score:
            best, score = it, sc
    if not best:
        return {"answer": "This is not stated in the policy document. (Mock server: keyword matching only.)", "citations": [],
                "needs_calculation": False, "out_of_scope": False, "note": None, "meta": meta()}
    return {"answer": f"{best['label']}: {best['summary']}. (Mock server: keyword matching only.)",
            "citations": [{"clause": best["clause"], "page": best["page"], "quote": best["quote"], "verified": True}],
            "needs_calculation": False, "out_of_scope": False, "note": None, "meta": meta()}


@app.get("/eval/latest")
async def eval_latest():
    if SETTINGS["no_report"]:
        return err(404, "no_report")
    return EVAL_REPORT


@app.get("/mock/settings")
async def mock_settings(no_report: int | None = None, latency: float | None = None):
    if no_report is not None:
        SETTINGS["no_report"] = bool(no_report)
    if latency is not None:
        SETTINGS["latency"] = latency
    return SETTINGS


@app.get("/")
async def root():
    return {"service": "PoliSure mock API", "docs": "/docs", "note": MOCK_META_NOTE}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
