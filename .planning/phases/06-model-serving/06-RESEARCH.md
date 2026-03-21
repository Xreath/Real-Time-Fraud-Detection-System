# Phase 6: Model Serving - Research

**Researched:** 2026-03-22
**Domain:** MLflow pyfunc model serving, Docker Compose integration, training-serving consistency
**Confidence:** HIGH

## Summary

Phase 6 wraps the LightGBM champion model and its preprocessing artifacts (scaler, label encoders, feature names) into a single MLflow pyfunc bundle so that `mlflow models serve` can expose it as a REST endpoint. The key engineering problem is training-serving skew: the existing `FraudScorer` class already contains the canonical preprocessing logic; the pyfunc must replicate it exactly using the same joblib artifacts, not re-derive them.

The serving infrastructure uses `mlflow models serve` (which uses Gunicorn/uvicorn under the hood) pointed at `models:/fraud-detection-model@champion`. A new Dockerfile extends `Dockerfile.mlflow` with LightGBM and scikit-learn, and a `fraud-api` service is added to `docker-compose.yml` on port 5002. The hybrid startup strategy (Docker Compose `depends_on` health check + container-level retry loop) mirrors the existing Kafka producer pattern already in the codebase.

The most critical implementation detail: the pyfunc `log_model` call must pass all three joblib files via the `artifacts` dict, and `load_context` must load them — not hard-code paths — so the model bundle is fully self-contained when downloaded from MinIO by the serving container.

**Primary recommendation:** Create `src/serving/register_pyfunc.py` that defines the `FraudPyfunc` class and re-registers it as `fraud-detection-model` with the `@champion` alias pointing to the new pyfunc version. Then build a `Dockerfile.serving` extending `Dockerfile.mlflow`, add the `fraud-api` service to `docker-compose.yml`, and add a `make register-pyfunc` target.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Create a custom `mlflow.pyfunc.PythonModel` subclass that bundles LightGBM model + scaler.joblib + label_encoders.joblib + feature_names.joblib as a single MLflow artifact
- **D-02:** `predict()` returns two columns: `fraud_score` (float 0.0-1.0) and `fraud_prediction` (int 0/1)
- **D-03:** Fraud threshold is configurable via `FRAUD_THRESHOLD` environment variable (default 0.5), read at model load time
- **D-04:** Re-register under the same model name (`fraud-detection-model`) and move `@champion` alias to the new pyfunc version. Old LightGBM-flavor version stays in registry history
- **D-05:** Reuse existing `Dockerfile.mlflow` base image (`ghcr.io/mlflow/mlflow:v2.12.2`) with added inference dependencies (lightgbm, scikit-learn)
- **D-06:** Gunicorn workers configurable via `SERVING_WORKERS` environment variable (default 2)
- **D-07:** Hybrid startup strategy: `depends_on` with MLflow health check in Docker Compose + retry loop with exponential backoff for model loading inside the container
- **D-08:** Docker Compose service named `fraud-api` exposed on host port 5002
- **D-09:** `/invocations` accepts raw transaction fields (amount, merchant_category, card_type, latitude, longitude, timestamp, etc.) — the pyfunc handles all feature engineering internally, no preprocessing responsibility on the caller

### Claude's Discretion
- How to handle prior-transaction fields (prev_latitude, prev_longitude, prev_timestamp) — optional with zero fallback, or required
- Exact response JSON structure (column-oriented vs record-oriented)
- Error response format for malformed requests
- Whether `/health` is a custom endpoint or the built-in MLflow health check
- Conda/pip environment spec for the pyfunc model
- Feature engineering logic placement (inline in pyfunc vs importing from existing modules)

