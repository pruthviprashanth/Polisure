"""PDF -> pages -> CoverageModel (LLM) -> quote verification. Results are cached by PDF hash."""
from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Iterator

import pymupdf
from rapidfuzz import fuzz

from . import config, llm
from .schemas import Category, Cite, CoverageExtract, CoverageModel

PROMPT = """You are a careful health-insurance policy analyst. Read the policy text (pages are marked [[PAGE n]]) and fill the JSON schema.

Rules:
- Use ONLY what the document says. If a rule is absent, leave that field null / empty. Never invent clauses.
- For EVERY rule give `clause` (the clause/code id as printed, e.g. 'III.A.1.i', '9.A.1', 'Excl02'), `page` (the number in the [[PAGE n]] marker of the page where the quote appears) and `quote`: text copied EXACTLY, verbatim and contiguous from the document, at most 220 characters, no ellipses, no paraphrase.
- room_rent: kind=percent_si with value=percent of sum insured per day (icu_value for ICU) or kind=fixed (rupees/day). Use kind=any ONLY if the document explicitly says there is no limit (actual expenses / any room category). If the wording merely lists room rent as covered, or says the limit is in the policy schedule, use kind=unknown. Set computable=false if the limit depends on hospital tariffs, 'entitled category' or similar and cannot be worked out from the sum insured alone.
- proportionate: applies=true if exceeding the room limit reduces other associated expenses proportionately; applies_to lists which buckets are reduced: 'linked' (doctor fees, OT, room-category linked charges, investigations), 'meds_implants' (only if the policy says medicines/implants are also reduced), 'other'. Default to ['linked'].
- copay: percent (0 if 'Not Applicable'); applies_when='always', 'non_network' (only non-network hospitals) or 'other'.
- waiting_initial (days), waiting_ped (months), specific_waits: one entry per listed disease/procedure with months. category must be one of the enum when it fits (cataract, hernia, joint_replacement, ...); otherwise use 'other' AND put lowercase keywords (e.g. ['piles','fistula']) so code can match the diagnosis text.
- sublimits: monetary caps per disease/procedure. pct_si = percent of sum insured, limit_inr = rupee cap (the lower of the two applies), per='eye'|'claim'|'year'. Same category/keywords rule.
- exclusions: permanent exclusions (one per item, up to 25). category when it fits the enum, else 'other' with keywords.
- plans: age bands per plan if the policy has plans. waiting_plans / sublimit_plans: the plan names those rules apply to ('Only applicable for Gold & Senior Citizen' -> ['Gold','Senior Citizen']); empty list = applies to all.
- sublimits: ONLY caps on in-patient treatment of a disease/procedure. Do NOT list ambulance, health check-up, pre/post-hospitalisation, domiciliary or daily-cash limits.
- unmodeled_terms: ONLY terms that change the payout of an ordinary in-patient claim and that a simple calculator cannot handle: an excess/deductible per claim, per-illness sub-caps on room/doctor/other charges, tariff-based or 'entitled category' room limits. Do NOT list pre/post-hospitalisation, domiciliary, ambulance, optional covers, or anything already captured in other fields. Empty list if none. One short string each.
- deduction_order: always return exactly ["sublimit","room_rent","copay","sum_insured"].
Category enum: appendectomy, cataract, hernia, joint_replacement, maternity, cosmetic, dental, infertility, accident_trauma, other, unknown."""


def read_pages(pdf_bytes: bytes) -> list[str]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    return [p.get_text() for p in doc]


def pdf_id(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:12]


def pages_text(pages: list[str], start: int = 1, end: int | None = None) -> str:
    end = end or len(pages)
    return "\n".join(f"[[PAGE {i}]]\n{pages[i - 1]}" for i in range(start, end + 1))


# ---------------------------------------------------------------- verifier
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("‘", "'").replace("’", "'").replace("“", '"').replace("”", '"')
    s = re.sub(r"-\s*\n\s*", "", s)
    s = s.lower()
    return re.sub(r"\s+", " ", s).strip()


