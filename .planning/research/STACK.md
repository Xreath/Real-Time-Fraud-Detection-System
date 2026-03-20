# Stack Research

**Domain:** MLOps Deployment, Orchestration, and Monitoring for Real-Time Fraud Detection
**Researched:** 2026-03-21
**Confidence:** MEDIUM (WebSearch/WebFetch unavailable; versions cross-checked against venv dist-info, requirements.txt, Dockerfile.mlflow, and training knowledge through August 2025)

---

## Context: What Already Exists

This is a milestone-scoped research document. The existing stack (Kafka, Spark 3.5.4, LightGBM, MLflow 2.12.2, PostgreSQL 16, MinIO, Docker Compose) is locked in and not re-evaluated here. All recommendations below are additive — they extend the existing system.

Constraints that constrain new component choices:
- MLflow server pinned to **v2.12.2** in Dockerfile.mlflow; new client code must stay `>=2.12.0,<3.0.0`
- Python 3.12 (confirmed by venv path)
- Java 11 required by Spark 3.5.x — Airflow workers must not assume Java 17+
- Everything must run locally via Docker Compose before any GCP deployment

---

## Recommended Stack (New Components Only)

### Model Serving

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `mlflow models serve` | 2.12.2 (existing server) | Local REST prediction endpoint | Zero new infrastructure — ships with MLflow. The `mlflow models serve` CLI wraps the registered model in a Flask/Gunicorn server at `/invocations`. Talks directly to MinIO artifact store already running. Avoids adding BentoML/Seldon/TorchServe complexity for a portfolio project. |
| `gunicorn` | >=22.0.0 | MLflow serve production-mode worker | MLflow uses Gunicorn under the hood when `--workers` is passed. Pin separately in Dockerfile for explicit control. Required for non-development serving. |

**What NOT to use for local serving:**
- BentoML, Seldon, KServe — production Kubernetes-native, total overkill for Docker Compose; adds 2–3 new infrastructure layers
- FastAPI custom server — builds a fine wrapper, but re-implements what `mlflow models serve` already does; doubles maintenance surface

### Load Testing

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `locust` | >=2.29.0 | HTTP load testing for prediction endpoint | Pure Python, scriptable, ships with a real-time web UI, designed for REST endpoint load tests. No Java, no separate JVM process (unlike JMeter/Gatling). Simple `@task` decorator pattern fits well with the existing Python codebase. |

**What NOT to use:**
- Apache JMeter — XML config, Java-based, no fit with Python-first project
- `ab` (Apache Bench) — no ramp-up control, single-threaded, no custom headers for MLflow's JSON payload

### GCP Vertex AI Deployment (Stretch Goal)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `google-cloud-aiplatform` | >=1.58.0 | Vertex AI SDK — upload model, create endpoint, deploy, traffic splitting | Official Google SDK. Required for all Vertex AI operations. Handles model registration, endpoint creation, and A/B traffic splitting. Already commented out in requirements.txt. |
| `google-cloud-storage` | >=2.16.0 | GCS bucket access for model artifacts | Vertex AI pulls from GCS. Required companion to aiplatform SDK for artifact staging. |
| `google-auth` | >=2.28.0 | ADC (Application Default Credentials) for local-to-GCP auth | Already installed (2.48.0 visible in venv). Use ADC + service account JSON; never hardcode credentials. |

**Confidence:** LOW for exact Vertex AI SDK version — GCP SDK versions increment rapidly. Use `>=1.58.0` as a floor; let pip resolve latest compatible.

**What NOT to use:**
- gcloud CLI scripts alone — insufficient for programmatic A/B traffic splitting; SDK required
- `google-cloud-ml-engine` — deprecated; superseded entirely by Vertex AI

### Airflow Orchestration

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Apache Airflow | 2.9.x (target: 2.9.3) | Retraining DAG + monitoring DAG orchestration | Airflow 2.9.x is the current stable 2.x line as of mid-2025. The project explicitly requires Airflow (learning goal). Airflow 2.x DAG-as-code with `@dag`/`@task` decorators (TaskFlow API) is far cleaner than 1.x operators for Python-heavy ML pipelines. |
| `apache-airflow-providers-apache-spark` | >=4.7.0 | `SparkSubmitOperator` / `SparkJDBCOperator` | Required to submit Spark jobs from DAGs without SSH hacks. Connects to spark-master:7077 directly. |
| `apache-airflow-providers-http` | >=4.10.0 | HTTP calls to MLflow REST API from DAGs | MLflow's Python client is simpler for most ops, but `SimpleHttpOperator` is useful for health-checks and triggering mlflow serve endpoints during DAG runs. |
| `apache-airflow-providers-postgres` | >=5.10.0 | PostgreSQL connections for data quality checks | DAGs need to query the same PostgreSQL that MLflow uses for metadata; provider gives `PostgresHook`. |