### Deferred Ideas (OUT OF SCOPE)
- Load testing of the serving endpoint — v2 requirement (LOAD-01, LOAD-02)
- GCP Vertex AI deployment — v2 requirement (CLOD-01 through CLOD-04)
- A/B testing via traffic splitting — Phase 7 canary deploy handles basic version comparison
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SERV-01 | Model served via MLflow REST endpoint at `/invocations` accepting JSON transaction payloads | `mlflow models serve --model-uri models:/fraud-detection-model@champion --host 0.0.0.0 --port 5002` exposes `/invocations`; pyfunc predict() handles JSON deserialization automatically |
| SERV-02 | Health check endpoint at `/health` returns 200 when model is loaded and ready | MLflow built-in `/health` endpoint returns 200 when server is up; confirmed via existing `docker-compose.yml` healthcheck pattern on mlflow service |
| SERV-03 | Serving uses same preprocessing artifacts (scaler, label encoders) as training — no training-serving skew | pyfunc `log_model` bundles `data/artifacts/scaler.joblib`, `label_encoders.joblib`, `feature_names.joblib` via `artifacts` dict; `load_context` loads them — identical to `FraudScorer._load()` logic |
| SERV-04 | Serving loads specific model version from MLflow Registry (champion alias), not "latest" | `--model-uri models:/fraud-detection-model@champion` syntax; MLflow resolves alias to pinned version at startup |
| SERV-05 | MLflow serve runs as a Docker Compose service with configurable workers | `fraud-api` service in docker-compose.yml; `mlflow models serve --workers ${SERVING_WORKERS:-2}` in container command |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| mlflow[extras] | 2.12.2 | pyfunc model bundling + REST serving via `mlflow models serve` | Already the project MLflow version; pyfunc is the standard way to bundle custom preprocessing with models |
| lightgbm | 4.0.0+ | LGBMClassifier inference inside pyfunc | Champion model flavor; must match training version |
| scikit-learn | 1.4.0+ | StandardScaler + LabelEncoder deserialization from joblib | Preprocessing artifacts are sklearn objects |
| joblib | 1.3.0+ | Load scaler.joblib, label_encoders.joblib, feature_names.joblib inside pyfunc | Already used in FraudScorer; matches serialization format |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pandas | 2.2.0+ | DataFrame input/output in pyfunc predict() | MLflow pyfunc passes DataFrame input by default |
| numpy | 1.26.0+ | Array operations in preprocessing | Used inside preprocess() pipeline |
| boto3 | 1.34.0+ | MinIO artifact download when serving container loads model | Required because artifacts are in MinIO (S3-compatible) |
| psycopg2-binary | latest | MLflow tracking server PostgreSQL backend | Already in Dockerfile.mlflow |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `mlflow models serve` (built-in REST) | FastAPI custom server | Built-in avoids boilerplate; custom gives more control over endpoints but is hand-rolling what MLflow already provides |
| pyfunc with bundled artifacts | Separate artifact volume mount | Bundled is self-contained and portable; volume mount creates deployment dependency |
| `--env-manager local` | `--env-manager virtualenv` | Local uses container's existing env (correct for Docker); virtualenv creates a nested venv inside the container (redundant overhead) |

**Installation (Dockerfile.serving):**
```dockerfile
FROM ghcr.io/mlflow/mlflow:v2.12.2
RUN pip install --no-cache-dir psycopg2-binary boto3 lightgbm scikit-learn
```

**Version verification:** Confirmed via project CLAUDE.md: LightGBM 4.0.0+, scikit-learn 1.4.0+, joblib 1.3.0+, MLflow 2.12.2 (pinned in Dockerfile.mlflow).

## Architecture Patterns

### Recommended Project Structure
```
src/serving/
├── model_scorer.py          # Existing FraudScorer (unchanged)
└── register_pyfunc.py       # NEW: FraudPyfunc class + registration script

Dockerfile.serving           # NEW: extends Dockerfile.mlflow + lgbm + sklearn
docker-compose.yml           # MODIFIED: add fraud-api service
Makefile                     # MODIFIED: add register-pyfunc target
```

### Pattern 1: MLflow pyfunc PythonModel with Bundled Artifacts

**What:** Define a class that subclasses `mlflow.pyfunc.PythonModel`, implement `load_context` to load the three joblib artifacts + the LightGBM model from MLflow, and implement `predict` to replicate `FraudScorer.preprocess()` + `FraudScorer.score()`.

**When to use:** Any time serving requires custom preprocessing that the native model flavor (sklearn/lightgbm) does not perform automatically.

