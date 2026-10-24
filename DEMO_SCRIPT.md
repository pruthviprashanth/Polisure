# PoliSure — 3-minute demo script

Policy: **United India Individual Health Insurance Policy** (prospectus, 19 pages, `data/policy.pdf`).
Profile for the whole demo: age **45** (→ Gold plan), sum insured **₹5,00,000**, pre-existing **No**, preferred room **₹8,000/day**, policy age **24 months**.

Expected figures below are what the code engine computes from the policy rules (room cap 1% of SI = ₹5,000/day, proportionate payment, no co-pay). If the live backend shows different numbers, say what it shows: the engine is the source of truth, not this script.

## Before you start (5 minutes earlier)

1. `python run.py` (or `python run.py --mock` if there is no network/keys — see Fallbacks).
2. In the browser: **My policy** → click the United India policy (listed by the backend as **Individual Health Insurance Policy**; cached, loads instantly). Set the profile above, click **Check my gaps**.
3. Do one dry run of the appendix case so every call is cached.
4. Close other tabs; zoom the browser to ~110%.

## The demo

**0:00 — The problem (15 s).**
"Policy wordings hide the rules that cut claims: room caps, proportionate deductions, waiting periods. People find out at the hospital desk. PoliSure reads your policy and estimates what a claim will actually pay, and shows its working."

**0:15 — My policy (35 s).**
- Point at the summary cards: each one has the clause, page, exact quote and a **verified** badge (the quote was found on that page by code).
- Click the clause chip on the **Proportionate payment** card (**p.2**) → the PDF opens at page 2. "Every claim we make is traceable to the document."
- Gap report, **High**: "Your preferred room exceeds the cap — at ₹8,000/day all associated expenses are reduced to 62.5%." Note the **cached** badge.

**0:50 — Appendix case → PARTIAL (45 s).**
- **What happened** → example **Appendix surgery**: *"My father had appendix surgery. 3 days in a single AC room at ₹8,000/day. Total bill ₹1.6 lakh."* → **Check my claim**.
- It asks one follow-up: *"How much of the bill was medicines and implants?"* → type **40000** → **Submit answers**. "When something that changes the money is missing, it asks instead of assuming."
- Verdict **PARTIALLY COVERED**, billed **₹1,60,000**, payout **₹1,15,000**.
- Walk the table: room 3 × ₹5,000 cap = ₹15,000; associated charges ₹96,000 × 62.5% = ₹60,000; medicines & implants ₹40,000 not reduced → **₹1,15,000**.
- "The language model extracted the facts and wrote the explanation. It never touched a number."

**1:35 — What-if (15 s).**
- What-if card: **"Choose a room within ₹5,000/day → ₹1,51,000 (+₹36,000)."** "A cheaper room saves you ₹36,000 — the engine re-ran with one change, it isn't a guess."

**1:50 — Waiting period → NOT COVERED (25 s).**
- Back to **What happened**, set **Policy age** to **12** months, example **Cataract**: *"My mother had cataract surgery on one eye. 1 day in hospital at ₹5,000/day. Bill was ₹60,000."* If asked for medicines and implants, type **20000**.
- Verdict **NOT COVERED**: cataract has a 24-month waiting period on the Gold plan (§ 9.A.2, p.5).
- What-if: if the waiting period had passed it would pay up to the cataract sub-limit (₹40,000 per eye). Set policy age back to 24.

**2:15 — Ambiguous case → NEEDS HUMAN REVIEW (20 s).**
- Set **Any pre-existing conditions?** to **Don't know**, then example **Not sure about history**: *"I was admitted for 3 days with appendix pain, room ₹8,000/day, total bill ₹1.6 lakh. I'm not sure if this was diagnosed before my policy started."*
- Follow-up questions: medicines and implants **40000**; for *"Was this condition diagnosed … before the policy started?"* leave **Don't know** → **Submit answers**.
- Verdict **NEEDS HUMAN REVIEW**, payout not estimated, "Why we won't guess": pre-existing status decides the 48-month exclusion. Next steps tell the user what to check. "It abstains instead of guessing."

**2:35 — Eval (20 s).**
- **Eval** page: verdict accuracy, payout error in ₹, abstention precision/recall, and the plain-LLM baseline side by side; confusion matrix. "Scenarios were authored by the team and checked against the policy."
- End on the disclaimer: **"Estimates the insurer's likely decision; not a legal ruling."**

**Optional, if time (20 s): My policies.** Tick two policies in **My policies**, re-run the appendix case: comparison table, the recommended policy and why, and the combined-claim estimate. The SBI policy shows **"Can't compute payouts"**: its room rule needs hospital tariffs, so it returns NEEDS_REVIEW rather than a guess.

## Fallbacks

| Problem | Do this |
|---|---|
| Upload/extraction is slow or quota is hit | Don't upload live; pick the cached United India policy from the list (instant, shows **cached**). |
| "The AI service is busy" (503) on a claim | Click **Try again** once. If it repeats, switch to the mock (below) and say so. |
| No network / no keys | Stop with Ctrl+C, run `python run.py --mock`. Same screens and the same appendix numbers; the badge says **via mock**. Be upfront that it's the mock. |
| PDF doesn't show in the dialog | Click **Open in new tab** in the dialog header. |
| Eval page says "No evaluation report yet" | Show `eval/report.md` from the repo, or skip to the disclaimer. |
| Browser shows stale state | Open a private window at `http://localhost:3000`, re-pick the policy. |
| Port already in use | Close the old terminal, or see Troubleshooting in `README.md`. |
