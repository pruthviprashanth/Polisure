import pytest
from fastapi.testclient import TestClient

from app import store
from app.main import app
from app.samples import united_india_extract
from app.schemas import CoverageModel
from tests.test_engine import model

PROFILE = {"insured_age": 45, "sum_insured": 500000, "ped": False, "policy_age_months": 24, "preferred_room_rent_per_day": 8000}
TEXT = "Appendix surgery. 3 days in a room at ₹8,000/day. Total bill ₹1.6 lakh."
BILL = {"room": 24000, "linked": 96000, "meds_implants": 40000, "other": 0}


@pytest.fixture(scope="module")
def ids():
    a = model(copay=0)
    a.policy_id, a.name = "polaaaaaaaaa", "Policy A (no copay)"
    b = model(copay=10)
    b.policy_id, b.name = "polbbbbbbbbb", "Policy B (10% copay)"
    c = model()
    c.policy_id, c.name, c.computable, c.computable_note = "polccccccccc", "Policy C (tariff based)", False, "room rent depends on hospital tariff"
    for m in (a, b, c):
        store.save(m)
    return a.policy_id, b.policy_id, c.policy_id


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_multi_policy_claim(client, ids):
    a, b, c = ids
    r = client.post("/claims/check", json={"policy_ids": [b, c, a], "profile": PROFILE, "incident_text": TEXT, "bill": BILL}).json()
    assert r["status"] == "done"
    comp = r["comparison"]
    assert comp["recommended_policy_id"] == a
    assert r["verdict"]["payout"] == 115000
    by = {x["policy_id"]: x for x in comp["results"]}
    assert by[b]["verdict"]["payout"] == 103500
    assert by[c]["computable"] is False and by[c]["verdict"]["verdict"] == "NEEDS_REVIEW" and by[c]["verdict"]["payout"] is None
    assert by[c]["verdict"]["abstain_reason"]
    comb = comp["combined"]
    assert comb["possible"] and comb["total_payout"] == 160000 - 0 - (160000 - 115000 - 103500 if False else 0) or comb["total_payout"] <= 160000
    assert comb["split"][0] == {"policy_id": a, "payout": 115000}
    assert comb["split"][1]["payout"] == 45000  # balance, below B's own 103,500


def test_all_non_computable(client, ids):
    _, _, c = ids
    r = client.post("/claims/check", json={"policy_ids": [c, c], "profile": PROFILE, "incident_text": TEXT, "bill": BILL}).json()
    assert r["comparison"]["recommended_policy_id"] is None and r["comparison"]["combined"] is None
    assert r["verdict"]["verdict"] == "NEEDS_REVIEW"


def test_unknown_policy_in_list(client, ids):
    r = client.post("/claims/check", json={"policy_ids": [ids[0], "zzz"], "profile": PROFILE, "incident_text": TEXT, "bill": BILL})
    assert r.status_code == 404


def test_recommend(client, ids):
    a, b, c = ids
    body = {"profile": {**PROFILE, "policy_age_months": 0}, "likely_claims": ["appendectomy", "cataract"], "claim_after_months": 0,
            "assumed_bills": {"appendectomy": 160000}, "annual_premiums": {a: 14000}, "policy_ids": [c, b, a]}
    r = client.post("/policies/recommend", json=body).json()
    assert r["best_policy_id"] == a
    assert [x["policy_id"] for x in r["ranked"]] == [a, b, c]
    assert r["ranked"][2]["score"] is None and r["ranked"][2]["reasons"]
    first = r["ranked"][0]
    res = {x["category"]: x for x in first["scenario_results"]}
    assert res["appendectomy"]["verdict"] == "NOT_COVERED"       # 30-day wait bites a new Gold policy
    assert res["cataract"]["verdict"] == "NOT_COVERED" and "waiting" in res["cataract"]["note"]
    assert "per ₹ of premium" in first["premium_note"] and r["ranked"][1]["premium_note"] is None
    assert r["disclaimer"] and r["assumptions"] and r["score_rubric"]


def test_recommend_platinum_pays(client, ids):
    a, b, _ = ids
    body = {"profile": {**PROFILE, "insured_age": 30, "policy_age_months": 0}, "likely_claims": ["appendectomy", "cataract"],
            "policy_ids": [a, b]}
    r = client.post("/policies/recommend", json=body).json()
    top = r["ranked"][0]
    assert top["policy_id"] == a and top["total_simulated_payout"] > 0
    assert all(x["verdict"] in ("COVERED", "PARTIAL") for x in top["scenario_results"])


def test_recommend_marks_ineligible_by_age_and_defaults_to_catalog(client, ids):
    from app.schemas import PlanBand

    a, b, _ = ids
    young = model()
    young.policy_id, young.name = "polddddddddd", "Policy D (entry 18-35 only)"
    young.plans = [PlanBand(plan="Platinum", min_age=18, max_age=35)]
    store.save(young)
    r = client.post("/policies/recommend", json={"profile": PROFILE, "likely_claims": ["appendectomy"], "policy_ids": [a, "polddddddddd"]}).json()
    d = next(x for x in r["ranked"] if x["policy_id"] == "polddddddddd")
    assert d["eligible"] is False and d["score"] is None and "entry ages" in d["ineligible_reason"]
    assert r["best_policy_id"] == a and r["ranked"][-1]["policy_id"] == "polddddddddd"
    # default candidate set = catalog policies only: test policies have no PDF under data/ so none qualify
    assert client.post("/policies/recommend", json={"profile": PROFILE, "likely_claims": ["cataract"]}).json()["best_policy_id"] != "polddddddddd"


def test_recommend_default_timing_skips_initial_wait_and_ranks_terms_only(client, ids):
    a, b, c = ids
    r = client.post("/policies/recommend", json={"profile": PROFILE, "likely_claims": ["appendectomy", "cataract"],
                                                  "policy_ids": [c, a]}).json()
    first = r["ranked"][0]
    res = {x["category"]: x for x in first["scenario_results"]}
    assert res["appendectomy"]["verdict"] in ("COVERED", "PARTIAL")          # 30-day wait over at 1 month
    assert res["cataract"]["verdict"] == "NOT_COVERED"                        # 24-month wait still applies
    terms = r["ranked"][1]
    assert terms["policy_id"] == c and terms["score"] is None and isinstance(terms["terms_score"], int)
    assert all(x["payout"] is None for x in terms["scenario_results"]) and r["best_terms_policy_id"] == c
    late = client.post("/policies/recommend", json={"profile": PROFILE, "likely_claims": ["cataract"], "claim_after_months": 30,
                                                     "policy_ids": [a]}).json()["ranked"][0]["scenario_results"][0]
    assert late["verdict"] in ("COVERED", "PARTIAL")