**Example:**
```python
# Source: https://mlflow.org/docs/latest/ml/model/python_model/
import mlflow
import mlflow.pyfunc
import joblib
import pandas as pd
import numpy as np
import os

CATEGORICAL_COLUMNS = ["merchant_category", "card_type", "country"]
FEATURE_COLUMNS = [
    "amount", "latitude", "longitude", "is_weekend", "is_night",
    "is_foreign", "hour_of_day", "day_of_week", "amount_log",
    "is_high_amount", "is_round_amount", "distance_km",
    "time_diff_hours", "speed_kmh",
]

class FraudPyfunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        import mlflow.lightgbm
        self.scaler = joblib.load(context.artifacts["scaler"])
        self.label_encoders = joblib.load(context.artifacts["label_encoders"])
        self.feature_names = joblib.load(context.artifacts["feature_names"])
        self.threshold = float(os.getenv("FRAUD_THRESHOLD", "0.5"))
        # Load the underlying LightGBM run artifact
        lgbm_uri = context.artifacts["lgbm_model"]
        self.model = mlflow.sklearn.load_model(lgbm_uri)

    def predict(self, context, model_input: pd.DataFrame, params=None):
        df = model_input.copy()
        # Categorical encoding with unknown fallback (mirrors FraudScorer)
        for col in CATEGORICAL_COLUMNS:
            if col in df.columns:
                le = self.label_encoders[col]
                df[col] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else 0
                )
        # Prior-transaction fields: optional with zero fallback
        for col in ["prev_latitude", "prev_longitude", "prev_timestamp"]:
            if col not in df.columns:
                df[col] = 0.0
        X = df[self.feature_names].fillna(0).values
        X = self.scaler.transform(X)
        probs = self.model.predict_proba(X)[:, 1]
        return pd.DataFrame({
            "fraud_score": probs.astype(float),
            "fraud_prediction": (probs >= self.threshold).astype(int),
        })
```

**Registration call:**
```python
# Source: https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html
with mlflow.start_run(run_name="fraud-pyfunc-registration"):
    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=FraudPyfunc(),
        artifacts={
            "scaler": "data/artifacts/scaler.joblib",
            "label_encoders": "data/artifacts/label_encoders.joblib",
            "feature_names": "data/artifacts/feature_names.joblib",
            "lgbm_model": f"models:/fraud-detection-model/{champion_version}",
        },
        pip_requirements=[
            "mlflow==2.12.2",
            "lightgbm>=4.0.0",
            "scikit-learn>=1.4.0",
            "joblib>=1.3.0",
            "pandas>=2.2.0",
            "numpy>=1.26.0",
            "boto3>=1.34.0",
        ],
        registered_model_name="fraud-detection-model",
    )
```

**Move champion alias after registration:**
```python
client = mlflow.tracking.MlflowClient()
client.set_registered_model_alias(
    name="fraud-detection-model",
    alias="champion",
    version=new_version,
)
```

### Pattern 2: `mlflow models serve` CLI in Docker Container

**What:** The container entrypoint runs `mlflow models serve` with the champion alias URI, binding to all interfaces on the internal port.

**When to use:** Standard MLflow REST serving — provides `/invocations`, `/health`, `/ping`, `/version` endpoints automatically.

```dockerfile
# Dockerfile.serving
FROM ghcr.io/mlflow/mlflow:v2.12.2
RUN pip install --no-cache-dir psycopg2-binary boto3 lightgbm scikit-learn
# entrypoint is mlflow (already set in base image)
```

```yaml
# docker-compose.yml fraud-api service
fraud-api:
  build:
    context: .
    dockerfile: Dockerfile.serving
  container_name: fraud-api
  depends_on:
    mlflow:
      condition: service_healthy
  ports:
    - "5002:5002"
  environment:
    MLFLOW_TRACKING_URI: http://mlflow:5000
    MLFLOW_S3_ENDPOINT_URL: http://minio:9000
    AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-minioadmin}
    AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-minioadmin}
    FRAUD_THRESHOLD: ${FRAUD_THRESHOLD:-0.5}
    SERVING_WORKERS: ${SERVING_WORKERS:-2}
  command: >
    mlflow models serve
    --model-uri models:/fraud-detection-model@champion
    --host 0.0.0.0
    --port 5002
    --workers ${SERVING_WORKERS:-2}
    --env-manager local
    --no-conda
  healthcheck:
    test: curl -f http://localhost:5002/health || exit 1
    interval: 15s
    timeout: 10s
    retries: 10
    start_period: 60s
```

**Key flags:**
- `--env-manager local` — Use container's pre-installed environment; avoids virtualenv creation inside container
- `--no-conda` — Skip conda; required because container has no conda
- `--workers 2` — Gunicorn worker count (the `--workers` flag confirmed in MLflow CLI docs)
- `start_period: 60s` — Model download from MinIO takes 30-60 seconds on first startup

### Pattern 3: Startup Retry Loop with Exponential Backoff

