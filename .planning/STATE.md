# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-21)

**Core value:** Demonstrate a complete, production-realistic MLOps pipeline that can be discussed in depth during interviews
**Current focus:** Phase 6 — Model Serving

## Current Position

Phase: 6 of 8 (Model Serving)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-03-21 — Roadmap created; phases 1-5 marked complete, phases 6-8 defined

Progress: [█████░░░░░░░░░░░] 5 of 8 phases complete (plans TBD)

## Performance Metrics

**Velocity:**
- Total plans completed: 0 (phases 1-5 pre-existed this workflow)
- Average duration: -
- Total execution time: -

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

**Recent Trend:**
- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Phase 5]: LightGBM champion model (Val AUC-PR=0.998, Test F1=0.982) promoted to MLflow Registry with @champion alias
- [Phase 6 prep]: Must wrap preprocessing artifacts (scaler.joblib, label_encoders.joblib) into mlflow.pyfunc custom model to avoid training-serving skew — do not use raw mlflow models serve against LightGBM flavor directly

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 7]: Airflow Docker Compose integration is highest-risk step: SQLAlchemy version conflict with MLflow 2.12.x requires constraints file; Docker socket mounting for container restarts has macOS quirks; validate network connectivity (service name resolution) before writing any DAG code
- [Phase 7]: SparkSubmitOperator configuration against existing spark-master:7077 is non-obvious — needs validation during planning
- [Phase 8]: Prometheus cannot scrape Spark Web UI HTML at port 8080; requires JMX Exporter sidecar on spark-master and spark-worker containers — exact config needs research
- [Phase 8]: Grafana dashboard provisioning must use JSON files in configs/grafana/dashboards/ — manual UI config is lost on restart

## Session Continuity

Last session: 2026-03-21
Stopped at: Roadmap created, STATE.md initialized — ready to plan Phase 6
Resume file: None
