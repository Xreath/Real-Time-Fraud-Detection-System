# Architecture Research

**Domain:** Real-time fraud detection MLOps pipeline — deployment, orchestration, and monitoring layer
**Researched:** 2026-03-21
**Confidence:** HIGH (based on direct codebase inspection and well-established integration patterns for these tools)

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                        INGESTION LAYER (existing)                     │
│  ┌──────────┐  ┌────────────────────────────────────────────────┐    │
│  │  Faker   │  │  Kafka (transactions / features / fraud-alerts │    │
│  │ producer │→ │  / transactions-dlq)  + Schema Registry        │    │
│  └──────────┘  └────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      PROCESSING LAYER (existing)                      │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  Spark Structured Streaming  (spark-master + spark-worker)   │    │
│  │  Feature Engineering → LightGBM pandas_udf scoring          │    │
│  │  Output: fraud-alerts topic + Parquet feature store          │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                       ML LAYER (existing)                             │
│  ┌──────────────────────────────────────────────────────────────┐    │
│  │  MLflow (tracking server :5001)                              │    │
│  │    └─ backend: PostgreSQL :5432                              │    │
│  │    └─ artifacts: MinIO (S3-compatible) :9000                 │    │
│  │    └─ Model Registry: LightGBM champion alias                │    │
│  └──────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          ▼                         ▼                         ▼
┌─────────────────┐   ┌─────────────────────────┐   ┌────────────────────┐
│  SERVING LAYER  │   │  ORCHESTRATION LAYER    │   │  MONITORING LAYER  │
│  (new)          │   │  (new)                  │   │  (new)             │
│                 │   │                         │   │                    │
│  mlflow serve   │   │  Airflow :8081          │   │  Prometheus :9090  │
│  :5002          │   │    └─ retraining DAG    │   │  Grafana :3000     │
│  REST /invocati │   │    └─ monitoring DAG    │   │                    │
│  ons/predict    │   │  Connections:           │   │  Scraped from:     │
│                 │   │    Kafka, Spark,        │   │  Kafka JMX         │
│  (stretch)      │   │    MLflow HTTP          │   │  Spark metrics     │
│  Vertex AI      │   │                         │   │  MLflow serve      │
│  endpoint       │   │                         │   │  custom fraud rate │
└─────────────────┘   └─────────────────────────┘   └────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|----------------|-------------------|
| MLflow serve | Expose champion model as REST API (`/invocations`); load model from MLflow Registry by alias | MLflow Registry (reads artifact), Airflow (rollback trigger), Prometheus (latency metrics) |
| Airflow | Schedule and trigger retraining + monitoring DAGs; manage dependencies between steps | MLflow HTTP API (promote/demote model), Spark (submit job via SparkSubmitOperator or BashOperator), Kafka (read fraud-alerts for monitoring), PostgreSQL (Airflow metadata DB) |
| Prometheus | Scrape metrics from Kafka JMX exporter, Spark metrics endpoint, MLflow serve, and a custom metrics emitter | Grafana (pushes to), all instrumented services (pulls from) |
| Grafana | Visualize dashboards and fire alerts | Prometheus (data source) |
| Vertex AI (stretch) | Managed model serving with auto-scaling and traffic splitting | MLflow Registry (model pulled via GCS artifact copy), Airflow (deploy via `google-cloud-aiplatform` SDK) |

## Recommended Project Structure

```
src/
├── serving/            # MLflow serve wrapper and load-test script
│   ├── serve.py        # Start mlflow models serve with champion alias
│   └── load_test.py    # Locust or requests-based load test
├── monitoring/         # Custom metrics emitters scraped by Prometheus
│   ├── metrics.py      # prometheus_client gauge/counter for fraud rate, model latency
│   └── drift.py        # KS/PSI computation, writes results to Prometheus or MLflow
├── orchestration/      # Airflow DAG helpers (non-DAG Python logic)
│   ├── retrain.py      # Retraining logic callable from Airflow PythonOperator
│   └── rollback.py     # MLflow Registry alias management, Vertex AI endpoint swap
airflow/
└── dags/
    ├── retraining_dag.py    # Weekly schedule + F1-triggered retraining
    └── monitoring_dag.py    # Daily drift + fraud rate + system health checks
configs/
├── prometheus.yml           # Scrape config for all services
└── grafana/
    └── dashboards/
        └── fraud_detection.json   # Dashboard: throughput, fraud rate, latency, lag
docker-compose.yml           # Add Airflow, Prometheus, Grafana services here
```

