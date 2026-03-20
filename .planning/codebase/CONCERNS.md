# Codebase Concerns

**Analysis Date:** 2026-03-20

## Tech Debt

### 1. Training-Serving Skew in Preprocessing

**Issue:** Different preprocessing logic between training and serving pipelines creates risk of model degradation in production.

**Files:**
- `src/training/train_model.py` (lines 105-150) — Training preprocessing
- `src/serving/model_scorer.py` (lines 164-188) — Serving preprocessing
- `src/training/evaluate.py` (lines 108-120) — Evaluation preprocessing

**Impact:**
- If scaler/encoder artifacts get out of sync, model predictions diverge from training performance
- Unknown categorical values in production default to index 0 (most frequent class) silently
- No validation that preprocessing matches between modules

**Fix approach:**
1. Create single shared preprocessing module `src/preprocessing.py` that both training and serving import from
2. Add preprocessing validation tests comparing train and serve pipeline outputs
3. Version control preprocessing artifacts and add checksums
4. Add logging when unknown categorical values are encountered

---

### 2. Hardcoded Model Version in Scorer

**Issue:** Model version is hardcoded as string "1" in scorer initialization.

**Files:**
- `src/serving/model_scorer.py` (line 129) — `model_version: str = "1"`
- `src/streaming/spark_consumer.py` (line 318) — FraudScorer instantiation without version param

**Impact:**
- When model is updated, scorer still loads v1 instead of latest version
- Manual code change required to use new model versions
- Could cause stale predictions in streaming pipeline for extended periods

**Fix approach:**
1. Change default to `model_version: str = "champion"` (use MLflow alias instead of version number)
2. Add version override via environment variable or config
3. Add model version logging to Spark consumer output
4. Implement model version health check at scorer initialization

---

### 3. Silent Exception Fallback in Streaming Scorer

**Issue:** Broad `except Exception` swallows all errors and returns -1.0 as fraud score without logging.

**Files:**
- `src/streaming/spark_consumer.py` (lines 335-341) — Scoring UDF error handling

**Impact:**
- Preprocessing errors, model prediction errors, or missing artifacts all silently return -1.0
- No visibility into why scoring failed — can't distinguish preprocessing failures from model errors
- Downstream systems interpret -1.0 as "manual review required" but actual error unknown
- Makes debugging production issues extremely difficult

**Fix approach:**
1. Catch specific exceptions separately (preprocessing, model loading, prediction)
2. Log error type, message, and input data context
3. Send error metrics to monitoring system (increment error counter)
4. Return different sentinel values for different failure modes (-1.0 for preprocessing, -2.0 for model)

---

## Known Bugs

### 1. Training-Serving Skew Actually Happened Once

**Status:** Fixed but pattern remains risky

**Description:** In early evaluation phase, `evaluate.py` was creating new scaler/encoder instances instead of loading training artifacts, causing misaligned preprocessing.

**Files:**
- `src/training/evaluate.py` (lines 108-110) — BUG FIX comment documents the issue

**Current mitigation:** Code now loads artifacts from `data/artifacts/` but only at module level, not through shared function

**Why it can happen again:** Different modules re-implement preprocessing logic instead of calling shared function

---

## Security Considerations

### 1. Environment Variables for MLflow S3 Access

**Risk:** MinIO credentials hardcoded as defaults in code.

**Files:**
- `src/serving/model_scorer.py` (lines 152-155)

**Current mitigation:**
```python
os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")
```

**Recommendations:**
1. Remove `setdefault` for credentials — require explicit env var configuration
2. Add validation at startup that credentials are set
3. Use IAM roles in production (GCP, AWS) instead of access keys
4. Add warning if MinIO defaults are detected in non-local environment

### 2. No Input Validation on Kafka Messages

**Risk:** Malformed messages could crash preprocessing pipeline.

**Files:**
- `src/streaming/spark_consumer.py` (lines 140-159) — JSON parsing with schema validation
- `src/serving/model_scorer.py` (lines 178-180) — Unknown categorical handling is silent

**Current state:** Schema validation exists for Kafka messages but handles failures by putting in DLQ, not preventing errors

**Recommendations:**
1. Add range validation on numeric fields (amount > 0, valid latitude/longitude ranges)
2. Add explicit handling for missing required fields before model prediction
3. Add rate limiting/circuit breaker if DLQ queue grows too large
4. Log suspicious patterns (negative amounts, invalid coordinates)

### 3. No Rate Limiting on Kafka Producer

**Risk:** Malicious actor could overwhelm broker with messages.

**Files:**
- `src/data_generator/kafka_producer.py` (lines 113-156) — Producer loop has no rate limit enforcement

