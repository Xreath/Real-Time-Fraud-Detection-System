# Pitfalls Research

**Domain:** MLOps deployment/orchestration/monitoring — fraud detection pipeline
**Researched:** 2026-03-21
**Confidence:** HIGH (grounded in existing codebase, known stack decisions, and MLOps production patterns)

---

## Critical Pitfalls

### Pitfall 1: Training-Serving Skew via Separate Preprocessing Paths

**What goes wrong:**
`mlflow models serve` serves the logged model object (LGBMClassifier) via REST API. The model only knows about raw feature arrays — it does NOT include the `scaler.joblib` or `label_encoders.joblib` that live in `data/artifacts/`. Any client calling the REST endpoint must apply the same preprocessing before sending features, or the model receives unscaled, un-encoded inputs and produces garbage scores. The current `FraudScorer` class handles preprocessing internally, but it is not part of the logged MLflow artifact.

**Why it happens:**
The project currently logs the model but not the preprocessing pipeline as a unified artifact. `mlflow.sklearn.log_model` logs the LGBMClassifier in isolation. When serving via REST, the preprocessing step is only embedded in `FraudScorer._load()` / `FraudScorer.preprocess()` — a Python class, not an MLflow artifact.

**How to avoid:**
Wrap the preprocessing + model into a single `mlflow.pyfunc` custom model before serving. Override `predict()` to perform the full pipeline: label encoding → scaling → LightGBM inference. Log this pyfunc as the model artifact so that `mlflow models serve` exposes an endpoint that accepts raw transaction fields (amount, merchant_category, etc.) and returns fraud scores without any external preprocessing contract.

Alternatively, log the scaler and label encoders as extra artifacts alongside the model and document the preprocessing contract explicitly in the model signature using `mlflow.models.ModelSignature`.

**Warning signs:**
- REST endpoint returns suspiciously uniform scores (near 0 or 0.5 for everything)
- Score from REST API does not match `FraudScorer.score()` for the same input
- Load test results show no variation across different transaction types

**Phase to address:**
Phase 6 (Local Model Serving) — must be resolved before load testing or any REST API integration.

---

### Pitfall 2: MLflow Version Mismatch Between Server and `mlflow models serve`

**What goes wrong:**
The MLflow server runs v2.12.2 inside Docker (see `Dockerfile.mlflow`). If `mlflow models serve` is run from a host Python environment with a different MLflow version (e.g., 2.14.x or 2.10.x), the served model may fail to load — particularly if the model was logged with version-specific flavor metadata. Additionally, `mlflow models serve` spawns a Flask/gunicorn server locally; if the host Python lacks the LightGBM dependency, the server will fail at inference even if it starts.

**Why it happens:**
MLflow's model flavor metadata includes a `mlflow_version` key. When serving, MLflow compares this against the running client version. Version drift between server (where model was logged) and client (where model is served) causes schema mismatch or deserialization errors. The Docker server is pinned at 2.12.2 but the host environment is unconstrained.

**How to avoid:**
Pin `mlflow==2.12.2` in `requirements.txt` (or a dedicated `requirements-serving.txt`). When using `mlflow models serve`, either use the Docker container's Python environment or explicitly activate a venv with the pinned version. Document this constraint in the project Makefile with a `serve-local` target that enforces the right environment.

**Warning signs:**
- `mlflow models serve` starts but crashes on first request with a deserialization error
- Error messages referencing `mlflow_version` mismatch
- `ImportError: cannot import name X from mlflow` during `mlflow models serve`

**Phase to address:**
Phase 6 (Local Model Serving) — pin versions before writing the serve command.

---

### Pitfall 3: Airflow DAG-Level Import Side Effects Break the Scheduler

**What goes wrong:**
If Airflow DAG files import heavyweight libraries (pandas, mlflow, sklearn, lightgbm) at the module level — not inside task callables — the Airflow scheduler parses and re-imports every DAG file every 30 seconds. Each import of LightGBM or MLflow takes 0.5–2 seconds and consumes significant memory. With multiple DAGs, this causes scheduler lag, DagBag parse timeouts, and memory pressure that can crash the scheduler container.