**Airflow Docker image recommendation:** `apache/airflow:2.9.3-python3.11`

Why 3.11 not 3.12: Airflow 2.9.x official images ship Python 3.11 as the primary tested version. Python 3.12 images exist but some provider packages had compatibility lags through 2025. Accept the 3.11/3.12 split (Airflow workers on 3.11, training pipeline on 3.12) — standard practice.

**What NOT to use:**
- Airflow 3.x — as of August 2025 it was in RC/early release with breaking API changes; 2.9.x is the stable production choice for 2025
- Prefect / Dagster — valid alternatives for greenfield projects, but project constraints require Airflow specifically
- `LocalExecutor` for production-like demo — use `CeleryExecutor` or `LocalExecutor` is fine for Docker Compose single-node, but document the limitation; `CeleryExecutor` adds Redis dependency that isn't needed here

**Airflow Executor recommendation:** `LocalExecutor` — sufficient for Docker Compose, no need for Celery/Redis. Document as known simplification.

### Monitoring: Metrics Collection

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Prometheus | 2.52.x (Docker: `prom/prometheus:v2.52.0`) | Time-series metrics scraping and storage | Pull-based model fits perfectly: each service exposes `/metrics`, Prometheus scrapes on interval. No code changes needed for infrastructure metrics (Kafka, Spark, JVM). |
| `prometheus-client` | >=0.20.0 | Python instrumentation for custom metrics | The official Python library. Exposes a `/metrics` HTTP endpoint from Python processes. Used to emit: fraud rate, model latency, prediction confidence histogram, Spark job durations. |
| Kafka JMX Exporter | 1.0.x (Docker: `bitnami/jmx-exporter:1.0.1`) | Kafka broker metrics → Prometheus | JMX Exporter is the standard path for Kafka metrics in Docker Compose. Confluent 7.6.0 exposes JMX on port 9999; the exporter converts JMX MBeans to Prometheus format. Required for Kafka consumer lag, topic throughput metrics. |

**What NOT to use:**
- Telegraf — valid but adds InfluxDB dependency; Prometheus is sufficient and more standard in ML observability stacks
- Datadog agent — SaaS cost, unnecessary for local portfolio project

### Monitoring: Visualization

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Grafana | 11.x (Docker: `grafana/grafana:11.0.0`) | Dashboard and alerting | Grafana 11 (released April 2024) is stable and includes built-in alerting that replaces Grafana Alertmanager. Native Prometheus datasource. Pre-built community dashboards available for Kafka (dashboard ID 7589) and JVM. |
| Alertmanager | 0.27.x (Docker: `prom/alertmanager:v0.27.0`) | Alert routing (Prometheus → notification) | Handles deduplication, grouping, silencing of Prometheus alerts. Required if alerts need to route to multiple channels. For a portfolio project, Grafana's built-in alerting may be sufficient — Alertmanager is optional. |

**What NOT to use:**
- Grafana 10.x — 11.x is current stable, no reason to regress
- Kibana — Elasticsearch-native, wrong stack for Prometheus metrics

### Drift Detection

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| `scipy` | >=1.13.0 | KS test (Kolmogorov-Smirnov) for feature drift | Already in venv (1.17.1 visible in dist-info). KS test is the standard statistical drift test: compare feature distributions between reference (training) window and current window. No new dependency needed. |
| `evidently` | >=0.4.30 | Data drift report generation | Evidently is the 2025 standard for ML monitoring reports in Python. Provides ready-made drift reports (PSI, KS, chi-squared), concept drift detection, and data quality checks. Generates HTML reports that can be logged to MLflow as artifacts. Much lighter than the full Great Expectations stack for this use case. |

**What NOT to use:**
- Great Expectations — powerful but heavyweight; more suited to data engineering pipelines than ML monitoring DAGs; significant config overhead for what is essentially a drift check
- `river` (online ML) — not relevant here; batch retraining model, not online learning

---

## Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `requests` | >=2.31.0 (already in requirements.txt) | HTTP calls to MLflow `/invocations` from DAGs or load tests | Already available; no change |
| `psutil` | >=5.9.0 | CPU/memory metrics from Python processes | Use in model serving container to expose resource metrics to Prometheus |
| `tenacity` | >=8.3.0 | Retry logic for GCP API calls in Vertex AI deployment code | GCP API calls during endpoint creation can be flaky; exponential backoff is essential |
| `schedule` | >=1.2.0 | Lightweight scheduler for standalone monitoring scripts (not needed if Airflow used) | Skip if Airflow is the orchestrator; only relevant for simplified monitoring without Airflow |