### Structure Rationale

- **src/serving/**: Isolated from training code; serve.py is a thin wrapper around `mlflow models serve --model-uri models:/fraud-detection@champion`. No application logic here.
- **src/monitoring/metrics.py**: A long-running process (or sidecar to the Spark consumer) that reads fraud-alerts from Kafka and increments Prometheus counters. Scraped by Prometheus.
- **airflow/dags/**: Airflow DAGs must live in a directory mounted into the Airflow container. Keep DAG logic thin — call functions from `src/orchestration/` via PythonOperator.
- **configs/prometheus.yml**: Single scrape config consumed by the Prometheus container via volume mount. Centralize all target definitions here.

## Architectural Patterns

### Pattern 1: Champion Alias for Zero-Downtime Model Swap

**What:** MLflow Model Registry supports named aliases (e.g., `@champion`). `mlflow models serve` or `mlflow.pyfunc.load_model` can resolve `models:/fraud-detection@champion` at load time. Retraining DAG promotes the new model by moving the alias; the serving process is restarted (or reloads on a health-check cycle).

**When to use:** Anytime model is retrained. Alias swap is the single promotion gate — no code change needed to deploy a new version.

**Trade-offs:** `mlflow serve` does not hot-reload the model when the alias moves. The DAG must restart the serving container after alias promotion. In Vertex AI this is handled automatically via endpoint traffic split.

**Example:**
```python
# Airflow retraining DAG — promote step
import mlflow
client = mlflow.MlflowClient(tracking_uri="http://mlflow:5000")
client.set_registered_model_alias("fraud-detection", "champion", new_version)
# Then restart mlflow-serve container via Docker SDK or docker compose restart
```

### Pattern 2: Kafka-Sourced Monitoring Metrics

**What:** A lightweight Python process (or a foreground thread in the Spark consumer) consumes from the `fraud-alerts` Kafka topic, computes rolling fraud rate and alert latency, and exposes them as a Prometheus `/metrics` endpoint via `prometheus_client`.

**When to use:** For real-time fraud rate and model latency dashboards. The Spark consumer already writes to `fraud-alerts`; this pattern avoids adding any polling logic to Prometheus itself.

**Trade-offs:** Adds a long-running process to Docker Compose. Alternatively, metrics can be pushed to a Prometheus Pushgateway if the job is short-lived. For a streaming consumer, a scrape endpoint is simpler.

**Example:**
```python
from prometheus_client import Counter, Gauge, start_http_server
fraud_alerts_total = Counter("fraud_alerts_total", "Total fraud alerts emitted")
fraud_rate_gauge = Gauge("fraud_rate_1min", "Fraud rate over last 60s")
start_http_server(8000)  # Prometheus scrapes :8000/metrics
```

### Pattern 3: Airflow PythonOperator Wrapping Existing src/ Modules

**What:** Airflow DAGs call `PythonOperator(python_callable=retrain_fn)` where `retrain_fn` is imported from `src/orchestration/retrain.py`. This keeps DAG files thin (scheduling + task graph only) and makes the business logic testable independently.

**When to use:** Always. Never put data-processing logic inline in a DAG file — it makes unit testing impossible and couples Airflow version to business logic.

**Trade-offs:** Requires that Airflow workers have the `src/` package in their Python path. Solved by volume-mounting `src/` into the Airflow container and setting `PYTHONPATH`.

## Data Flow

### Retraining Flow (Airflow DAG)

```
[Airflow Scheduler]
    ↓ (weekly cron OR F1 < 0.85 sensor)
[monitoring_dag: daily F1 check]
    ↓ triggers cross-DAG dependency if threshold breached
[retraining_dag]
    ├─ Task 1: data_quality_check
    │     reads Parquet feature store, checks nulls / fraud rate / schema
    ├─ Task 2: retrain_model
    │     python -m src.training.train_model (PythonOperator)
    │     logs new run to MLflow Tracking Server
    ├─ Task 3: evaluate_and_compare
    │     compares new run F1 vs champion in MLflow Registry
    ├─ Task 4: promote_if_better
    │     moves @champion alias in MLflow Registry
    │     restarts mlflow-serve container
    └─ Task 5: alert (on failure or degradation)
          email/Slack via Airflow connection
```

### Real-Time Scoring Flow (existing, shown for context)

```
Faker Producer
    ↓ (kafka-python)
Kafka "transactions" topic
    ↓ (Spark Structured Streaming reads, 10s micro-batch)
Feature Engineering (windowed + location + amount)
    ↓ (pandas_udf — LightGBM loaded from MLflow via @champion alias)
Fraud Score
    ├─→ Kafka "fraud-alerts" topic  (score >= threshold)
    └─→ Parquet feature store       (all records, for retraining)
```

### Monitoring Metrics Flow

```
Kafka "fraud-alerts" topic
    ↓ (metrics consumer reads continuously)
metrics.py (prometheus_client)
    ↓ exposes :8000/metrics
Prometheus (scrapes every 15s)
    ↓ stores time-series
Grafana (queries Prometheus)
    ↓ renders dashboards + fires alerts
```

### Model Serving Flow (new)

```
External caller (load test / upstream system)
    ↓ HTTP POST /invocations  {"inputs": [[...features...]]}
mlflow serve (port 5002)
    ↓ (loads model from models:/fraud-detection@champion at startup)
LightGBM pyfunc wrapper
    ↓
JSON response {"predictions": [0.94]}
```

## Build Order (Dependencies)

The following order is dictated by hard dependencies between components:

1. **MLflow serve (local)** — No new infrastructure needed. Depends only on existing MLflow Registry having a `@champion` alias (already present from Phase 5). Build first to validate the serving pattern before Airflow depends on it.

2. **Prometheus + Grafana** — Can be added to Docker Compose and brought up independently. The custom metrics emitter (`metrics.py`) can be stubbed with a static Gauge initially. No dependency on Airflow or Vertex AI.

3. **Airflow Docker setup** — Adds a new service to Docker Compose. Must come after MLflow serve is stable because the retraining DAG restarts the serve container. Requires Airflow connections to be configured (MLflow HTTP, Spark, optionally Kafka).

4. **Retraining DAG** — Depends on: Airflow running, Parquet feature store populated (existing), MLflow Registry accessible, serve container restartable.

5. **Monitoring DAG** — Depends on: Airflow running, Prometheus collecting metrics (for drift baseline), MLflow for F1 comparison.

6. **Vertex AI (stretch)** — Depends on: GCP project configured, `google-cloud-aiplatform` installed, model artifact accessible from GCS. Completely decoupled from local infrastructure.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| MLflow Tracking Server | HTTP API via `mlflow.MlflowClient(tracking_uri="http://mlflow:5000")` | Airflow workers must resolve `mlflow` hostname — use Docker Compose `network_mode: host` or shared network |
| Kafka (from Airflow) | `KafkaProducerOperator` or plain `kafka-python` in PythonOperator | Airflow container needs `kafka-python` in its image |
| Spark (from Airflow) | `SparkSubmitOperator` (preferred) or `BashOperator` running `spark-submit` via Docker exec | SparkSubmitOperator requires `apache-airflow-providers-apache-spark` and Spark binary in Airflow container OR submit to standalone cluster via `spark://spark-master:7077` |
| Prometheus (scrapes) | Pull model: Prometheus reads `/metrics` HTTP endpoint from each target | All targets must be on same Docker network as Prometheus container |
| Grafana | Data source: Prometheus at `http://prometheus:9090` | Provision dashboards via JSON in `configs/grafana/dashboards/` and `grafana.ini` |
| Vertex AI (stretch) | `google-cloud-aiplatform` SDK: `aiplatform.Model.upload()` then `endpoint.deploy()` | Model artifact must first be copied from MinIO to GCS; set `GOOGLE_APPLICATION_CREDENTIALS` env var |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Airflow DAG → MLflow Registry | MLflow Python client over HTTP | Use `http://mlflow:5000` not `http://localhost:5001` (container-internal address) |
| Airflow DAG → mlflow-serve container | Docker SDK (`docker.from_env().containers.get("mlflow-serve").restart()`) or `BashOperator("docker compose restart mlflow-serve")` | Airflow container needs Docker socket mounted (`/var/run/docker.sock`) for Docker SDK approach |
| Spark consumer → MLflow (model load) | `mlflow.pyfunc.load_model("models:/fraud-detection@champion")` at pandas_udf initialization | Model loaded once per JVM process, not per batch — verify this in Spark worker logs |
| Prometheus → custom metrics emitter | HTTP scrape of `metrics.py` process on `:8000/metrics` | Run metrics.py as a separate Docker Compose service alongside Spark consumer |
| Grafana → Prometheus | PromQL queries over HTTP to `http://prometheus:9090` | No auth needed for local setup; use `GF_AUTH_ANONYMOUS_ENABLED=true` in dev |

## Anti-Patterns

### Anti-Pattern 1: Mixing Airflow DAG Logic with Business Logic

**What people do:** Write data loading, model training, or MLflow promotion code directly inside the DAG file (in-line `PythonOperator` callables or `@task` functions with full logic).

**Why it's wrong:** The DAG file is imported by the Airflow scheduler on every heartbeat. Heavy imports (PySpark, LightGBM, pandas) slow the scheduler. The logic is also untestable without Airflow running.

**Do this instead:** DAG files define only the task graph and schedule. All callable logic lives in `src/orchestration/` and is imported by the DAG. Unit-test `src/orchestration/` independently.

### Anti-Pattern 2: Loading the MLflow Model on Every Batch

**What people do:** Call `mlflow.pyfunc.load_model(...)` inside the body of a pandas_udf (per-batch or per-partition), re-downloading the model artifact from MinIO on each invocation.

**Why it's wrong:** Model loading involves network I/O and deserialization (typically 1-5 seconds for LightGBM). At 10s micro-batch intervals this creates a constant load penalty and may cause timeout cascades.

**Do this instead:** Load the model once at the module level (outside the UDF function body), or use a broadcast variable pattern where the model is loaded once per Spark executor JVM process. The existing `spark_consumer.py` should load the model at startup — verify the model is not reloaded per-batch.

### Anti-Pattern 3: Using `localhost` Hostnames Across Docker Containers

**What people do:** Configure Airflow connections, Prometheus scrape targets, or MLflow URIs as `localhost:5001`, `localhost:9092`, etc.

**Why it's wrong:** `localhost` inside a container refers to that container's loopback, not the host machine or other containers. Connections will fail silently or with confusing timeout errors.

**Do this instead:** Use Docker Compose service names as hostnames: `mlflow:5000`, `kafka:29092`, `prometheus:9090`. All services on the same Compose network resolve each other by service name. The existing `src/config.py` correctly uses `kafka:29092` for container-internal access — extend this pattern to all new services.

### Anti-Pattern 4: Running Airflow Without a Proper Metadata DB

**What people do:** Use `airflow standalone` (SQLite default) inside Docker for "simplicity."

**Why it's wrong:** SQLite has locking issues under concurrent DAG runs. Existing PostgreSQL container is already running — reusing it for Airflow metadata DB adds zero infrastructure overhead.

**Do this instead:** Point Airflow to `postgresql://airflow:airflow@postgres:5432/airflow` (create a separate database in the existing PostgreSQL container). Set `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` in the Airflow service environment.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Local dev (current) | Single Kafka broker, 1 Spark worker, Docker Compose for all services. MLflow serve is the scoring path for load tests. |
| Small production (1K tx/s) | Kafka replication factor 3, 3 Spark workers, MLflow serve behind nginx with connection pooling. Prometheus retention 15 days. |
| Large production (100K+ tx/s) | Decommission `mlflow serve` (single-threaded Python); serve model via Vertex AI endpoint or Triton Inference Server. Separate Kafka cluster from processing cluster. Airflow on Kubernetes Executor. |

### Scaling Priorities

1. **First bottleneck:** `mlflow serve` is a single-threaded Flask/Gunicorn process. Under load test it will saturate at ~50-100 req/s. For this portfolio project, document the limit rather than solving it — it demonstrates awareness. Vertex AI is the production answer.

2. **Second bottleneck:** Airflow default LocalExecutor runs tasks sequentially per DAG. For parallel retraining experiments, switch to CeleryExecutor. Not needed at this scale.

## Sources

- Existing codebase: `docker-compose.yml`, `src/config.py`, `src/streaming/spark_consumer.py`, `src/training/train_model.py`
- Project context: `.planning/PROJECT.md`, `findings.md`, `tech_stack.md`
- Established patterns: MLflow Model Registry alias API (MLflow 2.x docs), Airflow PythonOperator best practices, Prometheus `prometheus_client` Python library scrape model, Docker Compose inter-service networking
- Confidence note: All integration patterns above are based on stable, well-documented behaviors of these tools. The MLflow serve single-thread limitation is a known characteristic of the default Flask-based server in MLflow 2.x.

---
*Architecture research for: Real-time fraud detection MLOps pipeline — deployment, orchestration, and monitoring*
*Researched: 2026-03-21*