**What:** Because `mlflow models serve` must download the model from MinIO before it can serve, add a wrapper script that retries the health check before signaling ready. The `depends_on` health check ensures MLflow tracking server is up; the retry loop handles artifact download latency.

**When to use:** Any container that downloads a model artifact from a remote store at startup.

**Example (entrypoint.sh):**
```bash
#!/bin/bash
set -e
MAX_RETRIES=5
WAIT=5
for i in $(seq 1 $MAX_RETRIES); do
    echo "Attempt $i/$MAX_RETRIES: Starting mlflow models serve..."
    mlflow models serve \
        --model-uri "models:/fraud-detection-model@champion" \
        --host 0.0.0.0 \
        --port 5002 \
        --workers "${SERVING_WORKERS:-2}" \
        --env-manager local \
        --no-conda && break
    echo "Failed. Waiting ${WAIT}s..."
    sleep $WAIT
    WAIT=$((WAIT * 2))
done
```

This mirrors the `_create_producer()` retry pattern in `src/data_generator/kafka_producer.py` (up to 5 retries with increasing wait).

### Pattern 4: MLflow Invocations Request Format

**What:** MLflow pyfunc REST endpoint accepts two JSON formats for `/invocations`:

Format 1 (dataframe_split — recommended for column clarity):
```json
{
  "dataframe_split": {
    "columns": ["amount", "merchant_category", "card_type", "latitude", "longitude", "timestamp"],
    "data": [[150.75, "grocery", "visa", 41.01, 28.97, "2024-01-15T14:30:00"]]
  }
}
```

Format 2 (dataframe_records — simpler for single transactions):
```json
{
  "dataframe_records": [
    {"amount": 150.75, "merchant_category": "grocery", "card_type": "visa",
     "latitude": 41.01, "longitude": 28.97, "timestamp": "2024-01-15T14:30:00"}
  ]
}
```

**Response format (column-oriented, default MLflow pyfunc):**
```json
{
  "predictions": [
    {"fraud_score": 0.023, "fraud_prediction": 0}
  ]
}
```

### Anti-Patterns to Avoid
- **Using `--env-manager virtualenv` inside Docker:** Creates a nested venv, doubles startup time, wastes space. Use `--env-manager local` inside Docker containers.
- **Hard-coding artifact paths inside pyfunc predict():** Artifacts must be accessed via `context.artifacts["key"]` in `load_context`, not via filesystem paths. The model bundle must be self-contained.
- **Registering with the LightGBM native flavor for serving:** The native LightGBM flavor lacks the preprocessing pipeline. Raw transaction JSON cannot be fed to a bare LightGBM model.
- **Re-fitting scalers or encoders inside the pyfunc:** Must load from the same fitted joblib artifacts as training. Re-fitting in serving creates training-serving skew.
- **Using `models:/fraud-detection-model/latest` as model URI:** "latest" is a numeric alias that changes when new versions are registered. Always use the `@champion` alias to pin to the production version.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| REST endpoint for model predictions | Custom Flask/FastAPI server | `mlflow models serve` | MLflow built-in provides `/invocations`, `/health`, `/ping`, `/version` — zero boilerplate, correct content-type handling, Gunicorn workers |
| JSON request deserialization | Custom parsing in predict() | MLflow pyfunc DataFrame conversion | MLflow automatically converts `dataframe_split`/`dataframe_records` JSON to pandas DataFrame before calling predict() |
| Docker health checking | Custom health polling script | Docker Compose `healthcheck` with `curl -f http://localhost:5002/health` | The built-in `/health` endpoint returns 200 only when the model is loaded; no custom implementation needed |
| Model version pinning | Store version number in config | MLflow `@champion` alias | Alias resolves to pinned version at startup; changing champion requires only alias reassignment in MLflow Registry |

**Key insight:** The entire REST serving layer is provided by `mlflow models serve`. The only custom code is the `FraudPyfunc` class (preprocessing bundling) and the Docker/Compose configuration.

## Common Pitfalls

