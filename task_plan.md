# Real-Time Fraud Detection System - Task Plan

## Project Overview
Gerçek zamanlı kredi kartı sahtecilik tespit sistemi. Kafka, Spark Streaming, MLflow ve Cloud deployment kullanarak end-to-end MLOps pipeline.

## Proje Amacı: ÖĞRENME
Bu proje bir **öğrenme/portfolio projesidir**. Amaçlar:
- Kafka, Spark, MLflow, Airflow, Vertex AI teknolojilerini pratikte öğrenmek
- End-to-end MLOps pipeline deneyimi kazanmak
- Mülakatlarda anlatılabilecek gerçekçi bir proje oluşturmak

**Yaklaşım:** Her adımda "ne" yapıldığı kadar "neden" yapıldığı da açıklanacak. Kod içinde öğretici yorumlar, her faz sonunda öğrenilen kavramların özeti yer alacak.

## Architecture
```
[Faker/Python] → [Kafka] → [Spark Streaming] → [Feature Store] → [ML Model] → [API Endpoint]
                                                                        ↑
                                                               [MLflow Tracking]
                                                                        ↑
                                                               [Airflow DAG]
```

---

## Phase 1: Project Setup & Infrastructure
**Status:** complete

### Task 1.1: Project Structure & Dependencies
- [x] Create project directory structure
- [x] Setup Python virtual environment (uv + .venv)
- [x] Create requirements.txt / pyproject.toml
- [x] Create Docker Compose for Kafka, Zookeeper, Spark, MLflow
- [x] Create .env file for configuration
- [x] Create Makefile for common commands

### Task 1.2: Docker Infrastructure
- [x] Kafka + Zookeeper container setup
- [x] Spark master + worker containers
- [x] MLflow tracking server container
- [x] PostgreSQL (MLflow backend store)
- [x] MinIO/S3 (MLflow artifact store - local S3 alternative)
- [x] docker-compose.yml with all services
- [x] kafka-init container (topic otomatik oluşturma)
- [x] minio-init container (bucket otomatik oluşturma)

> **Bilinen Trade-off'lar (Bilinçli Kararlar):**
> - **Zookeeper**: Kafka 3.0+ KRaft modu ile Zookeeper'a gerek yok. Bu projede Confluent 7.6.0 + Zookeeper kullanılıyor çünkü Confluent'ın managed platform'u hâlâ Zookeeper ile daha stabil. KRaft'a geçiş yapılabilir ama mülakatta "farkındayım, KRaft daha modern" demek yeterli.
> - **MinIO vs GCS**: Training local (MinIO), deployment cloud (GCS/Vertex AI). İki farklı ortam, bilinçli ayrım. Production'da her şey GCS'e taşınır.

---

## Phase 2: Data Generation (Faker)
**Status:** complete

### Task 2.1: Transaction Data Generator
- [x] Design transaction schema (user_id, amount, merchant, location, timestamp, card_type)
- [x] Implement realistic transaction patterns (normal vs fraudulent)
- [x] Add fraud patterns:
  - Unusual amounts (too high / round numbers)
  - Geographically impossible travel
  - Foreign country transactions
  - Late night + high amount
- [x] Label generator (is_fraud flag with ~2% fraud rate)
- [x] Configurable generation speed (transactions/sec)

### Task 2.2: Kafka Producer
- [x] Connect to Kafka broker
- [x] Serialize transactions to JSON
- [x] Send to "transactions" topic
- [x] Add error handling and retry logic
- [x] Metrics: messages sent/sec, errors

---

## Phase 3: Kafka Streaming Layer
**Status:** complete

### Task 3.1: Kafka Topic Configuration
- [x] Create "transactions" topic (partitioned by user_id for ordering)
- [x] Create "fraud-alerts" topic (for detected frauds)
- [x] Create "features" topic (for computed features)
- [x] Configure retention, replication, partitions
- [x] Schema Registry setup (JSON Schema) → container healthy, transactions-value schema id=1 kayıtlı, BACKWARD compatibility

### Task 3.2: Kafka Consumer Verification
- [x] Simple consumer script for debugging (kafka_consumer_debug.py)
- [x] Monitor topic lag and throughput (partition dağılımı raporlaması)
- [x] Test producer → consumer pipeline (E2E test: 213 mesaj, 3 partition)

---

## Phase 4: Spark Streaming & Feature Engineering
**Status:** complete

