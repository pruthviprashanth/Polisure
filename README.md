# PoliSure

Understand a health-insurance policy and estimate what a claim will pay.
**The language model reads and explains; plain Python code decides the money.** Every rule shown in the app cites the clause, page and exact quote from the policy PDF.

- **My policy**: upload a policy PDF (or pick a cached one), enter a short profile, and see the coverage summary and a gap report.
- **What happened**: describe the hospital stay in plain words (plus an optional itemised bill). If something is missing, the app asks short follow-up questions.
- **Verdict**: `COVERED`, `PARTIAL`, `NOT_COVERED` or `NEEDS_REVIEW`, with the calculation line by line, cited clauses that open the PDF at the right page, what-if scenarios, next steps and a disclaimer.
- **My policies / Find a policy**: keep the policies you own in a browser-only wallet, compare a claim across them, or rank library policies for the claims you expect.
- **Eval**: the latest evaluation report (accuracy, payout error, abstention quality, baseline).

Estimates the insurer's likely decision; not a legal ruling.

## Layout

| Path | What |
|---|---|
| `web/` | Next.js (App Router) + Tailwind frontend, port 3000 |
| `backend/` | FastAPI backend, port 8000 (LLM extraction, code engine) |
| `mock/` | Mock API that follows `CONTRACT.md` — no keys, no LLM calls |
| `run.py` | Starts API + web together, opens the browser, Ctrl+C stops both |
| `CONTRACT.md` | The frozen API contract between frontend and backend |
| `data/` | Policy PDFs and caches |

## Requirements

- Python 3.11+ (3.13 tested)
- Node.js 20+ (24 tested) and npm
- For the real backend only: a `.env` in the project root with `GEMINI_API_KEY` / `GROQ_API_KEY` (copy `.env.example`). Never commit `.env`.

## Setup

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt        # backend (also covers the mock)
cd web; npm install; cd ..
```

If activation is blocked, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

### macOS / Linux (bash or zsh)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
(cd web && npm install)
```

Mock-only machines can install just `pip install -r mock/requirements.txt`.

## Run

With the venv activated, from the project root:

```bash
python run.py --mock
```

Mock mode: starts `mock/server.py` on :8000 and the web app on :3000. No keys needed, no LLM calls.

```bash
python run.py
```

Real mode: starts the backend (`uvicorn app.main:app` from `backend/`) on :8000 and the web app on :3000.

To run the real backend without keys or LLM calls (its own mock LLM; cached policy summaries, keyword-based incident parsing):

```powershell
$env:LLM_MODE = "mock"; python run.py
```

```bash
LLM_MODE=mock python run.py
```

Add `--no-browser` to skip opening the browser. Press **Ctrl+C** to stop both processes.

### Running the pieces separately

```bash
python mock/server.py
```

```bash
cd backend && python -m uvicorn app.main:app --port 8000
```

```bash
cd web && npm run dev
```

The web app reads the API address from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`; see `web/.env.example`).

## Mock server scenarios

The mock follows `CONTRACT.md` and picks a scenario from words in the incident text. Calls that would hit an LLM wait 3–8 s so the loading states are real (`MOCK_LATENCY=0` disables, `0.3` shortens).

| Type in "What happened" | Result |
|---|---|
| `appendix` … `3 days … ₹8,000/day … ₹1.6 lakh` | PARTIAL ₹1,15,000 of ₹1,60,000; what-if ₹1,51,000 |
| `cataract` with policy age < 24 months | NOT_COVERED (24-month waiting period); what-if ₹40,000 |
| `hernia` with policy age ≥ 24 months | COVERED within the ₹1,00,000 sub-limit |
| `delivery` / `maternity` | NOT_COVERED (exclusion) |
| `not sure` / `unsure` / `don't know` | NEEDS_REVIEW (pre-existing status unknown) |
| no amounts at all, no bill | `needs_info`: asks for the bill split |
| profile "pre-existing: Yes" | `needs_info`: "diagnosed before the policy started?" |
| `llm down` | 503 `llm_unavailable` (retry message) |

Other mock behaviour: uploading a non-PDF returns 400; a PDF whose file name contains `fail` returns 503; `http://localhost:8000/mock/settings?no_report=1` makes `/eval/latest` return 404 (`?no_report=0` restores). The library holds the United India policy, the SBI policy (`computable: false`) and a fictional "Demo Health Plus" that exists only in the mock. The mock's eval report is a placeholder and says so on the Eval page.

## Troubleshooting

- **"Port 8000/3000 is already in use"**: an earlier run is still alive. PowerShell: `Get-NetTCPConnection -LocalPort 8000 -State Listen` then `Stop-Process -Id <OwningProcess>`. macOS: `lsof -i :8000` then `kill <pid>`.
- **"npm was not found"**: install Node.js 20+ and open a new terminal.
- **"Server unreachable" in the app**: the API isn't running on :8000, or `NEXT_PUBLIC_API_URL` points elsewhere.
- **"The AI service is busy right now"** (503): free-tier quota is paced or exhausted. Wait a minute and retry, or use `python run.py --mock`.
- **PDF chip opens a blank pane**: some browsers block PDFs in iframes; use "Open in new tab" in the PDF dialog.
- **`ModuleNotFoundError` when starting**: activate the venv first (`.venv\Scripts\Activate.ps1` or `source .venv/bin/activate`), then reinstall requirements.
- **Stale data in the app**: the active policy, profile, wallet and last verdict live in browser localStorage. Clear site data for `localhost:3000` to reset.
