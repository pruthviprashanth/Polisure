"""'why' and next steps. The LLM may only phrase text from the engine trace; any ₹ figure not in the trace falls back to a template."""
from __future__ import annotations

import re

from pydantic import BaseModel

from . import config, llm
from .present import inr
from .schemas import Verdict

SYSTEM = """You explain an insurance claim estimate to a layperson in plain English. You are given the computed result (verdict, payout, calculation trace). Write `why`: 2-3 short sentences explaining the result using ONLY the facts and rupee figures in the data. Write `next_steps`: 2-4 short practical actions. Never introduce a rupee amount that is not in the data. Never change the verdict or payout."""


class ExplainLLM(BaseModel):
    why: str
    next_steps: list[str]


def template(v: Verdict, extra_note: str = "") -> tuple[str, list[str]]:
    steps = [t for t in v.trace if t.step != "total"]
    if v.verdict == "NEEDS_REVIEW":
        return (f"A reliable estimate was not possible: {v.abstain_reason}",
                ["Ask the insurer or TPA to confirm coverage for this claim", "Keep the policy wording and the itemised hospital bill ready"])
    if v.verdict == "NOT_COVERED":
        reason = steps[0].label if steps else "the policy does not cover this claim"
        return (f"This claim is estimated as not payable: {reason}.",
                ["Ask the insurer to confirm in writing which clause applies", "Check whether any waiting period will end soon so a later claim could be payable"])
    if v.verdict == "COVERED":
        return (f"The estimated payout is {inr(v.payout)}, the full billed amount of {inr(v.billed)}; no reductions apply.",
                ["Submit the itemised bill and discharge summary", "Use a cashless admission at a network hospital if possible"])
    cuts = [t for t in steps if t.before is not None and t.after is not None and t.after < t.before]
    why = f"Of {inr(v.billed)} billed, the estimated payout is {inr(v.payout)}."
    if cuts:
        why += " Reductions: " + "; ".join(f"{t.label} ({inr(t.before)} → {inr(t.after)})" for t in cuts[:3]) + "."
    nxt = ["Ask the hospital for an itemised bill", "Request pre-authorisation before planned admissions"]
    if any(t.step in ("room_rent", "proportionate") for t in cuts):
        nxt.insert(1, "Choose a room within the policy's daily cap next time to avoid proportionate cuts")
    return why, nxt


def _allowed_numbers(v: Verdict) -> set[int]:
    s = {v.billed, v.payout}
    for t in v.trace:
        s.update({t.before, t.after})
        s.update(int(n.replace(",", "")) for n in re.findall(r"₹\s?([\d,]+)", t.label))
    for c in v.counterfactuals:
        s.update({c.new_payout, c.delta})
    return {x for x in s if x is not None}


def guarded(text: str, allowed: set[int]) -> bool:
    for m in re.findall(r"(?:₹|Rs\.?)\s?([\d,]+(?:\.\d+)?)", text):
        try:
            n = int(float(m.replace(",", "")))
        except ValueError:
            return False
        if n not in allowed:
            return False
    return True


def explain(v: Verdict) -> tuple[str, list[str], str]:
    """Returns (why, next_steps, provider)."""
    why, steps = template(v)
    if config.llm_mode() == "mock" or v.verdict == "NEEDS_REVIEW":
        return why, steps, "mock" if config.llm_mode() == "mock" else ""
    payload = v.model_dump_json(include={"verdict", "billed", "payout", "trace", "counterfactuals", "abstain_reason"})
    try:
        obj, prov = llm.extract(ExplainLLM, SYSTEM, payload, purpose="explain", can_fallback=True, max_out=500)
    except llm.LLMUnavailable:
        return why, steps, ""
    allowed = _allowed_numbers(v)
    if obj.why.strip() and guarded(obj.why + " " + " ".join(obj.next_steps), allowed):
        return obj.why.strip(), [s for s in obj.next_steps if s.strip()][:4] or steps, prov
    return why, steps, ""
