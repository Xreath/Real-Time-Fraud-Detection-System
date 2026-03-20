# Project Research Summary

**Project:** Realtime Fraud Detection — MLOps Deployment, Orchestration, and Monitoring
**Domain:** MLOps pipeline completion (serving, orchestration, observability) atop an existing Kafka/Spark/LightGBM stack
**Researched:** 2026-03-21
**Confidence:** HIGH (architecture and features grounded in direct codebase inspection; stack versions cross-referenced against venv and Docker configs)

## Executive Summary

This project is in the MLOps completion phase. Phases 1-5 (data ingestion, Spark streaming, LightGBM training, MLflow model registry) are already implemented and locked in. The remaining work — Phases 6-8 — adds the three operational layers that transform a working model into a production-grade ML system: model serving (Phase 6), orchestration/retraining (Phase 7), and observability (Phase 8). The recommended approach is additive, keeping the existing infrastructure intact and layering new services on top of the existing Docker Compose stack.

The recommended stack is deliberately minimal: `mlflow models serve` for local serving (zero new infrastructure), Apache Airflow 2.9.x for orchestration (explicitly required as a learning goal), and Prometheus + Grafana for monitoring (the dominant self-hosted ML observability stack). The single highest-risk technology addition is Airflow — its dependency surface is large, it requires a constraints file for installation, and its Docker Compose integration with the existing services has multiple known failure modes. The key recommendation is to treat Airflow network connectivity as the first validation step before writing any DAG code.

The most critical risk is training-serving skew: `mlflow models serve` exposes only the raw LightGBM model, not the preprocessing pipeline (`scaler.joblib`, `label_encoders.joblib`) that lives in `data/artifacts/`. This must be resolved in Phase 6 by wrapping preprocessing and model into a single `mlflow.pyfunc` artifact before load testing or any REST API integration. A secondary risk is that the absolute F1 threshold of 0.85 used in monitoring is too low relative to the model's actual performance of 0.982 — using a relative threshold (e.g., 3% relative drop from baseline) is the correct production pattern.

## Key Findings

### Recommended Stack

The existing stack (Kafka, Spark 3.5.4, LightGBM, MLflow 2.12.2, PostgreSQL 16, MinIO) is fixed. All new additions are additive. The MLflow server is pinned to v2.12.2 and all client code must stay `>=2.12.0,<3.0.0`. Airflow 2.9.x requires a constraints file on install to avoid SQLAlchemy conflicts with MLflow. Vertex AI deployment is a stretch goal and entirely decoupled from local infrastructure.

**Core technologies:**
- `mlflow models serve` (2.12.2): Local REST prediction endpoint — zero new infrastructure, serves registered champion model at `/invocations`
- Apache Airflow 2.9.3 (`python3.11` image): DAG orchestration for retraining and monitoring — required learning goal; use `LocalExecutor` (no Redis/Celery needed)
- Prometheus 2.52 + `prometheus-client` 0.20+: Time-series metrics scraping + Python instrumentation — pull model fits the existing service topology
- Grafana 11.0: Dashboard and alerting — Grafana 11 includes built-in alerting, eliminating Alertmanager dependency for portfolio scope
- `evidently` 0.4.30+: Drift detection reports — lighter than Great Expectations, generates HTML reports that can be logged to MLflow as artifacts
- `locust` 2.29+: Load testing — pure Python, designed for REST endpoints, no JVM dependency
- `google-cloud-aiplatform` 1.58+: Vertex AI SDK for stretch-goal cloud deployment — handles traffic splitting and auto-scaling natively
- Kafka JMX Exporter 1.0.x: Kafka broker metrics → Prometheus — standard path for Confluent 7.6.0 OSS setup

**Critical version constraints:**
- `mlflow<3.0.0` — server is pinned at 2.12.2; breaking API changes in 3.x
- Airflow must use official constraints file: `constraints-2.9.3/constraints-3.11.txt`
- Airflow workers need `JAVA_HOME` pointing to Java 11 (Spark 3.5.x requirement)
- Airflow image uses Python 3.11; rest of stack uses Python 3.12 — accepted split

### Expected Features

