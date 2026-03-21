---
phase: 06-model-serving
plan: 02
subsystem: infra
tags: [mlflow, docker, docker-compose, lightgbm, fraud-api, serving]

# Dependency graph
requires:
  - phase: 06-01
    provides: FraudPyfunc model registered in MLflow Model Registry with @champion alias
provides:
  - Dockerfile.serving extending MLflow 2.12.2 with lightgbm + scikit-learn for pyfunc inference
  - fraud-api Docker service on port 5002 serving models:/fraud-detection-model@champion
  - SERVING_WORKERS and FRAUD_THRESHOLD env vars in .env for runtime control
affects:
  - 06-03 (load testing and Vertex AI)
  - 07 (Airflow orchestration using fraud-api health endpoint)

# Tech tracking
tech-stack:
  added: [Dockerfile.serving, fraud-api docker-compose service]
  patterns:
    - MLflow models serve with --env-manager local --no-conda inside pre-built Docker image
    - start_period: 60s health check delay for model download from MinIO at startup
    - restart: on-failure:3 hybrid restart strategy for transient failures

key-files:
  created:
    - Dockerfile.serving
  modified:
    - docker-compose.yml
    - .env (gitignored - local changes only)

key-decisions:
  - "Port 5002 for fraud-api to avoid conflicts with MLflow (5001), Spark UI (8080), MinIO (9000/9001)"
  - "Model URI models:/fraud-detection-model@champion - uses alias not version for zero-downtime model updates"
  - "--env-manager local --no-conda - uses container pre-installed packages, no nested virtualenv overhead"
  - "start_period: 60s with retries: 10 - allows full model artifact download from MinIO before health checks"
  - ".env SERVING_WORKERS and FRAUD_THRESHOLD with docker-compose defaults as fallback"

patterns-established:
  - "Serving Dockerfile: Extend MLflow base image, install ML deps, no ENTRYPOINT (command in compose)"
  - "Service health check: start_period for model-heavy services that need download time before ready"

requirements-completed: [SERV-01, SERV-02, SERV-05]

# Metrics
duration: 5min
completed: 2026-03-21
---

# Phase 06 Plan 02: Docker Serving Infrastructure Summary

**MLflow fraud-api service on port 5002 with Dockerfile.serving extending MLflow 2.12.2 base image, lightgbm + scikit-learn inference deps, and champion model URI wired into docker-compose.yml**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-21T22:47:28Z
- **Completed:** 2026-03-21T22:52:00Z
- **Tasks:** 2
- **Files modified:** 3 (Dockerfile.serving created, docker-compose.yml updated, .env updated locally)

## Accomplishments
- Created Dockerfile.serving extending ghcr.io/mlflow/mlflow:v2.12.2 with all inference dependencies (lightgbm, scikit-learn, pandas, numpy, psycopg2-binary, boto3)
- Added fraud-api service to docker-compose.yml: port 5002, depends on mlflow healthcheck, model URI models:/fraud-detection-model@champion, --env-manager local --no-conda
- Configured robust health check with 60s start_period and 10 retries to handle model download from MinIO before readiness
- Added SERVING_WORKERS=2 and FRAUD_THRESHOLD=0.5 to .env (gitignored, local-only)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create Dockerfile.serving** - `441354c` (feat)
2. **Task 2: Add fraud-api service to docker-compose.yml** - `b3df219` (feat)

**Plan metadata:** (see below)

## Files Created/Modified
- `Dockerfile.serving` - MLflow 2.12.2 base image with lightgbm/sklearn inference deps, no ENTRYPOINT
- `docker-compose.yml` - Added fraud-api service with port 5002, model URI, health checks, restart policy
- `.env` - Added SERVING_WORKERS=2 and FRAUD_THRESHOLD=0.5 (gitignored, not committed)

## Decisions Made
- Model URI uses @champion alias (`models:/fraud-detection-model@champion`) not a version number — enables zero-downtime model updates by re-aliasing in MLflow Registry without redeploying containers
- `--env-manager local --no-conda` flag combination: uses container's pre-installed Python env from Dockerfile.serving, skips nested virtualenv creation that would fail in a container context
- `start_period: 60s` with `retries: 10` and `interval: 15s` = up to 2m30s total patience for MLflow to download model artifacts from MinIO before first health check failure is counted
- `.env` changes are local-only (gitignored) — docker-compose.yml contains `${SERVING_WORKERS:-2}` defaults as fallback

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `.env` file is gitignored (contains credentials). The `SERVING_WORKERS` and `FRAUD_THRESHOLD` lines were added to the local `.env` file successfully but are not committed to git. The docker-compose.yml uses `${SERVING_WORKERS:-2}` and `${FRAUD_THRESHOLD:-0.5}` defaults, so the service works without the .env values present.

## User Setup Required

No external service configuration required. The fraud-api service will start automatically with `docker compose up -d`, but requires the MLflow Model Registry to have the `fraud-detection-model@champion` alias registered (done in Plan 06-01).

## Next Phase Readiness
- Dockerfile.serving and fraud-api service ready for Plan 06-03 (load testing and Vertex AI stretch goal)
- The full stack can be tested with: `docker compose up -d` then `curl http://localhost:5002/health`
- Model serving endpoint at: `POST http://localhost:5002/invocations` with JSON transaction payload

## Self-Check: PASSED

- FOUND: Dockerfile.serving
- FOUND: docker-compose.yml (with fraud-api service)
- FOUND: 06-02-SUMMARY.md
- FOUND commit: 441354c (Dockerfile.serving)
- FOUND commit: b3df219 (docker-compose.yml fraud-api)

---
*Phase: 06-model-serving*
*Completed: 2026-03-21*
