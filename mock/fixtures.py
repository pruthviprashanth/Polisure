"""Fixture data for the mock API server.

Quotes and page numbers for the United India and SBI policies were copied from the text layer of
data/policy.pdf and data/policy_b.pdf. "Demo Health Plus" is a fictional policy that exists only in
the mock, so the multi-policy and recommender screens have something to compare.
"""

UI_ID = "a1b2c3d4e5f6"
SBI_ID = "b2c3d4e5f6a7"
DEMO_ID = "c3d4e5f6a7b8"

MOCK_META_NOTE = "Mock server: fixture data, no LLM calls"

DISCLAIMER = "This is an estimate of the insurer's likely decision, not a legal ruling."

UI_SUMMARY = [
    {"key": "room_rent", "label": "Room rent", "summary": "1% of sum insured per day, or actual if lower",
     "clause": "III.A.1.i", "page": 2,
     "quote": "up to 1% of Sum Insured per day or actual expenses whichever is less", "verified": True},
    {"key": "icu_rent", "label": "ICU rent", "summary": "2% of sum insured per day, or actual if lower",
     "clause": "III.A.1.ii", "page": 2,
     "quote": "up to 2% of Sum Insured per day or actual expenses whichever is less", "verified": True},
    {"key": "proportionate", "label": "Proportionate payment",
     "summary": "If the room exceeds the cap, all associated expenses are paid in the same proportion",
     "clause": "1.1(i)", "page": 2,
     "quote": "shall be effected in the same proportion as the admissible rate per day bears to the actual rate per day",
     "verified": True},
    {"key": "copay", "label": "Co-payment", "summary": "Not applicable", "clause": "6", "page": 2,
     "quote": "Co-Payment Not Applicable", "verified": True},
    {"key": "waiting_initial", "label": "Initial waiting period",
     "summary": "No illness claims in the first 30 days (accidents are covered)", "clause": "9.A.3 (Excl03)", "page": 5,
     "quote": "Expenses related to the treatment of any illness within 30 days from the first policy commencement date shall be excluded",
     "verified": True},
    {"key": "waiting_ped", "label": "Pre-existing diseases",
     "summary": "Excluded for 48 months of continuous cover (Gold and Senior plans)", "clause": "9.A.1 (Excl01)", "page": 5,
     "quote": "shall be excluded until the expiry of 48 months of continuous coverage after the date of inception of the first policy with us",
     "verified": True},
    {"key": "waiting_specific", "label": "Specified diseases",
     "summary": "24 months for cataract, hernia, BPH, hydrocele and others; 48 months for joint replacement (Gold and Senior plans)",
     "clause": "9.A.2 (Excl02)", "page": 5,
     "quote": "shall be excluded until the expiry of 24 months and 48 months respectively of continuous coverage",
     "verified": True},
    {"key": "sublimit_cataract", "label": "Cataract sub-limit",
     "summary": "25% of sum insured or ₹40,000 per eye, whichever is less (Gold and Senior plans)", "clause": "1.2", "page": 3,
     "quote": "Up to 25% of Sum Insured or Rs. 40,000 per eye, whichever is less", "verified": True},
    {"key": "sublimit_hernia", "label": "Hernia & hysterectomy sub-limit",
     "summary": "25% of sum insured or ₹1,00,000, whichever is less (Gold and Senior plans)", "clause": "1.2", "page": 3,
     "quote": "Up to 25% of Sum Insured or Rs. 1,00,000, whichever is less", "verified": True},
    {"key": "sublimit_major_surgery", "label": "Major surgeries sub-limit",
     "summary": "Cardiac, cancer, joint replacement and similar: up to 70% of sum insured (Gold and Senior plans)",
     "clause": "1.2", "page": 3, "quote": "Up to 70% of the Sum Insured", "verified": True},
    {"key": "exclusion_8", "label": "Cosmetic surgery", "summary": "Excluded unless reconstruction after accident, burns or cancer",
     "clause": "Excl08", "page": 6,
     "quote": "Expenses for cosmetic or plastic surgery or any treatment to change appearance", "verified": True},
    {"key": "exclusion_18", "label": "Maternity", "summary": "Childbirth expenses are excluded (except ectopic pregnancy)",
     "clause": "Excl18", "page": 7,
     "quote": "Medical treatment expenses traceable to childbirth", "verified": True},
]