**Must have (table stakes — interview-ready baseline):**
- REST prediction endpoint at `/invocations` with `/health` check — every ML deployment demo requires this
- Model version pinning in serving — reproducibility baseline
- Preprocessing consistency (training-serving parity) — single most common failure mode in MLOps
- Scheduled retraining DAG (weekly cron) — absolute minimum acceptable retraining pattern
- Data quality gates before retraining — prevents silent model degradation from data pipeline failures
- Model promotion gating (challenger vs champion comparison) — prevents retraining regressions
- Model rollback capability — required recovery path for bad deploys
- Monitoring DAG with daily F1 check and fraud rate anomaly detection
- Grafana dashboard: transaction throughput, fraud rate, model latency, Kafka consumer lag
- Alerting on F1 degradation and DAG failure

**Should have (competitive differentiators):**
- Canary deploy (10% traffic split) + automatic rollback — mirrors fintech production deploy patterns
- Data drift detection (KS test / PSI) in monitoring DAG — detects distribution shift before F1 degrades
- Hybrid retraining trigger (schedule + performance threshold) — shows understanding of gradual vs sudden drift
- Load test results documented — proves endpoint is production-viable, demonstrates performance awareness
- Grafana dashboard with Spark streaming + Kafka lag together — tells the full streaming story

**Defer to v2+:**
- GCP Vertex AI deployment — requires GCP project setup, significant cloud configuration
- A/B testing via Vertex AI traffic splitting — requires Vertex AI endpoint running
- SHAP-based feature importance shift detection — high complexity for marginal portfolio value
- Concept drift via sliding window F1 trend — add only after all other monitoring is complete

**Deliberate anti-features (do not build):**
- Feast feature store, Delta Lake, multi-model ensemble, gRPC serving, custom auth on endpoint, multi-region deployment, real-time sub-second Grafana refresh, Slack alerts — each adds complexity that obscures the ML story without adding demonstrable ML content

### Architecture Approach

The architecture separates concerns into four independent layers: serving (MLflow REST endpoint), orchestration (Airflow DAGs), and observability (Prometheus + Grafana) — all layered above the existing ingestion/processing/ML layers. The key structural principle is that Airflow DAG files contain only scheduling and task graph definitions; all executable logic lives in `src/orchestration/` and is called via `PythonOperator`. The custom metrics emitter (`src/monitoring/metrics.py`) runs as a separate Docker Compose service, consuming from the `fraud-alerts` Kafka topic and exposing a Prometheus-scrape endpoint. The model serving container restarts are triggered from Airflow DAGs using the Docker SDK after each champion alias promotion.

**Major components:**
1. `mlflow-serve` container: Exposes champion model as REST API, loads from `models:/fraud-detection@champion`, exposes latency metrics to Prometheus
2. Airflow (webserver + scheduler): Orchestrates retraining DAG (weekly cron + F1 sensor) and monitoring DAG (daily drift + fraud rate checks); connects to MLflow, Spark, Postgres, Kafka via Docker service names
3. Prometheus + Grafana: Scrapes Kafka JMX, Spark metrics, MLflow serve, and the custom metrics emitter; Grafana queries Prometheus for dashboards and alert evaluation
4. `src/monitoring/metrics.py` process: Reads `fraud-alerts` Kafka topic, computes rolling fraud rate, exposes Prometheus gauge/counter at `:8000/metrics`
5. Vertex AI endpoint (stretch): Managed cloud serving with auto-scaling and traffic splitting, deployed via `google-cloud-aiplatform` SDK from Airflow DAG

**Build order dictated by hard dependencies:**
MLflow serve → Prometheus + Grafana → Airflow Docker setup → Retraining DAG → Monitoring DAG → Vertex AI (decoupled stretch)

### Critical Pitfalls

1. **Training-serving skew (Pitfall 1)** — `mlflow models serve` exposes only the raw LightGBM model; preprocessing artifacts (`scaler.joblib`, `label_encoders.joblib`) are not part of the logged artifact. Fix: wrap preprocessing + model into a single `mlflow.pyfunc` custom model before serving. Verify by sending identical input to both `FraudScorer.score()` and the REST endpoint and confirming scores match within 0.001. Must resolve in Phase 6 before load testing.

