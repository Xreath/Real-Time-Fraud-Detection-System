# Phase 8: Observability - Research

**Researched:** 2026-03-23
**Domain:** Prometheus + Grafana monitoring stack, Python metrics instrumentation, JMX Exporter for Kafka/Spark, Airflow monitoring DAG with drift detection
**Confidence:** HIGH (core stack), MEDIUM (JMX Exporter YAML patterns), HIGH (Grafana provisioning)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
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

### Deferred Ideas (OUT OF SCOPE)
- Slack webhook integration for real-time push alerts — v2 requirement (ADVM-03)
- Evidently HTML drift reports logged to MLflow — v2 requirement (ADVM-02)
- SHAP-based feature importance shift detection — v2 requirement (ADVM-01)
- Load testing dashboard panels — depends on LOAD-01/LOAD-02 (v2)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MOND-01 | Monitoring DAG runs daily to check model F1 on validation set | Airflow DAG with PythonOperator; reuse `prepare_data.py` + `evaluate.py`; MLflow API for baseline comparison |
| MOND-02 | Data drift detection via KS test and PSI on top features against training baseline | `scipy.stats.ks_2samp` for KS test; custom PSI computation using numpy histograms; baseline stored as parquet in `data/splits/` |
| MOND-03 | Concept drift detection via sliding window F1 trend (7-day window) | MLflow `search_runs` API to retrieve last 7 daily runs; compute trend slope or min F1 in window |
| MOND-04 | Fraud rate anomaly detection (daily fraud rate vs expected ~2%) | Generate validation batch; count `fraud_prediction==1` / total; compare to 2% ± tolerance |
| MOND-05 | Alert triggered when F1 < 0.85 — signals retraining DAG | `TriggerDagRunOperator(trigger_dag_id="retraining_dag")`; reuse `write_alert()` from alerting.py |
| MOND-06 | Alert triggered when data drift PSI > 0.2 | Compute PSI per feature; `write_alert()` when any feature PSI > 0.2 |
| OBSV-01 | Prometheus scrapes metrics from model serving, Kafka (JMX), and custom Python exporters | Separate `fraud-metrics` sidecar with `prometheus_client`; Kafka JMX sidecar on port 7071; Spark JMX via `SPARK_DAEMON_JAVA_OPTS` |
| OBSV-02 | Grafana dashboard shows real-time transaction throughput | Prometheus query on `fraud_requests_total` counter rate; provisioned JSON panel |
| OBSV-03 | Grafana dashboard shows fraud detection rate over time | Prometheus query ratio of `fraud_detections_total` / `fraud_requests_total` |
| OBSV-04 | Grafana dashboard shows model prediction latency (p50/p95/p99) | Histogram metric `fraud_prediction_latency_seconds` with quantile queries |
| OBSV-05 | Grafana dashboard shows Kafka consumer lag | JMX MBean `kafka.consumer:type=consumer-fetch-manager-metrics,client-id=*` records-lag metric or kafka-lag-exporter |
| OBSV-06 | Grafana alerting rules for high fraud rate and model performance degradation | Provisioned `configs/grafana/provisioning/alerting/alerts.yaml` with Grafana-managed rules |
| OBSV-07 | Prometheus and Grafana run as Docker Compose services | Two new services in `docker-compose.yml` with volume mounts for configs |
</phase_requirements>

---

## Summary

Phase 8 adds a full observability layer: Prometheus scraping, Grafana dashboards, Grafana alerting, and a daily monitoring Airflow DAG. The stack is well-understood with mature tooling.

**Critical architectural insight:** The fraud-api uses `mlflow models serve` (gunicorn-based), not a custom Flask application. You cannot inject `prometheus_client` middleware into it directly. The standard solution is a **separate metrics sidecar container** (`fraud-metrics`) that exposes application-level counters/histograms to Prometheus. The sidecar pattern is explicitly recognized in D-01's wording ("Claude's Discretion: Custom Python exporter for application-level metrics vs embedding in fraud-api").

The monitoring DAG builds on Phase 7's Airflow infrastructure. It reuses `prepare_data.py` for validation data generation, `evaluate.py` for F1 computation, `alerting.py` for alert writing, and introduces `TriggerDagRunOperator` to call `retraining_dag` on F1 degradation.

**Primary recommendation:** Use the fraud-metrics sidecar pattern for OBSV-01; provision all Grafana state via JSON/YAML files mounted from `configs/grafana/`; implement KS/PSI drift detection using `scipy.stats` and numpy inside the monitoring DAG with no new external dependencies.

---

## Project Constraints (from CLAUDE.md)