**Why it happens:**
It is natural to write DAG files the same way as regular Python scripts. A `from src.serving.model_scorer import FraudScorer` at the top of a DAG file looks harmless but triggers the full import chain on every scheduler heartbeat.

**How to avoid:**
Move all heavy imports inside the task callable body or use Airflow's `PythonOperator` with `op_kwargs` to defer execution. Only import `datetime`, `pendulum`, `airflow.operators.*`, and Airflow hooks at DAG-file module level. Use `from __future__ import annotations` at the top to enable lazy annotation evaluation. For ML workloads, prefer `DockerOperator` or `KubernetesPodOperator` to completely isolate the execution environment.

**Warning signs:**
- `airflow dags list` takes more than 5 seconds
- Scheduler logs show repeated `DagBag import time` warnings
- Airflow UI shows "DAG file failed to import" errors intermittently

**Phase to address:**
Phase 7 (Airflow Setup + DAGs) — enforce this pattern from the first DAG written.

---

### Pitfall 4: Non-Idempotent Retraining DAG Causes Data Duplication or Double-Promotes Models

**What goes wrong:**
If the retraining DAG is not idempotent, a failed run followed by a manual re-trigger will append training data twice, log duplicate MLflow runs, or promote an already-promoted model to "champion" again (causing confusing version history). The current design writes to Parquet files incrementally — if the "append new data" step runs twice, the training dataset grows corrupt.

**Why it happens:**
Airflow's retry and backfill mechanics run tasks multiple times. Developers assume DAGs run once and write tasks that are not safe to re-execute. State is stored outside Airflow (MLflow registry, Parquet files) with no idempotency keys.

**How to avoid:**
Design every task to be idempotent:
- Use `execution_date` as a partition key when writing to Parquet (e.g., `data/splits/run_date=2026-03-21/train.parquet`)
- Before promoting a model in MLflow, check whether the current run's model is already promoted with the same `run_id`
- Use Airflow's `task_instance.xcom_push` to carry the MLflow `run_id` across tasks and validate it before each state-changing operation
- Never use `append` mode for training data Parquet writes without a deduplication step

**Warning signs:**
- MLflow shows multiple runs with identical metrics from the same date
- Training data row count grows faster than transaction generation rate
- Model registry shows the same model version promoted multiple times

**Phase to address:**
Phase 7 (Retraining DAG) — design for idempotency before writing any file I/O or registry promotion code.

---

### Pitfall 5: Canary Rollback Logic That Never Actually Triggers

**What goes wrong:**
A canary deployment is set up (10% traffic to new model), and an automated rollback condition is defined ("roll back if F1 drops"). But in practice, the rollback check runs against a validation set drawn from the same distribution as training data — not live inference traffic. Because the validation set is static and the model hasn't changed on it, F1 never drops and the rollback never fires, even when the canary model is worse on live data.

**Why it happens:**
Developers test the rollback condition using the held-out test set from Phase 5 training. This set was split before training, so the new model will always score similarly on it. The rollback condition needs to evaluate model quality on recently-seen production data, not the original test split.

**How to avoid:**
For local simulation: create a dedicated "canary evaluation set" by saving a window of the most recent generated transactions (e.g., last 2 hours of synthetic data) separately from the original train/val/test splits. Evaluate both champion and challenger on this set. Compare challenger F1 against champion F1 (not against an absolute threshold) to detect relative regression. Set rollback if `challenger_f1 < champion_f1 * 0.95`.

For Vertex AI canary: use online prediction request logs (if available) or a shadow evaluation job.

**Warning signs:**
- Canary has been live for 24+ hours with no evaluation result logged
- Rollback condition check always shows "challenger approved" regardless of model quality
- Monitoring DAG does not distinguish between champion and challenger traffic

**Phase to address:**
Phase 7 (Canary + Rollback mechanism) — define the evaluation dataset and comparison logic before the canary deployment logic.

---

### Pitfall 6: Prometheus Scrape Targets Not Reachable Inside Docker Network

