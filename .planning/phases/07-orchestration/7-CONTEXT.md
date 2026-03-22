# Phase 7: Orchestration - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Airflow runs in Docker Compose with validated connectivity to all services, executes a weekly retraining DAG with data quality gates and champion comparison, triggers retraining on F1 degradation, and deploys new models via canary with automatic rollback. Requirements: AFLO-01, AFLO-02, AFLO-03, AFLO-04, RETR-01, RETR-02, RETR-03, RETR-04, RETR-05, RETR-06, CNRY-01, CNRY-02, CNRY-03, CNRY-04.

</domain>

<decisions>
## Implementation Decisions

### Retraining data strategy
- **D-01:** Each retraining run generates fresh synthetic data with a new seed (different seed per run) to fully exercise the pipeline end-to-end
- **D-02:** Dataset size is configurable via an Airflow Variable, defaulting to 20K-50K transactions for faster local iteration
- **D-03:** The retraining DAG handles the full pipeline: generate data → Spark feature engineering → stratified split → train models → compare → promote. Fully self-contained, no dependency on pre-existing data files
- **D-04:** The monitoring DAG evaluates model F1 against a separately generated monitoring validation set (not the training test set) to trigger the retraining signal

### Canary deploy architecture
- **D-05:** Simulated canary via batch validation — after training, the DAG scores a held-out validation batch with both champion and challenger models using `mlflow.pyfunc.load_model()`, compares metrics, and promotes only if the challenger wins. No actual traffic split or second container
- **D-06:** No real-time observation window — evaluation happens immediately on a static validation set. Document that production would use time-based traffic splitting with an observation window
- **D-07:** Rollback is defined as reverting the `@champion` alias to the previous stable version in MLflow Model Registry. Since the challenger is never actually deployed to `fraud-api`, rollback means "don't promote"
- **D-08:** F1 is the primary promotion/rollback gate (per CNRY-02: challenger F1 must be >= champion F1 * 0.95). Precision, recall, and AUC-PR are also logged for comprehensive comparison records

### Model deployment mechanism
- **D-09:** DAG uses Docker Python SDK (`docker` library) via `PythonOperator` to restart the `fraud-api` container after champion promotion. Cleaner than BashOperator with raw docker commands
- **D-10:** Docker socket mounted as `/var/run/docker.sock` into the Airflow container (read-write). macOS-specific socket path documented if needed
- **D-11:** Post-restart verification task hits `/health` or `/invocations` with a test payload to confirm the fraud-api is up and serving the new model
- **D-12:** If restart fails, the DAG task fails and triggers `on_failure_callback` alert for manual intervention. No automatic alias rollback on restart failure — keep it simple

### Alerting strategy
- **D-13:** Dual-channel alerting: Airflow task logs for immediate visibility + structured alert files written to a mounted `alerts/` directory for persistence and auditability
- **D-14:** Alert content is detailed: alert type, timestamp, DAG/task context, relevant metrics (F1, AUC-PR), model versions involved, and links to associated MLflow runs
- **D-15:** Shared alerting utility in `airflow/dags/utils/` module — centralized `on_failure_callback` and alert-writing functions reused across all DAGs (DRY principle)
- **D-16:** Canary rollback alerts include a side-by-side comparison summary of champion vs challenger metrics (F1, precision, recall, AUC-PR) for instant evaluation of why rollback occurred

### Claude's Discretion
- Airflow image version selection (official apache/airflow vs custom build)
- SQLAlchemy version conflict resolution strategy with MLflow 2.12.x
- Exact DAG task graph structure and task naming
- Airflow connection configuration details (conn_id names, connection types)
- Data quality check implementation (custom PythonOperator vs Great Expectations vs simple pandas checks)
- How to generate unique seeds per retraining run (timestamp-based, run_id hash, incrementing counter)
- Alert file format (JSON vs structured text) and naming convention
- Makefile targets for Airflow operations

</decisions>

<specifics>
## Specific Ideas

- The retraining DAG should mirror the existing training pipeline structure: `prepare_data.py` generates + features + splits, `train_model.py` trains + compares + registers. DAG tasks should call these modules or their core functions
- Canary comparison should log results to MLflow as a dedicated "canary-evaluation" run so the comparison is traceable in the MLflow UI
- The alert file approach enables a future `make check-alerts` target and could feed into Phase 8's Grafana dashboard
- Interview talking point: "Why simulated canary?" → Local portfolio project prioritizes demonstrating the decision logic (promote/rollback) over infrastructure complexity. Production would use traffic-based A/B with an observation window

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Airflow setup
- `.planning/REQUIREMENTS.md` — AFLO-01 through AFLO-04: Airflow Docker Compose, connections, separate PostgreSQL, DAG mounting
- `.planning/ROADMAP.md` §Phase 7 — Success criteria: webserver UI at :8080, weekly schedule, data quality gates, champion comparison, canary deploy with rollback

