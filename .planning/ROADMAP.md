# Roadmap: Real-Time Fraud Detection System

## Overview

Phases 1-5 delivered the full data pipeline: Docker Compose infrastructure, synthetic transaction generation, Kafka streaming, Spark Structured Streaming feature engineering, LightGBM training with MLflow tracking, and model registry with a champion alias. Phases 6-8 complete the MLOps story by adding the three operational layers that make the model production-grade: a queryable REST serving endpoint (Phase 6), Airflow-orchestrated retraining and canary deploy (Phase 7), and Prometheus + Grafana observability (Phase 8).

## Phases

**Phase Numbering:**
- Integer phases (1-5): Complete — infrastructure, data generation, Kafka, Spark, ML training
- Integer phases (6-8): Planned — deployment, orchestration, observability

- [x] **Phase 1: Infrastructure** - Docker Compose stack with Kafka, Spark, MLflow, PostgreSQL, MinIO
- [x] **Phase 2: Data Generation** - Realistic transaction generator with 4 fraud patterns (~2% rate)
- [x] **Phase 3: Kafka Streaming** - Schema Registry, partitioned topics, DLQ, retention policies
- [x] **Phase 4: Spark Features** - Structured Streaming with windowed, location, and transaction features
- [x] **Phase 5: ML Training** - LightGBM champion (AUC-PR=0.998), MLflow Registry, SHAP artifacts
- [x] **Phase 6: Model Serving** - MLflow pyfunc REST endpoint with preprocessing bundled; health check (completed 2026-03-21)
- [ ] **Phase 7: Orchestration** - Airflow with retraining DAG, monitoring DAG trigger, canary deploy
- [ ] **Phase 8: Observability** - Prometheus + Grafana dashboards, alerting, drift detection

## Phase Details

### Phase 6: Model Serving
**Goal**: The LightGBM champion model is queryable via a REST endpoint that applies the same preprocessing as training, and the serving container is integrated into Docker Compose
**Depends on**: Phase 5 (MLflow Registry with champion alias)
**Requirements**: SERV-01, SERV-02, SERV-03, SERV-04, SERV-05
**Success Criteria** (what must be TRUE):
  1. `curl http://localhost:5002/health` returns HTTP 200 when the serving container is running
  2. `curl http://localhost:5002/invocations` with a valid JSON transaction payload returns a fraud probability score
  3. The same transaction sent to both `FraudScorer.score()` and the REST endpoint returns scores within 0.001 of each other (no training-serving skew)
  4. The serving container loads the model at `models:/fraud-detection-model@champion`, not an arbitrary latest version
  5. `docker compose up` starts the `fraud-api` service alongside all existing services without errors
**Plans:** 3/3 plans complete
Plans:
- [x] 06-01-PLAN.md — Create FraudPyfunc PythonModel class and register in MLflow with champion alias
- [x] 06-02-PLAN.md — Build Dockerfile.serving and add fraud-api service to Docker Compose
- [x] 06-03-PLAN.md — Test suite (unit + integration) and smoke test with human verification

### Phase 7: Orchestration
**Goal**: Airflow runs in Docker Compose with validated connectivity to all services, executes a weekly retraining DAG with data quality gates and champion comparison, triggers retraining on F1 degradation, and deploys new models via canary with automatic rollback
**Depends on**: Phase 6 (stable mlflow-serve container for DAG-triggered restarts)
**Requirements**: AFLO-01, AFLO-02, AFLO-03, AFLO-04, RETR-01, RETR-02, RETR-03, RETR-04, RETR-05, RETR-06, CNRY-01, CNRY-02, CNRY-03, CNRY-04
**Success Criteria** (what must be TRUE):
  1. The Airflow webserver UI is accessible at `http://localhost:8080` and shows the retraining and monitoring DAGs
  2. The retraining DAG runs on Sunday 02:00 schedule and can be manually triggered; failed runs send an alert via on_failure_callback
  3. Data quality checks block retraining when null rate exceeds 5%, fraud rate is outside tolerance, schema mismatches, fewer than 1000 rows, or fewer than 10 fraud cases
  4. After a successful retraining run, the new model is promoted to champion in MLflow Registry only if its validation F1 exceeds the current champion's F1
  5. A new model is deployed to 10% of traffic for 1 hour before full promotion, and automatically rolls back with an alert if its F1 drops below 95% of champion F1
**Plans**: TBD

### Phase 8: Observability
**Goal**: Prometheus scrapes metrics from all services, Grafana displays a live dashboard with throughput, fraud rate, model latency, and Kafka lag, alerting fires on F1 degradation and high fraud rate, and the monitoring DAG runs daily drift and anomaly checks
**Depends on**: Phase 7 (monitoring DAG wired to live Prometheus metrics; Airflow running)
**Requirements**: MOND-01, MOND-02, MOND-03, MOND-04, MOND-05, MOND-06, OBSV-01, OBSV-02, OBSV-03, OBSV-04, OBSV-05, OBSV-06, OBSV-07
**Success Criteria** (what must be TRUE):
  1. Grafana dashboard at `http://localhost:3000` shows real-time transaction throughput, fraud detection rate, model prediction latency (p50/p95/p99), and Kafka consumer lag — all updating without manual refresh
  2. Grafana alerting fires visibly when fraud rate exceeds the expected band or when model F1 falls below threshold
  3. The daily monitoring DAG run completes in Airflow and logs KS test and PSI scores for top features against training baseline
  4. The monitoring DAG triggers the retraining DAG when daily F1 check falls below the relative threshold (baseline F1 * 0.97)
  5. `docker compose up` starts Prometheus and Grafana alongside all other services; dashboard state is preserved on container restart via provisioned JSON
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure | - | Complete | 2026-03-21 |
| 2. Data Generation | - | Complete | 2026-03-21 |
| 3. Kafka Streaming | - | Complete | 2026-03-21 |
| 4. Spark Features | - | Complete | 2026-03-21 |
| 5. ML Training | - | Complete | 2026-03-21 |
| 6. Model Serving | 3/3 | Complete   | 2026-03-21 |
| 7. Orchestration | 0/TBD | Not started | - |
| 8. Observability | 0/TBD | Not started | - |
