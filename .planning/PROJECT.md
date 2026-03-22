# Real-Time Fraud Detection System

## What This Is

An end-to-end real-time credit card fraud detection system using Kafka, Spark Structured Streaming, MLflow, Airflow, and GCP Vertex AI. A learning/portfolio project demonstrating production-grade MLOps practices — from data generation through model training, deployment, orchestration, and monitoring.

## Core Value

Demonstrate a complete, production-realistic MLOps pipeline that can be discussed in depth during interviews — every component works end-to-end, not just in isolation.

## Requirements

### Validated

- ✓ Docker Compose infrastructure with Kafka, Zookeeper, Spark, MLflow, PostgreSQL, MinIO — existing
- ✓ Realistic transaction data generation with 4 fraud patterns (~2% fraud rate) — existing
- ✓ Kafka streaming layer with Schema Registry, partitioned topics, retention policies — existing
- ✓ Spark Structured Streaming with windowed features, location features, and transaction features — existing
- ✓ Real-time fraud scoring with LightGBM via pandas_udf in Spark — existing
- ✓ DLQ for unparseable messages and fallback scoring (score=-1) for model errors — existing
- ✓ ML model training pipeline: 4 models compared, Optuna tuning, MLflow tracking — existing
- ✓ MLflow Model Registry with versioning, champion alias, model signature — existing
- ✓ SHAP explainability and confusion matrix artifacts logged to MLflow — existing
- ✓ Feature preprocessing artifacts (scaler, label encoders) persisted and reused — existing

### Active

- ✓ Local model serving via MLflow serve with REST API — Validated in Phase 06: model-serving
- [ ] Load testing of local prediction endpoint
- [ ] GCP Vertex AI deployment with auto-scaling (stretch goal)
- [ ] A/B testing via Vertex AI traffic splitting (stretch goal)
- [ ] Airflow Docker setup with connections to Kafka, Spark, MLflow
- [ ] Retraining DAG: scheduled (weekly) + triggered (F1 < 0.85)
- [ ] Data quality checks before retraining (nulls, fraud rate, schema, outliers, minimums)
- [ ] Model rollback mechanism: canary deploy (10% traffic), auto-rollback if degraded
- [ ] Monitoring DAG: daily F1 check, data drift (KS/PSI), concept drift, fraud rate anomaly
- [ ] Grafana + Prometheus observability stack
- [ ] Dashboard: transaction throughput, fraud rate, model latency, Kafka lag, Spark timing
- [ ] Alerting: high fraud rate, system health, model performance degradation

### Out of Scope

- Real payment processor integration — synthetic data only, learning project
- Multi-region deployment — single region sufficient for portfolio
- Real-time feature store (Feast) — Parquet-based offline store sufficient for this scope
- Delta Lake — plain Parquet is adequate for append-only writes with stable schema
- KRaft migration — Zookeeper works, KRaft awareness demonstrated in documentation

## Context

- **Project type**: Learning/portfolio project for job interviews
- **Language**: Turkish comments and documentation alongside English code
- **Phases 1-6 complete**: Infrastructure, data generation, Kafka streaming, Spark features, ML training, model serving
- **Phases 7-8 remaining**: Airflow orchestration, monitoring
- **Tech decisions documented**: Findings.md captures every tradeoff with interview-ready explanations
- **Known issues resolved**: PySpark version compatibility, MLflow client/server version mismatch, Docker networking, Zookeeper healthchecks
- **Model performance**: LightGBM best performer (Val AUC-PR=0.998, Test F1=0.982)

## Constraints

- **Tech stack**: Python, Kafka, Spark, MLflow, Airflow, Docker — must use these specific technologies (learning goals)
- **Local-first**: Everything must work locally via Docker Compose before any cloud deployment
- **Cloud**: GCP Vertex AI is a stretch goal — local deployment is the minimum
- **Java**: Java 11 required by Spark 3.5.x — cannot upgrade without Spark version change
- **MLflow**: Server runs v2.12.2 in Docker — client version must be compatible

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Zookeeper over KRaft | Confluent 7.6.0 ecosystem stability | ✓ Good — working, KRaft awareness noted |
| Plain Parquet over Delta Lake | ACID/time-travel not needed for append-only batch training | ✓ Good — simpler, sufficient |
| Parquet feature store over Feast | Feast adds infra complexity beyond learning scope | ✓ Good — batch training works fine |
| LightGBM as champion model | Best AUC-PR (0.998), good balance of speed and accuracy | ✓ Good — production-deployed |
| MLflow 2.x over 3.x | Docker server compatibility (2.12.2) | ✓ Good — stable |
| Hybrid retraining (scheduled + triggered) | Weekly catches gradual drift, F1 threshold catches sudden shifts | — Pending |
| Grafana + Prometheus for monitoring | Full observability stack, industry standard | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-22 after Phase 06 completion*
