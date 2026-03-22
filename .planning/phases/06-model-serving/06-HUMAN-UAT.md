---
status: partial
phase: 06-model-serving
source: [06-VERIFICATION.md]
started: 2026-03-22T00:00:00Z
updated: 2026-03-22T00:00:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Start docker compose and confirm fraud-api is healthy
expected: docker compose ps shows fraud-api (healthy) after 60-90 seconds; curl http://localhost:5002/health returns HTTP 200
result: [pending]

### 2. POST to /invocations with a sample transaction JSON
expected: Response contains predictions[].fraud_score (float 0-1) and predictions[].fraud_prediction (0 or 1)
result: [pending]

### 3. Run pytest tests/test_serving.py with fraud-api healthy
expected: TestHealthCheck, TestInvocations, and TestNoSkew all pass; skew < 0.001 between FraudScorer.score() and REST scores
result: [pending]

### 4. Run bash scripts/smoke_test_serving.sh with fraud-api healthy
expected: 3/3 tests PASS: /health 200, normal transaction fraud_score returned, high-risk transaction fraud_score returned
result: [pending]

### 5. Check TestChampionAlias.test_model_uri_uses_champion behavior
expected: Note: test calls GET /version which MLflow does not expose (404). Confirm acceptable as known-failing edge case or fix to use /ping instead.
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