**Current state:** Has configurable `tps` (transactions per second) but no enforcement of rate limit

**Recommendations:**
1. Add token bucket rate limiter to enforce configured TPS
2. Add circuit breaker if producer can't keep up with configured rate
3. Add metrics for producer latency and broker lag

---

## Performance Bottlenecks

### 1. Pandas UDF Serialization Overhead in Spark Consumer

**Problem:** Creating new FraudScorer instance per micro-batch is inefficient.

**Files:**
- `src/streaming/spark_consumer.py` (lines 290-343) — Pandas UDF creates scorer in lazy-load cache

**Current implementation:**
```python
@F.pandas_udf(T.DoubleType())
def score_fraud(...):
    if "scorer" not in scorer_cache:
        scorer_cache["scorer"] = FraudScorer(threshold=threshold)
```

**Impact:**
- First micro-batch loads model (slow) — ~5-10 seconds latency spike
- Caching helps but cache is per-executor, not per-job
- Multiple executors = multiple model loads

**Improvement path:**
1. Pre-load model before starting streaming query
2. Pass loaded model to UDF via broadcast variable instead of lazy loading
3. Measure actual latency of first batch vs subsequent batches
4. Consider model quantization (ONNX) if model size is large

### 2. Location Features Compute Inefficiency in Streaming

**Problem:** Location features (distance_km, speed_kmh) cannot be computed in streaming due to lag-window dependency.

**Files:**
- `src/streaming/feature_engineering.py` (lines 128-208) — compute_location_features uses lag()
- `src/streaming/spark_consumer.py` (lines 330) — Hardcoded distance_km=0.0 for streaming

**Current workaround:** Streaming sets distance_km=0.0, impossible-travel detection unavailable in real-time

**Impact:**
- Real-time scorer cannot detect impossible-travel fraud (one of 4 main patterns)
- Velocity features available but location-based patterns missed
- Model trained with location features but serves without them

**Improvement path:**
1. Implement stateful processing in Spark to maintain last known location per user
2. Use foreachBatch with external state store (Redis) for user location tracking
3. Add memory-efficient LRU cache for recent user locations
4. Measure state store latency impact vs accuracy gain

### 3. Full DataFrame JSON Serialization for Kafka Output

**Problem:** Entire feature DataFrame serialized to JSON for every transaction.

**Files:**
- `src/streaming/spark_consumer.py` (lines 232-236) — F.to_json(F.struct("*"))

**Impact:**
- Kafka message size bloats with all features even if downstream only needs subset
- Network I/O becomes bottleneck with high transaction volume
- Unnecessary data duplication for simple scoring output

**Improvement path:**
1. Project only necessary columns before serialization
2. Use Avro or Protobuf instead of JSON (binary format, ~30% smaller)
3. Implement schema version tracking in Kafka headers
4. Add compression at producer level

---

## Fragile Areas

### 1. Label Encoder Fit on Combined Train/Val/Test Data

**Issue:** LabelEncoder fit on all three sets together before split-specific transforms.

**Files:**
- `src/training/train_model.py` (lines 120-130) — Training preprocessing
- `src/training/prepare_data.py` (lines 180-195) — Data prep preprocessing
- `src/serving/model_scorer.py` (lines 88-94) — Artifact preparation

**Why fragile:**
```python
# All values from all splits fitted together
all_values = pd.concat([train[col], val[col], test[col]]).astype(str)
le.fit(all_values)
```

- If test set contains unknown categorical value after split, encoder still has it in classes
- Test set leakage into encoder training (test classes used in training fit)
- Streaming scorer silently defaults unknown values to 0

**Safe modification approach:**
1. Fit encoders ONLY on training set
2. Use unseen_value handling in scoring for validation/test unknowns
3. Track and log percentage of unknown values encountered during evaluation
4. Add assertion that test set categories are subset of training categories

### 2. Spark Consumer Checkpoint Directory Hardcoding

**Issue:** Checkpoint locations hardcoded in code, not configurable.

**Files:**
- `src/streaming/spark_consumer.py` (lines 89, 184, 211, 246, 409, 446) — Multiple hardcoded paths

**Paths:**
- `data/checkpoints` (general)
- `data/checkpoints/kafka_dlq`
- `data/checkpoints/parquet`
- `data/checkpoints/kafka_features`
- `data/checkpoints/kafka_windowed`
- `data/checkpoints/kafka_fraud_alerts`

**Why fragile:**
- Changing storage location requires code changes
- Running multiple instances uses same checkpoint dir — state corruption
- No checkpoint cleanup/management strategy

**Safe modification approach:**
1. Make checkpoint base path configurable via env var
2. Add instance ID to checkpoint paths for multi-instance deployments
3. Implement checkpoint retention policy (delete old checkpoints)
4. Add health check that validates checkpoint integrity at startup

