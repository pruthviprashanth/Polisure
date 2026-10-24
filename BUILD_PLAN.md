# PoliSure / ClaimCheck — Hack-o-Ween build plan (Team Codeblooded)

Track: FinTech — The Vampire's Ledger. Date: Sat 24 Oct. Pick ONE product name (deck says PoliSure; use it everywhere).

## 0. Reality check — your real coding time

| Slot | Time | Use |
|---|---|---|
| Registration | 7:30–8:30 | Set up laptops, hotspot, repo (if rules allow) |
| Problem curation | 8:30–9:00 | Scaffold |
| Intro review | 9:00–10:00 | 60-second pitch ready |
| **Coding 1** | **10:00–12:00** | **2h** |
| Review 2 | 12:00–12:30 | 1 person presents, 3 keep coding |
| Lunch | 12:30–1:30 | Run eval during lunch; eat in 30 min |
| Review 2 cont. | 1:30–2:00 | 1 person presents, 3 keep coding |
| **Coding 2** | **2:00–3:30** | **1.5h** |
| **Final review** | **3:30–4:30** | **Demo must work by 3:30** |
| Top 7 announced | 4:30–5:30 | Prep 5-min pitch |
| Top 7 presentation | 5:30–6:30 | |

Dedicated coding = **3.5h** (about 5h if you code through the reviews). You cannot build the whole deck in that. Anything done *tonight* that isn't code (data, labels, PDFs, keys) is free time. Check the organisers' rules on pre-written code: do not bring pre-built code if it's banned.

## 1. Scope: build this, cut that

**P0 (must work by 12:00 / 3:30)**
1. Upload policy PDF → coverage model, every field with clause, page, quote.
2. Quote verifier: the quote must exist in the source page text, else the field is marked unverified.
3. Rules engine in pure Python with `Decimal`, unit tested.
4. Claim check: text → facts → engine → verdict + maths + clauses.
5. Minimal UI: 3 screens (My policy, What happened, Verdict).
6. Eval harness with ≥30 labelled scenarios and a metrics printout.

**P1**: gap report, counterfactual ("what-if"), follow-up questions, abstention gate, "open PDF at page" link.
**P2**: metrics page in the UI, BM25 retrieval, second policy upload.
**CUT**: weather/parametric mode (future-work slide only), OCR/Tesseract, ChromaDB/embeddings, PostgreSQL, auth, PDF highlight overlay.

Why the cuts are safe: a 40-page policy is about 25–40k tokens, so it fits in one Claude call with `[[PAGE n]]` markers. No vector DB needed. Store coverage models as JSON files. For citations use `<iframe src="/policy.pdf#page=7">`, which takes 5 minutes versus a day for highlighting.

## 2. Tonight (non-code prep, ~2h)

1. **Pick the one demo/eval policy.** Download a digital-text (not scanned) health policy wording, 30–45 pages, from a public insurer site. All eval and demo content is built on it. The deck's numbers (₹5,000 cap, §4.2…) are illustrative, so rewrite the demo story with the *real* clauses of your chosen policy. Don't present made-up clauses as real.
2. **Hand-write 40 scenarios** in a sheet (CSV/Google Sheet). Columns:
   `id, incident_text, room_rent_per_day, days, bill_room, bill_linked, bill_meds_implants, bill_other, policy_age_months, ped(Y/N/unknown), expected_verdict, expected_payout_inr, expected_clauses, should_abstain, split(dev|test)`
   Mix: ~10 covered, ~10 partial (room rent, co-pay, sub-limit), ~10 not covered (waiting period, exclusion), ~6 ambiguous (expected NEEDS_REVIEW), ~4 other. Compute the expected payouts **by hand** from the policy. Mark ~10 as `test` and don't tune on them.
3. **Gold-label the coverage fields** of the policy (≈10): room-rent rule, proportionate-deduction rule, co-pay, initial wait, PED wait, specific-illness wait + list, 2–3 sub-limits, key exclusions. Each with page and quote.
4. **Anthropic API key** with credit. Test one call. Use `claude-opus-5-5` for policy extraction (runs once, then cached); `claude-sonnet-5-5` or `claude-haiku-5-5` for per-claim calls if latency matters. These models reject `temperature` and forced `tool_choice`, so don't use either: get JSON via structured outputs and get repeatability from the cache + the code engine.
5. **Toolchain installed**: Python 3.11, Node 20, `fastapi uvicorn pydantic pymupdf pdfplumber anthropic rapidfuzz rank-bm25 pytest`. Phone hotspot as backup network.
6. **Roles** (assign by strength): A Engine, B LLM/Parsing, C Frontend, D Eval/Data/Glue.
7. Sleep. A tired team ships less than a rested one.

## 3. Architecture (trimmed)

