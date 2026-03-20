# Feature Research

**Domain:** MLOps deployment, orchestration, and monitoring for real-time fraud detection
**Researched:** 2026-03-21
**Confidence:** HIGH (based on well-established MLOps patterns, project context is fully known)

---

## Context: What Already Exists (Phases 1-5)

The following are complete and must not be re-built:

- Kafka streaming layer with Schema Registry, DLQ, partitioned topics
- Spark Structured Streaming with windowed features, location features, transaction features
- Real-time fraud scoring via LightGBM + pandas_udf
- MLflow Model Registry with champion alias, model signature, SHAP explainability
- Preprocessing artifacts (scaler, label_encoders) persisted to `data/artifacts/`
- `FraudScorer` class loading model + artifacts from MLflow (version-pinned)

The remaining work is in three domains: **model serving** (Phase 6), **orchestration** (Phase 7), and **observability** (Phase 8).

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any reviewer or interviewer expects in a production-grade MLOps pipeline. Missing these = the project looks incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| REST API endpoint for predictions | Every ML deployment demo needs a queryable endpoint. Without it there is no "serving" | MEDIUM | `mlflow models serve` gives this for free at `POST /invocations`; wrap with a thin FastAPI for health check |
| Health check endpoint (`/health`) | Load balancers and orchestration tools need this; interviewer expects to see it | LOW | MLflow serve exposes `/health` by default; must be surfaced in docker-compose |
| Model version pinning in serving | Serving must load a specific registry version, not "latest". Required for reproducibility | LOW | Already done in `FraudScorer` — wire this into the REST layer |
| Preprocessing consistency (training-serving parity) | Without this, model gets garbage input. The single most common failure mode | MEDIUM | Already solved via `data/artifacts/` joblib files — serving must load same artifacts |
| Scheduled retraining DAG | Models degrade. A weekly schedule is the absolute minimum acceptable pattern | HIGH | Airflow cron DAG: `0 2 * * 0` (Sunday 02:00) |
| Performance-triggered retraining | Scheduled retraining alone misses sudden concept drift (e.g., new fraud pattern burst) | MEDIUM | Airflow sensor that checks F1 daily; triggers retrain if F1 < 0.85 |
| Data quality gates before retraining | Training on corrupt data is worse than not retraining. Mandatory pre-training checks | MEDIUM | Null rate < 5%, fraud rate ~2% ± tolerance, schema match, min 1000 rows, class count |
| Model promotion gating (new > old) | New model must beat old model before being promoted. Otherwise retraining can regress | MEDIUM | Compare challenger vs champion on held-out val set before registry promote |
| Model rollback capability | When a bad deploy makes it to production, you need a recovery path | MEDIUM | Keep previous "champion" alias or version tag; re-point alias to revert |
| Transaction throughput metric | Reviewers expect to see "how fast is your system processing?" | LOW | Prometheus counter on Kafka consumer lag + Spark batch duration |
| Fraud rate metric over time | The core business metric — if this spikes or drops, something is wrong | LOW | Prometheus gauge: `fraud_detections / total_transactions` per time window |
| Model prediction latency metric | p50/p95/p99 latency on the scoring endpoint | LOW | Prometheus histogram in the serving wrapper |
| Kafka consumer lag metric | Lag = data falling behind real-time. Fundamental streaming health indicator | LOW | Kafka JMX metrics → Prometheus → Grafana |
| Alerting on F1 degradation | Without alerts, model drift is invisible. Any ops setup requires alert rules | MEDIUM | Airflow monitoring DAG → email/log alert when F1 < 0.85 |
| DAG failure alerting | Airflow DAG failures must surface. Silent failures are unacceptable | LOW | Airflow email_on_failure + on_failure_callback |

### Differentiators (Competitive Advantage)