**What goes wrong:**
Prometheus is configured with a `scrape_config` pointing to `localhost:8080` (Spark UI) or `localhost:5001` (MLflow) — addresses that are correct from the host machine but do not resolve inside the Prometheus container. Prometheus reports all targets as `DOWN` and no metrics are scraped, making the Grafana dashboards show empty panels. This is silent — Prometheus starts fine and reports no errors in logs beyond the target-down status.

**Why it happens:**
Docker Compose services communicate via service names on the internal Docker network, not via `localhost`. When copying scrape configs from host-facing documentation, the address `localhost` refers to the Prometheus container itself, not the other services.

**How to avoid:**
In `prometheus.yml`, use Docker service names as scrape targets:
- MLflow: `mlflow:5000` (internal port, not the host-mapped 5001)
- Spark Master: `spark-master:8080`
- Kafka: use JMX exporter sidecar on `kafka:9404` (requires adding JMX exporter to Kafka container)

Add Prometheus and Grafana to `docker-compose.yml` in the same network as the other services. Test scrape targets immediately using Prometheus's `http://localhost:9090/targets` page before building any Grafana dashboard.

**Warning signs:**
- Prometheus `/targets` page shows all targets as `DOWN (connection refused)`
- Grafana dashboards show "No data" for all panels
- `docker exec prometheus wget -q -O- http://mlflow:5000/health` fails

**Phase to address:**
Phase 8 (Grafana + Prometheus setup) — validate each scrape target before writing dashboard queries.

---

### Pitfall 7: Grafana Dashboard Built Before Metrics Are Emitted

**What goes wrong:**
The Grafana dashboard is designed and queries are written referencing metric names (e.g., `fraud_rate`, `model_latency_seconds`, `kafka_consumer_lag_sum`) before the application code actually emits those metrics. The dashboard queries return empty results, which looks identical to "no data yet" from a fresh start — making it impossible to tell whether the instrumentation is broken or the metrics simply haven't arrived yet.

**Why it happens:**
Dashboard design is a visual activity — it's tempting to do it first. But Prometheus metric names must exactly match what the application registers via `prometheus_client`. Any typo or naming convention mismatch (`fraud.rate` vs `fraud_rate`, snake_case vs camelCase) produces silent empty series.

**How to avoid:**
Follow the order: (1) instrument application code with `prometheus_client` and emit metrics, (2) verify metrics appear at the `/metrics` endpoint, (3) confirm Prometheus scrapes them (`prometheus_instant_query` in Prometheus UI), (4) then build Grafana dashboard panels.

Use Prometheus metric naming conventions from the start: `<namespace>_<subsystem>_<unit>` (e.g., `fraud_scorer_prediction_latency_seconds`, `kafka_consumer_lag_messages_total`). Document all metric names in a `metrics_registry.md` before writing any instrumentation code.

**Warning signs:**
- Grafana panels show "No data" even after the application has been running for minutes
- `curl localhost:<app_port>/metrics` returns no output or a 404
- Prometheus query explorer returns empty results for a metric name you believe is being emitted

**Phase to address:**
Phase 8 (Monitoring + Grafana) — instrument first, dashboard second.

---

### Pitfall 8: F1-Score Drift Threshold Tuned on Synthetic Data Acts as a False Alarm Factory

**What goes wrong:**
The monitoring DAG checks `F1 < 0.85` to trigger retraining. However, the model currently achieves `Test F1=0.982` on the held-out test set. On synthetic data (which follows the same generation distribution as training data), the daily F1 check will almost always return ~0.98. This means the threshold of 0.85 is set 13 percentage points below normal operating performance — the trigger will never fire unless there is catastrophic model failure, not the gradual drift it is meant to catch. Conversely, if data generation parameters are changed for simulation purposes, the metric can drop sharply and trigger false alerts.

**Why it happens:**
The 0.85 threshold is a reasonable production heuristic for models with typical F1 of 0.88–0.90. For a model operating at 0.982, it is far too permissive. This is a calibration mistake, not a design flaw.

**How to avoid:**
Set drift thresholds relative to baseline, not absolute: trigger retraining if `current_f1 < baseline_f1 * 0.97` (3% relative drop) rather than `current_f1 < 0.85`. Store the baseline F1 at model promotion time as an MLflow model tag (`baseline_f1`). The monitoring DAG reads this tag for comparison. This makes the threshold adaptive to future model generations with different absolute performance levels.

