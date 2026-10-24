# PoliSure evaluation report
Generated 2026-10-24T12:13:28 — policy: United India IHIP prospectus — 26 scenarios, split `dev`, mode `engine-only`

> Authored by the team; drafted with AI assistance and verified against the policy.

## Pipeline metrics
| metric | value |
|---|---|
| verdict_accuracy | 0.9615 |
| payout_mae_inr | 0.0 |
| payout_within_1_pct | 0.9583 |
| citation_correctness | 0.44 |
| quote_verified_pct | 0.9697 |
| extraction_accuracy | 1.0 |
| abstention_precision | 0.6667 |
| abstention_recall | 1.0 |
| confident_wrong_rate | 0.0 |

## Confusion (expected → predicted)
```
{
 "COVERED": {
  "COVERED": 6
 },
 "PARTIAL": {
  "PARTIAL": 9
 },
 "NOT_COVERED": {
  "NOT_COVERED": 8,
  "NEEDS_REVIEW": 1
 },
 "NEEDS_REVIEW": {
  "NEEDS_REVIEW": 2
 }
}
```