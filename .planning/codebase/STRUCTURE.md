# Codebase Structure

**Analysis Date:** 2026-03-20

## Directory Layout

```
realtime_fraud_detection/
├── src/                           # Main application code
│   ├── __init__.py
│   ├── config.py                  # Centralized config from environment
│   ├── data_generator/            # Transaction generation & Kafka producer
│   │   ├── __init__.py
│   │   ├── transaction_generator.py    # Realistic fraud patterns
│   │   ├── kafka_producer.py           # Publishes to Kafka
│   │   ├── kafka_consumer_debug.py     # Testing consumer
│   │   └── register_schemas.py         # Schema Registry registration
│   ├── streaming/                 # Spark real-time pipeline
│   │   ├── __init__.py
│   │   ├── spark_consumer.py           # Main streaming pipeline
│   │   └── feature_engineering.py      # Reusable feature functions
│   ├── training/                  # ML model training
│   │   ├── __init__.py
│   │   ├── prepare_data.py             # Generate & split historical data
│   │   ├── train_model.py              # Train & evaluate models
│   │   ├── tune_hyperparams.py         # Hyperparameter tuning
│   │   └── evaluate.py                 # Post-training evaluation
│   ├── serving/                   # Model inference
│   │   ├── __init__.py
│   │   └── model_scorer.py             # Fraud scorer + artifacts
│   └── utils/                     # Shared utilities
│       └── __init__.py
├── data/                          # Data storage (local + generated)
│   ├── raw/                       # Raw generated transactions (CSV/Parquet)
│   ├── features/                  # Real-time streaming features (Parquet, date-partitioned)
│   ├── features_historical/       # Batch features for training
│   ├── splits/                    # train.parquet, val.parquet, test.parquet
│   ├── artifacts/                 # Preprocessing (scaler.joblib, label_encoders.joblib)
│   ├── checkpoints/               # Spark streaming checkpoints (internal state)
│   └── charts/                    # Matplotlib outputs from evaluation
├── configs/                       # Configuration files
│   └── schemas/                   # JSON schemas for Kafka validation
│       └── transaction_value.json
├── docker-compose.yml             # Service definitions (Kafka, Spark, MLflow, etc.)
├── Dockerfile.mlflow              # MLflow service container
├── Makefile                       # Convenient command shortcuts
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (not in git)
├── .gitignore                     # Git exclusions
└── .planning/                     # GSD planning documents
    └── codebase/                  # Architecture analysis (this file)
```

## Directory Purposes

**src/:**
- Purpose: All application source code
- Contains: Modules for data generation, streaming, training, serving
- Key files: `config.py` is imported by all modules

**src/data_generator/:**
- Purpose: Create realistic synthetic transactions and publish to Kafka
- Contains: TransactionGenerator, FraudTransactionProducer, schema registration
- Key files: `transaction_generator.py` (fraud patterns), `kafka_producer.py` (publishing)
- Pattern: Generates labeled data with configurable fraud_rate

**src/streaming/:**
- Purpose: Real-time processing of transaction stream
- Contains: Spark Structured Streaming consumer, feature computation
- Key files: `spark_consumer.py` (main pipeline), `feature_engineering.py` (feature logic)
- Pattern: Reads Kafka → features → scoring → multiple outputs (Parquet, Kafka topics)

**src/training/:**
- Purpose: Build ML models from historical data
- Contains: Data preparation, training, hyperparameter optimization, evaluation
- Key files: `prepare_data.py` (generate + split), `train_model.py` (4 models)
- Pattern: Generates labeled data → features → train/val/test split → model selection

**src/serving/:**
- Purpose: Load trained model and preprocess for inference
- Contains: FraudScorer class, artifact management
- Key files: `model_scorer.py` (scorer class + prepare_artifacts function)
- Pattern: Loads scaler + encoders + model once, reuses across all scoring calls

**data/:**
- Purpose: Local storage for generated/computed data
- Contains: Raw transactions, computed features, splits, ML artifacts, checkpoints
- Committed to git: ❌ (data/ is in .gitignore)
- Generated: ✅ (created by prepare_data, spark_consumer, etc.)

