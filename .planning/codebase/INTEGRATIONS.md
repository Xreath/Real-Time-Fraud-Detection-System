# External Integrations

**Analysis Date:** 2026-03-20

## APIs & External Services

**Schema Registry (Confluent):**
- Service: Confluent Schema Registry 7.6.0
- What it's used for: Validates transaction message format before writing to Kafka; enforces schema evolution
- SDK/Client: requests (HTTP REST API)
- Authentication: None (basic auth can be configured)
- Implementation: `src/data_generator/register_schemas.py`
  - Registers JSON Schema for `transactions-value` subject
  - Sets compatibility mode to BACKWARD (new schema reads old data)
  - URL configured via `SCHEMA_REGISTRY_URL` env var (default: `http://localhost:8085`)

## Data Storage

**Databases:**

1. **PostgreSQL 16 (MLflow Metadata Store):**
   - Connection: `postgresql://mlflow:mlflow123@postgres:5432/mlflow`
   - Configured via docker-compose environment variables:
     - POSTGRES_USER
     - POSTGRES_PASSWORD
     - POSTGRES_DB
   - Purpose: Stores MLflow experiment runs, metrics, parameters, tags
   - Client: MLflow (uses psycopg2-binary driver)
   - Host: `postgres` (Docker service name)
   - Port: `5432`

**File Storage:**

1. **MinIO (S3-Compatible Artifact Store):**
   - Service: MinIO latest
   - Purpose: Stores MLflow model artifacts, training plots, SHAP plots
   - Bucket: `mlflow-artifacts`
   - Credentials:
     - MINIO_ROOT_USER - Default: `minioadmin`
     - MINIO_ROOT_PASSWORD - Default: `minioadmin`
   - Endpoint: `http://minio:9000` (internal), `localhost:9000` (external)
   - Console: `localhost:9001`
   - Configuration in MLflow: `--default-artifact-root s3://mlflow-artifacts/`
   - Client: boto3 (AWS SDK for Python)

2. **Local Filesystem:**
   - `data/` directory - Local storage for Parquet files (splits, features)
   - `data/checkpoints/` - Spark Structured Streaming checkpoint directory
   - `mlruns/` - Local MLflow backend (can be disabled with remote backend)

**Caching:**
- None (Kafka topics act as distributed event log)

## Message Broker

**Apache Kafka (Confluent Platform 7.6.0):**
- Bootstrap servers: `kafka:29092` (internal), `localhost:9092` (external)
- Topics created:
  1. `transactions` - Raw transaction events from producer (3 partitions, 7-day retention)
  2. `fraud-alerts` - Fraud detection results (3 partitions, 30-day retention)
  3. `features` - Computed feature vectors (3 partitions, 7-day retention)
  4. `transactions-dlq` - Dead letter queue for unparseable messages (1 partition, 7-day retention)
- Producers: `src/data_generator/kafka_producer.py` (FraudTransactionProducer)
- Consumers:
  - `src/data_generator/kafka_consumer_debug.py` - Debug consumer (reads transactions)
  - `src/streaming/spark_consumer.py` - Spark Structured Streaming (reads transactions, writes features)
- Configuration:
  - Partitioning key: `user_id` (ensures order per user)
  - Serialization: JSON
  - Producer acks: `all` (waits for all replicas)
  - Auto topic creation: disabled (`KAFKA_AUTO_CREATE_TOPICS_ENABLE=false`)

**Zookeeper (Confluent 7.6.0):**
- Purpose: Cluster coordination for Kafka
- Internal port: `2181`
- Configuration: ZOOKEEPER_CLIENT_PORT, ZOOKEEPER_TICK_TIME=2000ms

**Schema Registry (Confluent 7.6.0):**
- Purpose: Schema validation and evolution management
- Internal port: `8081`, external: `8085`
- Features used:
  - JSON Schema format (not Avro)
  - Schema subject: `transactions-value`
  - Compatibility level: BACKWARD
- Endpoints:
  - Register schema: POST `/subjects/{subject}/versions`
  - Get schema: GET `/subjects/{subject}/versions`
  - Check health: GET `/`

## Stream Processing

**Apache Spark Structured Streaming:**
- Master: `spark://spark-master:7077`
- Cluster: 1 master + 1 worker
- Consumer: `src/streaming/spark_consumer.py`
- Kafka integration: org.apache.spark:spark-sql-kafka-0-10 connector (Scala 2.12 for Spark 3.5)
- Processing mode: Micro-batch (10-second intervals)
- Checkpoint location: `data/checkpoints`
- Features computed: `src/streaming/feature_engineering.py`
  - Transaction-level features (amount transformations, temporal patterns)
  - Windowed aggregations (user behavior patterns over 1 hour and 24 hours)
- Output: Parquet files + Kafka (features topic)

## Experiment Tracking & Model Registry

**MLflow:**
- Server: `http://localhost:5001` (public), `http://mlflow:5000` (internal)
- Backend: PostgreSQL (metadata) + MinIO (artifacts)
- Experiment name: `fraud-detection` (default, configurable via env var)
- Models tracked:
  - LogisticRegression (baseline)
  - RandomForestClassifier
  - XGBoost
  - LightGBM