Also add a separate data drift signal (KS test p-value, PSI score) to the trigger logic so that retraining is triggered by distribution shift even before model F1 degrades.

**Warning signs:**
- Monitoring DAG always reports "model healthy" even when you manually introduce distribution shift in the data generator
- The F1 alert never fires during any test simulation
- No retrain occurs during a full week of operation despite changing data patterns

**Phase to address:**
Phase 7 (Monitoring DAG) — calibrate thresholds before the DAG is wired to trigger retraining.

---

### Pitfall 9: Airflow Docker Compose Network Isolation From Existing Services

**What goes wrong:**
Airflow is added as a new Docker Compose stack (separate `docker-compose.airflow.yml` or added to the existing file). Airflow's task containers need to connect to MLflow (port 5001), Postgres (port 5432), Kafka (port 29092), and MinIO (port 9000). If Airflow is brought up in a separate Docker Compose project, it creates its own Docker network and cannot reach the services on the `realtime_fraud_detection_default` network by service name.

**Why it happens:**
Adding Airflow to a large existing `docker-compose.yml` is messy, so developers separate it. But separate Compose projects create separate networks unless explicitly joined.

**How to avoid:**
Either:
(a) Add Airflow services (webserver, scheduler, worker) directly to the existing `docker-compose.yml` under the same network. This is the simpler approach and sufficient for a local portfolio project.
(b) If keeping a separate file, use `external: true` network references in both files pointing to the same named network, or use `docker network connect` for the Airflow containers.

Test inter-service connectivity before writing DAG code: `docker exec airflow-scheduler curl http://mlflow:5000/health` should return `{"status": "ok"}`.

**Warning signs:**
- Airflow tasks fail with `ConnectionRefusedError` or `Name or service not known` when connecting to MLflow/Kafka
- `airflow connections test` reports failure for all connections
- Airflow logs show the correct hostname but DNS resolution fails

