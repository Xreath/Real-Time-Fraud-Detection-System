---
phase: 07-orchestration
plan: 01
subsystem: infra
tags: [airflow, docker-compose, postgresql, orchestration, mlops]

# Dependency graph
requires:
  - phase: 06-model-serving
    provides: mlflow service with health check, fraud-api service definitions in docker-compose.yml
provides:
  - Dockerfile.airflow with apache/airflow:2.9.3-python3.11 and all required ML/MLflow packages
  - docker-compose.yml with 4 Airflow services (postgres-airflow, airflow-init, airflow-webserver, airflow-scheduler)
  - Dedicated postgres-airflow database on port 5433
  - DAG directory airflow/dags/ mounted into containers
  - Makefile targets for Airflow lifecycle management
affects:
  - 07-02: retraining DAG — needs webserver/scheduler running, DAGs dir mounted
  - 07-03: monitoring DAG — needs scheduler and src/ volume
  - 07-04: orchestration validation — needs all Airflow services healthy

# Tech tracking
tech-stack:
  added:
    - apache/airflow:2.9.3-python3.11
    - postgres:16-alpine (separate instance for Airflow metadata)
    - Airflow LocalExecutor (no Celery/Redis overhead needed)
  patterns:
    - YAML anchors (x-airflow-common) for shared environment/volume definitions across Airflow services
    - Two-phase Airflow startup (init container → webserver+scheduler) via docker compose wait
    - Separate PostgreSQL instances for MLflow and Airflow to avoid schema conflicts

key-files:
  created:
    - Dockerfile.airflow
    - airflow/dags/.gitkeep
  modified:
    - docker-compose.yml
    - Makefile

key-decisions:
  - "Airflow 2.9.3 with constraints-3.11.txt prevents SQLAlchemy version conflicts with MLflow 2.12.x"
  - "Separate postgres-airflow service on port 5433 to avoid conflict with MLflow postgres on 5432"
  - "YAML anchors (x-airflow-common) keep environment and volume config DRY across 3 Airflow service definitions"
  - "AIRFLOW_UID=50000 with group 0 for Docker socket access on macOS/Linux"
  - "Port 8081 for webserver to avoid conflict with Spark Master UI on 8080"
  - "airflow-init as one-shot container (restart: no) with service_completed_successfully condition"

patterns-established:
  - "Two-stage Airflow startup: init completes first, then webserver+scheduler via depends_on conditions"
  - "Docker socket mounted for container restart capability in DAG operators"
  - "alerts/ directory mounted into Airflow containers for DAG-generated alert persistence"

requirements-completed: [AFLO-01, AFLO-02, AFLO-03, AFLO-04]

# Metrics
duration: 2min
completed: 2026-03-22
---

# Phase 07 Plan 01: Airflow Docker Compose Infrastructure Summary

**Airflow 2.9.3 with LocalExecutor wired into docker-compose.yml: dedicated PostgreSQL, Docker socket, DAG mount, and all ML packages installed under Airflow constraints file**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-03-22T11:41:52Z
- **Completed:** 2026-03-22T11:43:36Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created Dockerfile.airflow with apache/airflow:2.9.3-python3.11 base, installing mlflow==2.12.2, pyspark==3.5.0, docker SDK, and all ML packages under Airflow's constraints file to avoid SQLAlchemy conflicts
- Added 4 Airflow services to docker-compose.yml using YAML anchors for DRY shared config: postgres-airflow (port 5433), airflow-init (one-shot DB initialization), airflow-webserver (port 8081), airflow-scheduler
- Added 4 Makefile targets (airflow-up, airflow-down, airflow-logs, airflow-dags) with staged startup flow

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Dockerfile.airflow and Airflow Docker Compose services** - `e211b56` (feat)
2. **Task 2: Add Makefile targets and validate Docker Compose config** - `890fb92` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `Dockerfile.airflow` - Custom Airflow image with ML packages installed under constraints
- `airflow/dags/.gitkeep` - Ensures DAG directory exists in git for volume mounting
- `docker-compose.yml` - Added YAML anchor block + 4 Airflow services + postgres_airflow_data volume
- `Makefile` - Added airflow-up/down/logs/dags targets and updated .PHONY
- `.env` - Added AIRFLOW_UID=50000 (not committed, gitignored by design)

## Decisions Made

- Used `--constraint` flag with Airflow's official constraints-3.11.txt to prevent SQLAlchemy version conflicts between Airflow 2.9.3 and MLflow 2.12.2
- Separate postgres-airflow service on port 5433 (host) / 5432 (container) avoids collision with MLflow postgres on host port 5432
- YAML anchors (`x-airflow-common`, `airflow-common-env`, `airflow-common-volumes`) keep all three Airflow services DRY
- airflow-init uses `restart: "no"` and webserver/scheduler use `service_completed_successfully` condition to guarantee DB is initialized before services start
- Port 8081 for webserver avoids conflict with Spark Master Web UI on 8080

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `.env` file is gitignored so AIRFLOW_UID=50000 addition is on disk but not tracked in git. This is by design — `.env` files are excluded from version control for security reasons.

## User Setup Required

None - no external service configuration required beyond what's in `.env`.

## Next Phase Readiness

- Airflow infrastructure fully defined and `docker compose config` validates successfully
- Ready for Plan 07-02: write the retraining DAG (postgres-airflow and Airflow services available)
- Ready for Plan 07-03: write the monitoring/alerting DAG
- `make airflow-up` will start the full Airflow stack when Docker services are running

---
*Phase: 07-orchestration*
*Completed: 2026-03-22*
