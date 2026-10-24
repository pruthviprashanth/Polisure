from app import engine
from app.samples import united_india_extract
from app.schemas import Bill, Category as C, ClaimFacts, CoverageModel


def model(copay=0.0, verified=True):
    m = CoverageModel(**united_india_extract(copay).model_dump(), policy_id="t", pages=19)
    if verified:
        for fld in ("room_rent", "proportionate", "copay", "waiting_initial", "waiting_ped"):
            getattr(m, fld).verified = True
        for lst in (m.specific_waits, m.sublimits, m.exclusions):
            for x in lst:
                x.verified = True
    return m


def facts(**kw):
    base = dict(category=C.appendectomy, insured_age=45, sum_insured=500000, policy_age_months=24, ped=False, days=3,
                room_rent_per_day=8000, bill=Bill(room=24000, linked=96000, meds_implants=40000, other=0), confidence=0.9)
    base.update(kw)
    return ClaimFacts(**base)


def test_test1_copay_10():
    m = model(copay=10)
    r = engine.run(m, facts())
    assert (r.verdict, r.payout, r.billed) == ("PARTIAL", 103500, 160000)
    steps = {t.step: (t.before, t.after) for t in r.trace}
    assert steps["room_rent"] == (24000, 15000)
    assert steps["proportionate"] == (96000, 60000)
    assert steps["meds_implants"] == (40000, 40000)
    r2 = engine.run(m, facts(room_rent_per_day=5000, bill=Bill(room=15000, linked=96000, meds_implants=40000)))
    assert r2.payout == 135900


def test_contract_example_no_copay():
    r = engine.run(model(), facts())
    assert r.payout == 115000 and r.verdict == "PARTIAL"
    assert r.trace[-1].step == "total"


def test_covered_when_room_within_cap():
    r = engine.run(model(), facts(room_rent_per_day=5000, bill=Bill(room=15000, linked=96000, meds_implants=40000)))
    assert r.verdict == "COVERED" and r.payout == 151000


def test_plan_derivation():
    m = model()
    assert engine.derive_plan(m, 30) == "Platinum" and engine.derive_plan(m, 45) == "Gold"
    assert engine.derive_plan(m, 63) == "Senior Citizen" and engine.derive_plan(m, 70) is None


def test_age_outside_bands_needs_review():
    assert engine.run(model(), facts(insured_age=70)).verdict == "NEEDS_REVIEW"


def test_platinum_has_no_waiting_or_sublimit():
    f = facts(insured_age=30, category=C.cataract, policy_age_months=2, ped=True, room_rent_per_day=2000, days=1,
              bill=Bill(room=2000, linked=80000, meds_implants=0))
    r = engine.run(model(), f)
    assert r.verdict == "COVERED" and r.payout == 82000


def test_gold_cataract_waiting():
    f = facts(category=C.cataract, policy_age_months=12, room_rent_per_day=2000, days=1,
              bill=Bill(room=2000, linked=80000))
    r = engine.run(model(), f)
    assert r.verdict == "NOT_COVERED" and r.payout == 0 and r.blocked == {"kind": "specific", "months_needed": 24}


def test_gold_cataract_sublimit_per_eye():
    f = facts(category=C.cataract, policy_age_months=30, room_rent_per_day=2000, days=1,
              bill=Bill(room=2000, linked=80000))
    r = engine.run(model(), f)
    assert r.verdict == "PARTIAL" and r.payout == 40000  # min(25% of 5L, 40000) per eye
    r2 = engine.run(model(), f.model_copy(update={"units": 2}))
    assert r2.payout == 80000


def test_hernia_sublimit_min_pct_or_cap():
    f = facts(category=C.hernia, policy_age_months=30, room_rent_per_day=3000, days=2,
              bill=Bill(room=6000, linked=300000))
    assert engine.run(model(), f).payout == 100000  # min(25% of 5L = 125000, 100000)


def test_initial_wait_and_accident_exempt():
    f = facts(policy_age_months=0)
    assert engine.run(model(), f).verdict == "NOT_COVERED"
    acc = f.model_copy(update={"is_accident": True, "category": C.accident_trauma})
    assert engine.run(model(), acc).verdict != "NOT_COVERED"


def test_ped_cases():
    assert engine.run(model(), facts(ped=True, policy_age_months=24)).verdict == "NOT_COVERED"
    assert engine.run(model(), facts(ped=None, policy_age_months=24)).verdict == "NEEDS_REVIEW"
    assert engine.run(model(), facts(ped=True, policy_age_months=60)).verdict in ("PARTIAL", "COVERED")
    assert engine.run(model(), facts(ped=None, policy_age_months=60)).verdict in ("PARTIAL", "COVERED")


def test_exclusion():
    r = engine.run(model(), facts(category=C.cosmetic))
    assert r.verdict == "NOT_COVERED" and r.trace[0].step == "exclusion"


def test_unknown_category_and_missing_inputs():
    assert engine.run(model(), facts(category=C.unknown)).verdict == "NEEDS_REVIEW"
    assert engine.run(model(), facts(bill=Bill())).verdict == "NEEDS_REVIEW"


def test_unverified_rule_forces_review():
    r = engine.run(model(verified=False), facts())
    assert r.verdict == "NEEDS_REVIEW" and r.payout is None and r.abstain_reason


def test_non_computable_policy():
    m = model()
    m.computable, m.computable_note = False, "room rent depends on hospital tariff"
    assert engine.run(m, facts()).verdict == "NEEDS_REVIEW"


def test_remaining_sum_insured_cap():
    f = facts(room_rent_per_day=5000, bill=Bill(room=15000, linked=96000, meds_implants=40000),
              remaining_sum_insured=100000)
    r = engine.run(model(), f)
    assert r.payout == 100000 and r.verdict == "PARTIAL"


def test_rounding_half_up():
    f = facts(room_rent_per_day=3, days=1, bill=Bill(room=3, linked=0, meds_implants=0), sum_insured=300)
    assert engine.run(model(copay=50), f).payout == 2  # 1.5 -> 2