**Phase to address:**
Phase 7 (Airflow Docker Setup) — validate network topology as the first task before any DAG code.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode MLflow model version (`model_version="1"`) in `FraudScorer` | Works immediately, simple | Scorer breaks silently when champion is promoted to version 2+ | Never — use `models:/fraud-detection-model@champion` alias instead |
| Load preprocessing artifacts from local path (`data/artifacts/`) | Simple for local dev | Breaks when Airflow runs tasks in Docker containers with different mount points | Only during local interactive testing; fix before any DAG execution |
| Skip `mlflow.set_experiment()` in retraining DAG | One less line of setup | All retraining runs land in `Default` experiment, making audit history unusable | Never for runs that touch model registry |
| Use Airflow `LocalExecutor` instead of `CeleryExecutor` | No Redis dependency, simpler setup | Task parallelism limited, blocking tasks can starve other DAGs | Acceptable for this portfolio project — document the limitation |
| Use `SequentialExecutor` during initial Airflow DAG development | Fast to iterate | Zero parallelism, not representative of production behavior | Only for first-run smoke tests |
| Skip Prometheus alertmanager, use only Grafana alerts | One less component | Grafana alerts fire only when someone has the UI open (if using free-tier alert evaluation) | Acceptable — note that `alertmanager` is the production approach |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Airflow → MLflow | Use `http://localhost:5001` as MLflow tracking URI inside Airflow task | Use `http://mlflow:5000` (Docker service name + internal port) inside any containerized task |
| Airflow → MinIO | Omit `MLFLOW_S3_ENDPOINT_URL` env var in Airflow worker environment | Set `MLFLOW_S3_ENDPOINT_URL=http://minio:9000` in `airflow.env` or Docker Compose env section |
| Prometheus → Spark | Try to scrape Spark metrics directly from port 8080 (HTML Web UI) | Add JMX Prometheus exporter to Spark container; or use Spark's built-in `/metrics/json` endpoint at port 4040 |
| Prometheus → Kafka | Scrape Kafka directly on port 9092 (broker port, not metrics) | Add `kafka-jmx-exporter` sidecar container that exposes metrics on port 9404 |
| MLflow serve → MinIO | Run `mlflow models serve` without setting `MLFLOW_S3_ENDPOINT_URL` | Export `MLFLOW_S3_ENDPOINT_URL=http://localhost:9000` before the serve command; MinIO must be running |
| Grafana → Prometheus | Use `localhost:9090` as Prometheus datasource URL in Grafana (when Grafana is in Docker) | Use `http://prometheus:9090` — the Docker service name |
| Airflow DAG → Parquet | Write feature store Parquet files with a relative path (`data/splits/`) | Use absolute paths or environment variables resolved at task execution time, not DAG parse time |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| `mlflow models serve` with default Flask server under load test | Requests queue up, p95 latency spikes to seconds | Use `--workers 4` flag with gunicorn backend, or add `--host 0.0.0.0 --port 5005` | Under 50+ concurrent requests |
| Loading MLflow model artifact from MinIO on every request | Cold-start latency of 2–5s per request if model is not cached | `mlflow models serve` caches the model in memory — do not restart the server between load test requests | On every server restart |
| Airflow scheduler scanning large `dags/` folder with many Python files | Scheduler heartbeat > 30s, DAG parse warnings | Keep DAG files small; use `.airflowignore` to exclude utility modules | With 10+ DAG files importing heavy libraries |
| Spark pandas_udf calling `FraudScorer()` constructor inside every batch | Model reloaded from MLflow on every micro-batch (every 10 seconds) | Initialize `FraudScorer` once using broadcast variable or module-level lazy initialization | From the first batch — this is the current risk in `spark_consumer.py` if scorer is constructed inside the UDF |
| KS test running on full historical feature distribution vs. new batch | Memory grows unbounded as historical window accumulates all data | Use a rolling window (last 7 days) stored as a sampled Parquet checkpoint | After 30+ days of operation |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| MinIO credentials hardcoded as `minioadmin/minioadmin` in `docker-compose.yml` | Credential leak if repo is public; no separation between environments | Use `.env` file with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` (already partially done) — ensure `.env` is in `.gitignore` |
| MLflow tracking URI and artifact credentials stored in Airflow connections as plaintext | Credentials visible in Airflow UI to any user with connection-view permission | Use Airflow's encrypted connection store; set `AIRFLOW__CORE__FERNET_KEY` for at-rest encryption |
| Prometheus `/metrics` endpoint exposed without authentication | Internal ML metrics (fraud rates, model version, feature distributions) visible to anyone with network access | For local dev this is acceptable; add a note in `findings.md` that production would require auth proxy |
| `docker-compose.yml` exposes Postgres on `0.0.0.0:5432` | Any local network host can connect to the MLflow database | For portfolio/local use this is acceptable; document that production would use internal networking only |

---

## "Looks Done But Isn't" Checklist

- [ ] **MLflow model serving:** The server starts and returns HTTP 200 — but verify that the `/invocations` endpoint accepts the actual feature schema (not just a health check ping) and returns a fraud score, not an error about missing columns.
- [ ] **Canary deployment:** Traffic split is configured — but verify that rollback actually fires by intentionally deploying a degraded model (e.g., a randomly initialized one) and confirming the DAG promotes the champion back.
- [ ] **Retraining DAG:** The DAG runs without error — but verify it produces a new MLflow run, that run's F1 is evaluated, and the champion alias is updated in the registry (not just that the run completes).
- [ ] **Airflow connections:** Connections are created in the Airflow UI — but verify each connection with `airflow connections test <conn_id>` from inside the scheduler container.
- [ ] **Prometheus scrape targets:** Prometheus is running — but check the `/targets` page and confirm each target shows `UP`, not `DOWN` or `UNKNOWN`.
- [ ] **Grafana dashboard:** Panels display data — but verify each panel still shows data after a Docker Compose restart (confirming Grafana datasource survives restarts and isn't relying on ephemeral in-memory state).
- [ ] **Data quality checks in retraining DAG:** Quality check task runs — but verify it actually rejects a corrupt dataset by injecting a test batch with 0% fraud rate and confirming the DAG halts before retraining.
- [ ] **Monitoring DAG F1 check:** The daily F1 check task runs — but verify it actually reads the latest scoring data, not the cached result from the initial test set that never changes.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Training-serving skew discovered after serving | MEDIUM | Wrap model + preprocessing into `mlflow.pyfunc`, re-log to registry as a new version, re-deploy |
| MLflow version mismatch crashes served model | LOW | Pin `mlflow==2.12.2` in host venv, recreate venv, restart serve command |
| Non-idempotent DAG created duplicate training data | MEDIUM | Delete duplicate Parquet partitions, delete spurious MLflow runs via UI, re-trigger DAG with corrected idempotency logic |
| Prometheus scraping nothing after setup | LOW | Fix service names in `prometheus.yml`, `docker compose restart prometheus`, verify `/targets` |
| Canary rollback never fires | MEDIUM | Replace absolute F1 threshold with relative comparison, add synthetic degraded-model test to DAG smoke test suite |
| Airflow cannot reach MLflow/Kafka | LOW | Update connection URIs to use Docker service names, restart Airflow scheduler |
| Grafana shows no data after restart | LOW | Verify Grafana datasource is provisioned via `provisioning/datasources/` directory, not manual UI config (manual config is lost on restart) |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Training-serving skew (Pitfall 1) | Phase 6 — Local Model Serving | Send same transaction to both `FraudScorer.score()` and REST endpoint; scores must match within 0.001 |
| MLflow version mismatch (Pitfall 2) | Phase 6 — Local Model Serving | Run `mlflow --version` in host venv; must equal 2.12.2 |
| Airflow DAG import side effects (Pitfall 3) | Phase 7 — Airflow Setup | Run `time airflow dags list`; must complete in under 3 seconds |
| Non-idempotent retraining DAG (Pitfall 4) | Phase 7 — Retraining DAG | Trigger DAG twice for same execution date; MLflow shows exactly one new run, not two |
| Canary rollback never triggers (Pitfall 5) | Phase 7 — Canary + Rollback | Deploy a zero-accuracy dummy model as challenger; rollback DAG must promote champion back within one evaluation cycle |
| Prometheus target unreachable (Pitfall 6) | Phase 8 — Prometheus Setup | All targets show `UP` on `/targets` page within 60 seconds of stack start |
| Dashboard built before metrics emitted (Pitfall 7) | Phase 8 — Instrumentation first | `curl <app>:<port>/metrics` returns Prometheus-format output before any Grafana panel is created |
| F1 threshold miscalibrated (Pitfall 8) | Phase 7 — Monitoring DAG | Simulate 5% relative F1 drop; retraining DAG must trigger |
| Airflow network isolation (Pitfall 9) | Phase 7 — Airflow Docker Setup | `docker exec airflow-scheduler curl http://mlflow:5000/health` returns `{"status": "ok"}` |

