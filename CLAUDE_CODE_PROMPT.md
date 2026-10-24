# TASK: Build PoliSure — a health-insurance claim-estimate web app (hackathon, ~3.5h of coding)

You are building this in the current working directory. Work autonomously, in milestones, without stopping to ask questions unless you are genuinely blocked (missing file, missing key). Make sensible decisions, note assumptions, and keep going. Prefer a working end-to-end demo over completeness.

## 1. What we are building

A web app (Next.js frontend + Python FastAPI backend, both run locally) that helps a policyholder understand a health-insurance policy and estimate what a claim will pay.

**Core principle: the LLM reads and explains; plain Python code decides the money.** The LLM must never produce or change a payout figure or a verdict.

User flow (3 screens + an eval page):
1. **My policy** — upload a policy PDF + enter a small profile (age, sum insured, pre-existing conditions, preferred room rent/day). Show a coverage summary (room-rent rule, proportional-deduction rule, co-pay, waiting periods, sub-limits, exclusions). Every item shows clause id, page and the exact quote, plus a link that opens the PDF at that page (`<iframe src=".../policy.pdf#page=N">` is enough; no highlight overlay). Show a **gap report** computed in code from coverage model + profile (e.g. "preferred room ₹8,000/day exceeds ₹5,000/day cap, so the whole bill is cut proportionately").
2. **What happened** — user types the incident in plain language. The app extracts structured facts; if something needed is missing, it asks short follow-up questions (also offer a small itemised-bill form: room, linked charges, meds/implants, other).
3. **Verdict** — one of `COVERED | PARTIAL | NOT_COVERED | NEEDS_REVIEW`, estimated payout with the calculation shown line by line, the clauses cited (page + quote + verified flag), a counterfactual "what if" (e.g. cheaper room → payout, or waiting period elapsed → covered), next steps, and a disclaimer: *"Estimates the insurer's likely decision; not a legal ruling."*
4. **Eval page** — shows the latest metrics report (see §8).

Scope: health insurance only. **Do NOT build:** weather/parametric mode, OCR, vector DB/embeddings, Postgres, auth/login, PDF highlight overlays. Storage = JSON files under `data/`.

## 2. Hard constraints

- **Free LLM APIs only:** Google Gemini (primary) and Groq (fallback). Keys come from env vars `GEMINI_API_KEY` and `GROQ_API_KEY` loaded from a git-ignored `.env`. Never print, log, commit or echo keys. Create `.env.example` (no secrets) and make sure `.env` is in `.gitignore` before anything else.
- **Free-tier limits are tight and uncertain. Spacing requests is mandatory** (see §4). Do not fire bursts of calls, ever, including in tests and eval scripts.
- **Do not guess SDK usage.** Before writing provider code, check current official docs (WebFetch) for the `google-genai` Python SDK and the `groq` Python SDK, then write the code. Do not hard-code model names: read `GEMINI_MODEL` and `GROQ_MODEL` from env, and write `scripts/list_models.py` that prints the models each key can use.
- Use mock mode (§4) for tests, UI work and plumbing. Keep **live API calls under ~300 total** during the whole build; print the running daily counter whenever a live call is made.
- Be honest in everything user-facing and in the eval: no invented metrics, no fabricated clauses. If a coverage model is loaded from cache/precomputed, the UI must say "cached".
- **Target machine is a Windows laptop (PowerShell); code must also run on macOS.** Write cross-platform code: `pathlib` for all paths, no bash-only scripts or commands in the README (give PowerShell commands, e.g. venv activation `.venv\Scripts\Activate.ps1`), open files with explicit `encoding="utf-8"`, and avoid `os.system` shell tricks. Check that every pinned dependency installs on Windows.
- Python 3.11+, Pydantic v2, `Decimal` for all money. Node 20+. Create a venv; pin deps in `requirements.txt`.
- `git init` locally and commit at each milestone. Do not push anywhere.

## 3. Inputs the user supplies (check these first, then stop and tell the user if missing)

