# API CONTRACT (frozen — neither session may change it; report mismatches to the user)

Backend: FastAPI at `http://localhost:8000` (CORS allows `http://localhost:3000`).
All money = integer rupees (INR). All responses are JSON unless noted. `quote` = exact text from the policy; `page` = PDF page number (1-based); `verified` = the quote was found on that page by code.

Every response that involved an LLM or cache includes `meta: { "cached": bool, "providers_used": ["gemini"|"groq"|"cache"|"mock"], "model_note": str|null }`.

## Profile object (sent by the UI)
```json
{ "insured_age": 45, "sum_insured": 500000, "ped": false,
  "policy_age_months": 24, "preferred_room_rent_per_day": 8000 }
```
`ped` is `true|false|null` (null = don't know). The backend derives `plan` from age (United India: Platinum 18–35, Gold 36–60, Senior 61–65).

## POST /policies  (multipart/form-data: `file` = PDF)
Response 200:
```json
{
  "policy_id": "a1b2c3d4e5f6",
  "name": "United India Individual Health Insurance Policy",
  "pages": 19,
  "summary_items": [
    { "key": "room_rent", "label": "Room rent", "summary": "1% of sum insured per day (ICU 2%)",
      "clause": "III.A.1.i", "page": 2, "quote": "up to 1% of Sum Insured per day or actual expenses whichever is less", "verified": true },
    { "key": "proportionate", "label": "Proportionate payment", "summary": "If the room exceeds the cap, all associated expenses are paid in the same proportion",
      "clause": "1.1(i)", "page": 2, "quote": "shall be effected in the same proportion as the admissible rate per day bears to the actual rate per day", "verified": true },
    { "key": "copay", "label": "Co-payment", "summary": "Not applicable", "clause": "6", "page": 2, "quote": "Co-Payment Not Applicable", "verified": true }
  ],
  "meta": { "cached": false, "providers_used": ["gemini"], "model_note": null }
}
```
`key` values: `room_rent, icu_rent, proportionate, copay, waiting_initial, waiting_ped, waiting_specific, sublimit_<name>, exclusion_<n>` (free-form extras allowed; UI must render any key generically).
Errors: `400 {"error": "..."}` (not a PDF / no text layer), `503 {"error":"llm_unavailable","detail":"..."}`.

## GET /policies
`[{ "policy_id": "...", "name": "...", "pages": 19 }]` — cached policies (so the UI can offer "use sample policy").

## GET /policies/{policy_id}
Same body as POST /policies (from cache; `meta.cached = true`).

## GET /policies/{policy_id}/pdf
Raw `application/pdf` (UI opens `…/pdf#page=N` in an iframe).

## GET /policies/{policy_id}/gaps?insured_age=45&sum_insured=500000&ped=false&preferred_room_rent_per_day=8000
```json
{
  "plan": "Gold",
  "gaps": [
    { "severity": "high", "title": "Your preferred room exceeds the cap",
      "detail": "Room cap is ₹5,000/day (1% of ₹5,00,000). At ₹8,000/day all associated expenses are reduced to 62.5%.",
      "clause": "1.1(i)", "page": 2, "quote": "…", "verified": true },
    { "severity": "medium", "title": "Hernia and cataract have a 24-month waiting period", "detail": "…", "clause": "…", "page": 5, "quote": "…", "verified": true }
  ],
  "meta": { "cached": true, "providers_used": ["cache"], "model_note": null }
}
```
`severity` ∈ `high|medium|info`.

## POST /claims/check  (JSON body)
```json
{
  "policy_id": "a1b2c3d4e5f6",
  "profile": { "insured_age": 45, "sum_insured": 500000, "ped": false, "policy_age_months": 24, "preferred_room_rent_per_day": 8000 },
  "incident_text": "My father had appendix surgery. 3 days in a single AC room at ₹8,000/day. Total bill ₹1.6 lakh.",
  "bill": { "room": 24000, "linked": 96000, "meds_implants": 40000, "other": 0 },
  "answers": { "ped": false }
}
```
`bill` and `answers` are optional. Response 200 is ONE of:

**A. Needs more info**
```json
{ "status": "needs_info",
  "questions": [ { "field": "bill.meds_implants", "question": "How much of the bill was medicines and implants?", "type": "number" },
                 { "field": "ped", "question": "Was this condition diagnosed before the policy started?", "type": "boolean" } ],
  "meta": { "cached": false, "providers_used": ["gemini"], "model_note": null } }
```
The UI re-submits the same request with the answers merged into `answers` / `bill`.

**B. Done**
```json
{
  "status": "done",
  "verdict": {
    "verdict": "PARTIAL",
    "billed": 160000,
    "payout": 115000,
    "trace": [
      { "step": "room_rent", "label": "Room: 3 days × ₹5,000 cap (actual ₹8,000/day)", "before": 24000, "after": 15000, "clause": "III.A.1.i", "page": 2 },
      { "step": "proportionate", "label": "Associated charges × 62.5% (cap ÷ actual)", "before": 96000, "after": 60000, "clause": "1.1(i)", "page": 2 },
      { "step": "meds_implants", "label": "Medicines & implants (not reduced)", "before": 40000, "after": 40000, "clause": "—", "page": null },
      { "step": "total", "label": "Payable", "before": 160000, "after": 115000, "clause": "—", "page": null }
    ],
    "citations": [ { "clause": "III.A.1.i", "page": 2, "quote": "…", "verified": true } ],
    "counterfactuals": [
      { "change": "Choose a room within ₹5,000/day", "new_payout": 151000, "delta": 36000 }
    ],
    "why": "Your room costs more than the policy's daily cap, so associated charges are reduced in proportion.",
    "next_steps": ["Ask the hospital for an itemised bill", "Request pre-authorisation for a room within the cap next time"],
    "abstain_reason": null,
    "disclaimer": "This is an estimate of the insurer's likely decision, not a legal ruling."
  },
  "meta": { "cached": false, "providers_used": ["gemini", "groq"], "model_note": null }
}
```
`verdict` ∈ `COVERED | PARTIAL | NOT_COVERED | NEEDS_REVIEW`. For `NEEDS_REVIEW`, `payout` may be `null` and `abstain_reason` is a non-empty string. The numbers above are an *example of the shape* — actual figures come from the engine and the policy.

Errors: `404 {"error":"unknown_policy"}`, `503 {"error":"llm_unavailable","detail":"…"}` (UI shows a retry message).

## GET /eval/latest
```json
{
  "generated_at": "2026-10-24T14:10:00",
  "models": { "gemini": "gemini-2.5-flash", "groq": "openai/gpt-oss-120b" },
  "policy": "United India IHIP prospectus", "n_scenarios": 40, "split": "test", "scenarios_note": "Authored by the team; drafted with AI assistance and verified against the policy.",
  "metrics": { "verdict_accuracy": 0.85, "payout_mae_inr": 1200, "payout_within_1_pct": 0.78, "citation_correctness": 0.9,
               "quote_verified_pct": 0.95, "extraction_accuracy": 0.8,
               "abstention_precision": 0.8, "abstention_recall": 0.75, "confident_wrong_rate": 0.05 },
  "confusion": { "COVERED": { "COVERED": 8, "PARTIAL": 1 } },
  "baseline": { "verdict_accuracy": 0.7, "payout_mae_inr": 9000, "abstention_recall": 0.1, "note": "plain LLM, same scenarios" },
  "cross_policy_extraction": [ { "policy": "SBI General Health Retail", "extraction_accuracy": 0.7 } ]
}
```
`baseline` and `cross_policy_extraction` may be `null`/empty. If no report exists: `404 {"error":"no_report"}`.