### Pitfall 1: pyfunc artifact URI for bundled LightGBM model
**What goes wrong:** When calling `mlflow.pyfunc.log_model(artifacts={"lgbm_model": ...})`, you cannot pass a `models:/...` URI directly as an artifact URI — MLflow resolves artifact URIs to local file paths, and registry URIs require downloading first.
**Why it happens:** The `artifacts` dict in `log_model` expects local filesystem paths or `runs:/` URIs, not registry aliases.
**How to avoid:** Before the pyfunc registration call, resolve the champion version number using `client.get_model_version_by_alias("fraud-detection-model", "champion")`, then download the model to a temp directory and pass that path, OR pass the `runs:/` URI from the original training run.
**Warning signs:** `MlflowException: Unable to resolve artifact URI` during `log_model`.

### Pitfall 2: MinIO S3 endpoint not set inside the serving container
**What goes wrong:** The serving container calls MLflow to download model artifacts, but fails with S3 connection errors because `MLFLOW_S3_ENDPOINT_URL` defaults to AWS S3 (not MinIO).
**Why it happens:** boto3 uses `MLFLOW_S3_ENDPOINT_URL` to route S3 requests; without it, requests go to real AWS endpoints.
**How to avoid:** Set `MLFLOW_S3_ENDPOINT_URL: http://minio:9000` in the `fraud-api` environment block in docker-compose.yml. The existing `mlflow` service already demonstrates this pattern.
**Warning signs:** `botocore.exceptions.EndpointConnectionError` or `Connection refused` when serving container starts.

### Pitfall 3: Feature column order mismatch between pyfunc and training
**What goes wrong:** Predictions differ between `FraudScorer.score()` and the REST endpoint by more than 0.001 (violates SERV-03 success criterion).
**Why it happens:** If the pyfunc assembles features in a different order than the training scaler was fitted on, scaled values will be wrong even with correct raw values.
**How to avoid:** Use the loaded `feature_names` artifact (from `feature_names.joblib`) to select and order columns: `df[self.feature_names].fillna(0).values` — same as `FraudScorer.preprocess()`.
**Warning signs:** Skew > 0.001 in the smoke test comparing `FraudScorer.score()` vs `/invocations` response.

### Pitfall 4: Docker Compose `depends_on` does not wait for model to load
**What goes wrong:** `fraud-api` passes the `depends_on: mlflow: condition: service_healthy` check, but `/invocations` returns 503 because the model is still downloading.
**Why it happens:** MLflow service_healthy means the tracking server is up, not that the serving container has finished downloading and loading the model.
**How to avoid:** Set `start_period: 60s` and `retries: 10` on the `fraud-api` healthcheck so Docker waits through the model download. Use the retry wrapper script as the container entrypoint for robustness.
**Warning signs:** `curl http://localhost:5002/health` returns 200 but `/invocations` returns 503 immediately after `docker compose up`.

### Pitfall 5: predict() signature change in MLflow 2.12 vs 2.20+
**What goes wrong:** In MLflow >= 2.20.0 the `context` parameter can be omitted from `predict()`. In MLflow 2.12.2 (the project version), `predict(self, context, model_input, params=None)` is the required signature.
**Why it happens:** API evolution — the newer signature without context is not backported.
**How to avoid:** Keep the full `predict(self, context, model_input, params=None)` signature. The `context` parameter in `predict` is different from `load_context`'s context — in `predict` it is rarely used; in `load_context` it provides `context.artifacts`.
**Warning signs:** `TypeError: predict() missing required argument: 'context'` when running `mlflow models serve`.

### Pitfall 6: `--workers` flag behavior with model startup
**What goes wrong:** With `--workers 2`, each Gunicorn worker process loads the model independently at startup. This doubles memory usage and doubles download time.
**Why it happens:** Gunicorn forks after initialization; each worker gets its own model copy.
**How to avoid:** This is expected behavior and acceptable. Default of 2 workers is correct for the project. Document this as an interview talking point: "Why 2 workers? — balance between memory (each worker loads the model) and concurrency."
**Warning signs:** Container OOM if `SERVING_WORKERS` is set too high.

## Code Examples

Verified patterns from official sources:

### PythonModel load_context pattern (verified against MLflow 2.12 API)
```python
# Source: https://mlflow.org/docs/latest/ml/model/python_model/
class FraudPyfunc(mlflow.pyfunc.PythonModel):
    def load_context(self, context):
        # context.artifacts["key"] returns the local filesystem path
        # to the artifact that was passed during log_model()
        self.scaler = joblib.load(context.artifacts["scaler"])
        self.label_encoders = joblib.load(context.artifacts["label_encoders"])
        self.feature_names = joblib.load(context.artifacts["feature_names"])
        self.threshold = float(os.getenv("FRAUD_THRESHOLD", "0.5"))

    def predict(self, context, model_input: pd.DataFrame, params=None):
        # model_input is a pd.DataFrame when called from /invocations
        # (MLflow deserializes JSON automatically)
        ...
        return pd.DataFrame({"fraud_score": ..., "fraud_prediction": ...})
```

