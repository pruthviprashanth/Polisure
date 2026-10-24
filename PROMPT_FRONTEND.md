# ROLE: FRONTEND session (Laptop B) — read this file, then follow it

You are one of TWO parallel Claude Code sessions building the same project on different laptops. **You own the frontend, the mock API server, the launcher and the demo materials.** A second session owns the backend.

## Read first, in this order
1. `CONTRACT.md` — the frozen API. Build against it **exactly**. Do not change it, and do not ask the backend to change; if something in it blocks the UI, tell the user and work around it in the UI.
2. `CLAUDE_CODE_PROMPT.md` — project background. Apply its §1 (what the app does), §6 (frontend), the `run.py` part of M6, and its Windows/cross-platform constraints. **Ignore** its LLM, engine, extraction and eval sections; those belong to the other session.

## Ownership (only touch these)
`web/`, `mock/`, `run.py`, `README.md`, `DEMO_SCRIPT.md`.
**Never edit** `backend/`, `eval/`, `data/`, `CONTRACT.md`, `.env`.

## Git workflow (shared private repo with the backend session)
- Work on `main`. Before each push: `git pull --rebase origin main`, then `git push origin main`. Commit small and often (after each F-task).
- You only ever change files in your ownership list, so rebases should never conflict. If one does, stop and tell the user; never force-push, never rewrite history.
- If no `origin` remote exists yet, commit locally and carry on; never create a remote yourself.
- Never commit `.env`, `node_modules/`, `.venv/` or `.next/` (already git-ignored).

## No keys, no live LLM
This laptop has **no API keys and must not make any LLM calls.** Everything runs against a mock server until the backend arrives.

## Tasks
- **F0** — Next.js (App Router) + Tailwind in `web/`; API base URL from `NEXT_PUBLIC_API_URL` (default `http://localhost:8000`). Windows (PowerShell) and macOS compatible.
- **F1** — `mock/server.py` (FastAPI, port 8000, same paths as CONTRACT.md) serving realistic fixtures copied from the contract: a policy with ~8 summary items, gaps, a `needs_info` response, a `done` PARTIAL verdict, a `NOT_COVERED` verdict (waiting period), a `NEEDS_REVIEW` verdict, `/eval/latest`, `/policies/{id}/pdf` (serve `data/policy.pdf` if present, else a generated one-page PDF), and error cases (`503 llm_unavailable`, `404 no_report`). Add a way to pick scenarios (e.g. keywords in `incident_text`: "appendix" → PARTIAL, "cataract" → NOT_COVERED, "unsure" → NEEDS_REVIEW). Simulate 3–8 s latency so loading states are real. `mock/requirements.txt` with only what it needs.
- **F2** — Screens per CLAUDE_CODE_PROMPT.md §1:
  1. **My policy:** upload PDF (or "use sample policy" from `GET /policies`), profile form (age, sum insured, PED yes/no/unknown, policy age in months, preferred room rent/day), summary items as cards with clause chip + page + quote + verified badge, "open in PDF" iframe/modal at `…/pdf#page=N`, gap report with severity colours.
  2. **What happened:** free-text incident box + optional itemised bill (room / associated charges / meds & implants / other); on `needs_info`, render the questions as small inputs and re-submit.
  3. **Verdict:** big verdict badge, billed vs payout, calculation table from `trace`, citation chips (open the PDF page), counterfactual cards, why + next steps, the disclaimer, a "cached"/provider badge from `meta`.
  4. **Eval page:** render `/eval/latest` (metrics, confusion table, baseline comparison, cross-policy extraction, scenarios note).
  Loading states with progress text (calls can take tens of seconds), friendly error states for 503/404, responsive layout, accessible colours. Keep it clean; no heavy UI libraries.
- **F3** — `run.py` at the project root: starts the backend (`uvicorn` from `backend/`, port 8000) and the frontend (`npm run dev` in `web/`), opens `http://localhost:3000`, stops both on Ctrl+C, works on Windows and macOS (resolve `npm` with `shutil.which("npm")` or `shell=True`). Add `python run.py --mock` which starts `mock/server.py` instead of the real backend.
- **F4** — `README.md` (PowerShell + bash setup and run commands for both modes, troubleshooting) and `DEMO_SCRIPT.md` (the 3-minute demo from BUILD_PLAN.md §7, adapted to the United India policy: appendix case, what-if, a waiting-period case, a needs-review case, the eval slide, and fallback steps).
- **F5 (integration, when the user brings the backend over)** — run against the real backend (`python run.py`), diff every response against CONTRACT.md, list mismatches for the user instead of changing either side, fix UI-side issues, and polish.

## Final report
What works in mock mode, what was verified against the real backend (if any), screenshots-worthy states you checked, known gaps, and the exact commands to run everything.