```
PDF → PyMuPDF text per page ([[PAGE n]]) → Claude (structured outputs via client.messages.parse + Pydantic) → CoverageModel
        → quote verifier (rapidfuzz on page n ±1) → saved as data/policies/<hash>.json
Incident text + profile → Claude → ClaimFacts (+ missing[] → follow-up questions)
        → Rules engine (Decimal, deterministic) → trace + verdict
        → counterfactuals (re-run engine with modified facts)
        → Claude writes 2–3 sentence "why" + next steps from the trace (numbers NOT allowed to come from LLM)
        → Gate: low confidence / unverified quote / unmapped diagnosis → NEEDS_HUMAN_REVIEW
```

**Backend**: FastAPI. Endpoints: `POST /policies`, `GET /policies/{id}`, `GET /policies/{id}/gaps?profile=…`, `POST /claims/check`, `GET /eval/latest`.
**Frontend**: Next.js + Tailwind, 3 screens. Start against `mock/*.json` so C is never blocked.
**Cache everything**: hash the PDF + prompt version → cached coverage model. Commit the demo policy's cached model so the demo works even if the wifi or API dies.

### Contract (agree at 10:00; both sides code against it)

```
Cited[T]      = { value: T, clause: str, page: int, quote: str, verified: bool }

CoverageModel = {
  policy_id, name, pages,
  room_rent:      Cited[{ kind: "percent_si"|"fixed"|"any", value: number, per_day: true }],
  proportionate:  Cited[{ applies: bool, applies_to: ["room","linked"] }],   // meds/implants usually excluded
  copay:          Cited[{ percent: number, condition: str|null }],
  waiting:        { initial_days: Cited[int], ped_months: Cited[int],
                    specific_months: Cited[int], specific_list: Cited[[category]] },
  sublimits:      [Cited[{ category, limit_inr, per: "eye"|"claim"|"year" }]],
  exclusions:     [Cited[{ category, text }]]       // category ∈ CLOSED ENUM shared with ClaimFacts
}

ClaimFacts = {
  diagnosis_text, category (closed enum or "unknown"), procedure, is_accident, is_planned,
  policy_age_months, ped: true|false|null, days, room_rent_per_day,
  bill: { room, linked, meds_implants, other },     // INR, linked = surgeon/OT/nursing/investigations
  sum_insured, remaining_sum_insured,
  missing: [str], confidence: 0..1
}

Verdict = {
  verdict: "COVERED"|"PARTIAL"|"NOT_COVERED"|"NEEDS_REVIEW",
  billed, payout,
  trace: [{ step, label, before, after, clause }],
  citations: [{ clause, page, quote, verified }],
  counterfactuals: [{ change, new_payout, delta }],
  why, next_steps: [str], abstain_reason: str|null
}
```

The **closed enum** of categories (e.g. `appendectomy, cataract, hernia, joint_replacement, maternity, cosmetic, dental, infertility, accident_trauma, other`) is what lets code, not the LLM, decide exclusions and waiting periods. Anything the LLM maps to `unknown` goes to NEEDS_REVIEW.

## 4. Rules engine spec (Person A)

Fixed order, every step appends to `trace`:

1. Initial waiting period (not for accidents) → NOT_COVERED if `policy_age_days < initial_days`.
2. Exclusions by category → NOT_COVERED (cite exclusion).
3. PED waiting: if `ped == true` and `policy_age_months < ped_months` → NOT_COVERED. If `ped == null` → NEEDS_REVIEW.
4. Specific-illness waiting: if category ∈ `specific_list` and age < `specific_months` → NOT_COVERED.
5. Sub-limit for category: cap that line item.
6. Room rent: if `rent_per_day > cap_per_day` → `ratio = cap / rent`. Eligible room = `cap × days`; linked × ratio; meds/implants untouched (only if the policy says so).
7. Co-pay: `× (1 − copay%)` on the amount after step 6.
8. Cap at remaining sum insured. Round with `Decimal` (`ROUND_HALF_UP` to ₹1).

Verdict: payout 0 → NOT_COVERED; payout == billed → COVERED; else PARTIAL.

**Test #1 (from your own deck, write this first):** room ₹8,000/day × 3, linked ₹96,000, meds/implants ₹40,000, cap ₹5,000/day, co-pay 10%.
`room 15,000 + linked 96,000×62.5% = 60,000 + meds 40,000 = 1,15,000 → −10% = ₹1,03,500`.
Counterfactual (room ≤ cap): `15,000 + 96,000 + 40,000 = 1,51,000 → −10% = ₹1,35,900`. Both numbers are in your wireframe, so the engine is correct when it reproduces them.

Counterfactuals = re-run the engine with one change each: room ≤ cap; waiting period elapsed (set age = threshold); PED = false.

