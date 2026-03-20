# Requirements: Real-Time Fraud Detection System

**Defined:** 2026-03-21
**Core Value:** Demonstrate a complete, production-realistic MLOps pipeline that can be discussed in depth during interviews

## v1 Requirements

### Model Serving

- [ ] **SERV-01**: Model is served via MLflow REST endpoint at `/invocations` accepting JSON transaction payloads
- [ ] **SERV-02**: Health check endpoint at `/health` returns 200 when model is loaded and ready
- [ ] **SERV-03**: Serving uses same preprocessing artifacts (scaler, label encoders) as training — no training-serving skew
- [ ] **SERV-04**: Serving loads a specific model version from MLflow Registry (champion alias), not "latest"
- [ ] **SERV-05**: MLflow serve runs as a Docker Compose service with configurable workers

### Airflow Setup

- [ ] **AFLO-01**: Airflow webserver and scheduler run in Docker Compose with LocalExecutor
- [ ] **AFLO-02**: Airflow has configured connections to Kafka, Spark, MLflow, and PostgreSQL
- [ ] **AFLO-03**: Airflow uses a separate PostgreSQL database for metadata (not shared with MLflow)
- [ ] **AFLO-04**: DAG files are mounted from `airflow/dags/` directory into the Airflow container

### Retraining Pipeline

- [ ] **RETR-01**: Retraining DAG runs on weekly schedule (Sunday 02:00)
- [ ] **RETR-02**: Retraining is triggered immediately when daily F1 check finds F1 < 0.85
- [ ] **RETR-03**: Data quality checks run before training: null rate < 5%, fraud rate ~2% ± tolerance, schema match, min 1000 rows, min 10 fraud cases
- [ ] **RETR-04**: New model is compared against champion on held-out validation set before promotion
- [ ] **RETR-05**: Model is promoted to champion alias in MLflow Registry only if it outperforms current champion
- [ ] **RETR-06**: DAG failure triggers email/log alert via Airflow on_failure_callback

### Canary Deploy & Rollback

- [ ] **CNRY-01**: New model is deployed to 10% of traffic for 1 hour before full promotion
- [ ] **CNRY-02**: If canary model F1 < champion F1 * 0.95, automatic rollback to previous champion
- [ ] **CNRY-03**: Previous champion model version is preserved and can be restored via MLflow alias
- [ ] **CNRY-04**: Rollback triggers an alert (log/email)

### Monitoring DAG

- [ ] **MOND-01**: Monitoring DAG runs daily to check model F1 on validation set
- [ ] **MOND-02**: Data drift detection via KS test and PSI on top features against training baseline
- [ ] **MOND-03**: Concept drift detection via sliding window F1 trend (7-day window)
- [ ] **MOND-04**: Fraud rate anomaly detection (daily fraud rate vs expected ~2%)
- [ ] **MOND-05**: Alert triggered when F1 < 0.85 — signals retraining DAG
- [ ] **MOND-06**: Alert triggered when data drift PSI > 0.2

### Observability Stack

- [ ] **OBSV-01**: Prometheus scrapes metrics from model serving, Kafka (JMX), and custom Python exporters
- [ ] **OBSV-02**: Grafana dashboard shows real-time transaction throughput
- [ ] **OBSV-03**: Grafana dashboard shows fraud detection rate over time
- [ ] **OBSV-04**: Grafana dashboard shows model prediction latency (p50/p95/p99)
- [ ] **OBSV-05**: Grafana dashboard shows Kafka consumer lag
- [ ] **OBSV-06**: Grafana alerting rules for high fraud rate and model performance degradation
- [ ] **OBSV-07**: Prometheus and Grafana run as Docker Compose services

## v2 Requirements

### Cloud Deployment

- **CLOD-01**: Model uploaded to GCP Vertex AI Model Registry
- **CLOD-02**: Model deployed to Vertex AI Endpoint with auto-scaling
- **CLOD-03**: A/B testing via Vertex AI traffic splitting
- **CLOD-04**: Cloud Monitoring integration

### Advanced Monitoring

- **ADVM-01**: SHAP-based feature importance shift detection
- **ADVM-02**: Evidently HTML drift reports logged to MLflow as artifacts
- **ADVM-03**: Slack integration for alerts (replacing email/log)

### Load Testing

- **LOAD-01**: Locust load test against serving endpoint with documented results
- **LOAD-02**: p95 latency and max RPS benchmarks documented

## Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time feature store (Feast) | Adds infra complexity beyond learning scope; Parquet batch + Spark online sufficient |
| Delta Lake / Apache Iceberg | Append-only writes with stable schema; ACID overhead is pure complexity here |
| Multi-model ensemble serving | LightGBM F1=0.982 already near-perfect on synthetic data; doubles inference latency |
| gRPC serving endpoint | Bottleneck is Spark batch processing, not endpoint latency; REST is sufficient |
| Custom auth on serving endpoint | Local Docker Compose project; mention as production concern in docs |
| Multi-region deployment | Single-region sufficient for portfolio project |
| Real-time sub-second dashboard | Grafana 15s scrape interval is operationally correct and visually sufficient |
| Automated A/B significance testing | Synthetic data at controlled rates makes significance testing meaningless |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| SERV-01 | Phase 6 | Pending |
| SERV-02 | Phase 6 | Pending |
| SERV-03 | Phase 6 | Pending |
| SERV-04 | Phase 6 | Pending |
| SERV-05 | Phase 6 | Pending |
| AFLO-01 | Phase 7 | Pending |
| AFLO-02 | Phase 7 | Pending |
| AFLO-03 | Phase 7 | Pending |
| AFLO-04 | Phase 7 | Pending |
| RETR-01 | Phase 7 | Pending |
| RETR-02 | Phase 7 | Pending |
| RETR-03 | Phase 7 | Pending |
| RETR-04 | Phase 7 | Pending |
| RETR-05 | Phase 7 | Pending |
| RETR-06 | Phase 7 | Pending |
| CNRY-01 | Phase 7 | Pending |
| CNRY-02 | Phase 7 | Pending |
| CNRY-03 | Phase 7 | Pending |
| CNRY-04 | Phase 7 | Pending |
| MOND-01 | Phase 8 | Pending |
| MOND-02 | Phase 8 | Pending |
| MOND-03 | Phase 8 | Pending |
| MOND-04 | Phase 8 | Pending |
| MOND-05 | Phase 8 | Pending |
| MOND-06 | Phase 8 | Pending |
| OBSV-01 | Phase 8 | Pending |
| OBSV-02 | Phase 8 | Pending |
| OBSV-03 | Phase 8 | Pending |
| OBSV-04 | Phase 8 | Pending |
| OBSV-05 | Phase 8 | Pending |
| OBSV-06 | Phase 8 | Pending |
| OBSV-07 | Phase 8 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-21 — traceability updated to Phase 6/7/8 numbering after roadmap creation*