### Retraining pipeline
- `.planning/REQUIREMENTS.md` — RETR-01 through RETR-06: weekly schedule, F1 trigger, data quality checks, champion comparison, promotion, alerting
- `src/training/prepare_data.py` — Full data preparation pipeline (generate → Spark features → split → save). DAG should invoke this pipeline's core functions
- `src/training/train_model.py` — Model training, comparison, and registration pipeline. `register_best_model()` at lines 416-449 handles champion alias promotion
- `src/training/tune_hyperparams.py` — Optuna hyperparameter tuning (may be invoked during retraining)

### Canary deploy
- `.planning/REQUIREMENTS.md` — CNRY-01 through CNRY-04: 10% traffic for 1 hour, F1 threshold rollback, champion preservation, rollback alerting
- `src/serving/register_pyfunc.py` — `FraudPyfunc` class and `register_pyfunc_model()` function. Shows how champion alias is managed and how pyfunc models are registered

### Model serving integration
- `docker-compose.yml` — `fraud-api` service definition (lines 223-254): port 5002, health check config, model URI `models:/fraud-detection-model@champion`, restart policy
- `src/serving/model_scorer.py` — `FraudScorer` class with preprocessing logic; useful reference for validation payload construction

### Infrastructure
- `docker-compose.yml` — Existing services and network. Airflow services must join the same default network. Ports in use: 2181, 5432, 7077, 8080, 8085, 9000, 9001, 9092, 29092, 5001, 5002
- `src/config.py` — Environment variable patterns and defaults (MLflow URI, Kafka broker, etc.)
- `.env` — Environment variables loaded by Docker Compose and Python

### Prior phase context
- `.planning/phases/06-model-serving/6-CONTEXT.md` — Phase 6 decisions: pyfunc wrapper design, Docker Compose integration, health check, champion alias usage

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `prepare_data.py` pipeline functions: `generate_historical_data()`, `compute_features_with_spark()`, `split_data()`, `save_splits()` — DAG tasks can call these directly or wrap them
- `train_model.py` pipeline functions: `load_data()`, `preprocess()`, `get_models()`, `train_and_log_model()`, `register_best_model()` — core training logic reusable from DAG
- `register_pyfunc.py` `register_pyfunc_model()` — re-registers champion as pyfunc; DAG needs to call this after training a new champion
- `FraudScorer.preprocess()` in `model_scorer.py` — reference for constructing validation payloads for post-restart health verification

### Established Patterns
- MLflow tracking URI: `http://mlflow:5000` (container-to-container) / `http://localhost:5001` (host)
- MinIO S3: `http://minio:9000` for artifact storage with `minioadmin/minioadmin` credentials
- Docker Compose health checks on all services with `condition: service_healthy`
- Environment variables centralized in `src/config.py` loaded from `.env`
- Model registered as `fraud-detection-model` with `@champion` alias
- Init containers for one-time setup (kafka-init, minio-init pattern)

### Integration Points
- Airflow webserver on port 8080 — **conflicts with Spark Master Web UI** (also 8080). Must remap one of them
- Airflow needs its own PostgreSQL database (AFLO-03) — add `postgres-airflow` service or use the existing postgres with a separate database
- Airflow containers need access to: MLflow (http://mlflow:5000), MinIO (http://minio:9000), Kafka (kafka:29092), Spark (spark-master:7077), Docker socket
- `fraud-api` container restart via Docker SDK requires container name `fraud-api` to be stable

</code_context>

<deferred>
## Deferred Ideas

- Slack webhook integration for real-time push alerts — could replace file-based alerting in a future iteration
- Great Expectations for data quality checks — more robust than custom pandas checks, but adds dependency complexity
- Airflow REST API for external DAG triggering — useful if Phase 8 monitoring wants to trigger retraining programmatically
- CeleryExecutor or KubernetesExecutor — LocalExecutor is sufficient for single-machine portfolio project
- DAG versioning and migration strategy — not needed for initial implementation

</deferred>

---

*Phase: 07-orchestration*
*Context gathered: 2026-03-22*
