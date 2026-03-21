---
phase: 06-model-serving
plan: 01
subsystem: serving
tags: [mlflow, pyfunc, lightgbm, preprocessing, model-registry, sklearn]

# Dependency graph
requires:
  - phase: 05-ml-training
    provides: "LightGBM champion model in MLflow Registry with @champion alias, scaler.joblib, label_encoders.joblib, feature_names.joblib"
provides:
  - "FraudPyfunc PythonModel class bundling preprocessing + LightGBM inference"
  - "register_pyfunc_model() function that resolves @champion, downloads model, logs pyfunc, reassigns alias"
  - "make register-pyfunc Makefile target"
affects: [06-02, 06-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "mlflow.pyfunc.PythonModel for training-serving skew prevention"
    - "Artifact bundle pattern: scaler + label_encoders + feature_names + model in one log_model call"
    - "FRAUD_THRESHOLD env var for runtime threshold override"

key-files:
  created:
    - src/serving/register_pyfunc.py
  modified:
    - Makefile

key-decisions:
  - "Used mlflow.pyfunc.PythonModel instead of raw LightGBM flavor so preprocessing artifacts travel with model and REST endpoint accepts raw transactions"
  - "load_context() handles both directory (sklearn flavor) and joblib file for LightGBM model path flexibility"
  - "Copied FEATURE_COLUMNS and CATEGORICAL_COLUMNS directly (no import from model_scorer) so pyfunc is self-contained inside MLflow serving container"
  - "FRAUD_THRESHOLD read from environment variable at load_context() time (not hardcoded) per D-03"

patterns-established:
  - "Pyfunc pattern: load_context loads all artifacts once, predict() is stateless per-batch"
  - "Unknown categorical fallback: le.transform([x])[0] if x in le.classes_ else 0 — matches FraudScorer exactly"
  - "Registration pattern: resolve champion run_id → download artifact → log pyfunc → reassign champion alias"

requirements-completed: [SERV-03, SERV-04]

# Metrics
duration: 10min
completed: 2026-03-22
---

# Phase 06 Plan 01: FraudPyfunc Registration Summary

**Custom mlflow.pyfunc.PythonModel wrapping LightGBM + scaler/encoder artifacts into a single REST-servable bundle with @champion alias**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-21T22:43:00Z
- **Completed:** 2026-03-21T22:45:53Z
- **Tasks:** 2 of 2
- **Files modified:** 2

## Accomplishments

- Created FraudPyfunc class (mlflow.pyfunc.PythonModel) that bundles LightGBM + preprocessing artifacts into a single self-contained unit
- Registration script resolves @champion, downloads its artifact, logs pyfunc with pip_requirements, and moves @champion alias to new version
- Added make register-pyfunc Makefile target with correct .PHONY declaration and help entry

## Task Commits

Each task was committed atomically:

1. **Task 1: Create FraudPyfunc class and registration script** - `3d84dca` (feat)
2. **Task 2: Add register-pyfunc Makefile target** - `9ef0c16` (chore)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `src/serving/register_pyfunc.py` - FraudPyfunc PythonModel with load_context/predict, plus register_pyfunc_model() registration function (275 lines)
- `Makefile` - Added register-pyfunc to .PHONY, added target and help entry

## Decisions Made

- Copied FEATURE_COLUMNS and CATEGORICAL_COLUMNS directly rather than importing from model_scorer.py — required for self-contained pyfunc deployable inside MLflow serving container (no src/ package available there)
- load_context() checks if lgbm_model artifact path is a directory (sklearn flavor) or a file (joblib) — handles both mlflow.artifacts.download_artifacts output formats
- FRAUD_THRESHOLD is read at load_context() time from environment variable, defaulting to 0.5 — matches plan decision D-03

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required beyond existing MLflow/MinIO Docker services.

## Next Phase Readiness

- FraudPyfunc is importable and verified: `from src.serving.register_pyfunc import FraudPyfunc`
- Registration requires MLflow + MinIO Docker services running and @champion alias set (from Phase 5 training)
- Ready for Plan 02 (mlflow models serve REST endpoint setup)
- Ready for Plan 03 (load testing with locust)

---
*Phase: 06-model-serving*
*Completed: 2026-03-22*