## 5. Hour-by-hour (day-of)

**Before 10:00**: `git init`, one repo, `main` + short branches, commit every 20 min, push to a shared remote. Scaffold FastAPI + Next.js hello-world (if rules allow). Confirm the API key works on every laptop.

**10:00–10:30 · Align + skeleton**
- All: paste the contract into `contract.md` and agree. Freeze the enum.
- A: engine skeleton + Test #1 (red).
- B: PyMuPDF → pages with `[[PAGE n]]`; first Claude extraction call on the demo policy. Eyeball the output.
- C: Next.js, 3 empty screens rendering `mock/*.json`.
- D: scenario CSV → JSON loader; eval runner skeleton.

**10:30–11:15**
- A: all 8 engine steps, 10+ unit tests, Test #1 green.
- B: quote verifier; save the cached coverage model; fix extraction on room rent and co-pay (usually tables, so try pdfplumber if text is messy).
- C: upload screen + coverage summary against real `/policies`.
- D: engine-only eval (scenarios give structured facts, so no LLM needed). Gold-label comparer for clause extraction.

**11:15–12:00 · M1 (end-to-end happy path)**
- B: fact-extraction prompt → `ClaimFacts`; `/claims/check` calls it, then A's engine.
- C: verdict screen with maths table and clause chips.
- D: first full engine-only eval number.
- **12:00 deliverable:** the appendix case runs from the UI and returns ₹1,03,500 with the maths and clauses. Ugly is fine.

**12:00–12:30 Review 2**: C or the best talker presents M1; three keep coding.

**12:30–1:30 Lunch**: start the eval run **before** you eat. Read failures over lunch and sort them into clusters: wrong extraction vs wrong rule vs wrong label.

**1:30–2:00 Review 2 cont.**: same, one person presents.

**2:00–2:45 · Fix + trust features**
- A: counterfactuals; fix the biggest failure cluster only (no long-tail chasing).
- B: abstention gate (low confidence, unverified quote, `unknown` category → NEEDS_REVIEW); follow-up questions when `missing[]` is non-empty; explanation guard (every ₹ figure in the text must appear in the trace, else use the template).
- C: follow-up Q&A UI, what-if card, "open PDF at page".
- D: end-to-end eval (free text → facts → engine) on dev scenarios.

**2:45–3:15 · Polish**
- Gap report on screen 1 (room-rent cap, waiting periods, co-pay, exclusions vs profile).
- Run the held-out **test** split **once** → these are your reported numbers. Metrics table into the UI or README.
- Disclaimer on every verdict: *estimates the insurer's likely decision, not a legal ruling.*

**3:15 · FEATURE FREEZE.** Tag the commit. Rehearse the demo twice, pre-load the cached policy, record a backup screen video. Do not merge anything new.

**3:30–4:30 Final review**: demo + Q&A.
**4:30–5:30**: if you're in the top 7, build a 5-minute pitch from your deck + one slide of real eval numbers.

## 6. Evaluation (Person D) — what to report

| Metric | How |
|---|---|
| Clause extraction accuracy | extracted value == gold, over ~10 gold fields |
| Verdict accuracy | exact match on the 4 classes + confusion matrix |
| Citation correctness | % of cited clauses in the gold set, and % of quotes verified in the source |
| Payout error | MAE in ₹ where both gold and predicted exist, plus % within ₹1 |
| Abstention quality | precision/recall of NEEDS_REVIEW vs `should_abstain`, plus "confident-and-wrong" rate |

Be upfront: scenarios were written by the team, with ~10 held out and untouched until the end. Report the failures too; judges trust honest numbers more than 100%.

## 7. Demo script (3 min)

1. Upload the policy → coverage model + gaps in ~20s (cached backup ready).
2. Appendix case → **PARTIAL ₹1,03,500**, maths line by line, click §4.2 → PDF opens at the page.
3. What-if → "a room within the cap would pay ₹1,35,900".
4. A genuinely ambiguous case → **NEEDS HUMAN REVIEW** with next steps (shows it doesn't guess).
5. Eval slide with real numbers and the "estimate, not a ruling" disclaimer.

## 8. Risks and fallbacks

| Risk | Fallback |
|---|---|
| Extraction misses table values | pdfplumber for those pages; hand-patch the cached JSON for the demo policy only if you disclose it as a cache |
| LLM/wifi down | cached coverage model + cached fact extraction for demo scenarios; hotspot |
| Engine/LLM disagree on category | closed enum; `unknown` → NEEDS_REVIEW |
| Behind at 12:00 | cut gap report to a static list; cut follow-up questions (use a form for bill split) |
| Behind at 3:00 | freeze; spend the time on demo reliability, not features |
| Merge conflicts | one file/dir per person: `engine/`, `llm/`, `web/`, `eval/` |
