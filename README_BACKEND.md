# PoliSure backend

FastAPI service implementing `CONTRACT.md`. The LLM only reads/explains; plain Python (`backend/app/engine.py`, `Decimal`) decides every payout and verdict.

## Setup

PowerShell (Windows):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # then fill in GEMINI_API_KEY / GROQ_API_KEY
```

bash (macOS/Linux):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

`.env` is git-ignored. Check which models your keys can use with `python scripts/list_models.py` and set `GEMINI_MODEL` / `GROQ_MODEL` accordingly (`gemini-2.5-flash` is no longer served to new keys; `gemini-flash-latest` worked).

## Run

From the repository root, then `backend/`:

```powershell
cd backend
uvicorn app.main:app --port 8000          # live LLM (uses .env)
$env:LLM_MODE = "mock"; uvicorn app.main:app --port 8000   # mock LLM, no keys needed
```

```bash
cd backend
uvicorn app.main:app --port 8000
LLM_MODE=mock uvicorn app.main:app --port 8000
```

The two sample policies' coverage models are committed under `data/cache/policies/`, so the demo policy works with no policy-extraction call. Claim checks still need the LLM (or `LLM_MODE=mock`, which uses a simple keyword parser for the incident text).

## Tests and evaluation

```powershell
cd backend; python -m pytest -q           # engine, limiter, API, multi-policy, recommender (mock mode, isolated cache)
python eval/run_eval.py --engine-only --cross --split all     # no LLM
python eval/run_eval.py --e2e --baseline --cross --split dev   # paced, resumable, cached live run
python eval/run_eval.py --e2e --split test                    # only when asked
python scripts/ingest_library.py                              # ingest data/library/*.pdf + sample policies (paced, resumable)
```

`GET /eval/latest` serves `eval/report.json`. With no `data/scenarios.csv`, the harness uses `data/scenarios.sample.csv`, which is labelled plumbing-only in the report.

## LLM layer

`backend/app/llm.py`: Gemini first, Groq fallback (not for policy extraction), per-provider sliding-window RPM/TPM limiter, daily counter in `data/cache/usage.json`, result cache in `data/cache/llm/`, call log in `data/cache/calls.log`, `LLM_MODE=mock`. Limits come from `.env` (`GEMINI_RPM`, `GEMINI_TPM`, `GEMINI_RPD`, `GROQ_*`) and are conservative guesses.

## Behaviour notes

- Unverified quotes are never used for money: the engine returns `NEEDS_REVIEW`.
- Policies whose structure the engine cannot compute (e.g. per-illness sub-caps, tariff-based room rent) are `computable:false` and always give `NEEDS_REVIEW`.
- Errors: `400 {error}` bad PDF, `404 {error:"unknown_policy"}`, `503 {error:"llm_unavailable", detail}`.
- CORS allows `http://localhost:3000`.