- Python snake_case for modules, PascalCase for classes
- No auto-formatter — follow PEP 8 manually
- Error handling: try-except with meaningful messages; fallback values where appropriate
- Print-based logging pattern: `print(f"[step/total] message")` for pipeline stages
- Module docstrings required; public functions need comprehensive docstrings with "Mulakat notu" sections
- `src/config.py` pattern for centralized env vars; load with `os.getenv("VAR", "default")`
- DAG files mounted from `airflow/dags/` — monitoring DAG goes there
- YAML anchors used in `docker-compose.yml` for shared config — extend with new services, don't duplicate
- Configs directory pattern established: `configs/kafka_config.yaml`, `configs/spark_config.yaml` — add `configs/prometheus/` and `configs/grafana/`
- New ports 9090 (Prometheus) and 3000 (Grafana) — no conflicts with existing services
- Java 11 is the JVM in the project — JMX exporter JAR must be compatible

---

## Standard Stack

### Core
| Library / Service | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| prometheus-client (Python) | 0.24.1 | Expose /metrics endpoint from fraud-metrics sidecar | Official Prometheus Python library; Counter/Histogram/Gauge types; make_wsgi_app() for HTTP |
| prom/prometheus | 2.x (Docker) | Scrapes all targets every 15s | Industry-standard time-series DB for metrics |
| grafana/grafana | 10.x (Docker) | Dashboards + alerting | Standard visualization layer for Prometheus |
| jmx_prometheus_javaagent | 1.1.0 or 0.20.0 | Scrape Kafka/Spark JMX MBeans | Attaches as Java agent; no code change to Kafka/Spark needed |
| scipy | 1.17.1 | KS test (`scipy.stats.ks_2samp`) for drift detection | Already in Python ecosystem; official stats library |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | 1.26.0+ (already installed) | PSI computation using histogram binning | PSI does not need a separate library; numpy bins + entropy formula suffices |
| mlflow (client) | 2.12.x (already installed) | Retrieve baseline metrics and run history from MLflow for monitoring DAG | Already used in Phase 7 DAGs |
| apache-airflow (already installed in Airflow container) | 2.9.3 | TriggerDagRunOperator for retraining trigger | Already in Airflow container |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate fraud-metrics sidecar | Modify mlflow models serve startup | mlflow models serve does not support middleware injection; sidecar is the only clean option |
| JMX exporter sidecar for Kafka | kafka-lag-exporter (Scala) | kafka-lag-exporter is Scala/JVM, heavier; JMX exporter is simpler but requires JMX MBean config; either works, JMX exporter is more general |
| scipy KS test | Evidently library | Evidently is v2 (ADVM-02); scipy already in Python ecosystem, no new dependency |
| TriggerDagRunOperator | Airflow REST API call via requests | TriggerDagRunOperator is the canonical Airflow pattern; REST API adds auth complexity |
| Grafana alerting (provisioned YAML) | Prometheus alertmanager | Prometheus alertmanager requires separate service + routing config; Grafana alerting is simpler for this scope |

**Installation (new packages only):**
```bash
# Add to requirements.txt
prometheus-client>=0.24.0
scipy>=1.11.0  # for ks_2samp

# In Dockerfile for fraud-metrics sidecar (new minimal Dockerfile)
pip install prometheus-client>=0.24.0 requests>=2.31.0
```

**Version verification (confirmed from PyPI 2026-03-23):**
- `prometheus-client`: 0.24.1
- `scipy`: 1.17.1

---

## Architecture Patterns

### Recommended Project Structure
```
configs/
├── prometheus/
│   └── prometheus.yml          # Scrape targets config (static)
├── grafana/
│   ├── provisioning/
│   │   ├── datasources/
│   │   │   └── prometheus.yaml # Prometheus datasource
│   │   ├── dashboards/
│   │   │   └── dashboards.yaml # Dashboard provider config
│   │   └── alerting/
│   │       └── alerts.yaml     # Grafana alert rules
│   └── dashboards/
│       └── fraud_detection.json # Dashboard JSON (exported from UI)
airflow/dags/
├── monitoring_dag.py            # New: daily monitoring DAG
├── retraining_dag.py            # Existing: triggered by monitoring DAG
└── utils/
    ├── alerting.py              # Existing: reuse write_alert()
    ├── mlflow_helpers.py        # Existing: reuse get_champion_metrics()
    ├── data_quality.py          # Existing
    └── drift_detection.py       # New: KS test + PSI computation functions
src/
└── metrics/                    # New package
    ├── __init__.py
    └── fraud_metrics.py        # HTTP server exposing /metrics via prometheus_client
```

