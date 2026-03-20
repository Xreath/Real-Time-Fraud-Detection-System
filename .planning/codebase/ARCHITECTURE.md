# Architecture

**Analysis Date:** 2026-03-20

## Pattern Overview

**Overall:** Event-Driven Real-Time Streaming with ML Scoring

**Key Characteristics:**
- Real-time event processing with Kafka as central message bus
- Multi-layer pipeline: ingestion → feature engineering → model scoring → alerting
- Separation of concerns: data generation, streaming processing, model training, and serving
- Batch training feeding real-time serving with consistent preprocessing
- Windowed aggregations for velocity attack detection

## Layers

**Data Generation Layer:**
- Purpose: Generate realistic transaction data with fraud patterns
- Location: `src/data_generator/`
- Contains: Transaction generator, Kafka producer, schema registry
- Depends on: Kafka, Faker library
- Used by: Kafka streaming pipeline

**Streaming Processing Layer:**
- Purpose: Real-time feature engineering and fraud scoring on transactions
- Location: `src/streaming/`
- Contains: Spark Structured Streaming consumer, feature engineering functions
- Depends on: Kafka, Spark, trained ML model
- Used by: Fraud alerts and downstream analytics

**Model Training Layer:**
- Purpose: Train and evaluate fraud detection models on historical data
- Location: `src/training/`
- Contains: Data preparation, model training, hyperparameter tuning, evaluation
- Depends on: Parquet data splits, scikit-learn, XGBoost, LightGBM
- Used by: MLflow for model versioning; model scorer for inference artifacts

**Model Serving Layer:**
- Purpose: Load trained model and preprocessing artifacts for real-time scoring
- Location: `src/serving/`
- Contains: FraudScorer class, preprocessing artifact management, MLflow integration
- Depends on: Trained model, StandardScaler, LabelEncoders from artifacts
- Used by: Spark streaming consumer for transaction scoring

**Configuration Layer:**
- Purpose: Centralize all configuration and environment variables
- Location: `src/config.py`
- Contains: Kafka broker, Schema Registry, Spark, MLflow endpoints
- Depends on: .env file
- Used by: All modules

## Data Flow

**Real-Time Pipeline (Production):**

1. **Data Ingestion** → `src/data_generator/kafka_producer.py`
   - TransactionGenerator creates realistic transactions with configurable fraud rate
   - Kafka producer sends JSON messages to `transactions` topic
   - Partition key = user_id (ensures ordering per user)

2. **Kafka Topics** (Message Bus)
   - `transactions` → Raw incoming transaction events
   - `transactions-dlq` → Parse failures for manual review
   - `features` → Computed features for downstream consumption
   - `fraud-alerts` → High-risk transactions exceeding threshold
   - `features-windowed` → 1-hour aggregated velocity metrics

3. **Stream Processing** → `src/streaming/spark_consumer.py`
   - Read from Kafka `transactions` topic using Spark Structured Streaming
   - Parse JSON with validation (invalid → DLQ)
   - Apply feature engineering (transaction-level + windowed)
   - Apply real-time ML scoring using FraudScorer
   - Filter and write alerts

4. **Feature Engineering** → `src/streaming/feature_engineering.py`
   - Transaction Features: hour_of_day, day_of_week, amount_log, is_high_amount, is_round_amount
   - Location Features: distance_km (Haversine), time_diff_hours, speed_kmh
   - Windowed Features: tx_count_1h, total_amount_1h, avg_amount_1h, unique_merchant_1h

5. **Model Scoring** → `src/serving/model_scorer.py`
   - Load preprocessing artifacts (StandardScaler, LabelEncoders)
   - Preprocess features (categorical encoding, scaling)
   - Invoke LGBMClassifier.predict_proba() → fraud_score (0-1)
   - Apply threshold (default 0.5) → fraud_prediction (0 or 1)

6. **Output Writes** (Multiple sinks in parallel)
   - Parquet files (date partitioned) in `data/features/` for batch analytics
   - Kafka `features` topic with all features for real-time dashboards
   - Kafka `fraud-alerts` topic with fraud_score ≥ threshold for alerting systems
   - Kafka `features-windowed` topic with velocity metrics

**Batch Training Pipeline (Offline):**

1. **Data Generation** → `src/training/prepare_data.py`
   - Generate 100K+ labeled transactions using TransactionGenerator
   - Group by merchant, card type, location for realistic patterns

2. **Feature Engineering** (Batch)
   - Apply same features as streaming using Spark DataFrame operations
   - Compute location features using window functions (lag for previous transaction)
   - Handle imbalance with class_weight strategy

3. **Data Splitting** → `src/training/prepare_data.py`
   - Stratified split: train (70%), validation (15%), test (15%)
   - Preserves fraud ratio across all splits
   - Save as Parquet in `data/splits/`

