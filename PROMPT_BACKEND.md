# ROLE: BACKEND session (Laptop A) — read this file, then follow it

You are one of TWO parallel Claude Code sessions building the same project on different laptops. **You own the backend, the LLM layer, the engine and the evaluation.** A second session owns the frontend.

## Read first, in this order
1. `CONTRACT.md` — the frozen API. Implement it **exactly** (paths, field names, types). Do not change it; if you think it is wrong, tell the user and keep going with the contract.
2. `CLAUDE_CODE_PROMPT.md` — full project background. Apply its §1, §2 (constraints), §3 (inputs), §4 (LLM layer: Gemini + Groq fallback with pacing/caching/mock), §5 (backend modules incl. engine spec and Test #1), §8 (evaluation), and §9. **Ignore** its frontend (§6) and `run.py` parts — those belong to the other session. Where that prompt's milestone list conflicts with this file, this file wins.

## Ownership (only touch these)
`backend/`, `eval/`, `scripts/`, `requirements.txt`, `data/` (read policies; write `data/cache/`, `data/fixtures/`, eval outputs), `README_BACKEND.md`.
**Never edit** `web/`, `mock/`, `run.py`, `README.md`, `CONTRACT.md`.

## Git workflow (shared private repo with the frontend session)
- Work on `main`. Before each push: `git pull --rebase origin main`, then `git push origin main`. Commit small and often (after each B-milestone).
- You only change files in your ownership list, so rebases should never conflict. If one does, stop and tell the user; never force-push, never rewrite history.
- Never commit `.env`. The frontend laptop deliberately has no keys.

## You are the only session allowed to call the live LLM APIs
The keys are in `.env` (never print or commit it). The other laptop uses a mock server and has no keys. All live calls go through your paced client. Keep live calls under ~300 total.

## Milestones (commit locally after each; if a git remote `origin` already exists, also push — never create a remote yourself)
- **B0** — cross-platform setup (Windows/PowerShell + macOS), venv, `requirements.txt`, `.env` loading, `llm.py` with pacing/limiter/cache/mock/fallback + unit tests with a fake clock, `scripts/list_models.py`.
- **B1** — `engine.py` + tests (Test #1: ₹1,03,500 and ₹1,35,900 with synthetic inputs, plus plan/age, waiting, exclusion, sub-limit, NEEDS_REVIEW cases). Use `data/policy.pdf` facts from CLAUDE_CODE_PROMPT.md §3.
- **B2** — FastAPI app serving **every endpoint in CONTRACT.md** in `LLM_MODE=mock` first, returning the contract's example shapes. **Push this first** — the frontend session depends on it only for final integration, but it proves the contract is implementable.
- **B3** — real policy extraction on `data/policy.pdf` (one live run, then cached; commit the cache file `data/cache/<policy>.json` by force-adding it, so the demo works offline), quote verifier, gap report, `/claims/check` end-to-end with abstention gate and counterfactuals.
- **B4** — eval harness: engine-only eval, paced end-to-end eval (resumable), plain-LLM baseline, cross-policy extraction test on `data/policy_b.pdf`, `eval/report.json` + `GET /eval/latest`.
- **B5** — hardening: error responses per contract (`503 llm_unavailable`), CORS for `http://localhost:3000`, `README_BACKEND.md` with exact start commands (PowerShell and bash).

Scenarios (`data/scenarios.csv`) may arrive later; use `data/scenarios.sample.csv` (labelled plumbing-only) until then.

## Final report
List what is real vs mocked/cached, live-call count, test results, known gaps, and the commands to start the backend: `uvicorn app.main:app --port 8000` from `backend/` (confirm the real module path).