### 3. No Deadletter Queue Monitoring

**Issue:** Parse failures written to DLQ topic but no monitoring or alerting.

**Files:**
- `src/streaming/spark_consumer.py` (lines 162-190) — write_dlq_to_kafka

**Current implementation:** DLQ topic exists but no consumer or alert system

**Risks:**
- DLQ silently grows unbounded
- Schema changes cause all messages to DLQ undetected
- Parsing errors could indicate upstream data quality issues

**Improvement path:**
1. Implement DLQ consumer that logs/alerts on threshold
2. Add metric: `dlq_queue_size` monitoring
3. Add daily report of DLQ message breakdown (parse errors by field)
4. Implement automatic schema migration detection

---

## Scaling Limits

### 1. Single User Profile Cache in Producer

**Problem:** All user profiles stored in memory in producer.

**Files:**
- `src/data_generator/transaction_generator.py` (lines 136-156)

**Current state:**
```python
self.users = self._create_user_profiles(num_users)  # Default 1000 users
```

**Limits:**
- 1000 users consumes ~10KB memory (acceptable)
- With 1M users: ~10MB (still manageable)
- With 100M users: needs optimization

**Current capacity:** Supports up to ~10M users before memory becomes issue

**Scaling path:**
1. If >1M users needed: implement random profile generation with seed instead of cache
2. Add user lookup cache (LRU with eviction) for stateful generators
3. Consider external user profile service for very large user bases

### 2. Micro-batch Processing Window Fixed at 10 Seconds

**Problem:** All streaming outputs trigger every 10 seconds, cannot adapt to load.

**Files:**
- `src/streaming/spark_consumer.py` (lines 185, 213, 247, 275, 410)
- `src/streaming/feature_engineering.py` (lines 81) — Window size "10 minutes"

**Current behavior:**
- Minimum latency: 10 seconds
- Cannot handle bursts (e.g., Black Friday shopping spikes)
- 10-minute aggregate window may miss fast attacks

**Scaling limits:**
- At ~1000 TPS, 10-second batches = ~10K records/batch (manageable)
- At ~100K TPS, 10-second batches = ~1M records/batch (Spark struggles, 30s+ processing time)

**Improvement path:**
1. Make triggerProcessingTime configurable
2. Implement adaptive batching based on queue depth
3. Add separate fast track (1-second window) for high-value/high-risk transactions
4. Consider switching to continuous processing mode for <1ms latency requirement

### 3. Model Reload Blocking

**Problem:** Spark consumer blocks during model reload operations.

**Files:**
- `src/streaming/spark_consumer.py` (lines 316-320) — Model loaded in UDF lazily

**Current state:** First batch in micro-batch waits for model load (~5-10 seconds)

**Scaling limits:**
- With multiple executors, each loads independently
- No coordination of model updates
- Model registry queries per micro-batch (network overhead)

**Improvement path:**
1. Implement async model loading in background
2. Use broadcast variable to share single model instance
3. Implement hot-swap mechanism for model updates without restarting
4. Cache model loads with TTL to reduce registry queries

---

## Test Coverage Gaps

### 1. No Unit Tests for Core Modules

**What's not tested:**
- `src/streaming/feature_engineering.py` — All feature computation functions
- `src/serving/model_scorer.py` — Preprocessing logic and score computation
- `src/training/prepare_data.py` — Data preparation pipeline
- `src/data_generator/transaction_generator.py` — Transaction generation logic

**Files:**
- Test directory is empty: `/Users/fazlikoc/Desktop/realtime_fraud_detection/tests/` is completely empty

**Risk:** High
- Feature engineering changes could break without detection
- Preprocessing bugs propagate silently
- Transaction generator correctness unvalidated

**Priority:** Critical

**How to test:**
```
tests/
├── test_feature_engineering.py
│   ├── test_haversine_distance
│   ├── test_windowed_features_correctness
│   └── test_transaction_features
├── test_preprocessing.py
│   ├── test_scaler_fit
│   ├── test_label_encoder_unknown_values
│   └── test_training_serving_consistency
└── test_transaction_generator.py
    ├── test_fraud_rate
    ├── test_normal_transaction_bounds
    └── test_fraud_patterns
```

### 2. No Integration Tests for Kafka Pipeline

**What's not tested:**
- Kafka producer → consumer → Spark pipeline end-to-end
- JSON schema validation and DLQ routing
- Feature output correctness through entire pipeline
- Fraud alert generation accuracy

**Risk:** Medium
- Pipeline could fail in production without detection
- Schema mismatches discovered only at runtime
- No validation that alerts match expected fraud patterns