Features that elevate this beyond a typical portfolio project. These demonstrate production depth without excessive scope.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Hybrid retraining trigger (schedule + threshold) | Most tutorials show only scheduled OR threshold. Hybrid demonstrates understanding of real operational tradeoffs (gradual drift vs sudden shift) | MEDIUM | Two Airflow sensors: time-based cron + performance-based ExternalTaskSensor or daily Python check |
| Canary deploy (10% traffic to new model) | Demonstrates awareness that full cutover is risky; mirrors how Stripe, PayPal deploy ML models | HIGH | For local: custom routing layer or Spark-side model selector by transaction_id hash. For cloud: Vertex AI traffic split |
| Automatic rollback on canary degradation | Closes the loop on canary — shows you know deploys can fail | HIGH | Monitoring DAG checks canary-model metrics after 1h; if F1 < champion * 0.95, revert alias |
| Data drift detection (KS test / PSI) | Feature distribution shift is a distinct problem from model performance. Detecting it separately shows ML maturity | MEDIUM | Airflow monitoring DAG: compute PSI for top-k features vs training baseline; alert on PSI > 0.2 |
| Concept drift detection (sliding window F1 trend) | F1 alone doesn't tell you why performance dropped. Concept drift tracking explains behavioral shift | MEDIUM | Daily F1 on rolling 7-day window; if trend slope is negative, flag for review |
| SHAP-based alert on feature importance shift | When the model starts relying on unexpected features, that signals training-serving skew or real drift | HIGH | Compare SHAP value rankings between training and recent live-scored data. Interesting interview conversation |
| Load test results documented | Shows you measured performance, didn't just assume. Proves the endpoint is production-viable | LOW | `locust` or `wrk` against `mlflow models serve`; document p95 latency and max RPS before degradation |
| Grafana dashboard with Spark streaming metrics | Visualizing Kafka lag + Spark batch duration together tells the full streaming story | MEDIUM | Requires Prometheus JMX exporter for Kafka + Spark metrics → Grafana |
| Interview-ready Findings.md entry per feature | The project's explicit learning goal. Each non-trivial feature should have a Findings.md section explaining the "why" | LOW | Already established pattern in the project |

### Anti-Features (Deliberately Not Building)

Features that seem like good additions but would harm this project's quality or scope.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time feature store (Feast) | Feast is "standard" in enterprise MLOps | Adds Feast infra (Redis, offline/online store sync) that obscures the learning. The project already has windowed features in Spark + Parquet. Feast solves a coordination problem this project doesn't have | Keep Parquet batch features for training; Spark computes online features in the streaming path |
| Delta Lake / Apache Iceberg | ACID writes, time-travel queries are "best practice" | This project uses append-only writes with stable schema. ACID overhead is pure complexity. Delta Lake requires Spark version alignment and adds 2+ hours of debugging for zero functional gain here | Plain Parquet. Document the tradeoff in Findings.md |
| Multi-model ensemble serving | Higher accuracy through ensemble | Doubles inference latency; LightGBM F1=0.982 is already near-perfect on this synthetic dataset. Ensemble adds architectural complexity for no measurable benefit | Single champion model via MLflow alias |
| gRPC serving endpoint | Higher performance than REST | The bottleneck is Spark batch processing, not the serving endpoint latency. gRPC adds proto schema management overhead and complicates local testing | REST via `mlflow models serve` — good enough for portfolio, correct performance tradeoff to explain |
| Custom authentication on serving endpoint | Security best practice | Local dev behind Docker Compose. Adding JWT/OAuth to a portfolio project obstructs the ML story without adding ML content. Mention it as a production concern, don't implement | Document "in production, endpoint sits behind API gateway with auth" in Findings.md |
| Multi-region deployment | Production resilience | Single-region Vertex AI is already a stretch goal. Multi-region is out of scope for a learning project and would take weeks of GCP configuration | Single-region deployment with documentation explaining multi-region extension path |
| Real-time dashboard with sub-second refresh | Impressive looking demo | Requires websocket or SSE streaming from Grafana, complex dashboard configuration. Grafana with 15-second scrape interval is visually sufficient and operationally correct | Grafana with 15s Prometheus scrape interval + 30s dashboard refresh |
| Slack integration for alerts | Polished production feel | Requires Slack API token management, webhook setup, and debugging across Docker networks. Email alerts (Airflow native) convey the same concept | Airflow `email_on_failure` + log-based alerts. Mention Slack as production extension |
| Automated A/B significance testing | Data science rigor | Computing statistical significance of A/B test results requires weeks of traffic accumulation on a live system. This project runs on synthetic data at controlled rates — significance testing is theater | Implement canary rollout and threshold-based rollback; describe significance testing as the production extension |

