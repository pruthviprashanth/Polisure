import pytest
from fastapi.testclient import TestClient

from app import engine, extraction, store
from app.extraction import ROOM_ASSUMPTION
from app.main import app
from app.schemas import Bill, Category as C, ClaimFacts, RoomRentRule
from tests.test_engine import facts, model

PROFILE = {"insured_age": 45, "sum_insured": 500000, "ped": False, "policy_age_months": 24, "preferred_room_rent_per_day": 8000}
TEXT = "Appendix surgery. 3 days in a room at Rs 8,000/day."
BILL = {"room": 24000, "linked": 96000, "meds_implants": 40000, "other": 0}


def best_case_model(pid="bcaaaaaaaaaa", name="Policy BC (limit in schedule)"):
    m = model()
    m.policy_id, m.name = pid, name
    m.room_rent = RoomRentRule(clause="IV.1.a", page=2, quote="up to 1% of Sum Insured per day or actual expenses whichever is less",
                               kind="unknown", verified=True, note="limit is in the schedule")
    m.proportionate.applies = False
    m.computable, m.estimate_quality, m.best_case_assumptions = False, "best_case", [ROOM_ASSUMPTION]
    return m


# ---------------------------------------------------------------- classification
def _classify(**kw):
    m = model()
    for k, v in kw.items():
        setattr(m, k, v)
    extraction.set_computable(m)
    return m


def test_classifier_tiers():
    assert _classify().estimate_quality == "exact"
    m = _classify(room_rent=RoomRentRule(kind="unknown", note="the limit is in the policy schedule"))
    assert (m.computable, m.estimate_quality) == (False, "best_case")
    assert ROOM_ASSUMPTION in m.best_case_assumptions and any("co-payment" in a for a in m.best_case_assumptions)
    m = _classify(unmodeled_terms=["Optional Aggregate Deductible of Rs. 50,000 per policy year"])
    assert m.estimate_quality == "best_case" and "optional deductible" in m.best_case_assumptions[0]
    m = _classify(unmodeled_terms=["Medical Practitioner/Surgeon Fees restricted to 40% of Sum Insured per illness"])
    assert m.estimate_quality == "terms_only" and m.best_case_assumptions == []
    m = _classify(unmodeled_terms=["Room rent capped at 2% of SI", "Zonal co-payment of 20%"])
    assert m.estimate_quality == "best_case" and len(m.best_case_assumptions) == 2
    assert _classify(room_rent=None).estimate_quality == "terms_only"


# ---------------------------------------------------------------- engine
def test_best_case_is_an_upper_bound_with_assumptions():
    m = best_case_model()
    assert engine.run(m, facts()).verdict == "NEEDS_REVIEW"                         # default: refuses
    r = engine.run(m, facts(), best_case=True)
    assert (r.verdict, r.payout, r.quality) == ("COVERED", 160000, "best_case")      # no room cut applied
    assert r.assumptions == [ROOM_ASSUMPTION] and any(t.step == "room_assumed" for t in r.trace)


def test_user_entered_room_limit_replaces_the_assumption():
    m = best_case_model()
    r = engine.run(m, facts(room_limit_per_day=5000), best_case=True)
    assert r.payout == 15000 + 96000 + 40000                                          # room capped; linked kept (no proportionate rule)
    assert ROOM_ASSUMPTION not in r.assumptions and "entered by you" in r.assumptions[0]


def test_best_case_still_applies_waiting_periods_and_terms_only_never_computes():
    m = best_case_model()
    cat = facts(category=C.cataract, policy_age_months=12, days=1, room_rent_per_day=2000, bill=Bill(room=2000, linked=80000))
    assert engine.run(m, cat, best_case=True).verdict == "NOT_COVERED"
    t = best_case_model()
    t.estimate_quality = "terms_only"
    assert engine.run(t, facts(), best_case=True).verdict == "NEEDS_REVIEW"
    assert engine.run(model(), facts(), best_case=True).quality == "exact"           # exact policies unaffected


# ---------------------------------------------------------------- API
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def ids():
    a = model()
    a.policy_id, a.name = "exaaaaaaaaaa", "Policy EX (exact)"
    b = best_case_model()
    for m in (a, b):
        store.save(m)
    return a.policy_id, b.policy_id


def test_claim_on_best_case_policy_is_labelled(client, ids):
    _, b = ids
    r = client.post("/claims/check", json={"policy_id": b, "profile": PROFILE, "incident_text": TEXT, "bill": BILL}).json()
    v = r["verdict"]
    assert v["estimate_quality"] == "best_case" and v["payout"] == 160000 and v["assumptions"]
    assert v["why"].startswith("Best-case estimate") and "room-rent limit" in v["next_steps"][0]
    r2 = client.post("/claims/check", json={"policy_id": b, "profile": PROFILE, "incident_text": TEXT, "bill": BILL,
                                            "answers": {"room_limit_per_day": 5000}}).json()["verdict"]
    assert r2["payout"] == 151000 and "entered by you" in r2["assumptions"][0]


def test_exact_ranks_above_best_case_even_if_best_case_pays_more(client, ids):
    a, b = ids
    r = client.post("/claims/check", json={"policy_ids": [b, a], "profile": PROFILE, "incident_text": TEXT, "bill": BILL}).json()
    comp = r["comparison"]
    assert comp["recommended_policy_id"] == a and r["verdict"]["estimate_quality"] == "exact"
    by = {x["policy_id"]: x for x in comp["results"]}
    assert by[b]["verdict"]["payout"] > by[a]["verdict"]["payout"] and by[b]["estimate_quality"] == "best_case"
    assert "not directly comparable" in comp["recommendation_reason"]
    assert "best-case" in comp["combined"]["note"].lower()


def test_recommender_groups_best_case_between_exact_and_terms_only(client, ids):
    a, b = ids
    t = best_case_model("tmaaaaaaaaaa", "Policy TO (terms only)")
    t.estimate_quality, t.best_case_assumptions = "terms_only", []
    store.save(t)
    r = client.post("/policies/recommend", json={"profile": PROFILE, "likely_claims": ["appendectomy"],
                                                  "policy_ids": [t.policy_id, b, a]}).json()
    assert [x["policy_id"] for x in r["ranked"]] == [a, b, t.policy_id]
    best = r["ranked"][1]
    assert best["estimate_quality"] == "best_case" and best["score"] is not None and best["assumptions"]
    assert best["scenario_results"][0]["payout"] is not None and r["best_case_policy_id"] == b
    assert r["ranked"][2]["estimate_quality"] == "terms_only" and r["ranked"][2]["score"] is None


def test_gap_report_and_list_expose_quality(client, ids):
    _, b = ids
    g = client.get(f"/policies/{b}/gaps", params={"insured_age": 45, "sum_insured": 500000, "ped": False}).json()
    assert g["metrics"]["estimate_quality"] == "best_case" and any("best-case" in x["title"].lower() for x in g["gaps"])
    assert {p["policy_id"]: p["estimate_quality"] for p in client.get("/policies").json()}[b] == "best_case"