def _found(q: str, page_text: str) -> bool:
    if not q:
        return False
    if q in page_text:
        return True
    if len(q) < 12:
        return False
    return fuzz.partial_ratio(q, page_text) >= 90


def iter_cites(obj) -> Iterator[Cite]:
    if isinstance(obj, Cite):
        yield obj
    if hasattr(type(obj), "model_fields"):
        for name in type(obj).model_fields:
            yield from iter_cites(getattr(obj, name))
    elif isinstance(obj, list):
        for x in obj:
            yield from iter_cites(x)


def verify(model: CoverageExtract, pages: list[str]) -> None:
    """Set `verified` on every cite; correct the page if the quote is on another page."""
    npages = [norm(p) for p in pages]
    for c in iter_cites(model):
        q = norm(c.quote)
        c.verified = False
        if not q:
            continue
        order = []
        if 1 <= c.page <= len(npages):
            order += [c.page] + [p for p in (c.page - 1, c.page + 1) if 1 <= p <= len(npages)]
        order += [p for p in range(1, len(npages) + 1) if p not in order]
        for p in order:
            if _found(q, npages[p - 1]):
                c.page, c.verified = p, True
                break


# ---------------------------------------------------------------- extraction
def _merge(parts: list[CoverageExtract]) -> CoverageExtract:
    out = parts[0].model_copy(deep=True)
    for p in parts[1:]:
        for f in ("room_rent", "proportionate", "copay", "waiting_initial", "waiting_ped"):
            cur, new = getattr(out, f), getattr(p, f)
            if new is not None and (cur is None or (not cur.verified and new.verified)):
                setattr(out, f, new)
        for f in ("specific_waits", "sublimits", "exclusions", "plans", "unmodeled_terms"):
            seen = {repr(x.model_dump()) for x in getattr(out, f)} if f != "unmodeled_terms" else set(out.unmodeled_terms)
            for x in getattr(p, f):
                k = repr(x.model_dump()) if f != "unmodeled_terms" else x
                if k not in seen:
                    getattr(out, f).append(x)
                    seen.add(k)
        for f in ("waiting_plans", "sublimit_plans"):
            for x in getattr(p, f):
                if x not in getattr(out, f):
                    getattr(out, f).append(x)
        out.name = out.name or p.name
    return out


def extract_coverage(pages: list[str], purpose: str = "coverage") -> tuple[CoverageExtract, list[str]]:
    """One call if the text fits Gemini's TPM budget, else chunk by page range and merge."""
    tpm = config.env_int("GEMINI_TPM", 100000)
    max_out = 8192
    budget_chars = int((tpm - max_out - 2000) * 3.5 * 0.8)
    full = pages_text(pages)
    if len(full) <= budget_chars:
        obj, prov = llm.extract(CoverageExtract, PROMPT, full, can_fallback=False, purpose=purpose, max_out=max_out)
        return obj, [prov]
    chunks, start, size = [], 1, 0
    for i, p in enumerate(pages, 1):
        if size + len(p) > budget_chars and i > start:
            chunks.append((start, i - 1))
            start, size = i, 0
        size += len(p)
    chunks.append((start, len(pages)))
    parts, provs = [], []
    for a, b in chunks:
        obj, prov = llm.extract(CoverageExtract, PROMPT, pages_text(pages, a, b), can_fallback=False,
                                purpose=f"{purpose}:{a}-{b}", max_out=max_out)
        verify(obj, pages)
        parts.append(obj)
        provs.append(prov)
    return _merge(parts), provs


def finalize(ext: CoverageExtract, pages: list[str], policy_id: str, pdf_rel: str, providers: list[str]) -> CoverageModel:
    clean(ext)
    verify(ext, pages)
    m = CoverageModel(**ext.model_dump(), policy_id=policy_id, pages=len(pages), pdf_path=pdf_rel,
                      source_providers=providers)
    set_computable(m)
    return m