---

## Feature Dependencies

```
[MLflow REST Endpoint]
    └──requires──> [Model artifact in MLflow Registry] (already done Phase 5)
    └──requires──> [Preprocessing artifacts in data/artifacts/] (already done Phase 5)

[Load Testing]
    └──requires──> [MLflow REST Endpoint]

[Scheduled Retraining DAG]
    └──requires──> [Airflow Docker setup + connections]
    └──requires──> [Data quality gate tasks]
    └──requires──> [Model promotion logic (challenger vs champion)]

[Performance-Triggered Retraining]
    └──requires──> [Monitoring DAG] (F1 check produces the trigger signal)
    └──requires──> [Scheduled Retraining DAG] (reuses same retrain tasks)

[Canary Deploy]
    └──requires──> [MLflow REST Endpoint] (need a serving layer to split traffic)
    └──requires──> [Model promotion logic]

[Automatic Rollback]
    └──requires──> [Canary Deploy]
    └──requires──> [Monitoring DAG] (watches canary performance)

[Monitoring DAG]
    └──requires──> [Airflow Docker setup]
    └──requires──> [Prometheus metrics] (needs a metrics sink to query)

[Grafana Dashboard]
    └──requires──> [Prometheus] (scrape target)
    └──requires──> [Kafka JMX metrics exposed]
    └──requires──> [Spark metrics exposed]

[Alerting Rules]
    └──requires──> [Grafana Dashboard] OR [Monitoring DAG] (two independent alert paths)

[Data Drift Detection]
    └──requires──> [Monitoring DAG]
    └──requires──> [Training baseline statistics persisted] (PSI needs reference distribution)

[Concept Drift Detection]
    └──requires──> [Monitoring DAG]
    └──requires──> [Daily F1 metric logged] (needs historical F1 series)

[SHAP Feature Importance Shift Detection]
    └──requires──> [SHAP artifacts from training] (already done Phase 5)
    └──requires──> [Monitoring DAG]
```

### Dependency Notes

- **Airflow setup is the critical path blocker for Phases 7 and 8**: Both the retraining DAG and the monitoring DAG require Airflow to be running with Docker Compose integration and connections configured. This must come before any DAG development.
- **Monitoring DAG feeds Performance-triggered Retraining**: The F1 daily check in the monitoring DAG is what signals the retraining DAG. They are separate DAGs but the monitoring DAG must exist first.
- **Canary deploy depends on a serving layer existing**: You cannot do traffic splitting until there is a REST endpoint to split. Local serving (Phase 6) is the prerequisite for rollback/canary work (Phase 7).
- **Prometheus/Grafana are independent of Airflow**: The observability stack (Phase 8) can be built without Airflow being complete. Kafka and Spark metrics can be scraped independently.

---

## MVP Definition

This is a portfolio/learning project. "MVP" means: minimum set of features that makes Phases 6-8 complete enough to discuss confidently in interviews.

### Launch With (v1) — Interview-Ready State

- [ ] `mlflow models serve` running locally with `/invocations` and `/health` endpoints — demonstrates model serving
- [ ] Load test results (any tool) showing the endpoint handles expected TPS — demonstrates performance awareness
- [ ] Airflow with Docker Compose, connections to Kafka, Spark, MLflow configured
- [ ] Retraining DAG: weekly schedule + data quality checks + champion vs challenger comparison + model promotion
- [ ] Monitoring DAG: daily F1 check + alert on F1 < 0.85 + fraud rate anomaly detection
- [ ] Grafana dashboard: transaction throughput, fraud rate, model latency, Kafka lag
- [ ] Alerting rules in Grafana or Airflow for F1 degradation and high fraud rate

### Add After Validation (v1.x) — Differentiators Worth Adding

- [ ] Canary deploy (10% traffic split) + automatic rollback — add after basic serving and retraining DAG are verified working
- [ ] Data drift detection (KS/PSI) in monitoring DAG — add after daily F1 check is stable
- [ ] Hybrid retraining trigger (performance-triggered DAG sensor) — add after scheduled retraining is proven
- [ ] Findings.md entries for each Phase 6-8 component — running task, add alongside implementation

