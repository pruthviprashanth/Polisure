import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def pid(client):
    with open(config.DATA / "policy.pdf", "rb") as f:
        r = client.post("/policies", files={"file": ("policy.pdf", f, "application/pdf")})
    assert r.status_code == 200
    return r.json()["policy_id"]


PROFILE = {"insured_age": 45, "sum_insured": 500000, "ped": False, "policy_age_months": 24, "preferred_room_rent_per_day": 8000}
TEXT = "My father had appendix surgery. 3 days in a single AC room at ₹8,000/day. Total bill ₹1.6 lakh."


def test_upload_and_summary(client, pid):
    r = client.post("/policies", files={"file": ("x.pdf", open(config.DATA / "policy.pdf", "rb"), "application/pdf")}).json()
    keys = {i["key"] for i in r["summary_items"]}
    assert {"room_rent", "proportionate", "copay"} <= keys
    assert all(i["verified"] for i in r["summary_items"]), [i["key"] for i in r["summary_items"] if not i["verified"]]
    assert r["pages"] == 19


def test_bad_upload(client):
    r = client.post("/policies", files={"file": ("x.pdf", b"hello", "application/pdf")})
    assert r.status_code == 400 and "error" in r.json()


def test_list_get_pdf(client, pid):
    assert any(p["policy_id"] == pid and "computable" in p for p in client.get("/policies").json())
    assert client.get(f"/policies/{pid}").json()["meta"]["cached"] is True
    r = client.get(f"/policies/{pid}/pdf")
    assert r.headers["content-type"] == "application/pdf"
    assert client.get("/policies/nope/pdf").status_code == 404


def test_gaps(client, pid):
    r = client.get(f"/policies/{pid}/gaps", params={"insured_age": 45, "sum_insured": 500000, "ped": False, "preferred_room_rent_per_day": 8000}).json()
    assert r["plan"] == "Gold" and r["gaps"][0]["severity"] == "high" and "62.5%" in r["gaps"][0]["detail"]


def test_claim_needs_info_then_done(client, pid):
    body = {"policy_id": pid, "profile": PROFILE, "incident_text": TEXT}
    r = client.post("/claims/check", json=body).json()
    assert r["status"] == "needs_info"
    assert [q["field"] for q in r["questions"]] == ["bill.meds_implants"]
    body["answers"] = {"bill.meds_implants": 40000}
    r = client.post("/claims/check", json=body).json()
    assert r["status"] == "done"
    v = r["verdict"]
    assert (v["verdict"], v["billed"], v["payout"]) == ("PARTIAL", 160000, 115000)
    assert v["counterfactuals"][0]["new_payout"] == 151000 and v["counterfactuals"][0]["delta"] == 36000


def test_claim_with_bill_form(client, pid):
    body = {"policy_id": pid, "profile": PROFILE, "incident_text": TEXT,
            "bill": {"room": 24000, "linked": 96000, "meds_implants": 40000, "other": 0}}
    r = client.post("/claims/check", json=body).json()
    assert r["status"] == "done" and r["verdict"]["payout"] == 115000


def test_unknown_policy(client):
    r = client.post("/claims/check", json={"policy_id": "nope", "profile": PROFILE, "incident_text": TEXT})
    assert r.status_code == 404 and r.json() == {"error": "unknown_policy"}


def test_eval_latest_missing_or_present(client):
    assert client.get("/eval/latest").status_code in (200, 404)