### log_model with local artifact paths
```python
# Source: https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html
mlflow.pyfunc.log_model(
    artifact_path="model",
    python_model=FraudPyfunc(),
    artifacts={
        "scaler": "data/artifacts/scaler.joblib",        # local path
        "label_encoders": "data/artifacts/label_encoders.joblib",
        "feature_names": "data/artifacts/feature_names.joblib",
        "lgbm_model": lgbm_local_path,                   # downloaded from registry
    },
    pip_requirements=[...],
    registered_model_name="fraud-detection-model",
)
```

### Resolving champion version before bundling
```python
client = mlflow.tracking.MlflowClient()
mv = client.get_model_version_by_alias("fraud-detection-model", "champion")
champion_run_id = mv.run_id
# Download to temp dir for artifact bundling
import tempfile
with tempfile.TemporaryDirectory() as tmpdir:
    lgbm_local_path = mlflow.sklearn.load_model(
        f"runs:/{champion_run_id}/model",
        dst_path=tmpdir
    )
    # or use mlflow.artifacts.download_artifacts(...)
```

### curl smoke test commands
```bash
# Health check (SERV-02)
curl http://localhost:5002/health

# Single transaction score (SERV-01)
curl -X POST http://localhost:5002/invocations \
  -H "Content-Type: application/json" \
  -d '{
    "dataframe_records": [{
      "amount": 150.75,
      "merchant_category": "grocery",
      "card_type": "visa",
      "latitude": 41.01,
      "longitude": 28.97,
      "is_weekend": 0,
      "is_night": 0,
      "is_foreign": 0,
      "hour_of_day": 14,
      "day_of_week": 1,
      "amount_log": 5.02,
      "is_high_amount": 0,
      "is_round_amount": 0,
      "distance_km": 0.0,
      "time_diff_hours": 0.0,
      "speed_kmh": 0.0,
      "country": "TR"
    }]
  }'
```

### Skew validation script
```python
# Compare FraudScorer.score() vs REST endpoint for same transaction
import requests, pandas as pd
from src.serving.model_scorer import FraudScorer

scorer = FraudScorer(model_name="fraud-detection-model", model_version="1")
sample = pd.read_parquet("data/splits/test.parquet").iloc[:5]
local_scores = scorer.score(sample)["fraud_score"].values

payload = {"dataframe_records": sample.to_dict("records")}
resp = requests.post("http://localhost:5002/invocations", json=payload)
rest_scores = [p["fraud_score"] for p in resp.json()["predictions"]]

for i, (local, rest) in enumerate(zip(local_scores, rest_scores)):
    skew = abs(local - rest)
    assert skew < 0.001, f"Row {i}: skew={skew:.6f} exceeds 0.001"
print("Skew check PASSED: all scores within 0.001")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MLflow stage aliases (Production/Staging) | Named aliases (@champion, @challenger) | MLflow 2.x | `transition_model_version_stage` is deprecated; use `set_registered_model_alias` |
| `mlflow.pyfunc.log_model(artifact_path=...)` | `mlflow.pyfunc.log_model(name=...)` | MLflow 2.18+ | The `name` parameter was added; `artifact_path` still works in 2.12.2 |
| context parameter required in predict() | context optional in predict() | MLflow 2.20+ | Irrelevant for 2.12.2 — keep full signature |

**Deprecated/outdated:**
- `mlflow.pyfunc.log_model` with `conda_env` dict: Still works but pip_requirements list is simpler and sufficient for Docker deployments where the environment is pre-built.
- `mlflow.register_model` + `transition_model_version_stage("Production")`: The stage system is deprecated in favor of aliases. The project already uses aliases correctly.

## Open Questions

1. **Bundling the LightGBM model inside the pyfunc artifacts dict**
   - What we know: `log_model(artifacts=...)` accepts local filesystem paths; `models:/` URIs may not resolve directly.
   - What's unclear: Whether `mlflow.artifacts.download_artifacts(f"models:/fraud-detection-model@champion")` can be used as a local path directly in the artifacts dict, or if a temp directory download is required.
   - Recommendation: In `register_pyfunc.py`, download the champion model to a temp dir first using `mlflow.sklearn.load_model()` with `dst_path`, then pass that local path. Add a comment explaining why.

2. **Prior-transaction fields (Claude's Discretion)**
   - What we know: `FraudScorer` requires `prev_latitude`, `prev_longitude`, `prev_timestamp` for `distance_km`, `time_diff_hours`, `speed_kmh` computation, but those are derived features already in the parquet splits.
   - What's unclear: CONTEXT.md says D-09 accepts "raw transaction fields" — does this mean the derived velocity features are pre-computed by the caller, or that the pyfunc must compute them from prev_* fields?
   - Recommendation: Accept derived features (`distance_km`, `time_diff_hours`, `speed_kmh`) as optional inputs with zero fallback, same as `FraudScorer`. Document this in the API contract.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (not yet configured — Wave 0 gap) |
| Config file | None detected — see Wave 0 |
| Quick run command | `pytest tests/test_pyfunc.py -x -q` |
| Full suite command | `pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SERV-01 | `/invocations` returns fraud_score and fraud_prediction for valid JSON | integration | `pytest tests/test_serving.py::test_invocations -x` | Wave 0 |
| SERV-02 | `/health` returns HTTP 200 when container is running | smoke | `pytest tests/test_serving.py::test_health_check -x` | Wave 0 |
| SERV-03 | Score from REST vs FraudScorer.score() within 0.001 | integration | `pytest tests/test_serving.py::test_no_skew -x` | Wave 0 |
| SERV-04 | Serving loads `@champion` alias specifically | unit | `pytest tests/test_pyfunc.py::test_champion_alias_loaded -x` | Wave 0 |
| SERV-05 | `fraud-api` service starts with `docker compose up` | smoke | `docker compose ps fraud-api` (manual verify) | N/A — manual |