---

## Docker Compose Service Additions

The following new services should be added to `docker-compose.yml`:

```yaml
# Airflow
airflow-webserver:   apache/airflow:2.9.3-python3.11
airflow-scheduler:   apache/airflow:2.9.3-python3.11
airflow-init:        apache/airflow:2.9.3-python3.11  # one-shot DB init
redis:               redis:7-alpine                    # only if CeleryExecutor chosen

# Monitoring
prometheus:          prom/prometheus:v2.52.0
grafana:             grafana/grafana:11.0.0
alertmanager:        prom/alertmanager:v0.27.0         # optional

# MLflow serving
mlflow-serve:        custom Dockerfile extending ghcr.io/mlflow/mlflow:v2.12.2
```

Airflow requires its own PostgreSQL database. Options:
1. Add a second PostgreSQL service (`airflow-postgres`) — cleanest isolation
2. Add a second database in the existing `postgres` container — simpler but mixes concerns

**Recommendation:** Option 1 (separate `airflow-postgres` service). Easier to debug, mirrors real-world separation.

---

## Installation

```bash
# Airflow (pinned constraints file is mandatory to avoid dependency resolver hell)
pip install apache-airflow==2.9.3 \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-2.9.3/constraints-3.11.txt"

# Airflow providers
pip install apache-airflow-providers-apache-spark>=4.7.0 \
            apache-airflow-providers-http>=4.10.0 \
            apache-airflow-providers-postgres>=5.10.0

# GCP (stretch goal — currently commented out in requirements.txt)
pip install google-cloud-aiplatform>=1.58.0 \
            google-cloud-storage>=2.16.0

# Load testing
pip install locust>=2.29.0

# Drift detection
pip install evidently>=0.4.30

# Metrics
pip install prometheus-client>=0.20.0

# Utilities
pip install psutil>=5.9.0 tenacity>=8.3.0
```

**CRITICAL:** Never `pip install apache-airflow` without the constraints file. Airflow's dependency surface is enormous and will conflict with existing packages (especially SQLAlchemy, which MLflow also depends on). The constraints file from Apache is the official solution.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `mlflow models serve` | FastAPI custom wrapper | When the model needs non-standard preprocessing at inference time that can't be packaged in a pyfunc flavor. Not this project — preprocessing artifacts are already in the model artifact directory. |
| `locust` | `k6` | When load testing non-HTTP protocols or when running in CI/CD with JavaScript tooling. `k6` is faster and more Go-friendly but adds non-Python tooling. |
| Apache Airflow 2.9.x | Prefect 2.x | Greenfield projects without Airflow as a learning goal. Prefect has a much simpler local setup but Airflow is the stated requirement. |
| Evidently | Alibi-detect | When needing multivariate drift (MMD, LSDD) or adversarial detection on tabular data. Evidently is simpler for univariate KS/PSI drift and HTML report generation. |
| Grafana 11 | Kibana | When the stack is already Elasticsearch-based. This project is Prometheus-native; Kibana adds Elasticsearch as a new dependency for no gain. |
| JMX Exporter | Confluent Platform metrics | When using Confluent Control Center (licensed). For the existing Confluent 7.6.0 OSS setup, JMX Exporter is the standard path. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| MLflow 3.x client | Docker MLflow server is pinned to 2.12.2; 3.x client has breaking API changes that will cause `MlflowException` against a 2.x server | Stay `>=2.12.0,<3.0.0` as in requirements.txt |
| `CeleryExecutor` for Airflow | Adds Redis as a new required service; `LocalExecutor` is sufficient for Docker Compose single-node; Celery only needed when scaling to multiple Airflow worker nodes | `LocalExecutor` with a single scheduler |
| Airflow 3.x | RC/early release as of 2025; breaking TaskFlow API changes; ecosystem of providers not yet stable | Apache Airflow 2.9.3 |
| `apache-airflow` without constraints file | Unconstrained install causes SQLAlchemy version conflicts between Airflow, MLflow, and PySpark | Always use `--constraint constraints-{version}.txt` from Apache's GitHub |
| Seldon / KServe | Kubernetes-native model serving; requires a full K8s cluster; incompatible with Docker Compose local-first constraint | `mlflow models serve` locally; Vertex AI for cloud deployment |
| InfluxDB + Telegraf | Different time-series stack; incompatible with Prometheus exporters already available for Kafka/Spark/JVM | Prometheus + Grafana |
| Great Expectations | Heavy framework designed for data pipelines, not ML monitoring; requires a "Data Context" setup and YAML config files for what amounts to 5 lines of `scipy` + Pandas | `scipy` for KS tests, `evidently` for full drift reports |

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| `mlflow>=2.12.0,<3.0.0` | MLflow server 2.12.2 (in Docker) | Client and server major version must match. The `<3.0.0` ceiling is critical. |
| `apache-airflow==2.9.3` | `SQLAlchemy>=1.4,<2.0` | Airflow 2.9.x uses SQLAlchemy 1.4 internally. MLflow 2.12.x also uses SQLAlchemy 1.4. They should coexist — but ONLY with the Airflow constraints file applied. Without it, pip may resolve SQLAlchemy 2.x and break both. |
| `pyspark>=3.5.0,<4.0.0` | Java 11 | Spark 3.5.x requires Java 11 (not 17, not 21). Airflow workers submitting Spark jobs must have `JAVA_HOME` set to a Java 11 installation. |
| `google-cloud-aiplatform>=1.58.0` | `google-auth>=2.28.0` | aiplatform SDK requires google-auth for ADC. google-auth 2.48.0 already in venv — compatible. |
| `prometheus-client>=0.20.0` | Prometheus 2.52.x | Prometheus scrape format is stable across versions; no compatibility issues expected. |
| `grafana/grafana:11.0.0` | Prometheus 2.52.x | Grafana 11's Prometheus datasource fully compatible with Prometheus 2.x. |
| `evidently>=0.4.30` | `pandas>=2.0.0`, `numpy>=1.26.0` | Evidently 0.4.x requires pandas 2.x. Both already in requirements.txt. |
| `apache/airflow:2.9.3-python3.11` | Docker network with `mlflow:5000` | Airflow containers must be on the same Docker network as the existing services. Use `external: true` network reference or put everything in one compose file. |