- `.env` already exists in the project root with working keys and `GEMINI_MODEL=gemini-2.5-flash`, `GROQ_MODEL=openai/gpt-oss-120b` (both keys were verified by listing models). Never print it. The rate-limit values in it are conservative guesses, not the account's real limits.
- `data/policy.pdf` — the primary demo/eval policy: **United India Individual Health Insurance Policy prospectus** (19 pages, digital text). Facts the engine must handle: co-pay is "Not Applicable"; room rent 1% of sum insured/day, ICU 2%/day; a proportionate-payment clause applies the cap/actual-rent ratio to all associated expenses (not applied where the hospital does not bill differentially by room category); plan is derived from age (Platinum 18–35, Gold 36–60, Senior Citizen 61–65); waiting periods and sub-limits apply only to Gold and Senior plans (30-day initial wait, PED 48 months, specified diseases 24 months — cataract, BPH, hernia, hydrocele, menorrhagia/fibroid/prolapse — and 48 months for Table B; cataract limit 25% of SI or ₹40,000 per eye; hernia & hysterectomy 25% of SI or ₹1,00,000; major surgeries up to 70% of SI). Add `insured_age` and `plan` to the profile and `ClaimFacts`, and a plan-eligibility step to the engine. Cite prospectus page numbers.
- `data/policy_b.pdf` — a **second policy (SBI General Health Insurance Policy – Retail, 27-page full wording)** used ONLY for cross-policy extraction tests, not for the scenario eval. Its structure differs: room 1% SI/day (ICU 2%) with per-illness caps (room 25%, doctor fees 40%, other charges 40% of SI), cataract 15% of SI max ₹25,000 per eye, 10% co-pay only in non-network hospitals, an excess, a 30-day wait, PED 48 months, and 1-year and 2-year exclusion lists. Its room-rent rule limits associated charges to "the entitled category" and cannot be computed exactly from user input, so the correct behaviour on it is NEEDS_REVIEW, not a guess.
- `data/scenarios.csv` — hand-labelled eval scenarios. Columns: `id, incident_text, room_rent_per_day, days, bill_room, bill_linked, bill_meds_implants, bill_other, policy_age_months, ped, expected_verdict, expected_payout_inr, expected_clauses, should_abstain, split` (`split` = `dev` or `test`). If absent, create `data/scenarios.sample.csv` with ~6 rows **clearly labelled as plumbing-only samples, not real labels**, and say so in the eval report.
- `data/gold_coverage.json` (optional) — gold clause values for the extraction-accuracy metric.

## 4. LLM layer — `backend/app/llm.py` (build this first, carefully)

A single entry point used by the whole app:

```python
extract(schema: type[BaseModel], system: str, user: str, *, can_fallback: bool = True,
        purpose: str = "") -> tuple[BaseModel, str]   # (validated object, provider_name)
```

Requirements:
- **Provider-agnostic JSON:** put `schema.model_json_schema()` in the prompt, request JSON mode on each provider, validate with Pydantic, and on `ValidationError` retry once with the error message appended ("fix your JSON"). Do not rely on provider-specific structured-output features.
- **Order:** Gemini first; on quota exhaustion / persistent errors fall back to Groq **only if** `can_fallback` and the estimated request size fits Groq's token limit. Policy extraction uses `can_fallback=False`.
- **Pacing (the important part):** per-provider thread-safe limiter with a sliding 60-second window tracking both requests and *estimated* tokens (estimate = `len(text)/3.5` + max output tokens). Before each call, sleep until both RPM and TPM budgets fit. Limits come from env with conservative defaults, editable after the user checks the consoles:
  `GEMINI_RPM=8 GEMINI_TPM=100000 GEMINI_RPD=200` and `GROQ_RPM=20 GROQ_TPM=5000 GROQ_RPD=800`.
  A single request larger than the TPM budget must never be sent as-is: Gemini path → raise a clear error telling the caller to chunk; Groq path → skip Groq.