ROOM_ASSUMPTION = "your room (and ICU) is within the policy's room-rent limit"
_ASSUMABLE = [
    (re.compile(r"room|icu|iccu|boarding|nursing|proportion|tariff|entitle", re.I), ROOM_ASSUMPTION),
    (re.compile(r"deductible", re.I), "you did not choose the optional deductible"),
    (re.compile(r"zon", re.I), "treatment is in your own zone, so no zonal co-payment applies"),
    (re.compile(r"stent|nppa|dpco", re.I), "no coronary stent is used (stent prices are capped by regulation)"),
    (re.compile(r"modern treatment|modern procedure", re.I), "the claim is not for a modern-treatment procedure with its own sub-limit"),
]


def set_computable(m: CoverageModel) -> None:
    """Derive computable / estimate_quality / assumptions from the rules.

    exact:      the engine can compute payouts exactly.
    best_case:  every blocker is something that can only LOWER the payout (room limit, optional deductible, zonal
                co-pay, stent price caps, modern-treatment sub-limits), so the engine can give an upper bound that
                states those assumptions.
    terms_only: a blocker changes the covered amount in a way we cannot bound (e.g. per-illness caps on fees), or
                the room-rent rule could not be read at all: no payout, compare on terms only.
    """
    rr = m.room_rent
    m.best_case_assumptions = []
    if rr is None:
        m.computable, m.estimate_quality = False, "terms_only"
        m.computable_note = "The room-rent rule could not be read from this policy."
        return
    notes, assume, blockers = [], [], False
    if rr.kind == "unknown":
        notes.append(rr.note or "The room-rent rule could not be read from this policy.")
        assume.append(ROOM_ASSUMPTION)
        if "schedule" in (rr.note or "").lower():
            assume.append("no co-payment applies (any co-payment is set in the policy schedule)")
    elif not rr.computable:
        notes.append(rr.note or "The room-rent limit depends on hospital tariffs or the 'entitled category', so payouts cannot be computed exactly.")
        assume.append(ROOM_ASSUMPTION)
    for t in m.unmodeled_terms:
        hit = next((txt for pat, txt in _ASSUMABLE if pat.search(t)), None)
        notes.append(t)
        if hit:
            assume.append(hit)
        else:
            blockers = True
    if not notes:
        m.computable, m.estimate_quality, m.computable_note = True, "exact", None
        return
    m.computable = False
    m.computable_note = ("Contains terms the estimator cannot compute exactly: " + "; ".join(notes[:3])) if m.unmodeled_terms else notes[0]
    if blockers:
        m.estimate_quality = "terms_only"
    else:
        m.estimate_quality, m.best_case_assumptions = "best_case", list(dict.fromkeys(assume))



_NOISE = re.compile(r"ambulance|check-?up|domiciliary|pre-?\s?hospital|post-?\s?hospital|daily cash|cash allowance", re.I)
_NO_LIMIT = re.compile(r"no (?:limit|cap|sub-?limit)|without (?:any )?(?:limit|cap)|any (?:room|category)|actual|all categor|irrespective|not (?:be )?(?:restricted|limited)", re.I)
_VALID_ORDER = {"sublimit", "room_rent", "copay", "sum_insured"}


def clean(ext: CoverageExtract) -> None:
    """Deterministic guards on LLM output (applied before verification)."""
    ext.sublimits = [s for s in ext.sublimits if not _NOISE.search(f"{s.label} {s.quote} {' '.join(s.keywords)}")]
    ext.unmodeled_terms = [t for t in ext.unmodeled_terms if not _NOISE.search(t)]
    rr = ext.room_rent
    if rr and rr.kind == "any" and not _NO_LIMIT.search(rr.quote):
        # A heading like "Room rent, boarding expenses" is not a statement that there is no limit: the limit is
        # normally set in the policy schedule, which is not part of the wording.
        rr.kind = "unknown"
        rr.note = ("The wording lists room rent as covered but states no limit; the limit and any co-payment are set in the "
                   "policy schedule, which is not part of this document.")
    if set(ext.deduction_order) != _VALID_ORDER or len(ext.deduction_order) != 4:
        ext.deduction_order = ["sublimit", "room_rent", "copay", "sum_insured"]
