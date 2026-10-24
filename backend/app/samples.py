"""Hand-built United India coverage model (real clauses/quotes from data/policy.pdf).

Used by engine tests and as the mock-mode extraction fixture. Not a substitute for the live extraction."""
from __future__ import annotations

from .schemas import (Category as C, CopayRule, CoverageExtract, Exclusion, PlanBand, ProportionateRule,
                      RoomRentRule, SpecificWait, SubLimit, WaitInitial, WaitPED)


def united_india_extract(copay_pct: float = 0.0) -> CoverageExtract:
    return CoverageExtract(
        name="United India Individual Health Insurance Policy",
        room_rent=RoomRentRule(clause="III.A.1.i", page=2, kind="percent_si", value=1, icu_value=2,
                               quote="up to 1% of Sum Insured per day or actual expenses whichever is less"),
        proportionate=ProportionateRule(clause="1.1(i)", page=2, applies=True, applies_to=["linked"],
                                        quote="shall be effected in the same proportion as the admissible rate per day bears to the actual rate per day of Room Rent"),
        copay=CopayRule(clause="6", page=2, percent=copay_pct,
                        quote="Co-Payment Not Applicable" if copay_pct == 0 else "Co-Payment"),
        waiting_initial=WaitInitial(clause="9.A.3", page=5, days=30,
                                    quote="Expenses related to the treatment of any illness within 30 days from the first policy commencement date shall be excluded"),
        waiting_ped=WaitPED(clause="9.A.1", page=5, months=48,
                            quote="until the expiry of 48 months of continuous coverage after the date of inception of the first policy with us"),
        specific_waits=[
            SpecificWait(clause="9.A.2 Table A", page=5, category=C.cataract, months=24, label="Cataract", quote="Cataract"),
            SpecificWait(clause="9.A.2 Table A", page=5, category=C.hernia, months=24, label="Hernia", quote="Hernia of all types"),
            SpecificWait(clause="9.A.2 Table B", page=5, category=C.joint_replacement, months=48,
                         label="Joint replacement (degenerative)", quote="Joint Replacement due to Degenerative"),
        ],
        sublimits=[
            SubLimit(clause="1.2", page=3, category=C.cataract, label="Cataract", pct_si=25, limit_inr=40000, per="eye",
                     quote="Up to 25% of Sum Insured or"),
            SubLimit(clause="1.2", page=3, category=C.hernia, label="Hernia & hysterectomy", pct_si=25, limit_inr=100000,
                     per="claim", quote="Hernia & Hysterectomy"),
            SubLimit(clause="1.2", page=3, category=C.joint_replacement, label="Major surgeries (joint replacement)",
                     pct_si=70, per="claim", quote="Up to 70% of the Sum Insured"),
        ],
        exclusions=[
            Exclusion(clause="Excl18", page=7, category=C.maternity, text="Maternity",
                      keywords=["childbirth", "caesarean", "delivery"],
                      quote="Medical treatment expenses traceable to childbirth"),
            Exclusion(clause="Excl08", page=6, category=C.cosmetic, text="Cosmetic or plastic surgery",
                      keywords=["cosmetic", "plastic surgery"],
                      quote="Expenses for cosmetic or plastic surgery or any treatment to change appearance"),
            Exclusion(clause="Excl17", page=7, category=C.infertility, text="Sterility and infertility",
                      keywords=["infertility", "ivf"], quote="Expenses related to sterility and infertility"),
            Exclusion(clause="C.11", page=8, category=C.dental, text="Dental treatment", keywords=["dental"],
                      quote="Dental treatment or surgery of any kind unless necessitated by disease or accident"),
        ],
        plans=[PlanBand(plan="Platinum", min_age=18, max_age=35), PlanBand(plan="Gold", min_age=36, max_age=60),
               PlanBand(plan="Senior Citizen", min_age=61, max_age=65)],
        waiting_plans=["Gold", "Senior Citizen"],
        sublimit_plans=["Gold", "Senior Citizen"],
    )