- **Daily counter:** persist per-provider request counts per calendar day in `data/cache/usage.json`. When RPD is reached, mark that provider exhausted for the day and move to the next one.
- **Retries:** on 429/5xx honour `Retry-After` / provider retry-delay hints if present, else exponential backoff with jitter (max 4 tries). A per-minute limit error → wait and retry the *same* provider before falling back. Daily-quota error → fall back.
- **Cache:** key = sha256(schema name + prompt version + system + user). Store results in `data/cache/llm/<key>.json`. Cache hit = zero API calls. Env `LLM_CACHE=off` bypasses it.
- **Mock mode:** `LLM_MODE=mock` returns fixtures from `data/fixtures/<purpose>.json` (create plausible fixtures matching the schemas for the demo flow). Frontend dev and all unit tests use mock mode.
- **Logging:** append one line per call to `data/cache/calls.log` (time, provider, purpose, est tokens, latency, cache hit/miss) and print the running daily total for live calls.
- Unit-test the limiter with a fake clock/fake provider (no network): it must delay, not burst, and must respect both RPM and TPM.

## 5. Backend modules (`backend/app/`)

Use the contract below. Keep schemas flat/simple; if a schema is too nested for a provider to follow, split into smaller extraction calls.

```
Cited[T] = { value: T, clause: str, page: int, quote: str, verified: bool }

CoverageModel = {
  policy_id, name, pages,
  room_rent:     Cited[{kind: "percent_si"|"fixed"|"any", value: number}],
  proportionate: Cited[{applies: bool, applies_to: ["room","linked"]}],   # meds/implants usually excluded
  copay:         Cited[{percent: number, condition: str|null}],
  waiting:       {initial_days, ped_months, specific_months, specific_list: [Category]},  # each Cited
  sublimits:     [Cited[{category, limit_inr, per: "eye"|"claim"|"year"}]],
  exclusions:    [Cited[{category, text}]],
  deduction_order: [str]    # default: ["sublimit","room_rent","copay","sum_insured"]; override per policy if wording says otherwise
}

Category (closed enum, shared by code and LLM): appendectomy, cataract, hernia, joint_replacement,
  maternity, cosmetic, dental, infertility, accident_trauma, other, unknown

ClaimFacts = { diagnosis_text, category: Category, procedure, is_accident, is_planned,
  policy_age_months, ped: bool|null, days, room_rent_per_day,
  bill: {room, linked, meds_implants, other}, sum_insured, remaining_sum_insured,
  missing: [str], confidence: 0..1 }

Verdict = { verdict, billed, payout, trace: [{step,label,before,after,clause}],
  citations: [{clause,page,quote,verified}], counterfactuals: [{change,new_payout,delta}],
  why, next_steps: [str], abstain_reason: str|null, providers_used: [str] }
```

- `extraction.py` — PyMuPDF text per page with `[[PAGE n]]` markers → `extract(CoverageModel…, can_fallback=False)`. If the estimated size exceeds the Gemini TPM budget, chunk by page ranges, extract partial models and merge (prefer verified fields). Cache by PDF hash. **Quote verifier:** normalise whitespace/case/hyphenation/ligatures, `rapidfuzz` partial match ≥ 90 on the cited page (±1); set `verified` and correct the page if found elsewhere; unverified fields are never used for money (→ NEEDS_REVIEW).
- `gaps.py` — pure code: coverage model + profile → list of gaps with clause refs. The LLM may only phrase the explanation text.
- `facts.py` — incident text (+ optional form/answers) → `ClaimFacts`; derive follow-up questions from `missing`.
- `engine.py` — **no LLM, `Decimal` only.** Fixed pipeline, every step appends to `trace`:
  1. initial waiting period (not for accidents) → NOT_COVERED
  2. exclusions by category → NOT_COVERED
  3. PED: `ped==true` and age < ped_months → NOT_COVERED; `ped is None` → NEEDS_REVIEW
  4. specific-illness waiting (category in list and age < months) → NOT_COVERED
  5. sub-limit cap for the category
  6. room rent: if `rent/day > cap/day`, `ratio = cap/rent`; eligible room = `cap*days`; linked × ratio; meds/implants untouched (only if the policy says so)
  7. co-pay on the amount after step 6
  8. cap at remaining sum insured; round half-up to ₹1
  Order of 5–8 follows `deduction_order`. Verdict: payout 0 → NOT_COVERED, payout == billed → COVERED, else PARTIAL. Unit-test heavily.
  **Test #1 (must pass first):** room ₹8,000/day × 3 days, linked ₹96,000, meds/implants ₹40,000, cap ₹5,000/day, co-pay 10% → room 15,000 + linked 96,000×62.5% = 60,000 + meds 40,000 = 1,15,000 → −10% = **₹1,03,500**. Counterfactual (room ≤ cap) → 15,000 + 96,000 + 40,000 = 1,51,000 → −10% = **₹1,35,900**.
