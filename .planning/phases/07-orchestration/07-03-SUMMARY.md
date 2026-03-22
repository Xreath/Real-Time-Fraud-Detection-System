---
phase: 07-orchestration
plan: 03
subsystem: orchestration
tags: [airflow, mlflow, docker, retraining, canary, mlops]

# Dependency graph
requires:
  - phase: 07-02
    provides: utility modules (alerting.py, data_quality.py, mlflow_helpers.py)
  - phase: 07-01
    provides: Airflow Docker Compose setup and infrastructure
  - phase: 05-training
    provides: train_model.py and prepare_data.py pipeline functions
  - phase: 06-model-serving
    provides: register_pyfunc.py for pyfunc re-registration, fraud-api container

provides:
  - "airflow/dags/retraining_dag.py: full retraining DAG with 10-task pipeline"
  - "Weekly Sunday 02:00 UTC retraining schedule (RETR-01)"
  - "Automated model promotion via canary evaluation (CNRY-01 through CNRY-04)"
  - "Data quality gate blocking training on validation failure (RETR-03)"
  - "fraud-api container restart + health check after champion promotion"

affects:
  - "08-monitoring (monitoring DAG will trigger this DAG on F1 degradation)"
  - "fraud-api container (restarted by promote branch)"

# Tech tracking
tech-stack:
  added:
    - "docker Python SDK (docker.from_env()) for container management"
  patterns:
    - "BranchPythonOperator for canary promote/rollback routing"
    - "XCom for inter-task state sharing (best_model, canary_result, prev_champion_version)"
    - "Simulated canary via batch validation (no real traffic split)"
    - "MLflow dedicated canary-evaluation run for traceability"

key-files:
  created:
    - airflow/dags/retraining_dag.py
  modified: []

key-decisions:
  - "Challenger must achieve F1 >= champion_F1 * 0.95 to be promoted (threshold=0.95 per CNRY-02)"
  - "Rollback means: do not promote, champion alias unchanged — challenger never deployed (per D-07)"
  - "Unique seed per run derived from run_id MD5 hash for fresh data while maintaining reproducibility"
  - "Pyfunc re-registration after promote_model: ensures fraud-api loads preprocessing artifacts (Phase 6 pattern)"
  - "register_pyfunc non-fatal on failure: champion alias promoted first, restart still proceeds"

patterns-established:
  - "DAG task functions as module-level functions (not lambdas) for testability and readability"
  - "XCom for cross-task state: best_model, champion_metrics, challenger_metrics, prev_champion_version"
  - "trigger_rule=none_failed_min_one_success on EmptyOperator end task for branch convergence"
  - "Canary evaluation logged to MLflow as dedicated run (canary-evaluation) for audit trail"

requirements-completed: [RETR-01, RETR-02, RETR-04, RETR-05, CNRY-01, CNRY-02, CNRY-03, CNRY-04]

# Metrics
duration: 15min
completed: 2026-03-22
---

# Phase 07 Plan 03: Retraining DAG Summary

**Airflow retraining DAG with 10-task pipeline: data generation, quality gate, Spark features, model training, simulated canary evaluation (challenger vs champion F1 >= 0.95), promote/rollback branching, fraud-api container restart, and health verification**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-22T11:45:56Z
- **Completed:** 2026-03-22T12:01:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `airflow/dags/retraining_dag.py` (495 lines) with the full retraining pipeline
- Implemented 10 Airflow tasks in a clear dependency chain with BranchPythonOperator for promote/rollback
- Integrated all utility modules from Plan 02 (alerting, data_quality, mlflow_helpers) and existing training pipeline (prepare_data.py, train_model.py, register_pyfunc.py)
- Canary evaluation logged to MLflow as dedicated `canary-evaluation` run for full auditability

## Task Commits

Each task was committed atomically:

1. **Task 1: Create retraining DAG with data generation and quality gate** - (feat(07-03))

**Plan metadata:** (docs(07-03))

## Files Created/Modified

- `airflow/dags/retraining_dag.py` - Full 10-task retraining DAG with weekly schedule, data quality gate, Spark features, 4-model training, simulated canary evaluation (F1 threshold 0.95), BranchPythonOperator promote/rollback, Docker SDK container restart, health check

## Decisions Made

- **Pyfunc re-registration non-fatal:** `register_pyfunc_model()` is called after `promote_to_champion()` but wrapped in try/except. If it fails, the champion alias is already promoted and `fraud-api` restart will pick up the native LightGBM model. This prevents a pyfunc-registration issue from blocking the entire deployment.
- **No `champion_metrics` propagation issue:** When no champion exists (first run), `canary_evaluate` unconditionally promotes and sets `should_promote=True` without calling `compare_models`, avoiding division-by-zero on empty champion metrics.
- **train_and_log_model `params` argument:** The actual signature in `train_model.py` takes `params` as the third positional argument (between `model` and `X_train`), so `get_models()` returns `(name, model, params)` tuples and the DAG correctly unpacks all three.

## Deviations from Plan

None - plan executed exactly as written, with minor additions to handle edge cases (first-run unconditional promotion, pyfunc non-fatal failure handling).

## Issues Encountered

- **train_and_log_model signature mismatch in plan:** The plan's interface spec omits the `params` argument that exists in the actual `train_model.py` (line 318: `def train_and_log_model(name, model, params, X_train, ...)`). The DAG correctly implements the actual signature by unpacking `(name, model, params)` from `get_models()` tuples. This is a documentation error in the plan, not a code issue.

## User Setup Required

None - no external service configuration required beyond what was set up in Plans 01 and 02.

## Next Phase Readiness

- Retraining DAG is complete and ready for deployment into the running Airflow instance
- Phase 07 Plan 04 (monitoring DAG) can now reference `retraining_dag` as the trigger target for F1 degradation alerts
- The `canary-evaluation` MLflow run pattern establishes how the monitoring DAG should log its own evaluation results

---
*Phase: 07-orchestration*
*Completed: 2026-03-22*