---

## Stack Patterns by Variant

**For local serving only (minimum viable Phase 6):**
- Use `mlflow models serve` — no new infrastructure
- Load test with `locust`
- Skip Vertex AI entirely (stretch goal)

**For full Phase 6 including GCP:**
- Local serve first, validate with locust
- Package model artifacts to GCS with `google-cloud-storage`
- Deploy to Vertex AI endpoint with `google-cloud-aiplatform` SDK
- Vertex AI handles auto-scaling and A/B traffic splitting natively

**For Airflow (Phase 7):**
- Add `airflow-postgres` + `airflow-webserver` + `airflow-scheduler` to docker-compose
- Use `LocalExecutor` (no Redis/Celery)
- DAGs trigger Python callables that use existing `mlflow` client and `SparkSubmitOperator` for Spark jobs
- Airflow must access MLflow at `http://mlflow:5000` (internal Docker network) not `localhost:5001`

**For monitoring (Phase 8):**
- Add Prometheus + Grafana to docker-compose
- Instrument `mlflow models serve` container with `prometheus-client`
- Add JMX Exporter sidecar to Kafka container for consumer lag metrics
- Use Grafana community dashboards for Kafka (ID: 7589) and JVM as starting point, add custom fraud-rate panels

---

## Sources

- `Dockerfile.mlflow` in this repo — MLflow server version 2.12.2 confirmed (HIGH confidence)
- `requirements.txt` in this repo — existing dependency floor versions (HIGH confidence)
- `docker-compose.yml` in this repo — service image versions for Confluent 7.6.0, Spark 3.5.4, Postgres 16 (HIGH confidence)
- `.venv/lib/python3.12/site-packages/` dist-info visible in directory listing — scipy 1.17.1, google-auth 2.48.0, pandas 2.3.3, fastapi 0.135.1, uvicorn 0.41.0 installed (HIGH confidence)
- Training knowledge (cutoff August 2025) — Airflow 2.9.x as stable line, Grafana 11.0, Prometheus 2.52, Evidently 0.4.x patterns (MEDIUM confidence — versions may have incremented; use as floors not ceilings)
- Apache Airflow constraints-file requirement — well-documented community knowledge, multiple sources (MEDIUM confidence)
- Airflow Python 3.11 vs 3.12 compatibility — MEDIUM confidence; official Airflow images were slower to adopt 3.12 as of mid-2025
- GCP Vertex AI SDK version ceiling — LOW confidence; increment rapidly, use `>=1.58.0` as floor only

---
*Stack research for: MLOps Deployment, Orchestration, and Monitoring (Fraud Detection Pipeline)*
*Researched: 2026-03-21*

