# Phase 8: Observability - Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Prometheus scrapes metrics from all services, Grafana displays a live dashboard with throughput, fraud rate, model latency, and Kafka lag, alerting fires on F1 degradation and high fraud rate, and the monitoring DAG runs daily drift and anomaly checks. Requirements: MOND-01, MOND-02, MOND-03, MOND-04, MOND-05, MOND-06, OBSV-01, OBSV-02, OBSV-03, OBSV-04, OBSV-05, OBSV-06, OBSV-07.

</domain>

<decisions>
## Implementation Decisions

### Metrics exposure strategy
- **D-01:** fraud-api exposes metrics via `prometheus_client` Python library at a `/metrics` endpoint — request count, latency histogram (p50/p95/p99), fraud rate counter, prediction score distribution
- **D-02:** Kafka metrics exposed via JMX Exporter sidecar container alongside the Confluent Kafka broker — consumer lag, throughput, ISR metrics scraped from JMX MBeans
- **D-03:** Spark metrics exposed via JMX Exporter agent on spark-master and spark-worker containers — add JMX exporter JAR and configure via `SPARK_DAEMON_JAVA_OPTS`. Provides executor counts, task timing, memory usage
- **D-04:** Prometheus runs on port 9090 with 15-second scrape interval (industry standard)

### Claude's Discretion
- Dashboard layout and panel organization (single vs multiple Grafana dashboards)
- Which specific panels beyond the required ones (throughput, fraud rate, latency p50/p95/p99, Kafka lag)
- Grafana provisioning directory structure (`configs/grafana/dashboards/`, `configs/grafana/provisioning/`)
- Monitoring DAG implementation: how validation data is generated for daily F1 check, KS test and PSI score thresholds, concept drift sliding window configuration
- How Grafana alerting integrates with existing Phase 7 alerting (JSON files in `alerts/`)
- Alert severity levels and notification channels (log-based vs webhook)
- Grafana port selection (standard 3000 unless conflicting)
- Prometheus configuration file structure (`configs/prometheus/prometheus.yml`)
- JMX Exporter configuration YAML for Kafka and Spark targets
- How the monitoring DAG triggers the retraining DAG (Airflow TriggerDagRunOperator vs REST API)
- Custom Python exporter for application-level metrics vs embedding in fraud-api

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Observability requirements
- `.planning/REQUIREMENTS.md` — OBSV-01 through OBSV-07: Prometheus scraping, Grafana dashboard panels, alerting rules, Docker Compose integration
- `.planning/REQUIREMENTS.md` — MOND-01 through MOND-06: monitoring DAG schedule, drift detection (KS/PSI), concept drift, fraud rate anomaly, F1 alert trigger
- `.planning/ROADMAP.md` §Phase 8 — Success criteria: Grafana at :3000, real-time panels, alerting fires, monitoring DAG logs KS/PSI, DAG triggers retraining, provisioned dashboard JSON

### Existing alerting infrastructure (Phase 7)
- `airflow/dags/utils/alerting.py` — `write_alert()`, `write_canary_alert()`, `on_failure_callback()` — dual-channel alerting pattern (logs + JSON files in alerts/). Phase 8 monitoring DAG should reuse this module
- `airflow/dags/retraining_dag.py` — Retraining DAG that monitoring DAG should trigger on F1 degradation

### Model serving (Phase 6)
- `docker-compose.yml` — All existing services and ports: fraud-api on 5002, MLflow on 5001, Kafka on 9092, Spark on 8080/7077, Airflow on 8081, PostgreSQL on 5432/5433, MinIO on 9000/9001, Zookeeper on 2181, Schema Registry on 8085
- `src/serving/register_pyfunc.py` — FraudPyfunc class; `/invocations` endpoint format for test payloads

### Training baseline
- `src/training/train_model.py` — Training pipeline and metrics logged to MLflow; monitoring DAG compares against these baseline metrics
- `src/training/evaluate.py` — Evaluation metrics computation (F1, precision, recall, AUC-PR)
- `data/artifacts/` — Scaler, label encoders, feature names artifacts for generating validation data

### Prior phase context
- `.planning/phases/06-model-serving/6-CONTEXT.md` — Phase 6 decisions: pyfunc design, health check, champion alias
- `.planning/phases/07-orchestration/7-CONTEXT.md` — Phase 7 decisions: retraining strategy, canary deploy, alerting channels, Docker SDK container restart

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `airflow/dags/utils/alerting.py`: `write_alert()` and `on_failure_callback()` — reuse for monitoring DAG alerting
- `airflow/dags/utils/mlflow_helpers.py`: MLflow helper utilities from Phase 7 — reuse for model loading and metric comparison in monitoring DAG
- `src/training/prepare_data.py`: Data generation pipeline — monitoring DAG can reuse for generating validation datasets
- `src/training/evaluate.py`: Metric computation functions — reuse for monitoring DAG's daily F1 check

### Established Patterns
- YAML anchors in `docker-compose.yml` for shared Airflow configuration (`x-airflow-common`)
- Health checks on all Docker Compose services with `condition: service_healthy`
- Environment variables centralized in `src/config.py` with `.env` loading
- Airflow DAGs mounted from `airflow/dags/` into containers
- Configs directory pattern: `configs/kafka_config.yaml`, `configs/spark_config.yaml` — extend with `configs/prometheus/` and `configs/grafana/`

### Integration Points
- Prometheus needs network access to: fraud-api:5002 (/metrics), Kafka JMX exporter, Spark JMX exporter
- Grafana connects to Prometheus as data source (http://prometheus:9090)
- Monitoring DAG runs in existing Airflow infrastructure (same container, same DAG mount)
- New ports needed: 9090 (Prometheus), 3000 (Grafana) — no conflicts with existing services
- JMX Exporter sidecar needs shared network with Kafka/Spark containers

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<deferred>
## Deferred Ideas

- Slack webhook integration for real-time push alerts — v2 requirement (ADVM-03)
- Evidently HTML drift reports logged to MLflow — v2 requirement (ADVM-02)
- SHAP-based feature importance shift detection — v2 requirement (ADVM-01)
- Load testing dashboard panels — depends on LOAD-01/LOAD-02 (v2)

</deferred>

---

*Phase: 08-observability*
*Context gathered: 2026-03-23*