2. **Airflow DAG-level import side effects (Pitfall 3)** — Importing heavy libraries (LightGBM, pandas, mlflow) at DAG file module level causes the Airflow scheduler to re-execute those imports every 30 seconds, causing scheduler lag and memory pressure. Fix: keep DAG files thin — only `datetime`, `pendulum`, and Airflow operators at module level. All heavy logic moves to `src/orchestration/`. Enforce from the first DAG written.

3. **Docker networking: `localhost` vs service names (Pitfall 6 + 9)** — `localhost` inside any container refers to that container's loopback, not the host or other containers. All Airflow connections, Prometheus scrape targets, and MLflow URIs must use Docker service names (`mlflow:5000`, `kafka:29092`, `prometheus:9090`). Validate Airflow network connectivity with `docker exec airflow-scheduler curl http://mlflow:5000/health` before writing any DAG code.

4. **Non-idempotent retraining DAG (Pitfall 4)** — Airflow retries and backfill mechanics run tasks multiple times. Parquet append without a deduplication step and MLflow runs without idempotency keys will corrupt training data and create duplicate registry history. Fix: use `execution_date` as Parquet partition key; check MLflow `run_id` before any registry promotion; use XCom to carry `run_id` across tasks.

5. **Miscalibrated F1 drift threshold (Pitfall 8)** — The absolute threshold of `F1 < 0.85` will never trigger for a model operating at 0.982. Fix: use a relative threshold (`current_f1 < baseline_f1 * 0.97`) stored as an MLflow model tag at promotion time. Verify by simulating a 5% relative drop and confirming the retraining DAG triggers.

## Implications for Roadmap

Based on combined research, the three remaining phases have a clear dependency order with internal structure:

### Phase 6: Local Model Serving + Load Testing

**Rationale:** MLflow Registry already has a `@champion` alias from Phase 5. This phase has zero new infrastructure dependencies — it only requires running `mlflow models serve`. It is also the prerequisite for the retraining DAG (which restarts the serve container) and for the canary deploy pattern. Resolving training-serving skew here prevents compounding downstream issues. This is the fastest win and the clearest validation gate.

**Delivers:** Queryable REST prediction endpoint at `/invocations` and `/health`; load test results documenting p50/p95 latency and max RPS; preprocessing bundled into pyfunc artifact.

**Addresses:** REST endpoint (P1 table stakes), health check (P1), preprocessing consistency (P1 — most critical), model version pinning (P1), load test documentation (P2 differentiator).

**Avoids:** Training-serving skew (Pitfall 1), MLflow version mismatch (Pitfall 2).

**Research flags:** Standard pattern — `mlflow models serve` is well-documented. No additional research phase needed. The pyfunc preprocessing wrapper pattern is high-confidence.

### Phase 7: Airflow Orchestration + Retraining + Canary

**Rationale:** Airflow is the critical path blocker for both retraining and monitoring DAGs. Docker Compose integration has multiple known failure modes (network isolation, SQLAlchemy conflicts, import side effects) that must be validated before writing any DAG logic. This phase bundles Airflow setup, the retraining DAG, the monitoring DAG trigger logic, and the canary/rollback mechanism — all tightly coupled through Airflow's task graph and MLflow alias management.

**Delivers:** Airflow running in Docker Compose with all connections validated; weekly retraining DAG with data quality gates, challenger vs champion comparison, and model promotion; performance-triggered retraining sensor; canary deploy (10% traffic split) with automatic rollback; hybrid trigger (schedule + threshold).

**Addresses:** Scheduled retraining (P1), data quality gates (P1), model promotion gating (P1), model rollback (P1), performance-triggered retraining (P2), canary deploy + rollback (P2 differentiator), hybrid trigger (P2).

**Avoids:** Airflow DAG import side effects (Pitfall 3), non-idempotent DAG (Pitfall 4), canary rollback that never fires (Pitfall 5), Airflow network isolation (Pitfall 9), miscalibrated F1 threshold (Pitfall 8).