**data/splits/:**
- Purpose: Train/val/test Parquet files for model training
- Contains: train.parquet, val.parquet, test.parquet (100K+ rows each)
- Created by: `src/training/prepare_data.py`
- Used by: `src/training/train_model.py`, `src/serving/model_scorer.py`

**data/artifacts/:**
- Purpose: Preprocessing state needed for scoring consistency
- Contains: scaler.joblib, label_encoders.joblib, feature_names.joblib
- Created by: `src/serving.model_scorer.prepare_scoring_artifacts()`
- Used by: Spark UDF in streaming consumer

**data/checkpoints/:**
- Purpose: Spark streaming fault tolerance (internal state management)
- Contains: Parquet files with offset tracking and micro-batch state
- Managed by: Spark (automatic)
- Delete to reset: Flushes all pending streaming data

**configs/:**
- Purpose: Non-Python configuration files
- Contains: JSON schemas for validation
- Key files: `schemas/transaction_value.json` (Kafka message schema)

**Root level:**
- `docker-compose.yml`: Service orchestration (Zookeeper, Kafka, Schema Registry, Spark, MLflow, PostgreSQL, MinIO)
- `Makefile`: Shortcuts for common commands (make producer, make stream, make train)
- `requirements.txt`: Python package dependencies (Kafka, PySpark, scikit-learn, MLflow, etc.)
- `.env`: Environment variables (Kafka broker, MLflow tracking URI, etc.) - NOT in git

## Key File Locations

**Entry Points:**

- `src/data_generator/kafka_producer.py`: Start data pipeline (make producer)
- `src/streaming/spark_consumer.py`: Start streaming consumer (make stream)
- `src/training/prepare_data.py`: Generate training data (make prepare-data)
- `src/training/train_model.py`: Train models (make train)

**Configuration:**

- `src/config.py`: All configurable values (Kafka broker, Schema Registry URL, MLflow URI)
- `.env`: Secrets and environment-specific values (KAFKA_BROKER, MLFLOW_TRACKING_URI)
- `docker-compose.yml`: Service configuration and dependencies

**Core Logic:**

- `src/data_generator/transaction_generator.py`: Fraud pattern generation
- `src/streaming/feature_engineering.py`: Feature computation logic
- `src/serving/model_scorer.py`: Scoring pipeline
- `src/training/train_model.py`: Model selection and training

**Testing & Data:**

- `data/splits/`: Train/val/test sets for reproducible evaluation
- `data/artifacts/`: Preprocessing artifacts for inference
- `data/features/`: Output features from streaming (historical record)

## Naming Conventions

**Files:**

- Snake case: `transaction_generator.py`, `kafka_producer.py`, `spark_consumer.py`
- Modules named by responsibility: `train_model.py`, `prepare_data.py`, `feature_engineering.py`
- Test modules (when present): `test_*.py` or `*_test.py`

**Directories:**

- Snake case, plural for collections: `data_generator/`, `streaming/`, `training/`, `configs/`
- Data directories plural: `splits/`, `artifacts/`, `checkpoints/`, `features/`
- Logic organized by domain: `data_generator/`, `streaming/`, `training/`, `serving/`

**Python Classes:**

- PascalCase: `TransactionGenerator`, `FraudTransactionProducer`, `FraudScorer`
- Inherit responsibility: `TransactionGenerator` generates, `FraudScorer` scores

**Python Functions:**

- Snake case: `generate_transaction()`, `prepare_scoring_artifacts()`, `compute_transaction_features()`
- Prefixed by action: `create_spark_session()`, `read_from_kafka()`, `write_features_to_parquet()`

**Variables & Constants:**

- Constants UPPERCASE: `KAFKA_BROKER`, `FEATURE_COLUMNS`, `MERCHANTS`, `US_LOCATIONS`
- Variables lowercase: `user`, `transaction`, `spark`, `model`
- Private with underscore: `_create_producer()`, `_on_success()`

## Where to Add New Code

**New Feature (e.g., new fraud detection pattern):**

- Primary code: `src/training/train_model.py` (add feature engineering)
- Streaming computation: `src/streaming/feature_engineering.py` (add compute function)
- Serving preprocessing: `src/serving/model_scorer.py` (update FEATURE_COLUMNS, add encoding)
- Tests: `tests/test_feature_engineering.py` (if test structure created)

