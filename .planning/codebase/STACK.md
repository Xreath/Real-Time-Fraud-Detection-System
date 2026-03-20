# Technology Stack

**Analysis Date:** 2026-03-20

## Languages

**Primary:**
- Python 3.x - Core application, data generation, ML training, streaming consumer
- YAML - Configuration management for Kafka and Spark
- JSON - Schema definitions (Confluent Schema Registry), configuration

## Runtime

**Environment:**
- Python 3.x (installed via `uv` package manager)
- Java 11 (required by Spark and Kafka)

**Package Manager:**
- `uv` - Fast Python package manager (referenced in Makefile)
- `pip` - Secondary package installation via uv
- Lockfile: `.venv` virtual environment present

## Frameworks

**Core:**
- PySpark 3.5.0+ - Distributed stream processing with Structured Streaming
- kafka-python 2.0.2+ - Kafka producer/consumer client

**ML/Training:**
- scikit-learn 1.4.0+ - Baseline models (LogisticRegression), preprocessing (StandardScaler, LabelEncoder)
- XGBoost 2.0.0+ - Gradient boosting classifier
- LightGBM 4.0.0+ - Gradient boosting (alternative to XGBoost)
- Optuna 4.0.0+ - Bayesian hyperparameter tuning
- imbalanced-learn 0.12.0+ - Class imbalance handling (SMOTE capability)
- joblib 1.3.0+ - Model and artifact serialization

**Experiment Tracking & Model Registry:**
- MLflow 2.12.0+ - Experiment tracking, model versioning, model serving
  - Backend: PostgreSQL 16 (metadata store)
  - Artifact store: MinIO (S3-compatible)
  - Server: Docker image ghcr.io/mlflow/mlflow:v2.12.2

**Visualization & Explainability:**
- matplotlib 3.8.0+ - Plotting (non-interactive Agg backend for servers)
- seaborn 0.13.0+ - Statistical visualization
- shap 0.45.0+ - Model explainability (SHAP values)

**Utilities:**
- python-dotenv 1.0.0+ - Environment variable loading from .env
- pyyaml 6.0.0+ - YAML parsing
- pandas 2.2.0+ - Data manipulation and analysis
- numpy 1.26.0+ - Numerical computing
- requests 2.31.0+ - HTTP requests (Schema Registry API calls)

**Data Generation:**
- Faker 24.0+ - Realistic synthetic transaction data generation

## Key Dependencies

**Critical:**
- kafka-python - Bridges application to Kafka cluster; without it, data ingestion fails
- pyspark - Distributed stream processing; core of real-time pipeline
- mlflow - Enables reproducible model tracking and deployment; without it no experiment history
- scikit-learn - ML model training; critical for fraud detection algorithms
- pandas/numpy - Data manipulation; used across all data processing stages

**Infrastructure:**
- boto3 1.34.0+ - S3/MinIO client for artifact storage with MLflow

## Configuration

**Environment:**
- `.env` file present - Contains environment variables for all services
- Configuration via `src/config.py` - Centralizes all settings with sensible defaults:
  - KAFKA_BROKER - Default: `localhost:9092`
  - KAFKA_TOPIC_TRANSACTIONS - Default: `transactions`
  - KAFKA_TOPIC_FRAUD_ALERTS - Default: `fraud-alerts`
  - KAFKA_TOPIC_FEATURES - Default: `features`
  - KAFKA_TOPIC_DLQ - Default: `transactions-dlq` (dead letter queue)
  - SCHEMA_REGISTRY_URL - Default: `http://localhost:8085`
  - SPARK_MASTER_URL - Default: `spark://spark-master:7077`
  - MLFLOW_TRACKING_URI - Default: `http://localhost:5001`
  - MLFLOW_EXPERIMENT_NAME - Default: `fraud-detection`
  - GENERATOR_TRANSACTIONS_PER_SEC - Default: `10`
  - GENERATOR_FRAUD_RATE - Default: `0.02` (2%)

**Build:**
- Dockerfile.mlflow - Custom MLflow image with psycopg2-binary and boto3
- docker-compose.yml - Orchestrates all services (Kafka, Spark, MLflow, PostgreSQL, MinIO)

## Platform Requirements

**Development:**
- Docker Engine - For running containerized services
- Docker Compose - For multi-container orchestration
- Python 3.x with venv support
- Make - For convenient command shortcuts

**Production:**
- Docker/Kubernetes for container orchestration
- PostgreSQL 16 (or compatible) - MLflow metadata store
- MinIO or AWS S3 - MLflow artifact repository
- Apache Kafka 7.6.0+ (Confluent CP) - Message broker
- Apache Spark 3.5.4+ - Stream processing cluster
- Zookeeper 7.6.0 - Kafka coordination

## Services & Versions

**Message Broker:**
- Kafka (Confluent): 7.6.0
- Zookeeper: 7.6.0
- Schema Registry: 7.6.0

**Stream Processing:**
- Apache Spark: 3.5.4 (master + worker setup)

**Metadata & Artifacts:**
- PostgreSQL: 16 (Alpine)
- MinIO: latest

**Monitoring & Tracking:**
- MLflow: 2.12.2 (custom image)

---

*Stack analysis: 2026-03-20*