4. **Model Training** → `src/training/train_model.py`
   - Train 4 models: LogisticRegression, RandomForest, XGBoost, LightGBM
   - Track all experiments in MLflow
   - Log metrics: precision, recall, F1, ROC-AUC, average precision
   - Log feature importance with SHAP

5. **Model Registry** → MLflow Model Registry
   - Register best performing model (LightGBM usually wins)
   - Version tracking for reproducibility
   - Artifact storage in MinIO (S3-compatible)

6. **Serving Artifacts** → `src/serving/model_scorer.py`
   - Extract and save preprocessing artifacts (scaler, label_encoders, feature_names)
   - Store in `data/artifacts/`
   - Loaded by Spark UDF for scoring

**State Management:**

- **Kafka Offsets:** Spark checkpoints track streaming position automatically
- **Window State:** Spark manages 1-hour window state in memory with watermarking
- **Model State:** Cached in Spark UDF (FraudScorer instance per partition)
- **Preprocessing State:** Loaded once from joblib, cached in memory

## Key Abstractions

**TransactionGenerator:**
- Purpose: Simulate realistic fraud patterns (velocity, impossible travel, unusual amounts)
- Examples: `src/data_generator/transaction_generator.py`
- Pattern: Generates transactions with configurable fraud_rate and user profiles
- Outputs: Dict with transaction fields (transaction_id, user_id, amount, etc.)

**FraudScorer:**
- Purpose: Encapsulate preprocessing + model inference
- Examples: `src/serving/model_scorer.py`
- Pattern: Loads artifacts on __init__, exposes .preprocess() and .score() methods
- Critical: Ensures training-serving consistency (same scaler, encoders, feature order)

**Feature Engineering Functions:**
- Purpose: Reusable computation for both streaming and batch
- Examples: `src/streaming/feature_engineering.py`
- Pattern: Pure Spark SQL/UDF functions, partition-aware windowing
- Streaming: windowed aggregations with watermarking
- Batch: lag-based location features using window functions

**Kafka Producer Pattern:**
- Purpose: Reliable message sending with callback handling
- Examples: `src/data_generator/kafka_producer.py`
- Pattern: FraudTransactionProducer class with configurable TPS, graceful shutdown
- Ensures: acks='all', user_id as partition key, JSON serialization

## Entry Points

**Kafka Producer:**
- Location: `src/data_generator/kafka_producer.py`
- Triggers: `make producer` or `python -m src.data_generator.kafka_producer`
- Responsibilities: Generates transactions at configurable rate, publishes to Kafka

**Spark Streaming Consumer:**
- Location: `src/streaming/spark_consumer.py`
- Triggers: `make stream` or `python -m src.streaming.spark_consumer --debug`
- Responsibilities: Continuously reads Kafka, computes features, scores, writes outputs
- Command-line args: --broker, --topic, --output-parquet, --output-topic, --debug

**Data Preparation (Batch):**
- Location: `src/training/prepare_data.py`
- Triggers: `make prepare-data` or `python -m src.training.prepare_data`
- Responsibilities: Generates historical data, applies features, creates stratified splits

**Model Training:**
- Location: `src/training/train_model.py`
- Triggers: `make train` or `python -m src.training.train_model`
- Responsibilities: Trains 4 models, logs metrics to MLflow, registers best model

**Schema Registry:**
- Location: `src/data_generator/register_schemas.py`
- Triggers: `make register-schemas`
- Responsibilities: Registers JSON schema for transaction validation

## Error Handling

**Strategy:** Graceful degradation with Dead Letter Queues and fallback scoring

**Patterns:**

- **Parse Errors** → Messages sent to `transactions-dlq` for manual inspection
- **Scoring Failures** → Fallback to fraud_score=-1 (triggers manual review)
- **Missing Features** → fillna(0) for numeric, unknown categories → index 0
- **Kafka Connection** → Retry with exponential backoff (up to 5 attempts)
- **Graceful Shutdown** → Signal handlers (SIGINT, SIGTERM) flush and close cleanly

## Cross-Cutting Concerns

**Logging:**
- Framework: Python logging + Spark logging
- Approach: print() statements for major pipeline stages; Spark logs set to WARN level
- Recommendation: Should migrate to structured logging (JSON) for production

**Validation:**
- Schema Registry validates Kafka messages against JSON schema
- Spark's .filter(data.isNotNull()) catches malformed records
- Type checking in feature engineering with .cast()

**Authentication:**
- MLflow S3 access via AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY environment variables
- Schema Registry accessed via HTTP (no auth in docker-compose)
- Kafka plaintext protocol (suitable for internal networks only)

**Monitoring:**
- MLflow tracks all model experiments (metrics, parameters, artifacts)
- Kafka consumer lag can be monitored via Confluent command-line tools
- Manual metrics reporting: sent_count, error_count in producer
- Recommendation: Add Prometheus metrics export for production

---

*Architecture analysis: 2026-03-20*