### 3. No Model Performance Regression Tests

**What's not tested:**
- Model inference results against baseline metrics
- Threshold changes impact on precision/recall
- Model API compatibility (signature changes)

**Risk:** Medium-High
- Model updates could degrade performance undetected
- Threshold tuning has no automated validation
- Silent model degradation possible

---

## Missing Critical Features

### 1. Monitoring and Alerting System Completely Absent

**What's missing:**
- No metrics collection (precision, recall, false positive rate)
- No system health monitoring (Kafka lag, Spark job status, model latency)
- No alerts for anomalies (fraud rate spike, model performance drop, DLQ growth)
- No dashboard for operational visibility

**Impact:** Cannot observe system health in production

**Blocks:** Production deployment without operational visibility

### 2. Model Versioning and A/B Testing

**What's missing:**
- Only one model version supported
- No ability to run multiple models in parallel for A/B testing
- No gradual rollout mechanism

**Impact:** Cannot safely test new models in production

**Blocks:** Continuous model improvement without downtime

### 3. Explainability and Audit Trail

**What's missing:**
- No per-transaction explanation of fraud score
- No audit trail of which model version made which predictions
- SHAP importance calculated during training but not available at serving time
- No way to explain false positives to customers

**Impact:** Cannot debug fraud alerts or defend against disputes

**Blocks:** High-confidence fraud system for user-facing features

### 4. Data Quality Validation

**What's missing:**
- No schema enforcement beyond Kafka-level
- No range/bounds checks on input features
- No data drift detection
- No alerting on invalid data patterns

**Impact:** Bad data silently propagates through pipeline

**Blocks:** Confidence in data integrity for fraud scoring

---

## Dependencies at Risk

### 1. PySpark Version Constraints

**File:** `requirements.txt` (line 10)

**Constraint:** `pyspark>=3.5.0,<4.0.0`

**Risk:** Kafka connector compatibility

- Spark 3.x uses Scala 2.12 but Spark 4.x uses Scala 2.13
- Code has version detection (spark_consumer.py lines 78-82) but only at runtime
- No automated testing of Spark 4.x compatibility

**Migration plan:**
1. Test against Spark 4.0 in CI
2. Remove version cap when 4.x compatibility confirmed
3. Consider using Universal Kafka connector that works across versions

### 2. LightGBM Model Artifact Serialization

**File:** `src/training/train_model.py` (line 392)

**Risk:** LightGBM <-> MLflow compatibility

```python
if "xgboost" in name.lower():
    mlflow.xgboost.log_model(...)
else:
    mlflow.sklearn.log_model(...)  # LightGBM logged as sklearn
```

- LightGBM is logged as generic sklearn model
- No guarantee MLflow version compatibility
- ONNX conversion not used

**Migration plan:**
1. Consider using native `mlflow.lightgbm.log_model()`
2. Add ONNX export as backup artifact format
3. Test serialization/deserialization round-trip

### 3. joblib for Preprocessing Artifacts

**Files:** `src/serving/model_scorer.py` (lines 109-111)

**Risk:** joblib version compatibility and security

- joblib pickle format not backward compatible across versions
- Pickle is security risk if loading untrusted artifacts

**Migration plan:**
1. Switch to `pickle` protocol=5 (Python 3.8+) for better compression
2. Or use JSON/YAML for preprocessing config, numpy arrays for weights
3. Add artifact version checking

---

## Dependencies Missing

### 1. No Input Validation Library

**Risk:** Manual validation scattered across code, error-prone

**Recommendation:** Add `pydantic` or `marshmallow` for schema validation

### 2. No Configuration Management

**Risk:** Configs scattered in `config.py` with no validation

**Recommendation:** Add `pydantic.BaseSettings` or `dynaconf`

### 3. No Logging Library

**Risk:** Print statements instead of structured logging

**Recommendation:** Add `python-logging-loki` or `python-json-logger`

---

## Recommended Immediate Fixes (Priority Order)

### 🔴 Critical (Blocks Production)

1. **Implement shared preprocessing module** — Prevent training-serving skew recurrence
2. **Add comprehensive test suite** — Core modules need unit tests
3. **Add monitoring/alerting** — Cannot operate system blind

### 🟠 High (Should fix before scaling)

1. **Fix silent error handling in scorer** — Enable debugging of production issues
2. **Implement model version health check** — Prevent stale model usage
3. **Add input validation** — Prevent bad data propagation

### 🟡 Medium (Nice to have)

1. **Add DLQ monitoring** — Detect data quality issues
2. **Implement checkpoint management** — Prevent state corruption
3. **Add explainability at serving time** — Debug fraud alerts

---

*Concerns audit: 2026-03-20*