---

## Sources

- Project codebase analysis: `/Users/fazlikoc/Desktop/realtime_fraud_detection/src/serving/model_scorer.py`, `docker-compose.yml`, `findings.md`
- Known project decisions: MLflow 2.12.2 server pin, MinIO as artifact store, LightGBM champion model, hybrid retraining strategy, canary rollback via traffic splitting
- MLOps deployment patterns: MLflow pyfunc model format for preprocessing bundling (HIGH confidence — core MLflow design pattern)
- Airflow DAG authoring best practices: idempotency, import-time side effects, executor selection (HIGH confidence — documented in Airflow official best practices)
- Prometheus + Docker Compose networking: service name resolution vs localhost (HIGH confidence — fundamental Docker networking behavior)
- Grafana provisioning: datasource persistence via provisioning files vs manual UI config (MEDIUM confidence — Grafana provisioning directory behavior)
- Canary evaluation: champion vs challenger comparison on recent data (HIGH confidence — standard A/B testing / canary evaluation pattern)
- F1 threshold calibration: relative vs absolute thresholds for anomaly detection (MEDIUM confidence — common MLOps operational wisdom)

---
*Pitfalls research for: MLOps deployment, Airflow orchestration, Grafana/Prometheus monitoring on fraud detection pipeline*
*Researched: 2026-03-21*

