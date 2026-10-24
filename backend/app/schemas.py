"""Pydantic models shared by the extractor, engine and API."""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Category(str, Enum):
    appendectomy = "appendectomy"
    cataract = "cataract"
    hernia = "hernia"
    joint_replacement = "joint_replacement"
    maternity = "maternity"
    cosmetic = "cosmetic"
    dental = "dental"
    infertility = "infertility"
    accident_trauma = "accident_trauma"
    other = "other"
    unknown = "unknown"


class Cite(BaseModel):
    clause: str = Field("", description="Clause id as printed, e.g. 'III.A.1.i' or '9.A.1'")
    page: int = Field(0, description="1-based PDF page number from the [[PAGE n]] marker")
    quote: str = Field("", description="Exact text copied from the policy supporting this rule")
    verified: bool = Field(False, description="Leave false; set by code")


# ---------------------------------------------------------------- coverage model
class RoomRentRule(Cite):
    kind: Literal["percent_si", "fixed", "any", "unknown"] = "unknown"
    value: float = Field(0, description="percent of sum insured per day (kind=percent_si) or rupees per day (kind=fixed)")
    icu_value: Optional[float] = Field(None, description="same unit as value, for ICU")
    computable: bool = Field(True, description="false if the limit depends on hospital tariffs / 'entitled category' and cannot be computed from the sum insured alone")
    note: Optional[str] = None


class ProportionateRule(Cite):
    applies: bool = False
    applies_to: list[Literal["linked", "meds_implants", "other"]] = Field(
        default_factory=lambda: ["linked"], description="bill buckets reduced by the cap/actual rent ratio")


class CopayRule(Cite):
    percent: float = 0
    applies_when: Literal["always", "non_network", "other"] = "always"
    condition: Optional[str] = None


class WaitInitial(Cite):
    days: int = 0


class WaitPED(Cite):
    months: int = 0


class SpecificWait(Cite):
    category: Category
    months: int
    label: str = ""
    keywords: list[str] = Field(default_factory=list, description="lowercase words for conditions not in the Category enum (e.g. 'piles', 'bph')")


class SubLimit(Cite):
    category: Category
    label: str = ""
    pct_si: Optional[float] = Field(None, description="percent of sum insured cap, if any")
    limit_inr: Optional[float] = Field(None, description="rupee cap, if any (the lower of the two applies)")
    per: Literal["eye", "claim", "year"] = "claim"
    keywords: list[str] = Field(default_factory=list)


class Exclusion(Cite):
    category: Category = Category.other
    text: str = ""
    keywords: list[str] = Field(default_factory=list, description="lowercase words identifying the excluded condition/procedure")


class PlanBand(BaseModel):
    plan: str
    min_age: int
    max_age: int


class CoverageExtract(BaseModel):
    """What the LLM fills in (policy_id/pages are added by code)."""
    name: str = ""
    room_rent: Optional[RoomRentRule] = None
    proportionate: Optional[ProportionateRule] = None
    copay: Optional[CopayRule] = None
    waiting_initial: Optional[WaitInitial] = None
    waiting_ped: Optional[WaitPED] = None
    specific_waits: list[SpecificWait] = Field(default_factory=list)
    sublimits: list[SubLimit] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)
    deduction_order: list[str] = Field(default_factory=lambda: ["sublimit", "room_rent", "copay", "sum_insured"])
    plans: list[PlanBand] = Field(default_factory=list, description="age bands per plan, if the policy has plans")
    waiting_plans: list[str] = Field(default_factory=list, description="plans the waiting periods apply to; empty = all plans")
    sublimit_plans: list[str] = Field(default_factory=list, description="plans the sub-limits apply to; empty = all plans")
    unmodeled_terms: list[str] = Field(default_factory=list, description="payout-relevant terms a simple engine cannot compute (excess/deductible, per-illness caps, tariff-based limits)")


class CoverageModel(CoverageExtract):
    policy_id: str = ""
    pages: int = 0
    computable: bool = True
    computable_note: Optional[str] = None
    # exact = payouts computed exactly; best_case = an upper bound that assumes the listed things; terms_only = no payout
    estimate_quality: Literal["exact", "best_case", "terms_only"] = "exact"
    best_case_assumptions: list[str] = Field(default_factory=list)
    pdf_path: str = ""
    source_providers: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- claim facts
class Bill(BaseModel):
    room: float = 0
    linked: float = 0
    meds_implants: float = 0
    other: float = 0


class ClaimFacts(BaseModel):
    diagnosis_text: str = ""
    category: Category = Category.unknown
    procedure: str = ""
    is_accident: bool = False
    is_planned: bool = False
    insured_age: Optional[int] = None
    plan: Optional[str] = None
    policy_age_months: Optional[int] = None
    ped: Optional[bool] = None
    days: Optional[int] = None
    icu_days: int = 0
    units: int = Field(1, description="e.g. number of eyes for cataract")
    network_hospital: Optional[bool] = None
    room_rent_per_day: Optional[float] = None
    room_limit_per_day: Optional[float] = Field(None, description="the policy's room-rent limit per day, if the user knows it (used for best-case policies)")
    bill: Bill = Field(default_factory=Bill)
    sum_insured: Optional[float] = None
    remaining_sum_insured: Optional[float] = None
    missing: list[str] = Field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------- engine output
class TraceStep(BaseModel):
    step: str
    label: str
    before: Optional[int] = None
    after: Optional[int] = None
    clause: str = "—"
    page: Optional[int] = None


class Citation(BaseModel):
    clause: str
    page: Optional[int] = None
    quote: str = ""
    verified: bool = False


class Counterfactual(BaseModel):
    change: str
    new_payout: int
    delta: int


class Verdict(BaseModel):
    verdict: Literal["COVERED", "PARTIAL", "NOT_COVERED", "NEEDS_REVIEW"]
    billed: Optional[int] = None
    payout: Optional[int] = None
    trace: list[TraceStep] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    counterfactuals: list[Counterfactual] = Field(default_factory=list)
    why: str = ""
    next_steps: list[str] = Field(default_factory=list)
    abstain_reason: Optional[str] = None
    estimate_quality: Literal["exact", "best_case"] = "exact"
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str = "This is an estimate of the insurer's likely decision, not a legal ruling."


class Profile(BaseModel):
    insured_age: Optional[int] = None
    sum_insured: Optional[float] = None
    ped: Optional[bool] = None
    policy_age_months: Optional[int] = None
    preferred_room_rent_per_day: Optional[float] = None