### Future Consideration (v2+) — Stretch Goals

- [ ] GCP Vertex AI deployment with auto-scaling — requires GCP project setup, significant cloud configuration
- [ ] A/B testing via Vertex AI traffic splitting — requires Vertex AI endpoint running
- [ ] SHAP-based feature importance shift detection — interesting but high complexity for marginal portfolio value
- [ ] Concept drift detection (sliding window F1 trend) — add if time allows after other monitoring is complete

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| MLflow REST endpoint (local) | HIGH | LOW | P1 |
| Airflow Docker setup + connections | HIGH | MEDIUM | P1 |
| Retraining DAG (scheduled) | HIGH | HIGH | P1 |
| Data quality gates | HIGH | MEDIUM | P1 |
| Model promotion gating | HIGH | MEDIUM | P1 |
| Monitoring DAG (daily F1 + fraud rate) | HIGH | MEDIUM | P1 |
| Grafana dashboard (throughput, fraud rate, latency, lag) | HIGH | MEDIUM | P1 |
| Alerting (F1 degradation, fraud rate anomaly) | HIGH | LOW | P1 |
| Load testing results | MEDIUM | LOW | P2 |
| Canary deploy + automatic rollback | HIGH | HIGH | P2 |
| Data drift detection (KS/PSI) | MEDIUM | MEDIUM | P2 |
| Hybrid retraining trigger (performance-based) | MEDIUM | MEDIUM | P2 |
| Concept drift (sliding window F1) | MEDIUM | HIGH | P3 |
| GCP Vertex AI deployment | MEDIUM | HIGH | P3 |
| A/B testing via Vertex AI | LOW | HIGH | P3 |
| SHAP feature importance shift detection | LOW | HIGH | P3 |

**Priority key:**
- P1: Must have for interview-ready portfolio
- P2: Strong differentiator, add if time allows
- P3: Stretch goal, mention in documentation as production extension

---

## MLOps Industry Pattern Reference

This section documents the industry norm for each layer so the project can be compared against it.

**Model Serving norms:** REST endpoint over HTTP, JSON in/out, health check at `/health`, versioned model loading from registry. MLflow serve does all of this. FastAPI wrappers are common when custom preprocessing logic cannot be bundled into the model signature.

**Retraining norms:** Scheduled weekly or monthly cadence plus performance-triggered on metric thresholds (F1, AUC, PSI). Airflow is the standard orchestrator for batch ML workloads. Data quality gates before training are universal in production systems — they prevent silent model degradation from data pipeline failures.

**Canary/rollback norms:** Deploy new model to small traffic slice (5-20%). Monitor for 1-24 hours. Auto-rollback if degraded. Full rollout if stable. This is the standard pattern used at Stripe, PayPal, and most fintechs for fraud model deploys. Vertex AI traffic splitting is the GCP-native implementation.

**Monitoring norms:** Three distinct signal types — system health (latency, throughput, Kafka lag), model performance (F1, precision, recall on labeled feedback), and drift (feature distribution shift via KS/PSI, prediction distribution shift). Grafana + Prometheus is the dominant local/self-hosted stack. Production teams at scale use Evidently AI or WhyLabs for drift monitoring.

---

## Sources

- Project context: `/Users/fazlikoc/Desktop/realtime_fraud_detection/.planning/PROJECT.md`
- Task plan: `/Users/fazlikoc/Desktop/realtime_fraud_detection/task_plan.md`
- Existing serving implementation: `src/serving/model_scorer.py`
- MLOps pattern knowledge: Training data (HIGH confidence for Airflow DAG patterns, Grafana/Prometheus stack, MLflow serve capabilities, canary deploy patterns)
- Confidence note: All recommendations are grounded in established patterns for Kafka + Spark + MLflow + Airflow stacks as of 2025. The specific tool versions (Airflow 2.x, MLflow 2.12.2, Grafana + Prometheus) are well-documented and stable.

---

*Feature research for: MLOps deployment, orchestration, and monitoring layer*
*Researched: 2026-03-21*