SBI_SUMMARY = [
    {"key": "room_rent", "label": "Room rent", "summary": "1% of sum insured per day (ICU 2%), capped per illness",
     "clause": "C.1", "page": 7, "quote": "Room, Boarding and Nursing expenses", "verified": False},
    {"key": "proportionate", "label": "Associated charges",
     "summary": "Limited to the charges of the 'entitled' room category; depends on hospital tariffs",
     "clause": "Definitions", "page": 3,
     "quote": "the expenses which the Insured/Insured Person is entitled for applicable room rent and other charges",
     "verified": True},
    {"key": "copay", "label": "Co-payment", "summary": "10% only when treated at a non-network hospital",
     "clause": "Definitions", "page": 2,
     "quote": "the agreed share of the claim amount which is to be borne by the Insured", "verified": True},
    {"key": "excess", "label": "Excess", "summary": "An excess may apply before the insurer pays",
     "clause": "Definitions", "page": 3,
     "quote": "the % of sum insured/claim or amount up to which all Expenses covered by this Policy are to be borne by the Insured",
     "verified": True},
    {"key": "sublimit_cataract", "label": "Cataract sub-limit", "summary": "15% of sum insured, max ₹25,000 per eye",
     "clause": "C.1", "page": 8, "quote": "Cataract", "verified": False},
    {"key": "waiting_ped", "label": "Pre-existing diseases", "summary": "48 months", "clause": "Excl01", "page": 14,
     "quote": "48 months", "verified": False},
]

DEMO_SUMMARY = [
    {"key": "room_rent", "label": "Room rent", "summary": "No room-rent cap", "clause": "2.1", "page": 1,
     "quote": "Room rent is payable at actuals with no daily limit", "verified": True},
    {"key": "copay", "label": "Co-payment", "summary": "20% on every claim", "clause": "4.2", "page": 1,
     "quote": "a co-payment of 20% applies to every admissible claim", "verified": True},
    {"key": "waiting_initial", "label": "Initial waiting period", "summary": "30 days (accidents covered)", "clause": "5.1",
     "page": 1, "quote": "30 days from the first policy commencement date", "verified": True},
    {"key": "waiting_specific", "label": "Specified diseases", "summary": "None", "clause": "5.2", "page": 1,
     "quote": "No specified-disease waiting period applies", "verified": True},
    {"key": "sublimit_maternity", "label": "Maternity", "summary": "Covered up to ₹50,000 per delivery", "clause": "3.4",
     "page": 1, "quote": "Maternity expenses up to Rs. 50,000 per delivery", "verified": True},
]

POLICIES = {
    UI_ID: {
        "policy_id": UI_ID, "name": "United India Individual Health Insurance Policy", "pages": 19,
        "summary_items": UI_SUMMARY, "computable": True, "computable_note": None, "pdf": "data/policy.pdf",
    },
    SBI_ID: {
        "policy_id": SBI_ID, "name": "SBI General Health Insurance Policy - Retail", "pages": 27,
        "summary_items": SBI_SUMMARY, "computable": False,
        "computable_note": "Associated charges are limited to the 'entitled' room category, which needs the hospital's tariff; payouts can't be computed from your bill.",
        "pdf": "data/policy_b.pdf",
    },
    DEMO_ID: {
        "policy_id": DEMO_ID, "name": "Demo Health Plus (fictional, mock only)", "pages": 1,
        "summary_items": DEMO_SUMMARY, "computable": True, "computable_note": None, "pdf": None,
    },
}

# Default bills when the user gives none: (room, linked, meds_implants, other, days)
DEFAULT_BILLS = {
    "appendectomy": (24000, 96000, 40000, 0, 3),
    "cataract": (5000, 35000, 20000, 0, 1),
    "hernia": (12000, 60000, 18000, 0, 3),
    "joint_replacement": (40000, 150000, 160000, 0, 5),
    "maternity": (12000, 55000, 13000, 0, 3),
    "other": (24000, 96000, 40000, 0, 3),
}

EVAL_REPORT = {
    "generated_at": "2026-10-24T14:10:00",
    "models": {"gemini": "gemini-2.5-flash", "groq": "openai/gpt-oss-120b"},
    "policy": "United India IHIP prospectus",
    "n_scenarios": 40,
    "split": "test",
    "scenarios_note": "MOCK REPORT: placeholder numbers from the API contract, not a real eval run. Real scenarios are authored by the team; drafted with AI assistance and verified against the policy.",
    "metrics": {
        "verdict_accuracy": 0.85, "payout_mae_inr": 1200, "payout_within_1_pct": 0.78, "citation_correctness": 0.9,
        "quote_verified_pct": 0.95, "extraction_accuracy": 0.8, "abstention_precision": 0.8,
        "abstention_recall": 0.75, "confident_wrong_rate": 0.05,
    },
    "confusion": {
        "COVERED": {"COVERED": 8, "PARTIAL": 1},
        "PARTIAL": {"PARTIAL": 12, "COVERED": 1, "NEEDS_REVIEW": 1},
        "NOT_COVERED": {"NOT_COVERED": 8, "PARTIAL": 1},
        "NEEDS_REVIEW": {"NEEDS_REVIEW": 6, "NOT_COVERED": 1, "PARTIAL": 1},
    },
    "baseline": {"verdict_accuracy": 0.7, "payout_mae_inr": 9000, "abstention_recall": 0.1,
                 "note": "plain LLM, same scenarios"},
    "cross_policy_extraction": [{"policy": "SBI General Health Retail", "extraction_accuracy": 0.7}],
}