### Sampling Rate
- **Per task commit:** `pytest tests/test_pyfunc.py -x -q` (unit tests, no running container needed)
- **Per wave merge:** `pytest tests/ -q` (full suite including integration tests requiring running fraud-api)
- **Phase gate:** Full suite green + manual curl smoke test before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_pyfunc.py` — unit tests for FraudPyfunc class (no server needed): preprocessing logic, threshold env var, feature column order
- [ ] `tests/test_serving.py` — integration tests requiring running `fraud-api` container: /health, /invocations, skew check
- [ ] `tests/conftest.py` — shared fixtures (sample transaction DataFrame, expected score ranges)
- [ ] Framework install: `uv pip install pytest pytest-requests` if not already in requirements.txt

## Sources

### Primary (HIGH confidence)
- https://mlflow.org/docs/latest/ml/model/python_model/ — PythonModel API: load_context, predict signature, artifacts access pattern
- https://mlflow.org/docs/latest/python_api/mlflow.pyfunc.html — log_model full signature with artifacts parameter
- https://mlflow.org/docs/latest/cli.html — `mlflow models serve` CLI flags: --model-uri, --host, --port, --workers, --env-manager, --no-conda
- `src/serving/model_scorer.py` (project codebase) — canonical preprocessing logic to replicate in pyfunc
- `docker-compose.yml` (project codebase) — existing service patterns, port map, health check patterns
- `Dockerfile.mlflow` (project codebase) — base image to extend

### Secondary (MEDIUM confidence)
- https://mlflow.org/blog/custom-pyfunc — Practical pyfunc patterns with joblib artifacts; cross-verified with official API docs
- MLflow WebSearch result (2025): `MLFLOW_MODELS_WORKERS` env var for uvicorn; `--workers` flag for gunicorn — confirmed `--workers` is the correct CLI flag from CLI docs

### Tertiary (LOW confidence)
- None — all critical claims verified against official sources or project codebase

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions from project CLAUDE.md + Dockerfile.mlflow; MLflow 2.12.2 pinned
- Architecture: HIGH — pyfunc pattern from official MLflow docs; Docker Compose patterns from existing project
- Pitfalls: HIGH — most from direct code analysis of existing FraudScorer + MLflow API; one (artifact URI format) from MLflow exception behavior knowledge
- Validation: MEDIUM — test framework (pytest) assumed; no existing test infrastructure found in project

**Research date:** 2026-03-22
**Valid until:** 2026-04-22 (30 days — MLflow 2.12.2 is pinned, so API is stable)
