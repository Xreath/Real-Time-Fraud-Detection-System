<!-- GSD:project-start source:PROJECT.md -->
## Project

**Real-Time Fraud Detection System**

An end-to-end real-time credit card fraud detection system using Kafka, Spark Structured Streaming, MLflow, Airflow, and GCP Vertex AI. A learning/portfolio project demonstrating production-grade MLOps practices — from data generation through model training, deployment, orchestration, and monitoring.

**Core Value:** Demonstrate a complete, production-realistic MLOps pipeline that can be discussed in depth during interviews — every component works end-to-end, not just in isolation.

### Constraints

- **Tech stack**: Python, Kafka, Spark, MLflow, Airflow, Docker — must use these specific technologies (learning goals)
- **Local-first**: Everything must work locally via Docker Compose before any cloud deployment
- **Cloud**: GCP Vertex AI is a stretch goal — local deployment is the minimum
- **Java**: Java 11 required by Spark 3.5.x — cannot upgrade without Spark version change
- **MLflow**: Server runs v2.12.2 in Docker — client version must be compatible
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.x - Core application, data generation, ML training, streaming consumer
- YAML - Configuration management for Kafka and Spark
- JSON - Schema definitions (Confluent Schema Registry), configuration
## Runtime
- Python 3.x (installed via `uv` package manager)
- Java 11 (required by Spark and Kafka)
- `uv` - Fast Python package manager (referenced in Makefile)
- `pip` - Secondary package installation via uv
- Lockfile: `.venv` virtual environment present
## Frameworks
- PySpark 3.5.0+ - Distributed stream processing with Structured Streaming
- kafka-python 2.0.2+ - Kafka producer/consumer client
- scikit-learn 1.4.0+ - Baseline models (LogisticRegression), preprocessing (StandardScaler, LabelEncoder)
- XGBoost 2.0.0+ - Gradient boosting classifier
- LightGBM 4.0.0+ - Gradient boosting (alternative to XGBoost)
- Optuna 4.0.0+ - Bayesian hyperparameter tuning
- imbalanced-learn 0.12.0+ - Class imbalance handling (SMOTE capability)
- joblib 1.3.0+ - Model and artifact serialization
- MLflow 2.12.0+ - Experiment tracking, model versioning, model serving
- matplotlib 3.8.0+ - Plotting (non-interactive Agg backend for servers)
- seaborn 0.13.0+ - Statistical visualization
- shap 0.45.0+ - Model explainability (SHAP values)
- python-dotenv 1.0.0+ - Environment variable loading from .env
- pyyaml 6.0.0+ - YAML parsing
- pandas 2.2.0+ - Data manipulation and analysis
- numpy 1.26.0+ - Numerical computing
- requests 2.31.0+ - HTTP requests (Schema Registry API calls)
- Faker 24.0+ - Realistic synthetic transaction data generation
## Key Dependencies
- kafka-python - Bridges application to Kafka cluster; without it, data ingestion fails
- pyspark - Distributed stream processing; core of real-time pipeline
- mlflow - Enables reproducible model tracking and deployment; without it no experiment history
- scikit-learn - ML model training; critical for fraud detection algorithms
- pandas/numpy - Data manipulation; used across all data processing stages
- boto3 1.34.0+ - S3/MinIO client for artifact storage with MLflow
## Configuration
- `.env` file present - Contains environment variables for all services
- Configuration via `src/config.py` - Centralizes all settings with sensible defaults:
- Dockerfile.mlflow - Custom MLflow image with psycopg2-binary and boto3
- docker-compose.yml - Orchestrates all services (Kafka, Spark, MLflow, PostgreSQL, MinIO)
## Platform Requirements
- Docker Engine - For running containerized services
- Docker Compose - For multi-container orchestration
- Python 3.x with venv support
- Make - For convenient command shortcuts
- Docker/Kubernetes for container orchestration
- PostgreSQL 16 (or compatible) - MLflow metadata store
- MinIO or AWS S3 - MLflow artifact repository
- Apache Kafka 7.6.0+ (Confluent CP) - Message broker
- Apache Spark 3.5.4+ - Stream processing cluster
- Zookeeper 7.6.0 - Kafka coordination
## Services & Versions
- Kafka (Confluent): 7.6.0
- Zookeeper: 7.6.0
- Schema Registry: 7.6.0
- Apache Spark: 3.5.4 (master + worker setup)
- PostgreSQL: 16 (Alpine)
- MinIO: latest
- MLflow: 2.12.2 (custom image)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Module/script names: `snake_case` (e.g., `kafka_producer.py`, `transaction_generator.py`, `model_scorer.py`)
- Package directories: `snake_case` (e.g., `data_generator/`, `streaming/`, `training/`, `serving/`)
- All functions: `snake_case` (e.g., `generate_transaction()`, `compute_metrics()`, `train_and_log_model()`)
- Private methods: prefix with underscore (e.g., `_create_producer()`, `_on_success()`, `_generate_fraud_transaction()`)
- Callback methods: descriptive names with action prefix (e.g., `_on_success()`, `_on_error()`, `_shutdown()`)
- Utility functions at module level: lowercase, snake_case
- Type hints used for function parameters and returns (e.g., `def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`)
- Constants (module-level): `SCREAMING_SNAKE_CASE` (e.g., `KAFKA_BROKER`, `FEATURE_COLUMNS`, `TRANSACTIONS_SCHEMA`)
- Instance variables: `snake_case` (e.g., `self.sent_count`, `self.fraud_rate`, `self.scaler`)
- Local variables: `snake_case` (e.g., `fraud_count`, `train_df`, `X_train`)
- Dataframe variables: suffix with `_df` (e.g., `train_df`, `test_df`, `spark_df`)
- Dictionary/mapping variables: end with `_dict` or descriptive names (e.g., `label_encoders`, `MERCHANTS`, `FOREIGN_MERCHANTS`)
- Dataclasses for structured data: `@dataclass` decorator with field names in `snake_case` (e.g., `Transaction` dataclass in `src/data_generator/transaction_generator.py`)
- Classes: `PascalCase` (e.g., `TransactionGenerator`, `FraudTransactionProducer`, `FraudScorer`)
## Code Style
- No automatic formatter configured (no Black, ruff, or Prettier in requirements)
- Manual style follows PEP 8 conventions:
- No linting configuration detected (no `.pylintrc`, `.flake8`, or ESLint config)
- Code follows implicit PEP 8 style guidelines
## Import Organization
- No aliases configured; all imports use absolute module paths from project root
- Standard imports: `from src.config import KAFKA_BROKER, KAFKA_TOPIC_TRANSACTIONS`
- Submodule imports: `from src.data_generator.transaction_generator import TransactionGenerator`
- Framework-specific imports group multiple functions: `from sklearn.metrics import precision_score, recall_score, f1_score, ...`
## Error Handling
- Try-except blocks for external integration points (Kafka connection, MLflow model loading)
- Retry logic with exponential backoff for Kafka broker connection: `_create_producer()` in `src/data_generator/kafka_producer.py` retries up to 5 times with increasing wait periods
- Generic exception handling in streaming loops with logged errors: `except Exception as e: print(f"Error: {e}")`
- Graceful shutdown using signal handlers: `signal.signal(signal.SIGINT, self._shutdown)` in producer
- Validation before processing (e.g., check if DataFrame columns exist before transformation)
- Direct exception raising for critical failures: `raise RuntimeError(f"Kafka connection failed: {broker}")` when max retries exceeded
- Fallback values for unknown categorical values in scoring: `le.transform([x])[0] if x in le.classes_ else 0` in `src/serving/model_scorer.py`
## Logging
- Print progression messages for multi-step processes (e.g., `print("[1/4] Loading data...")`)
- Use `print(f"...")` for formatted output with variables
- Section separators: `print("=" * 60)` for major workflow boundaries
- Status messages with timestamps: `print(f"[{datetime.now().strftime('%H:%M:%S')}] Message")`
- Metrics reporting: Print counts and percentages (e.g., `f"Sent: {self.sent_count} | Error: {self.error_count}"`)
- Progress updates at intervals (e.g., every 100 messages in producer): `if total > 0 and total % 100 == 0`
- Muted library logging: `matplotlib.use("Agg")` (non-interactive backend), `spark.sparkContext.setLogLevel("WARN")`
## Comments
- Module docstrings: Always present, explain purpose and usage (e.g., in `kafka_producer.py`, `train_model.py`)
- Function docstrings: Comprehensive docstrings for public functions with Args, Returns, and usage notes
- "Mülakat notu" (interview notes): Custom sections in docstrings explaining design decisions and answers to common questions
- Section separators: Comment blocks marking pipeline phases (`# ============================================================`)
- Complex algorithms: Comments explaining why, not what (e.g., Haversine formula explanation in `feature_engineering.py`)
- Configuration rationale: Comments explaining non-obvious settings (e.g., `acks='all'` for Kafka producer guarantees)
- Data/constant definitions: Comments for large static data structures explaining purpose (e.g., `MERCHANTS`, `FOREIGN_MERCHANTS`)
- Not used (Python project, not TypeScript/JavaScript)
- Python docstrings follow Google/NumPy-style format implicitly
## Function Design
- Functions range from 5-50 lines typically
- Single-responsibility principle observed (e.g., `_create_producer()` only creates producer, `preprocess()` only handles feature preprocessing)
- Complex workflows broken into multiple functions (e.g., `prepare_data.py` separates generation, feature engineering, splitting, and saving)
- Optional parameters with sensible defaults (e.g., `fraud_rate: float = 0.02`, `seed: Optional[int] = None`)
- Type hints for all parameters (e.g., `num_users: int`, `df: pd.DataFrame`, `spark: SparkSession`)
- Kwargs not commonly used; explicit named parameters preferred
- Dictionary unpacking for configuration (e.g., `**params` in MLflow logging)
- Explicit return types in function signatures
- Tuple returns for multiple values (e.g., `tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`)
- Dictionary returns for structured results (e.g., `{"precision": ..., "recall": ...}` from `compute_metrics()`)
- None returns for side-effect functions (e.g., `def start(self)` in producer)
## Module Design
- Main entry point: `if __name__ == "__main__"` pattern used for CLI invocation
- Public classes exported directly (e.g., `class TransactionGenerator`, `class FraudScorer`)
- Utility functions prefixed with underscore if for internal use only (e.g., `_create_producer()`)
- Module-level constants exported at top level (e.g., `FEATURE_COLUMNS`, `KAFKA_BROKER`)
- No barrel files (index.py) observed
- `__init__.py` files exist but are empty (`src/__init__.py`, `src/data_generator/__init__.py`)
- Direct imports from submodules required (e.g., `from src.training.train_model import main`)
## Special Patterns
- `@dataclass` decorator for immutable data containers (e.g., `Transaction` in `transaction_generator.py`)
- Field definitions with type hints
- Methods within dataclasses minimal; mostly data storage
- MLflow context: `with mlflow.start_run(run_name=name):` for experiment tracking scopes
- File operations: Standard context managers not extensively shown but implicitly used
- Centralized config module: `src/config.py`
- Environment variables loaded with defaults: `os.getenv("VAR_NAME", "default_value")`
- Type conversions inline: `int(os.getenv("VAR", "10"))`, `float(os.getenv("VAR", "0.02"))`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Real-time event processing with Kafka as central message bus
- Multi-layer pipeline: ingestion → feature engineering → model scoring → alerting
- Separation of concerns: data generation, streaming processing, model training, and serving
- Batch training feeding real-time serving with consistent preprocessing
- Windowed aggregations for velocity attack detection
## Layers
- Purpose: Generate realistic transaction data with fraud patterns
- Location: `src/data_generator/`
- Contains: Transaction generator, Kafka producer, schema registry
- Depends on: Kafka, Faker library
- Used by: Kafka streaming pipeline
- Purpose: Real-time feature engineering and fraud scoring on transactions
- Location: `src/streaming/`
- Contains: Spark Structured Streaming consumer, feature engineering functions
- Depends on: Kafka, Spark, trained ML model
- Used by: Fraud alerts and downstream analytics
- Purpose: Train and evaluate fraud detection models on historical data
- Location: `src/training/`
- Contains: Data preparation, model training, hyperparameter tuning, evaluation
- Depends on: Parquet data splits, scikit-learn, XGBoost, LightGBM
- Used by: MLflow for model versioning; model scorer for inference artifacts
- Purpose: Load trained model and preprocessing artifacts for real-time scoring
- Location: `src/serving/`
- Contains: FraudScorer class, preprocessing artifact management, MLflow integration
- Depends on: Trained model, StandardScaler, LabelEncoders from artifacts
- Used by: Spark streaming consumer for transaction scoring
- Purpose: Centralize all configuration and environment variables
- Location: `src/config.py`
- Contains: Kafka broker, Schema Registry, Spark, MLflow endpoints
- Depends on: .env file
- Used by: All modules
## Data Flow
- **Kafka Offsets:** Spark checkpoints track streaming position automatically
- **Window State:** Spark manages 1-hour window state in memory with watermarking
- **Model State:** Cached in Spark UDF (FraudScorer instance per partition)
- **Preprocessing State:** Loaded once from joblib, cached in memory
## Key Abstractions
- Purpose: Simulate realistic fraud patterns (velocity, impossible travel, unusual amounts)
- Examples: `src/data_generator/transaction_generator.py`
- Pattern: Generates transactions with configurable fraud_rate and user profiles
- Outputs: Dict with transaction fields (transaction_id, user_id, amount, etc.)
- Purpose: Encapsulate preprocessing + model inference
- Examples: `src/serving/model_scorer.py`
- Pattern: Loads artifacts on __init__, exposes .preprocess() and .score() methods
- Critical: Ensures training-serving consistency (same scaler, encoders, feature order)
- Purpose: Reusable computation for both streaming and batch
- Examples: `src/streaming/feature_engineering.py`
- Pattern: Pure Spark SQL/UDF functions, partition-aware windowing
- Streaming: windowed aggregations with watermarking
- Batch: lag-based location features using window functions
- Purpose: Reliable message sending with callback handling
- Examples: `src/data_generator/kafka_producer.py`
- Pattern: FraudTransactionProducer class with configurable TPS, graceful shutdown
- Ensures: acks='all', user_id as partition key, JSON serialization
## Entry Points
- Location: `src/data_generator/kafka_producer.py`
- Triggers: `make producer` or `python -m src.data_generator.kafka_producer`
- Responsibilities: Generates transactions at configurable rate, publishes to Kafka
- Location: `src/streaming/spark_consumer.py`
- Triggers: `make stream` or `python -m src.streaming.spark_consumer --debug`
- Responsibilities: Continuously reads Kafka, computes features, scores, writes outputs
- Command-line args: --broker, --topic, --output-parquet, --output-topic, --debug
- Location: `src/training/prepare_data.py`
- Triggers: `make prepare-data` or `python -m src.training.prepare_data`
- Responsibilities: Generates historical data, applies features, creates stratified splits
- Location: `src/training/train_model.py`
- Triggers: `make train` or `python -m src.training.train_model`
- Responsibilities: Trains 4 models, logs metrics to MLflow, registers best model
- Location: `src/data_generator/register_schemas.py`
- Triggers: `make register-schemas`
- Responsibilities: Registers JSON schema for transaction validation
## Error Handling
- **Parse Errors** → Messages sent to `transactions-dlq` for manual inspection
- **Scoring Failures** → Fallback to fraud_score=-1 (triggers manual review)
- **Missing Features** → fillna(0) for numeric, unknown categories → index 0
- **Kafka Connection** → Retry with exponential backoff (up to 5 attempts)
- **Graceful Shutdown** → Signal handlers (SIGINT, SIGTERM) flush and close cleanly
## Cross-Cutting Concerns
- Framework: Python logging + Spark logging
- Approach: print() statements for major pipeline stages; Spark logs set to WARN level
- Recommendation: Should migrate to structured logging (JSON) for production
- Schema Registry validates Kafka messages against JSON schema
- Spark's .filter(data.isNotNull()) catches malformed records
- Type checking in feature engineering with .cast()
- MLflow S3 access via AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY environment variables
- Schema Registry accessed via HTTP (no auth in docker-compose)
- Kafka plaintext protocol (suitable for internal networks only)
- MLflow tracks all model experiments (metrics, parameters, artifacts)
- Kafka consumer lag can be monitored via Confluent command-line tools
- Manual metrics reporting: sent_count, error_count in producer
- Recommendation: Add Prometheus metrics export for production
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