**Research flags:** Airflow Docker Compose integration with the existing stack (service name resolution, SQLAlchemy constraint file, Docker socket mounting for container restarts) has enough project-specific complexity to warrant a research-phase pass. Specifically: SparkSubmitOperator configuration against the existing spark-master:7077 and Airflow → MinIO artifact path resolution are non-obvious.

### Phase 8: Prometheus + Grafana Observability

**Rationale:** Prometheus and Grafana are independent of Airflow — they can be added to Docker Compose and started without Airflow running. However, the monitoring DAG (Phase 7) needs Prometheus metrics to exist before it can query drift signals. Placing observability after Airflow setup allows the monitoring DAG to be wired to live metrics rather than stubs. The custom metrics emitter (`metrics.py`) requires Kafka's `fraud-alerts` topic, which has been populated since Phase 3.

**Delivers:** Prometheus scraping Kafka JMX, Spark metrics, MLflow serve latency, and custom fraud rate emitter; Grafana dashboard with throughput, fraud rate, model latency, and Kafka consumer lag panels; alerting rules for F1 degradation and high fraud rate; data drift detection (KS/PSI) in monitoring DAG; daily F1 check with relative threshold.

**Addresses:** Transaction throughput metric (P1), fraud rate metric (P1), model prediction latency metric (P1), Kafka consumer lag metric (P1), alerting on F1 degradation (P1), DAG failure alerting (P1), data drift detection (P2), Grafana Spark/Kafka dashboard (P2 differentiator).

**Avoids:** Prometheus scrape targets using localhost (Pitfall 6), dashboard built before metrics emitted (Pitfall 7), miscalibrated F1 threshold (Pitfall 8).

**Research flags:** Prometheus JMX Exporter sidecar configuration for Confluent 7.6.0 (port 9404) is operationally fiddly and worth a targeted research pass. Grafana dashboard provisioning (JSON via `configs/grafana/dashboards/` rather than manual UI) needs verification against Grafana 11 provisioning API — manual config is lost on restart.

### Phase 9 (Stretch): GCP Vertex AI Deployment

**Rationale:** Completely decoupled from Phases 6-8. Requires a GCP project, GCS bucket for artifact staging, and `google-cloud-aiplatform` SDK. This is the cloud deployment validation of the serving pattern established in Phase 6, plus native A/B traffic splitting.

**Delivers:** Model artifact copied from MinIO to GCS; Vertex AI endpoint with champion model deployed; traffic split (90% champion / 10% challenger) via Vertex AI SDK; documented A/B deployment pattern.

**Addresses:** GCP Vertex AI deployment (P3), A/B testing via traffic splitting (P3).

**Research flags:** Requires a full research-phase pass. GCP SDK versions increment rapidly (LOW confidence), Vertex AI endpoint configuration for a custom pyfunc model has project-specific considerations, and ADC credential setup in Docker Compose is non-trivial.

### Phase Ordering Rationale

- Serving before orchestration: The retraining DAG restarts the `mlflow-serve` container. Serving must be stable before Airflow depends on it.
- Monitoring infrastructure before monitoring DAG: The monitoring DAG queries Prometheus. Prometheus must be scraping before the DAG logic is wired.
- Airflow setup is a sequential prerequisite within Phase 7: Network validation must complete before any DAG is written. This is the single highest-risk step in the entire roadmap and should be its own milestone.
- Vertex AI is fully decoupled: It can be done in parallel with or after Phase 8, purely based on available time and GCP access.

### Research Flags

Phases needing deeper research during planning:
- **Phase 7 (Airflow setup):** SparkSubmitOperator against existing spark-master:7077, Docker socket mounting for container restarts from DAGs, and MinIO endpoint environment variable propagation to Airflow workers are all project-specific integration challenges.
- **Phase 9 (Vertex AI):** GCP SDK version pinning, pyfunc model upload to GCS, Vertex AI endpoint configuration — all LOW confidence; requires research before planning.