- Logged artifacts: training plots, confusion matrices, SHAP plots, label encoders, scalers
- Implementation:
  - Training: `src/training/train_model.py` - Uses mlflow.log_metrics, mlflow.log_artifact
  - Hyperparameter tuning: `src/training/tune_hyperparams.py` - Uses Optuna + MLflow
  - Serving: `src/serving/model_scorer.py` - Loads model from Model Registry
- Version control: Model Registry tracks model versions and stages

## Workflow Orchestration

**Apache Airflow (commented out in current setup):**
- Configuration: `airflow/` directory present
- Purpose: Schedule training, scoring, retraining pipelines
- Status: Not actively integrated in current phase; setup for Phase 6+

## Authentication & Identity

**Auth Provider:**
- None - No external identity provider integrated
- Internal access: Docker network (container-to-container communication via service names)
- External access: Localhost/custom hostname (no auth required in dev setup)
- Production consideration: Would require adding auth to Kafka, Schema Registry, MLflow endpoints

## Monitoring & Observability

**Error Tracking:**
- None (external service)
- Local logging via Python logging and MLflow logs

**Logs:**
- Docker logs: `docker compose logs [service]`
- Accessible via Makefile: `make logs`, `make logs-kafka`, `make logs-spark`, `make logs-mlflow`
- Log levels:
  - Spark: WARN (configured in spark_consumer.py)
  - Python: Default (can be adjusted via logging configuration)

**Spark Web UI:**
- Master: `http://localhost:8080` (Spark Master dashboard)
- Worker access via master UI

**MLflow UI:**
- URL: `http://localhost:5001`
- Features: View experiments, compare runs, register models, inspect artifacts

## CI/CD & Deployment

**Hosting:**
- Docker Compose (local development)
- Target deployment: Google Cloud Platform (AI Platform) - Phase 6+
  - Commented imports in requirements.txt: google-cloud-aiplatform, google-cloud-storage

**CI Pipeline:**
- None configured (future phase)

**Docker Images:**
- `confluentinc/cp-zookeeper:7.6.0`
- `confluentinc/cp-kafka:7.6.0`
- `confluentinc/cp-schema-registry:7.6.0`
- `apache/spark:3.5.4`
- `postgres:16-alpine`
- `minio/minio:latest` (with init container `minio/mc:latest`)
- Custom: `Dockerfile.mlflow` (based on `ghcr.io/mlflow/mlflow:v2.12.2`)

## Environment Configuration

**Required env vars:**
- KAFKA_BROKER - Kafka bootstrap servers
- SCHEMA_REGISTRY_URL - Schema Registry endpoint
- SPARK_MASTER_URL - Spark Master address
- MLFLOW_TRACKING_URI - MLflow server URL
- MLFLOW_EXPERIMENT_NAME - Experiment identifier
- GENERATOR_TRANSACTIONS_PER_SEC - Throughput (default: 10 tx/sec)
- GENERATOR_FRAUD_RATE - Fraud label ratio (default: 0.02)
- POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB - MLflow backend DB
- MINIO_ROOT_USER, MINIO_ROOT_PASSWORD - MinIO credentials
- AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY - S3/MinIO credentials for MLflow

**Secrets location:**
- `.env` file in project root (Git-ignored, contains environment configuration)
- Docker compose service environment variables
- No external secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.) in current setup

## Data Flow & Integration Patterns

**Ingestion Pipeline:**
```
TransactionGenerator → KafkaProducer → Kafka (transactions topic) → Schema Registry validation
```

**Processing Pipeline:**
```
Kafka (transactions) → Spark Structured Streaming → Feature Engineering →
  Parquet (local) + Kafka (features topic)
```

**Training Pipeline:**
```
Parquet files → Data preparation → scikit-learn/XGBoost models →
  MLflow experiment tracking → PostgreSQL + MinIO artifact store → Model Registry
```

**Serving Pipeline:**
```
MLflow Model Registry → Load fitted model + preprocessors →
  Apply feature engineering → Fraud score prediction
```

## Webhooks & Callbacks

**Incoming:**
- None configured

**Outgoing:**
- None configured
- Future: Fraud alerts could be sent to external systems (email, Slack, payment system)

## Scalability Considerations

**Current Limitations:**
- Single Spark worker (2 cores, 2GB memory) - suitable for development
- Single Kafka partition processing - no parallelism across partitions
- MinIO local storage - not highly available
- PostgreSQL single instance - no replication

**Scaling Path:**
- Kafka: Add more partitions per topic, scale consumers
- Spark: Increase worker nodes, allocate more CPU/memory
- MLflow: External PostgreSQL with replication, S3 for artifacts
- Feature Store: Migrate to dedicated solution (Tecton, Feast)
- Deployment: Kubernetes with horizontal scaling policies

---

*Integration audit: 2026-03-20*
