---
phase: 07-orchestration
plan: 02
subsystem: airflow-utils
tags: [airflow, alerting, data-quality, mlflow, utilities]
dependency_graph:
  requires: []
  provides:
    - airflow/dags/utils/alerting.py
    - airflow/dags/utils/data_quality.py
    - airflow/dags/utils/mlflow_helpers.py
  affects:
    - airflow/dags/ (all DAGs consuming utils)
tech_stack:
  added: []
  patterns:
    - Dual-channel alerting (Airflow logs + JSON files per D-13, D-14)
    - Centralized DAG utility modules per D-15
    - F1 threshold comparison gate per CNRY-02 (threshold=0.95)
key_files:
  created:
    - airflow/dags/utils/__init__.py
    - airflow/dags/utils/alerting.py
    - airflow/dags/utils/data_quality.py
    - airflow/dags/utils/mlflow_helpers.py
    - alerts/.gitkeep
  modified: []
decisions:
  - Used dict union type hints (dict | None) compatible with Python 3.10+
  - write_canary_alert uses side-by-side comparison dict per D-16
  - compare_models default threshold=0.95 per CNRY-02
  - ALERTS_DIR defaults to /opt/airflow/alerts (Docker Compose mount point)
metrics:
  duration: 113s
  completed_date: "2026-03-22T11:43:51Z"
  tasks_completed: 2
  files_created: 5
---

# Phase 07 Plan 02: DAG Utility Modules Summary

**One-liner:** Three shared utility modules (alerting, data-quality, MLflow helpers) enabling reusable, testable DAG logic with dual-channel alerting and F1-gated champion comparison.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create alerting utility module | 1c07e96 | airflow/dags/utils/__init__.py, airflow/dags/utils/alerting.py, alerts/.gitkeep |
| 2 | Create data quality and MLflow helper modules | aac1c25 | airflow/dags/utils/data_quality.py, airflow/dags/utils/mlflow_helpers.py |

## What Was Built

**airflow/dags/utils/alerting.py** — Dual-channel alert system:
- `write_alert()` — writes structured JSON alert files to alerts/ directory plus prints to Airflow logs
- `write_canary_alert()` — specialized alert for canary decisions with side-by-side champion/challenger metrics
- `on_failure_callback()` — Airflow callback that extracts dag_id, task_id, exception from context and writes dag_failure alert

**airflow/dags/utils/data_quality.py** — 5-check validation function per RETR-03:
- `run_data_quality_checks(df)` — validates null rate (<5%), fraud rate (1%-4%), schema match, minimum row count (1000), minimum fraud cases (10)
- Returns `{"passed": bool, "checks": [...]}` with full check details

**airflow/dags/utils/mlflow_helpers.py** — MLflow registry operations:
- `get_champion_metrics()` — retrieves champion model metrics from MLflow Registry
- `compare_models()` — F1-gated challenger vs champion comparison (threshold=0.95 per CNRY-02)
- `promote_to_champion()` — sets @champion alias for a given model version
- `get_previous_champion_version()` — reads current champion before promotion (for rollback tracking per CNRY-03)

## Verification

All three modules import successfully with the project venv. compare_models logic tested inline:
- challenger F1=0.96 vs champion F1=0.95 → should_promote=True (0.96 >= 0.9025)
- challenger F1=0.80 vs champion F1=0.95 → should_promote=False (0.80 < 0.9025)

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None — all utility functions are fully implemented. MLflow functions that connect to the registry (get_champion_metrics, promote_to_champion, get_previous_champion_version) will be exercised by the actual DAG in subsequent plans when MLflow is running.

## Self-Check: PASSED

Files created:
- airflow/dags/utils/__init__.py: FOUND
- airflow/dags/utils/alerting.py: FOUND
- airflow/dags/utils/data_quality.py: FOUND
- airflow/dags/utils/mlflow_helpers.py: FOUND
- alerts/.gitkeep: FOUND

Commits:
- 1c07e96: FOUND
- aac1c25: FOUND