- Counterfactuals = re-run the engine with one change each (room ≤ cap; waiting period elapsed; PED=false). Exact numbers, not LLM estimates.
- `explain.py` — LLM writes a 2–3 sentence "why" and next steps **from the engine trace only**. Guard: every ₹ figure in the text must appear in the trace, else use a deterministic template.
- **Abstention gate:** low confidence, unverified quote used, `missing` non-empty, category `unknown`, or `ped is None` → `NEEDS_REVIEW` with a reason and next steps. Never guess.
- `main.py` (FastAPI, CORS for `http://localhost:3000`): `POST /policies`, `GET /policies/{id}`, `GET /policies/{id}/gaps`, `POST /claims/check`, `GET /eval/latest`, `GET /policies/{id}/pdf`. Use plain `def` endpoints (the SDK clients are sync). Return `providers_used` and whether data came from cache.

## 6. Frontend (`web/`, Next.js + Tailwind)

Three screens + eval page per §1. Build against the backend running in mock mode first. Requirements: loading states that tolerate slow/paced calls (calls can take tens of seconds — show progress text), a maths table for the trace, clause chips that open the PDF page, a clearly visible disclaimer and a "cached"/"provider" badge. Keep styling simple and clean; no extra libraries beyond what is needed.

## 7. Milestones (stop and verify at each; commit after each)

- **M0** — repo, `.gitignore`/`.env.example`, venv, `llm.py` with pacing + cache + mock mode + limiter tests, `scripts/list_models.py`.
- **M1** — `engine.py` + tests (Test #1 green), `schemas`, mock-mode fixtures.
- **M2** — policy upload → coverage model → verifier → gap report (live LLM once on `data/policy.pdf`, then cached).
- **M3** — `/claims/check` end-to-end: facts → engine → counterfactuals → explanation → gate. Appendix example returns ₹1,03,500 with trace and citations (in mock mode, then live).
- **M4** — frontend wired to the API; full demo flow in the browser.
- **M5** — eval harness (§8) and eval page.
- **M6** — polish, a root-level `run.py` that starts uvicorn (backend, port 8000) and `npm run dev` (web, port 3000) together, opens the browser at http://localhost:3000, and stops both on Ctrl+C (must work on Windows and macOS; on Windows `npm` is `npm.cmd`, so resolve it with `shutil.which("npm")` or use `shell=True`; no exe/packaging), README with run instructions, demo script, backup: committed cached coverage JSON for the demo policy so the demo works offline.

If time runs short, cut in this order: eval page UI (keep the report file) → follow-up-question UI (use the itemised form) → gap report styling → baseline run.

## 8. Evaluation (`eval/`) — real numbers only

- **Engine-only eval (no LLM, runs every time):** scenarios feed structured fields straight to the engine; report verdict accuracy and payout error (₹ MAE, % exact).
- **End-to-end eval (LLM):** free text → facts → engine. **Paced, sequential, resumable, cached.** A re-run must make zero API calls for already-completed scenarios. Add `--limit N` and `--split dev|test`. Run `test` split only when asked.
- **Baseline:** a plain "policy text + incident → JSON verdict & payout" prompt through the same paced client, same scenarios, run once and cached, to compare against the pipeline.
- **Metrics (write `eval/report.json` + `eval/report.md`):** clause-extraction accuracy (vs `gold_coverage.json` if present), 4-class verdict accuracy + confusion matrix, citation correctness (cited clauses in expected set; % quotes verified), payout error (₹ MAE; within ₹1), abstention quality (precision/recall of `NEEDS_REVIEW` vs `should_abstain`, plus confident-and-wrong rate). Record provider, model names, scenario count and split in the report. State that scenarios were authored by the team.

## 9. Working rules

- Start by reading this file fully, then do §3 checks, then M0.
- Run tests after each milestone and show the result.
- Never run live-LLM loops over many scenarios without the pacing client; never remove the pacing to "go faster".
- At the end, give a short summary: what works, what's mocked/cached, live-call count used, known gaps, and exact commands to run backend, frontend and eval.