### Pattern 1: Fraud-Metrics Sidecar
**What:** A standalone Python HTTP server using `prometheus_client.make_wsgi_app()` that exposes application-level metrics. Runs as a separate Docker Compose service (`fraud-metrics`) on port 9101.
**When to use:** When the main serving process (mlflow models serve / gunicorn) cannot be modified to inject middleware.
**Design:** The sidecar maintains shared state via Prometheus's multiprocess metric registry or by proxying requests to fraud-api and recording timing/outcome. Simpler approach: the sidecar exposes a `/record` internal endpoint that the monitoring DAG or any test script can push metrics to, but for production-realistic behavior, the sidecar intercepts calls from the outside by acting as a reverse proxy in front of fraud-api.

**Practical recommendation:** For this portfolio project, the simplest correct approach is a lightweight Python HTTP server that:
1. Accepts calls at `/invocations` (proxying to fraud-api:5002)
2. Records Counter and Histogram metrics via `prometheus_client`
3. Exposes `/metrics` at port 9101

**Example:**
```python
# Source: prometheus_client official docs (prometheus.github.io/client_python/)
from prometheus_client import Counter, Histogram, make_wsgi_app, REGISTRY
from wsgiref.simple_server import make_server
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import flask, requests, time

REQUEST_COUNT = Counter(
    'fraud_requests_total', 'Total prediction requests', ['status']
)
FRAUD_DETECTIONS = Counter(
    'fraud_detections_total', 'Total fraud predictions'
)
PREDICTION_LATENCY = Histogram(
    'fraud_prediction_latency_seconds',
    'Model prediction latency',
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5]
)
FRAUD_SCORE = Histogram(
    'fraud_score_distribution',
    'Distribution of fraud probability scores',
    buckets=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
)
```

### Pattern 2: Grafana Dashboard Provisioning
**What:** Mount `configs/grafana/provisioning/` into Grafana container at `/etc/grafana/provisioning`. Grafana reads YAML files at startup and auto-configures datasources, dashboard providers, and alert rules.
**When to use:** Always — manual UI config is lost on container restart (noted as concern in STATE.md).

**File structure:**
```yaml
# configs/grafana/provisioning/datasources/prometheus.yaml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    editable: false
```

```yaml
# configs/grafana/provisioning/dashboards/dashboards.yaml
apiVersion: 1
providers:
  - name: 'fraud-detection'
    orgId: 1
    folder: 'Fraud Detection'
    type: file
    disableDeletion: false
    updateIntervalSeconds: 30
    allowUiUpdates: true
    options:
      path: /var/lib/grafana/dashboards
```

```yaml
# configs/grafana/provisioning/alerting/alerts.yaml
apiVersion: 1
groups:
  - orgId: 1
    name: fraud-detection-alerts
    folder: Fraud Detection
    interval: 1m
    rules:
      - uid: high-fraud-rate
        title: High Fraud Rate
        condition: C
        data:
          - refId: A
            queryType: ''
            relativeTimeRange: {from: 300, to: 0}
            datasourceUid: prometheus
            model:
              expr: 'rate(fraud_detections_total[5m]) / rate(fraud_requests_total[5m])'
        noDataState: NoData
        execErrState: Alerting
        for: 2m
```

### Pattern 3: JMX Exporter for Kafka (Sidecar Container)
**What:** A separate `kafka-jmx-exporter` container downloads the JMX exporter JAR, mounts a config YAML, connects to Kafka's JMX port, and exposes metrics for Prometheus scraping.
**When to use:** Confluent cp-kafka containers support JMX via `KAFKA_JMX_PORT` env var; the exporter sidecar reads from that JMX port and translates to Prometheus format.

**Kafka environment additions:**
```yaml
kafka:
  environment:
    KAFKA_JMX_PORT: 9999
    KAFKA_JMX_HOSTNAME: kafka
    KAFKA_JMX_OPTS: >-
      -Dcom.sun.management.jmxremote
      -Dcom.sun.management.jmxremote.authenticate=false
      -Dcom.sun.management.jmxremote.ssl=false
      -Djava.rmi.server.hostname=kafka
  ports:
    - "9999:9999"
```

**JMX exporter sidecar:**
```yaml
kafka-jmx-exporter:
  image: bitnami/jmx-exporter:latest
  container_name: kafka-jmx-exporter
  depends_on:
    kafka:
      condition: service_healthy
  command: ["7071", "/etc/jmx-exporter/kafka.yaml"]
  ports:
    - "7071:7071"
  volumes:
    - ./configs/jmx/kafka.yaml:/etc/jmx-exporter/kafka.yaml
```