**New Output Stream (e.g., export to external system):**

- Implementation: Add write function in `src/streaming/spark_consumer.py`
- Pattern: Follow existing `write_features_to_parquet()`, `write_features_to_kafka()` style
- Configuration: Add Kafka topic/endpoint to `src/config.py`

**New Data Source (e.g., pull in customer profiles):**

- Data loading: Create in `src/data_generator/` (e.g., `customer_loader.py`)
- Integration: Import and join in `src/streaming/spark_consumer.py`
- Configuration: Add connection details to `src/config.py`

**New Training Model:**

- Implementation: Add to `src/training/train_model.py` in the training loop
- Pattern: Follow existing pattern (fit, log metrics, log params, compare)
- MLflow: Automatically tracked via mlflow.sklearn or mlflow.xgboost decorators

**Utilities & Shared Helpers:**

- Location: `src/utils/`
- Pattern: Pure functions without side effects
- Imports: Imported explicitly where needed

## Special Directories

**data/checkpoints/:**
- Purpose: Spark Structured Streaming checkpointing (for fault tolerance)
- Generated: ✅ (Spark manages automatically)
- Committed: ❌ (in .gitignore)
- Delete to reset: Yes - flushes all pending streaming data

**data/artifacts/:**
- Purpose: Preprocessing state (scaler, encoders) for consistent scoring
- Generated: ✅ (created by prepare_scoring_artifacts())
- Committed: ❌ (in .gitignore)
- Regenerate: Run `python -m src.serving.model_scorer --prepare`

**data/features/ and data/features_historical/:**
- Purpose: Record of computed features (for debugging, retraining)
- Generated: ✅ (streaming writes to features/, training writes to features_historical/)
- Committed: ❌ (in .gitignore)
- Retention: Can be cleaned up; re-generated by running pipelines

**configs/schemas/:**
- Purpose: JSON schemas for Kafka message validation
- Committed: ✅ (source code)
- Edited: Rarely; only when changing transaction structure

## Module Dependencies

```
data_generator/
  ├── Depends on: config, faker
  └── Imports: transaction_generator, kafka_producer

streaming/
  ├── Depends on: config, serving, pyspark
  ├── feature_engineering.py: Pure Spark UDFs
  └── spark_consumer.py: Orchestrates pipeline

training/
  ├── Depends on: config, data_generator, streaming, sklearn, xgboost, mlflow
  ├── prepare_data.py: Uses transaction_generator, feature_engineering
  └── train_model.py: Uses preprocessed data from prepare_data

serving/
  ├── Depends on: config, sklearn, mlflow
  ├── Loads: joblib artifacts from data/artifacts/
  └── Used by: streaming (Spark UDF)
```

## Code Organization Pattern

**Module Structure (example: training):**

```python
# src/training/train_model.py

# 1. Imports (stdlib, third-party, local)
import os
import pandas as pd
import mlflow
from src.config import MLFLOW_TRACKING_URI

# 2. Constants
FEATURE_COLUMNS = [...]
CATEGORICAL_COLUMNS = [...]

# 3. Helper functions
def load_data() -> tuple[...]:
    """Load and return train/val/test splits."""
    ...

def preprocess(df: pd.DataFrame) -> tuple[...]:
    """Apply feature transformations."""
    ...

# 4. Main logic
def train_models() -> dict:
    """Train all models and return results."""
    ...

# 5. Entry point
if __name__ == "__main__":
    train_models()
```

**Streaming Function Structure (example: feature_engineering):**

```python
# src/streaming/feature_engineering.py

# 1. UDFs (simple, stateless)
@F.udf(T.DoubleType())
def haversine_km(lat1, lon1, lat2, lon2):
    """Pure calculation, no state."""
    ...

# 2. DataFrame transformations (chainable)
def compute_transaction_features(df: DataFrame) -> DataFrame:
    """Add columns, return modified DataFrame."""
    return df.withColumn(...).withColumn(...)

def compute_windowed_features(df: DataFrame) -> DataFrame:
    """Windowed aggregations with watermarking."""
    return df.groupBy(window(...)).agg(...)
```

---

*Structure analysis: 2026-03-20*