Phases with standard, well-documented patterns (skip research-phase):
- **Phase 6 (MLflow serving):** `mlflow models serve` behavior, pyfunc preprocessing wrapper pattern, and locust load testing are HIGH confidence established patterns.
- **Phase 8 (Prometheus + Grafana):** Core Prometheus scrape model, `prometheus-client` Python instrumentation, and Grafana 11 datasource provisioning are well-documented. JMX Exporter sidecar configuration may need a targeted lookup but does not require a full research phase.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | Existing stack versions are HIGH confidence (confirmed from Docker configs and venv). New additions (Airflow 2.9.3, Grafana 11, Prometheus 2.52) are MEDIUM — versions cross-referenced against training knowledge through August 2025; may have minor increments but recommended floors are correct. GCP SDK is LOW confidence — use as floor only. |
| Features | HIGH | Based on well-established MLOps patterns for Kafka + Spark + MLflow + Airflow stacks. Feature prioritization (P1/P2/P3) is grounded in direct project context and industry norms. |
| Architecture | HIGH | Based on direct codebase inspection (`docker-compose.yml`, `src/config.py`, `spark_consumer.py`, `train_model.py`). Integration patterns (Docker service names, MLflow alias API, Airflow PythonOperator) are all stable well-documented behaviors. |
| Pitfalls | HIGH | 7 of 9 pitfalls are HIGH confidence — they describe fundamental behaviors of Docker networking, Airflow scheduler mechanics, and MLflow model serving. 2 are MEDIUM — F1 threshold calibration heuristics and Grafana provisioning directory behavior. |

**Overall confidence:** HIGH for Phase 6 and Phase 8; MEDIUM for Phase 7 Airflow integration details; LOW for Phase 9 Vertex AI.

### Gaps to Address

- **Airflow constraints file resolution for SQLAlchemy:** MLflow 2.12.x and Airflow 2.9.x both depend on SQLAlchemy. The constraints file is supposed to resolve this, but the exact venv interaction with the existing `requirements.txt` should be validated with a dry-run install before committing to the approach.
- **Docker socket mounting for container restart from DAGs:** The pattern `docker.from_env().containers.get("mlflow-serve").restart()` requires mounting `/var/run/docker.sock` into the Airflow scheduler container. This works on Linux but has known quirks on macOS Docker Desktop. The macOS path is `/var/run/docker.sock.raw` in some setups. Validate during Phase 7 setup.
- **Spark metrics endpoint for Prometheus:** Prometheus cannot scrape the Spark Web UI HTML at port 8080. The correct path is either the Spark metrics servlet at port 4040 `/metrics/json` (Prometheus-incompatible format) or a JMX Exporter sidecar on the Spark containers. The exact configuration against the existing `spark-master` and `spark-worker` service names needs validation.
- **GCP project availability:** Phase 9 assumes a GCP project exists and `gcloud auth application-default login` has been run. This is an external dependency that cannot be validated during research.

## Sources

### Primary (HIGH confidence)
- `Dockerfile.mlflow` in this repo — MLflow server version 2.12.2 confirmed
- `requirements.txt` in this repo — existing dependency floor versions
- `docker-compose.yml` in this repo — service image versions, network topology
- `.venv/lib/python3.12/site-packages/` dist-info — scipy 1.17.1, google-auth 2.48.0, pandas 2.3.3 confirmed installed
- `src/serving/model_scorer.py` — preprocessing artifact loading pattern confirmed
- `.planning/PROJECT.md`, `task_plan.md` — project phase scope and learning goals

### Secondary (MEDIUM confidence)
- Training knowledge (cutoff August 2025) — Airflow 2.9.x as stable 2.x line, Grafana 11.0 release, Prometheus 2.52, Evidently 0.4.x patterns, MLOps retraining trigger patterns, canary deploy norms at fintechs
- Apache Airflow constraints-file requirement — well-documented community knowledge
- Airflow Python 3.11 vs 3.12 official image compatibility — MEDIUM; official images slower to adopt 3.12

### Tertiary (LOW confidence)
- GCP Vertex AI SDK exact version ceiling — `>=1.58.0` as floor only; increment rapidly
- Grafana provisioning directory behavior on restart — MEDIUM-LOW; validate empirically during Phase 8 setup

---
*Research completed: 2026-03-21*
*Ready for roadmap: yes*
