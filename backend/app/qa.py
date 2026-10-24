"""Grounded policy Q&A. The LLM answers only from the policy text and must quote it; code verifies the quotes.

It never computes payouts: money questions are redirected to the claim estimator (the deterministic engine).
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field

from . import config, extraction, llm
from .schemas import CoverageModel

SYSTEM = """You answer questions about ONE health-insurance policy, using ONLY the policy text provided (pages are marked [[PAGE n]]).
Rules:
- Answer in 2-5 plain sentences for a layperson. If the policy does not say, answer exactly that it is not stated in this document. Never use outside knowledge about the insurer or other policies.
- Support every factual claim with entries in `citations`: `page` (from the [[PAGE n]] marker), `clause` (id as printed, or empty) and `quote` copied EXACTLY and verbatim from the text, at most 200 characters, no ellipses.
- Do not add caveats, conditions or exceptions that are not supported by one of your quotes.
- Only state rupee amounts, percentages and durations that appear in the policy text.
- Do NOT calculate what a specific claim would pay. If the user asks what they would receive, whether a particular bill is payable, or asks for a rupee estimate, set needs_calculation=true and tell them to use the claim estimator, optionally explaining the relevant rule in words.
- If the question is unrelated to this policy or health insurance cover, set out_of_scope=true and say so briefly.
- Do not give legal, medical or financial advice."""


class CiteLLM(BaseModel):
    page: int = 0
    clause: str = ""
    quote: str = ""


class AnswerLLM(BaseModel):
    answer: str
    citations: list[CiteLLM] = Field(default_factory=list)
    needs_calculation: bool = False
    out_of_scope: bool = False


# ---------------------------------------------------------------- mock handler (keyword retrieval over the prompt text)
_STOP = set("the a an of to in is are do does what how my i me for on and or if it be can will with this that about policy cover covered".split())


def mock_qa(system: str, user: str) -> dict:
    q = re.search(r"QUESTION:\s*(.*)\Z", user, re.S)
    question = (q.group(1) if q else "").lower()
    words = {w for w in re.findall(r"[a-z]{3,}", question) if w not in _STOP}
    if re.search(r"how much|will i get|would it pay|payout|estimate", question):
        return {"answer": "I can explain the rules, but only the claim estimator computes payouts. Use the 'What happened' screen for a figure.",
                "needs_calculation": True}
    best, best_score = None, 0
    body = user.split("QUESTION:")[0]
    for m in re.finditer(r"\[\[PAGE (\d+)\]\](.*?)(?=\[\[PAGE|\Z)", body, re.S):
        page = int(m.group(1))
        lines = [l.strip() for l in m.group(2).splitlines() if len(l.strip()) > 25]
        for i in range(len(lines)):
            chunk = " ".join(lines[i:i + 2])
            score = len(words & set(re.findall(r"[a-z]{3,}", chunk.lower())))
            if score > best_score:
                best, best_score = (page, lines[i][:200]), score
    if not best or best_score < 2:
        return {"answer": "This is not stated in the policy document.", "citations": []}
    return {"answer": f"The most relevant wording I found (page {best[0]}) is quoted below.",
            "citations": [{"page": best[0], "clause": "", "quote": best[1]}]}


llm.register_mock("qa", mock_qa)


# ---------------------------------------------------------------- helpers
def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def _figures_grounded(answer: str, source_numbers: set[str]) -> bool:
    for m in re.findall(r"(?:₹|Rs\.?)\s?(\d[\d,]*(?:\.\d+)?)", answer):
        if m.replace(",", "").rstrip(".") not in source_numbers:
            return False
    return True


def _verify(c: CiteLLM, npages: list[str]) -> Optional[dict]:
    q = extraction.norm(c.quote)
    if not q:
        return None
    order = ([c.page] + [p for p in (c.page - 1, c.page + 1)] if 1 <= c.page <= len(npages) else []) + list(range(1, len(npages) + 1))
    seen = set()
    for p in order:
        if p in seen or not (1 <= p <= len(npages)):
            continue
        seen.add(p)
        if q in npages[p - 1]:
            return {"clause": c.clause, "page": p, "quote": c.quote.strip(), "verified": True}
    return None


def ask(cov: CoverageModel, question: str, history: Optional[list[dict]] = None) -> dict:
    pdf = config.ROOT / cov.pdf_path if cov.pdf_path else None
    if not pdf or not pdf.exists():
        raise FileNotFoundError("policy PDF not available")
    pages = extraction.read_pages(pdf.read_bytes())
    text = extraction.pages_text(pages)
    hist = ""
    for h in (history or [])[-4:]:
        role = "User" if h.get("role") == "user" else "Assistant"
        hist += f"{role}: {str(h.get('content', ''))[:400]}\n"
    user = f"POLICY: {cov.name}\n\n{text}\n\n" + (f"EARLIER CHAT:\n{hist}\n" if hist else "") + f"QUESTION: {question.strip()[:600]}"
    obj, prov = llm.extract(AnswerLLM, SYSTEM, user, can_fallback=False, purpose="qa", max_out=900)

    npages = [extraction.norm(p) for p in pages]
    cites = [v for v in (_verify(c, npages) for c in obj.citations[:5]) if v]
    answer = obj.answer.strip()
    out = {"answer": answer, "citations": cites, "needs_calculation": obj.needs_calculation,
           "out_of_scope": obj.out_of_scope, "note": None}
    src = _numbers(text) | _numbers(question)
    if not _figures_grounded(answer, src):
        out["answer"] = ("I could not confirm the figures in my draft answer against the policy text, so I will not state them. "
                         "Please open the cited pages or use the claim estimator for amounts.")
        out["note"] = "figure_guard"
    elif not cites and not (obj.out_of_scope or obj.needs_calculation) and "not stated" not in answer.lower():
        out["note"] = "no_verified_quote"
        out["answer"] = answer + " (No exact policy quote could be verified for this answer, so treat it with caution.)"
    out["meta"] = {"cached": prov == "cache", "providers_used": [prov], "model_note": None}
    return out
