# Phase 6: Model Serving - Context

**Gathered:** 2026-03-22
**Status:** Ready for planning

<domain>
## Phase Boundary

The LightGBM champion model is queryable via a REST endpoint that applies the same preprocessing as training, and the serving container is integrated into Docker Compose. Requirements: SERV-01, SERV-02, SERV-03, SERV-04, SERV-05.

</domain>

<decisions>
## Implementation Decisions

### Pyfunc wrapper design
- **D-01:** Create a custom `mlflow.pyfunc.PythonModel` subclass that bundles LightGBM model + scaler.joblib + label_encoders.joblib + feature_names.joblib as a single MLflow artifact
- **D-02:** `predict()` returns two columns: `fraud_score` (float 0.0–1.0) and `fraud_prediction` (int 0/1)
- **D-03:** Fraud threshold is configurable via `FRAUD_THRESHOLD` environment variable (default 0.5), read at model load time
- **D-04:** Re-register under the same model name (`fraud-detection-model`) and move `@champion` alias to the new pyfunc version. Old LightGBM-flavor version stays in registry history

### Serving container configuration
- **D-05:** Reuse existing `Dockerfile.mlflow` base image (`ghcr.io/mlflow/mlflow:v2.12.2`) with added inference dependencies (lightgbm, scikit-learn)
- **D-06:** Gunicorn workers configurable via `SERVING_WORKERS` environment variable (default 2)
- **D-07:** Hybrid startup strategy: `depends_on` with MLflow health check in Docker Compose + retry loop with exponential backoff for model loading inside the container
- **D-08:** Docker Compose service named `fraud-api` exposed on host port 5002

### Request/response format
- **D-09:** `/invocations` accepts raw transaction fields (amount, merchant_category, card_type, latitude, longitude, timestamp, etc.) — the pyfunc handles all feature engineering internally, no preprocessing responsibility on the caller

### Claude's Discretion
- How to handle prior-transaction fields (prev_latitude, prev_longitude, prev_timestamp) — optional with zero fallback, or required
- Exact response JSON structure (column-oriented vs record-oriented)
- Error response format for malformed requests
- Whether `/health` is a custom endpoint or the built-in MLflow health check
- Conda/pip environment spec for the pyfunc model
- Feature engineering logic placement (inline in pyfunc vs importing from existing modules)

</decisions>

<specifics>
## Specific Ideas

- Pyfunc wrapper should mirror the existing `FraudScorer` class logic in `src/serving/model_scorer.py` — same preprocessing steps, same feature order, same fallback for unknown categories
- The retry-with-backoff pattern should follow the existing Kafka producer pattern in `src/data_generator/kafka_producer.py` (up to 5 retries with increasing wait)
- Configurable workers is an interview talking point: "Why configurable?" → production scaling, resource constraints vary per environment

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Model serving
- `.planning/REQUIREMENTS.md` — SERV-01 through SERV-05: serving endpoint, health check, preprocessing skew, champion alias, Docker Compose integration
- `.planning/ROADMAP.md` §Phase 6 — Success criteria: health check 200, invocations returns score, skew < 0.001, champion alias loading, compose integration

### Existing preprocessing pipeline
- `src/serving/model_scorer.py` — `FraudScorer` class with `preprocess()` and `score()` methods; defines FEATURE_COLUMNS, CATEGORICAL_COLUMNS, and fallback logic for unknown categories. The pyfunc wrapper must replicate this logic
- `src/training/train_model.py` — `register_best_model()` function shows current registration flow (model name, champion alias). Lines 416-447

### Infrastructure
- `docker-compose.yml` — Existing service definitions; new `fraud-api` service must integrate here
- `Dockerfile.mlflow` — Base image to extend for serving
- `src/config.py` — Centralized config; MLFLOW_TRACKING_URI and other env vars

### Artifacts
- `data/artifacts/scaler.joblib` — Fitted StandardScaler
- `data/artifacts/label_encoders.joblib` — Dict of fitted LabelEncoders per categorical column
- `data/artifacts/feature_names.joblib` — Ordered list of feature names (FEATURE_COLUMNS + CATEGORICAL_COLUMNS)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `FraudScorer` class (`src/serving/model_scorer.py`): Contains the exact preprocessing logic (categorical encoding with unknown fallback, feature selection, scaling) that the pyfunc `predict()` must replicate
- `prepare_scoring_artifacts()` (`src/serving/model_scorer.py`): Already creates the joblib artifacts from training data — these are the artifacts to bundle into the pyfunc
- `_create_producer()` retry pattern (`src/data_generator/kafka_producer.py`): Template for the model-loading retry loop with exponential backoff

### Established Patterns
- MLflow tracking URI at `http://localhost:5001` (host) / `http://mlflow:5000` (container)
- MinIO S3 endpoint at `http://minio:9000` for artifact storage
- Environment variables centralized in `src/config.py` with `.env` file loading
- Docker Compose health checks on all services (postgres, minio, kafka, mlflow)
- Model registered as `fraud-detection-model` with `@champion` alias via `client.set_registered_model_alias()`

### Integration Points
- New `fraud-api` service connects to: MLflow tracking server (model download), MinIO (artifact storage), Docker network (shared with existing services)
- Port 5002 must not conflict with existing ports: 5001 (MLflow), 9000/9001 (MinIO), 5432 (PostgreSQL), 9092 (Kafka), 8080 (Spark), 2181 (Zookeeper), 8085 (Schema Registry)
- The pyfunc re-registration script should be runnable via Makefile target (e.g., `make register-pyfunc`)

</code_context>

<deferred>
## Deferred Ideas

- Load testing of the serving endpoint — v2 requirement (LOAD-01, LOAD-02)
- GCP Vertex AI deployment — v2 requirement (CLOD-01 through CLOD-04)
- A/B testing via traffic splitting — Phase 7 canary deploy handles basic version comparison

</deferred>

---

*Phase: 06-model-serving*
*Context gathered: 2026-03-22*
