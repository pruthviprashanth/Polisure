# PoliSure evaluation report
Generated 2026-10-24T11:25:43 — policy: United India IHIP prospectus — 2 scenarios, split `dev`, mode `end-to-end`

> PLUMBING-ONLY SAMPLE scenarios (data/scenarios.sample.csv) - NOT real labels; metrics below are not evidence of accuracy.

## Pipeline metrics
| metric | value |
|---|---|
| verdict_accuracy | 1.0 |
| payout_mae_inr | 0.0 |
| payout_within_1_pct | 1.0 |
| citation_correctness | 1.0 |
| quote_verified_pct | 1.0 |
| extraction_accuracy | 1.0 |
| abstention_precision | None |
| abstention_recall | None |
| confident_wrong_rate | 0.0 |

## Plain-LLM baseline (same scenarios)
| metric | value |
|---|---|
| verdict_accuracy | 1.0 |
| payout_mae_inr | 0.0 |
| abstention_recall | None |
| n_scored | 2 |
| note | plain LLM (policy text + incident -> JSON), same scenarios |

## Cross-policy extraction
- SBI General Health Insurance - Retail (data/policy_b.pdf): 1.0 (built-in checks from facts stated in the task brief)

## Confusion (expected → predicted)
```
{
 "PARTIAL": {
  "PARTIAL": 1
 },
 "COVERED": {
  "COVERED": 1
 }
}
```