### Task 4.1: Spark Structured Streaming Setup
- [x] Configure Spark to read from Kafka (spark_consumer.py)
- [x] Parse JSON messages (TRANSACTION_SCHEMA)
- [x] Watermarking for late data handling (10 minutes)
- [x] **Error Handling & Recovery**:
  - Checkpoint location → `/data/checkpoints/` (Spark state recovery)
  - [x] DLQ: parse edilemeyen mesajlar → `transactions-dlq` topic'ine yazılır
  - [x] Model inference hatasında fallback: score = -1 (manual_review)
  - Job crash sonrası otomatik restart → Phase 7 (Airflow sensor) ile

### Task 4.2: Feature Engineering Pipeline
- [x] **Windowed Features (1-hour window):**
  - Transaction count per user (last 1h)
  - Total amount per user (last 1h)
  - Average transaction amount (last 1h)
  - Unique merchant count (last 1h)
  - Unique locations count (last 1h)
- [x] **Location Features:**
  - Distance from last transaction (haversine)
  - Speed between transactions (km/h) - impossible travel detection
  - Number of unique locations (last 1h)
- [x] **Transaction Features:**
  - Amount deviation from user average (z-score)
  - Time since last transaction (dakika)
  - Is weekend / night transaction (generator'dan)
  - Foreign country flag (generator'dan)
- [x] Write features to "features" topic + **Parquet** dosyaları (local `/data/features/`)
  > Delta Lake değil düz Parquet: ACID/time-travel bu proje için overkill. İleride Delta Lake'e geçiş mümkün.

### Task 4.3: Real-Time Scoring
- [x] Load trained model in Spark (FraudScorer + pandas_udf)
- [x] Score each transaction in real-time (LightGBM predict_proba)
- [x] Write fraud alerts to "fraud-alerts" topic (threshold >= 0.5)
- [x] Preprocessing artifacts (scaler, label_encoders) kaydedildi → `data/artifacts/`
- [ ] Latency monitoring (< 500ms target) → Phase 8 ile

---

## Phase 5: ML Model Training & MLflow
**Status:** complete

### Task 5.1: Historical Data Preparation
- [x] Generate labeled historical dataset (100K transactions)
- [x] Train/validation/test split (stratified: 70/10/20, fraud oranı korundu)
- [x] Feature preprocessing pipeline (StandardScaler + LabelEncoder)
- [x] Handle class imbalance (class_weight="balanced" + scale_pos_weight=48.3)

### Task 5.2: Model Training with MLflow Tracking
- [x] Setup MLflow experiment ("fraud-detection")
- [x] Train models:
  - Logistic Regression (baseline) → F1=0.935
  - Random Forest → F1=0.995
  - XGBoost → F1=0.990
  - LightGBM → F1=0.993 ★ (AUC-PR en yüksek)
- [x] Log for each run:
  - Hyperparameters
  - Metrics (precision, recall, F1, AUC-ROC, AUC-PR)
  - Confusion matrix
  - Feature importance (top 10)
  - Model artifact
- [x] Hyperparameter tuning (Optuna) → 20 trial, AUC-PR=0.9970
- [x] Compare models in MLflow UI (http://localhost:5001)

### Task 5.3: MLflow Model Registry
- [x] Register best model in MLflow Model Registry (fraud-detection-model v1)
- [x] Set model stages: Production (v1)
- [x] Model versioning (v1 = LightGBM)
- [x] Model signature and input example (infer_signature + input_example)

---

## Phase 6: Model Deployment (Cloud Endpoint)
**Status:** pending

### Task 6.1: Local Deployment (MLflow Serve)
- [ ] Serve model locally with `mlflow models serve`
- [ ] REST API for predictions
- [ ] Test endpoint with sample transactions
- [ ] Load testing (requests/sec)

### Task 6.2: Cloud Deployment (GCP Vertex AI)
- [ ] GCP Project setup & authentication (gcloud CLI)
- [ ] Upload model to Vertex AI Model Registry
- [ ] Deploy to Vertex AI Endpoint
- [ ] Auto-scaling configuration
- [ ] Cloud Monitoring setup
- [ ] A/B testing setup (traffic splitting)

---

## Phase 7: Airflow Orchestration
**Status:** pending

### Task 7.1: Airflow Setup
- [ ] Add Airflow to Docker Compose
- [ ] Configure Airflow connections (Kafka, Spark, MLflow, Cloud)
- [ ] Create DAGs directory structure

### Task 7.2: Retraining DAG (HYBRID Strategy)
- [ ] **Scheduled trigger**: Her Pazar gecesi 02:00 (weekly cron)
- [ ] **Performance trigger**: F1 < 0.85 olduğunda anında tetikleme
- [ ] DAG Steps:
  1. Validation set üzerinde mevcut modeli test et
  2. F1 < 0.85 VEYA scheduled gün ise → devam
  3. **Data quality checks** (detay aşağıda)
  4. Yeni veriyi feature store'dan çek (Parquet)
  5. Model retrain (hyperparameter search dahil)
  6. Yeni model > eski model ise → MLflow Registry promote
  7. Vertex AI endpoint güncelle (yeni model version)
  8. Sonuç raporu logla + Slack notification
- [ ] Alerting on DAG failures (email/Slack)
- [ ] **Data Quality Checks** (training öncesi):
  - Null/missing value oranı < %5 kontrolü
  - Fraud rate kontrolü (beklenen ~%2, sapma varsa alert)
  - Schema uyumluluk kontrolü (feature sayısı, tipler)
  - Outlier tespiti (amount > 3 std dev → flag, drop değil)
  - Minimum veri miktarı kontrolü (< 1000 satırsa train etme)
  - Class imbalance kontrolü (fraud sayısı < 10 ise skip)
- [ ] **Rollback Mekanizması**:
  - Yeni model deploy öncesi production model version'ı kaydet
  - Deploy sonrası 1 saat A/B test (traffic %10 yeni model)
  - Eğer yeni model F1 < eski model F1 * 0.95 → otomatik rollback
  - MLflow'dan previous "Production" model tag'ini çek → Vertex AI'ya re-deploy
  - Rollback durumunda Slack alert + DAG failure log

### Task 7.3: Monitoring DAG (Daily)
- [ ] Her gün F1-score kontrolü (validation set üzerinde)
- [ ] Data drift detection (KS test, PSI - feature dağılım karşılaştırma)
- [ ] Concept drift detection (F1 trend - sliding window)
- [ ] Fraud rate anomaly detection (günlük fraud oranı normal mi?)
- [ ] Alert: F1 < 0.85 → retrain tetikle + Slack
- [ ] Alert: Data drift tespit → uyarı
- [ ] Grafana dashboard'a metric push

---

## Phase 8: Monitoring & Dashboard
**Status:** pending

### Task 8.1: Grafana Dashboard (Optional)
- [ ] Transaction throughput (real-time)
- [ ] Fraud detection rate
- [ ] Model latency
- [ ] Kafka consumer lag
- [ ] Spark processing time

### Task 8.2: Alerting
- [ ] High fraud rate alert
- [ ] System health alerts
- [ ] Model performance degradation alert

---

## Technology Stack Summary
| Component | Technology |
|-----------|-----------|
| Data Generation | Python, Faker |
| Message Broker | Apache Kafka |
| Stream Processing | Apache Spark (Structured Streaming) |
| ML Training | XGBoost, LightGBM, Scikit-learn |
| Experiment Tracking | MLflow |
| Model Registry | MLflow Model Registry |
| Orchestration | Apache Airflow |
| Cloud Deployment | GCP Vertex AI |
| Containerization | Docker, Docker Compose |
| Monitoring | Grafana (optional) |
| Feature Store | Delta Lake / Parquet |

---

## Implementation Order
1. Phase 1 → Project setup, Docker infra
2. Phase 2 → Data generator + Kafka producer
3. Phase 3 → Kafka topics + verification
4. Phase 4 → Spark streaming + features
5. Phase 5 → ML training + MLflow
6. Phase 6 → Deployment (local first, then cloud)
7. Phase 7 → Airflow automation
8. Phase 8 → Monitoring (bonus)

## Estimated File Structure
```
realtime_fraud_detection/
├── docker-compose.yml
├── Makefile
├── requirements.txt
├── .env
├── README.md
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── data_generator/
│   │   ├── __init__.py
│   │   ├── transaction_generator.py
│   │   └── kafka_producer.py
│   ├── streaming/
│   │   ├── __init__.py
│   │   ├── spark_consumer.py
│   │   └── feature_engineering.py
│   ├── training/
│   │   ├── __init__.py
│   │   ├── prepare_data.py
│   │   ├── train_model.py
│   │   └── evaluate.py
│   ├── serving/
│   │   ├── __init__.py
│   │   ├── local_serve.py
│   │   └── cloud_deploy.py
│   └── utils/
│       ├── __init__.py
│       └── helpers.py
├── airflow/
│   └── dags/
│       ├── retrain_dag.py
│       └── monitoring_dag.py
├── notebooks/
│   └── exploration.ipynb
├── tests/
│   ├── test_generator.py
│   ├── test_features.py
│   └── test_model.py
└── configs/
    ├── kafka_config.yaml
    └── spark_config.yaml
```
