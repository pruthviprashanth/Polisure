"""FastAPI app implementing CONTRACT.md. Run from backend/: uvicorn app.main:app --port 8000"""
from __future__ import annotations

import json
import uuid
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from . import claims, config, llm, present, qa, recommend as reco, store
from .schemas import CoverageModel


@asynccontextmanager
async def lifespan(_: FastAPI):
    _seed()
    yield


app = FastAPI(title="PoliSure API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
                   allow_methods=["*"], allow_headers=["*"])


# Changes every time the backend starts; the web app clears its saved state when it sees a new value.
BOOT_ID = uuid.uuid4().hex


def err(status: int, error: str, detail: Optional[str] = None) -> JSONResponse:
    body = {"error": error}
    if detail:
        body["detail"] = detail
    return JSONResponse(body, status_code=status)


@app.exception_handler(llm.LLMUnavailable)
async def _llm_unavailable(_: Request, exc: llm.LLMUnavailable):
    return err(503, "llm_unavailable", str(exc)[:300])


def _seed() -> None:
    """Mock mode only: make the bundled sample policy available without any API key."""
    if config.llm_mode() == "mock":
        p = config.DATA / "policy.pdf"
        if p.exists():
            try:
                store.ingest(p.read_bytes(), source=p)
            except Exception:
                pass


def _meta(cached: bool, provs: list[str]) -> dict:
    return {"cached": cached, "providers_used": provs, "model_note": None}


def _policy_body(m: CoverageModel, cached: bool, provs: list[str]) -> dict:
    return {"policy_id": m.policy_id, "name": m.name, "pages": m.pages, "summary_items": present.summary_items(m),
            "meta": _meta(cached, provs)}


@app.get("/session")
def session():
    return {"boot_id": BOOT_ID}


@app.post("/policies")
def upload_policy(file: UploadFile = File(...)):
    data = file.file.read()
    try:
        m, cached, provs = store.ingest(data)
    except store.NotAPdf as e:
        return err(400, str(e))
    return _policy_body(m, cached, provs)


@app.get("/policies")
def list_policies():
    return [{"policy_id": m.policy_id, "name": m.name, "pages": m.pages, "computable": m.computable,
             "computable_note": m.computable_note, "catalog": store.is_catalog(m)} for m in store.list_all()]


@app.get("/policies/{policy_id}")
def get_policy(policy_id: str):
    m = store.load(policy_id)
    if m is None:
        return err(404, "unknown_policy")
    return _policy_body(m, True, ["cache"])


@app.get("/policies/{policy_id}/pdf")
def get_pdf(policy_id: str):
    m = store.load(policy_id)
    p = store.pdf_file(m) if m else None
    if p is None:
        return err(404, "unknown_policy")
    return FileResponse(p, media_type="application/pdf")


@app.get("/policies/{policy_id}/gaps")
def get_gaps(policy_id: str, insured_age: Optional[int] = None, sum_insured: Optional[float] = None,
             ped: Optional[bool] = None, preferred_room_rent_per_day: Optional[float] = None,
             policy_age_months: int = 0):
    m = store.load(policy_id)
    if m is None:
        return err(404, "unknown_policy")
    plan, gaps = present.gaps(m, insured_age, sum_insured, ped, preferred_room_rent_per_day, policy_age_months)
    metrics = present.gap_metrics(m, insured_age, sum_insured, preferred_room_rent_per_day, policy_age_months)
    metrics["typical_claims"] = reco.typical_claims(m, insured_age, sum_insured, ped, preferred_room_rent_per_day, policy_age_months)
    return {"plan": plan, "gaps": gaps, "metrics": metrics, "meta": _meta(True, ["cache"])}


class ClaimRequest(BaseModel):
    policy_id: Optional[str] = None
    policy_ids: Optional[list[str]] = None
    profile: dict = {}
    incident_text: str = ""
    bill: Optional[dict] = None
    answers: Optional[dict] = None


@app.post("/claims/check")
def check_claim(req: ClaimRequest):
    ids = req.policy_ids or ([req.policy_id] if req.policy_id else [])
    if not ids:
        return err(400, "policy_id or policy_ids is required")
    try:
        return claims.check(ids, req.profile, req.incident_text, req.bill, req.answers, store.load)
    except claims.UnknownPolicy:
        return err(404, "unknown_policy")


class AskRequest(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/policies/{policy_id}/ask")
def ask_policy(policy_id: str, req: AskRequest):
    m = store.load(policy_id)
    if m is None:
        return err(404, "unknown_policy")
    if not req.question.strip():
        return err(400, "question is required")
    try:
        return qa.ask(m, req.question, req.history)
    except FileNotFoundError:
        return err(404, "unknown_policy")


class RecommendRequest(BaseModel):
    profile: dict = {}
    likely_claims: list[str] = []
    assumed_bills: Optional[dict] = None
    annual_premiums: Optional[dict] = None
    policy_ids: Optional[list[str]] = None
    claim_after_months: int = 1


@app.post("/policies/recommend")
def recommend_policies(req: RecommendRequest):
    from . import recommend
    return recommend.recommend(req.profile, req.likely_claims, req.assumed_bills, req.annual_premiums, req.policy_ids, max(req.claim_after_months, 0))


@app.get("/eval/latest")
def eval_latest():
    p = config.ROOT / "eval" / "report.json"
    if not p.exists():
        return err(404, "no_report")
    return json.loads(p.read_text(encoding="utf-8"))