### Pattern 4: JMX Exporter for Spark (Java Agent)
**What:** Download `jmx_prometheus_javaagent-1.1.0.jar` and mount into spark containers; configure via `SPARK_DAEMON_JAVA_OPTS`.
**When to use:** For apache/spark:3.5.4 image (project's Spark image).

**Docker Compose additions to spark-master and spark-worker:**
```yaml
spark-master:
  environment:
    - SPARK_DAEMON_JAVA_OPTS=-javaagent:/opt/jmx_exporter/jmx_prometheus_javaagent.jar=8090:/opt/jmx_exporter/spark.yaml
  ports:
    - "8090:8090"   # Spark master JMX metrics
  volumes:
    - ./configs/jmx:/opt/jmx_exporter

spark-worker:
  environment:
    - SPARK_DAEMON_JAVA_OPTS=-javaagent:/opt/jmx_exporter/jmx_prometheus_javaagent.jar=8091:/opt/jmx_exporter/spark.yaml
  ports:
    - "8091:8091"   # Spark worker JMX metrics
  volumes:
    - ./configs/jmx:/opt/jmx_exporter
```

The JAR must be placed in `configs/jmx/` or downloaded via a `curl` step in an init container/Makefile target.

### Pattern 5: Prometheus Scrape Config
```yaml
# configs/prometheus/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'fraud-api'
    static_configs:
      - targets: ['fraud-metrics:9101']
        labels:
          service: 'fraud-api'

  - job_name: 'kafka-jmx'
    static_configs:
      - targets: ['kafka-jmx-exporter:7071']
        labels:
          service: 'kafka'

  - job_name: 'spark-master'
    static_configs:
      - targets: ['spark-master:8090']
        labels:
          service: 'spark-master'

  - job_name: 'spark-worker'
    static_configs:
      - targets: ['spark-worker:8091']
        labels:
          service: 'spark-worker'
```

### Pattern 6: Monitoring DAG with TriggerDagRunOperator
**What:** Daily Airflow DAG that checks F1, runs KS/PSI drift detection, and triggers `retraining_dag` when F1 falls below threshold.
**When to use:** MOND-01 through MOND-06 requirements.

```python
# Source: https://airflow.apache.org/docs/apache-airflow/stable/_api/airflow/operators/trigger_dagrun/index.html
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

# Conditional trigger via BranchPythonOperator
def check_f1_and_branch(**kwargs):
    f1 = kwargs['ti'].xcom_pull(key='daily_f1', task_ids='check_daily_f1')
    return 'trigger_retraining' if f1 < F1_ALERT_THRESHOLD else 'no_retraining_needed'

t_trigger = TriggerDagRunOperator(
    task_id='trigger_retraining',
    trigger_dag_id='retraining_dag',
    wait_for_completion=False,   # monitoring DAG finishes independently
    conf={'trigger_reason': 'f1_degradation', 'daily_f1': '{{ ti.xcom_pull(...) }}'},
)
```

### Pattern 7: PSI Computation (No External Library)
```python
# Pure numpy PSI implementation — no additional dependencies
import numpy as np

def compute_psi(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """
    Population Stability Index between reference and current distributions.
    PSI < 0.1: stable, 0.1-0.2: minor shift, > 0.2: major shift (MOND-06 threshold).
    """
    reference_hist, bin_edges = np.histogram(reference, bins=bins, density=False)
    current_hist, _ = np.histogram(current, bins=bin_edges, density=False)

    # Avoid division by zero
    reference_pct = reference_hist / len(reference)
    current_pct = current_hist / len(current)

    reference_pct = np.where(reference_pct == 0, 1e-4, reference_pct)
    current_pct = np.where(current_pct == 0, 1e-4, current_pct)

    psi = np.sum((current_pct - reference_pct) * np.log(current_pct / reference_pct))
    return float(psi)
```

### Anti-Patterns to Avoid
- **Attempting to inject prometheus_client into mlflow models serve:** The gunicorn process does not support WSGI middleware injection without modifying mlflow internals. Use the sidecar pattern instead.
- **Using Grafana UI to create dashboards:** Dashboard state is lost on container restart. Always export JSON and commit to `configs/grafana/dashboards/`.
- **Scraping Spark Web UI port 8080 directly:** The Spark Web UI returns HTML, not Prometheus-format metrics. JMX exporter is required.
- **Using alertmanager:** Adds another service with routing config complexity. Grafana-managed alerting is sufficient for this scope.
- **Storing drift baseline in container memory:** Baseline feature distributions must be persisted to disk (parquet) so monitoring DAG can reload them across container restarts.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Prometheus exposition format | Custom text format generator | `prometheus_client.generate_latest()` | Format spec has edge cases; library handles multiprocess, content types, escaping |
| Grafana dashboard state persistence | Custom DB export scripts | Grafana provisioning (JSON mount) | Built-in feature; official support; survives container restart |
| KS test statistic | Manual CDF comparison | `scipy.stats.ks_2samp()` | Correct two-sample KS implementation with p-value; handles ties |
| PSI binning | Pandas-based custom logic | numpy histogram (Pattern 7 above) | Concise, fast, no extra dependency; well-documented formula |
| Cross-DAG triggering | Airflow REST API via requests | `TriggerDagRunOperator` | Native operator; handles auth, serialization, error states automatically |

**Key insight:** The observability domain's complexity is in configuration and wiring, not computation. Use standard libraries for all statistical tests and metrics exposition — the value of this phase is in having correct wiring, not novel algorithms.

---

## Common Pitfalls

### Pitfall 1: fraud-api Cannot Expose /metrics Directly
**What goes wrong:** Developer adds `prometheus_client` to `Dockerfile.serving` and tries to run a metrics server alongside `mlflow models serve`. Port conflict or the gunicorn process owns the port.
**Why it happens:** `mlflow models serve` starts gunicorn bound to 0.0.0.0:5002 and there is no hook to run additional HTTP servers in the same process.
**How to avoid:** Use the fraud-metrics sidecar container pattern (Pattern 1). The sidecar owns port 9101 and proxies to fraud-api:5002 while recording metrics.
**Warning signs:** `OSError: [Errno 98] Address already in use` when starting the serving container.

### Pitfall 2: JMX Exporter JAR Missing at Spark Startup
**What goes wrong:** Spark containers fail to start because `SPARK_DAEMON_JAVA_OPTS` references a JAR path that doesn't exist in the container.
**Why it happens:** The JAR must be physically present in the container via volume mount or copied in. It is not bundled in `apache/spark:3.5.4`.
**How to avoid:** Either (a) add a `jmx-init` container that downloads the JAR to a named volume, or (b) download the JAR to `configs/jmx/` during `make setup` and mount the directory. Option (b) is simpler.
**Warning signs:** `java.lang.instrument.IllegalClassFormatException` or Spark container exits immediately with non-zero code.

### Pitfall 3: Grafana Dashboard JSON Has Wrong UID After Export
**What goes wrong:** Dashboard JSON exported from one Grafana instance cannot be imported into a fresh instance because the datasource UID does not match.
**Why it happens:** Grafana generates datasource UIDs internally. The exported dashboard JSON hardcodes the UID from the source instance.
**How to avoid:** In the provisioned datasource YAML, set `uid: prometheus` explicitly. In the dashboard JSON, reference the same UID string.
**Warning signs:** Panels show "No data" or "Datasource not found" after provisioning.

### Pitfall 4: Prometheus Scrape Target Unreachable Inside Docker Network
**What goes wrong:** Prometheus shows targets as DOWN even though containers are running.
**Why it happens:** Prometheus runs in its own container and must resolve service names via Docker's internal DNS. Using `localhost` as a scrape target references the Prometheus container itself, not the fraud-metrics sidecar.
**How to avoid:** Always use Docker Compose service names in `prometheus.yml` targets (e.g., `fraud-metrics:9101`, `kafka-jmx-exporter:7071`). Ensure all services are on the same Docker network.
**Warning signs:** Target scrape errors in Prometheus UI at `http://localhost:9090/targets`.

### Pitfall 5: Monitoring DAG F1 Check with No Validation Data
**What goes wrong:** Monitoring DAG runs the F1 check but the validation parquet (`data/splits/val.parquet`) doesn't exist or is from a different schema version.
**Why it happens:** The monitoring DAG depends on `data/splits/val.parquet` written by `prepare_data.py` during the last retraining run. If retraining hasn't run, or if splits were written to a different path, the check fails.
**How to avoid:** Monitoring DAG must generate its own fresh validation batch using `generate_historical_data()` from `prepare_data.py`, rather than depending on stale split files. Generate ~5000 rows, score via fraud-api, compute F1 against known labels.
**Warning signs:** `FileNotFoundError: data/splits/val.parquet` in DAG logs.

### Pitfall 6: KS Test p-value vs Statistic Threshold Confusion
**What goes wrong:** Developer uses `p < 0.05` as the drift threshold instead of the PSI > 0.2 threshold from MOND-06, causing spurious alerts with large datasets.
**Why it happens:** KS test p-value decreases with sample size — with 30,000 rows, almost any drift triggers p < 0.05. PSI is sample-size agnostic.
**How to avoid:** Use PSI as the primary drift alerting signal (MOND-06: PSI > 0.2). Log KS statistics alongside PSI for interpretability but do NOT trigger alerts based on p-value alone.
**Warning signs:** Monitoring DAG generates drift alerts on every run even when data looks healthy.

### Pitfall 7: Grafana Alert Rules Referencing Non-Existent Metrics
**What goes wrong:** Provisioned alerting YAML references Prometheus metric names that are not yet being scraped (e.g., if fraud-metrics sidecar is down).
**Why it happens:** Grafana provisioning is declarative — it loads regardless of whether the metric exists. Alert state becomes "No data" which may or may not fire depending on `noDataState` setting.
**How to avoid:** Set `noDataState: NoData` (not `Alerting`) so that missing data doesn't create false positive alerts. Also verify Prometheus targets are UP before testing alerts.
**Warning signs:** Alert fires immediately after deployment when no traffic has occurred.

---

## Code Examples

Verified patterns from official sources:

### prometheus_client Counter/Histogram with Labels
```python
# Source: https://prometheus.github.io/client_python/instrumenting/counter/
from prometheus_client import Counter, Histogram, Gauge

REQUESTS = Counter(
    'fraud_requests_total',
    'Total fraud prediction requests',
    ['status']          # labels: success, error
)

LATENCY = Histogram(
    'fraud_prediction_latency_seconds',
    'Fraud prediction latency in seconds',
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

FRAUD_RATE_GAUGE = Gauge(
    'fraud_rate_current',
    'Current fraud detection rate (rolling)'
)

# Usage
start = time.time()
result = requests.post("http://fraud-api:5002/invocations", json=payload)
LATENCY.observe(time.time() - start)
REQUESTS.labels(status='success').inc()
```

### Expose /metrics via Flask + DispatcherMiddleware
```python
# Source: https://prometheus.github.io/client_python/
from flask import Flask
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

app = Flask(__name__)
app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
    '/metrics': make_wsgi_app()
})

if __name__ == '__main__':
    run_simple('0.0.0.0', 9101, app.wsgi_app)
```

### TriggerDagRunOperator
```python
# Source: https://airflow.apache.org/docs/apache-airflow/stable/_api/airflow/operators/trigger_dagrun/index.html
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

t_trigger_retraining = TriggerDagRunOperator(
    task_id='trigger_retraining_dag',
    trigger_dag_id='retraining_dag',
    wait_for_completion=False,
    conf={'trigger_reason': 'monitoring_f1_below_threshold'},
    trigger_rule='all_success',
)
```

### KS Test via scipy
```python
# Source: https://docs.scipy.org/doc/scipy-1.14.0/reference/generated/scipy.stats.mstats.ks_2samp.html
from scipy import stats
import numpy as np

def compute_ks_test(reference: np.ndarray, current: np.ndarray) -> dict:
    """KS test between reference and current feature distributions."""
    stat, p_value = stats.ks_2samp(reference, current)
    return {
        "ks_statistic": float(stat),
        "p_value": float(p_value),
        "drifted": stat > 0.1,  # threshold: KS statistic > 0.1 indicates meaningful shift
    }
```

### Grafana Datasource Provisioning
```yaml
# configs/grafana/provisioning/datasources/prometheus.yaml
# Source: https://grafana.com/docs/grafana/latest/administration/provisioning/
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    uid: prometheus          # fixed UID so dashboard JSON can reference it
    isDefault: true
    editable: false
    jsonData:
      timeInterval: "15s"   # matches Prometheus scrape_interval
```

### Docker Compose Prometheus + Grafana Services
```yaml
prometheus:
  image: prom/prometheus:latest
  container_name: prometheus
  ports:
    - "9090:9090"
  volumes:
    - ./configs/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
    - prometheus_data:/prometheus
  command:
    - '--config.file=/etc/prometheus/prometheus.yml'
    - '--storage.tsdb.path=/prometheus'
    - '--web.console.libraries=/etc/prometheus/console_libraries'
    - '--web.console.templates=/etc/prometheus/consoles'
  healthcheck:
    test: wget -q --tries=1 http://localhost:9090/-/healthy -O /dev/null || exit 1
    interval: 10s
    timeout: 5s
    retries: 5
  restart: unless-stopped

grafana:
  image: grafana/grafana:latest
  container_name: grafana
  ports:
    - "3000:3000"
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=admin
    - GF_PATHS_PROVISIONING=/etc/grafana/provisioning
  volumes:
    - ./configs/grafana/provisioning:/etc/grafana/provisioning
    - ./configs/grafana/dashboards:/var/lib/grafana/dashboards
    - grafana_data:/var/lib/grafana
  depends_on:
    prometheus:
      condition: service_healthy
  healthcheck:
    test: wget -q --tries=1 http://localhost:3000/api/health -O /dev/null || exit 1
    interval: 10s
    timeout: 5s
    retries: 5
  restart: unless-stopped
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual Grafana UI dashboard setup | Provisioned JSON + YAML (GitOps) | Grafana 5.0+ | Dashboards survive container restart; version-controlled |
| Alertmanager for Prometheus alerts | Grafana-managed alerting rules | Grafana 9.0 unified alerting | Single service for both dashboards and alerts |
| Standalone JMX Exporter process | Java agent (javaagent mode) | JMX Exporter 0.6+ | No RMI config complexity; strongly recommended by project |
| prometheus-flask-exporter library | Direct prometheus_client + DispatcherMiddleware | Current | More control; no Flask-specific magic |

**Deprecated/outdated:**
- Prometheus Alertmanager for simple threshold alerts: still valid but adds service complexity; Grafana unified alerting (9.x+) replaces it for dashboard-integrated workflows
- `start_http_server()` from prometheus_client: still works but make_wsgi_app() integrates cleaner with Flask
- JMX Exporter version 0.15.x and older: current stable is 1.1.0 with different config YAML structure (lowercase `rules` key is same; HTTP mode naming changed)

---

## Open Questions

1. **kafka-lag-exporter vs JMX for consumer lag (OBSV-05)**
   - What we know: Kafka JMX MBean `kafka.consumer:type=consumer-fetch-manager-metrics` exposes `records-lag` per partition; but this requires the consumer (Spark streaming) to be running
   - What's unclear: Whether JMX consumer lag metrics are available from the broker side or only from the consumer side. If consumer-side, the Spark streaming consumer would need JMX configuration too.
   - Recommendation: Use kafka-lag-exporter (Scala Docker container) which reads from Kafka AdminClient API — simpler than JMX consumer config and gives cleaner per-consumer-group metrics. Alternatively, verify broker-side `kafka.server:type=FetcherLagMetrics` MBean is available via broker JMX.

2. **JMX exporter JAR delivery mechanism**
   - What we know: The JAR must be at the path specified in `SPARK_DAEMON_JAVA_OPTS` before Spark starts
   - What's unclear: Best delivery approach — commit JAR to repo (large binary), `curl` in Makefile, or init container
   - Recommendation: Add `make download-jmx-exporter` target that runs `curl` to download `jmx_prometheus_javaagent-1.1.0.jar` from GitHub releases into `configs/jmx/`. Add to `.gitignore`. Simplest approach for local dev.

3. **Monitoring DAG: how to generate labeled validation data for daily F1**
   - What we know: `generate_historical_data()` from `prepare_data.py` creates labeled transactions with known fraud flags
   - What's unclear: Whether to score via fraud-api REST call (real serving path) or load model directly in DAG
   - Recommendation: Score via fraud-api REST call (`http://fraud-api:5002/invocations`) using generated validation batch. This tests the full serving path. Compute F1 by comparing `fraud_prediction` output against known `is_fraud` labels.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Docker | All services | Yes | 29.2.1 | — |
| Python 3.x | fraud-metrics sidecar, monitoring DAG | Yes | 3.12.12 | — |
| prometheus-client (Python) | fraud-metrics sidecar | Not installed in .venv | 0.24.1 (PyPI) | — (must install) |
| scipy | monitoring DAG KS test | Not installed in .venv | 1.17.1 (PyPI) | — (must install, lightweight) |
| prom/prometheus (Docker image) | Prometheus service | Pull on demand | latest (2.x) | — |
| grafana/grafana (Docker image) | Grafana service | Pull on demand | latest (10.x) | — |
| jmx_prometheus_javaagent JAR | Spark JMX metrics | Not present | 1.1.0 (GitHub releases) | Skip Spark JMX panels (degrade gracefully) |
| bitnami/jmx-exporter (Docker) | Kafka JMX metrics | Pull on demand | latest | kafka-lag-exporter as alternative |
| Airflow TriggerDagRunOperator | monitoring DAG retraining trigger | Yes (bundled with Airflow 2.9.3) | 2.9.3 | — |

**Missing dependencies with no fallback:**
- `prometheus-client` Python library (needs `pip install prometheus-client>=0.24.0`)
- `scipy` Python library (needs `pip install scipy>=1.11.0`)

**Missing dependencies with fallback:**
- JMX exporter JAR: if download fails, Spark JMX panels can be omitted from dashboard; core fraud-api and Kafka metrics still work

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (already in project) |
| Config file | none — invoked directly |
| Quick run command | `python3 -m pytest tests/ -x -q` |
| Full suite command | `python3 -m pytest tests/ -v` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MOND-01 | Monitoring DAG has expected tasks | unit | `python3 -m pytest tests/test_monitoring_dag.py::test_dag_has_expected_tasks -x` | Wave 0 |
| MOND-02 | KS test function returns correct keys and detects drift | unit | `python3 -m pytest tests/test_drift_detection.py::test_ks_test -x` | Wave 0 |
| MOND-02 | PSI function returns correct value and threshold | unit | `python3 -m pytest tests/test_drift_detection.py::test_psi_computation -x` | Wave 0 |
| MOND-05 | F1 alert threshold branch returns 'trigger_retraining' when F1 < 0.85 | unit | `python3 -m pytest tests/test_monitoring_dag.py::test_f1_alert_branch -x` | Wave 0 |
| MOND-06 | PSI alert fires when PSI > 0.2 | unit | `python3 -m pytest tests/test_drift_detection.py::test_psi_threshold -x` | Wave 0 |
| OBSV-01 | fraud-metrics sidecar exposes /metrics with expected metric names | unit | `python3 -m pytest tests/test_fraud_metrics.py::test_metrics_endpoint_has_required_metrics -x` | Wave 0 |
| OBSV-07 | docker-compose.yml contains prometheus and grafana services | unit | `python3 -m pytest tests/test_docker_compose.py::test_observability_services_present -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_monitoring_dag.py` — covers MOND-01, MOND-05 (DAG structure + branch logic)
- [ ] `tests/test_drift_detection.py` — covers MOND-02, MOND-06 (KS test, PSI computation, thresholds)
- [ ] `tests/test_fraud_metrics.py` — covers OBSV-01 (metrics sidecar exports expected metric names)
- [ ] `tests/test_docker_compose.py` — covers OBSV-07 (prometheus + grafana services in compose)
- [ ] `airflow/dags/utils/drift_detection.py` — new utility module with `compute_psi()` and `compute_ks_test()` functions

---

## Sources

### Primary (HIGH confidence)
- `prometheus.github.io/client_python/` — Counter, Histogram, Gauge, make_wsgi_app() usage
- `grafana.com/docs/grafana/latest/administration/provisioning/` — Dashboard and datasource provisioning YAML structure
- `airflow.apache.org/docs/apache-airflow/stable/_api/airflow/operators/trigger_dagrun/` — TriggerDagRunOperator API
- `docs.confluent.io/platform/current/installation/docker/operations/monitoring.html` — KAFKA_JMX_PORT, KAFKA_JMX_HOSTNAME, KAFKA_JMX_OPTS

### Secondary (MEDIUM confidence)
- `docs.scipy.org/doc/scipy-1.14.0/reference/generated/scipy.stats.mstats.ks_2samp.html` — KS test API
- `github.com/confluentinc/jmx-monitoring-stacks` — JMX monitoring stack reference for Confluent Platform
- WebSearch results for JMX exporter Docker Compose patterns (multiple corroborating sources)
- WebSearch for PSI implementation patterns (multiple corroborating sources from 2024)

### Tertiary (LOW confidence)
- Spark + SPARK_DAEMON_JAVA_OPTS JMX agent pattern (found via WebSearch, kubeflow docs; Kubernetes context vs Docker Compose, same env var name, treat as MEDIUM pending verification during implementation)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — prometheus-client, Grafana provisioning, Airflow TriggerDagRunOperator verified via official docs
- Architecture (sidecar pattern): HIGH — confirmed fraud-api is mlflow models serve/gunicorn; sidecar is the only clean option
- JMX Exporter config (KAFKA_JMX_OPTS, SPARK_DAEMON_JAVA_OPTS): MEDIUM — patterns from multiple WebSearch sources; Confluent docs confirmed KAFKA_JMX_ vars; SPARK_DAEMON_JAVA_OPTS confirmed via community but needs verification at runtime
- Drift detection (KS/PSI): HIGH — scipy official docs; PSI formula is standard financial risk practice
- Grafana alerting provisioning YAML: MEDIUM — official docs reference confirmed; exact rule schema is Grafana 9.x+ unified alerting format

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (30 days — Prometheus/Grafana APIs are stable; JMX exporter versions may change)
