# Technology Stack - Gerçek Zamanlı Sahtecilik Tespit Sistemi

> **ÖĞRENME PROJESİ** - Bu proje production değil, öğrenme amaçlıdır.
> - Kod içinde açıklayıcı yorumlar olacak (ne + neden)
> - Her faz sonunda "Bu fazda ne öğrendik?" özeti yazılacak
> - Mülakatta anlatılabilecek şekilde tasarlanmıştır
> - Basitlik tercih edilir: kafka-python (confluent değil), JSON (Avro değil), Parquet (Delta Lake değil)

## 1. Python Ecosystem (Core Language)

### Python 3.11+
- Projenin ana dili
- Tüm bileşenler Python ile yazılacak

### Paket Yönetimi
- **uv + .venv** (virtual environment) — pip'ten ~10x hızlı
- `requirements.txt` ile dependency management

---

## 2. Data Generation

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **Faker** | 24.x | Rastgele kullanıcı, adres, kredi kartı verisi üretimi |
| **uuid** | stdlib | Unique transaction ID üretimi |
| **random** | stdlib | Fraud pattern'leri ve olasılık kontrolü |

---

## 3. Message Broker - Apache Kafka

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **Apache Kafka** | 3.7.x | Message broker - transaction event'lerini taşır |
| **Zookeeper** | 3.9.x | Kafka cluster coordination (Kafka 3.x hala kullanıyor) |
| **kafka-python** | 2.0.x | Python Kafka producer/consumer client |
| **confluent-kafka** | (alternatif) | Daha performanslı C-based Python client |

**Kafka Neden?**
- High throughput (saniyede yüz binlerce mesaj)
- Mesaj kaybı yok (durable, replicated)
- Partition ile paralel işleme
- Consumer group ile load balancing

---

## 4. Stream Processing - Apache Spark

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **Apache Spark** | 3.5.x | Distributed data processing engine |
| **Spark Structured Streaming** | (Spark içinde) | Real-time stream processing |
| **PySpark** | 3.5.x | Spark'ın Python API'si |
| **spark-sql-kafka** | 3.5.x | Spark ↔ Kafka connector |

**Spark Neden?**
- Windowed aggregations (1 saatlik pencere hesaplamaları)
- Fault-tolerant streaming (checkpoint + watermark)
- Büyük veri setlerinde hızlı feature engineering
- ML modeli ile entegre scoring

---

## 5. Machine Learning

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **scikit-learn** | 1.4.x | Preprocessing, Logistic Regression, Random Forest |
| **XGBoost** | 2.0.x | Gradient boosting model (ana model) |
| **LightGBM** | 4.x | Alternatif gradient boosting model |
| **imbalanced-learn** | 0.12.x | SMOTE - class imbalance handling |
| **pandas** | 2.2.x | Data manipulation, feature preparation |
| **numpy** | 1.26.x | Numerical computations |

**Model Seçim Mantığı:**
- Logistic Regression → baseline (karşılaştırma için)
- Random Forest → interpretable ensemble
- XGBoost → genelde en iyi performans (tabular data)
- LightGBM → hız avantajı, büyük veri setleri

---

## 6. Experiment Tracking & Model Registry - MLflow

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **MLflow** | 2.x | Experiment tracking, model registry, model serving |
| **MLflow Tracking** | (MLflow içinde) | Metric, parametre, artifact loglama |
| **MLflow Models** | (MLflow içinde) | Model paketleme ve serve etme |
| **MLflow Registry** | (MLflow içinde) | Model versiyonlama (Staging → Production) |

**MLflow Neden?**
- Her deneyi kaydeder (hangi parametre → hangi sonuç)
- Model versiyonlarını yönetir
- UI ile görsel karşılaştırma
- Model serve (REST API) desteği

---

## 7. Cloud Deployment - GCP Vertex AI

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **Google Cloud SDK (gcloud)** | latest | GCP CLI erişimi |
| **google-cloud-aiplatform** | 1.x | Vertex AI Python SDK |
| **Vertex AI Model Registry** | - | Model yükleme ve versiyonlama |
| **Vertex AI Endpoints** | - | Model serving (REST API) |
| **Cloud Storage (GCS)** | - | Model artifact depolama |

**Vertex AI Neden?**
- Managed model serving (sunucu yönetimi yok)
- Auto-scaling (trafik arttıkça otomatik ölçekleme)
- A/B testing (traffic splitting)
- Monitoring dashboard built-in

---

## 8. Orchestration - Apache Airflow

| Tool | Versiyon | Görevi |
|------|---------|--------|
| **Apache Airflow** | 2.8.x | Workflow orchestration |
| **airflow-providers-google** | - | GCP Vertex AI operatörleri |
| **airflow-providers-apache-spark** | - | Spark job submit operatörleri |

**Airflow Neden?**
- DAG ile görsel pipeline tanımlama
- Schedule (her gece model retrain)
- Retry, alerting, dependency management
- Web UI ile monitoring

---

## 9. Infrastructure & DevOps

| Tool | Görevi |
|------|--------|
| **Docker** | Container'lar ile izole çalışma ortamı |
| **Docker Compose** | Multi-container orchestration (local dev) |
| **Makefile** | Sık kullanılan komutları kısayol yapma |

---

## 10. Data Storage

| Tool | Görevi |
|------|--------|
| **PostgreSQL** | MLflow backend store (experiment metadata) |
| **MinIO** | Local S3-compatible storage (MLflow artifacts) |
| **Parquet** | Feature store format (columnar, compressed) |
| **Delta Lake** | (opsiyonel) ACID transactions on Parquet |

---

## 11. Monitoring & Visualization (Bonus)

| Tool | Görevi |
|------|--------|
| **Grafana** | Dashboard ve alerting |
| **Prometheus** | Metric collection |
| **matplotlib/seaborn** | Model performance grafikleri |

---

## Docker Compose Services Özeti

```
┌─────────────────────────────────────────────────────┐
│                  Docker Compose                      │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │Zookeeper │  │  Kafka    │  │ Spark Master     │  │
│  │ :2181    │  │  :9092    │  │ :7077 / :8080    │  │
│  └──────────┘  └───────────┘  └──────────────────┘  │
│                                                      │
│  ┌──────────────┐  ┌──────────┐  ┌──────────────┐   │
│  │Spark Worker  │  │ MLflow   │  │ PostgreSQL   │   │
│  │              │  │ :5000    │  │ :5432        │   │
│  └──────────────┘  └──────────┘  └──────────────┘   │
│                                                      │
│  ┌──────────┐  ┌───────────┐  ┌──────────────────┐  │
│  │ MinIO    │  │ Airflow   │  │ Grafana          │  │
│  │ :9000    │  │ :8081     │  │ :3000            │  │
│  └──────────┘  └───────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## Python Requirements (Tahmini)

```
# Core
python>=3.11

# Data Generation
faker>=24.0
kafka-python>=2.0.2

# Spark
pyspark>=3.5.0

# ML
scikit-learn>=1.4.0
xgboost>=2.0.0
lightgbm>=4.0.0
imbalanced-learn>=0.12.0
pandas>=2.2.0
numpy>=1.26.0

# MLflow
mlflow>=2.12.0

# GCP
google-cloud-aiplatform>=1.50.0
google-cloud-storage>=2.16.0

# Airflow (Docker'da ayrı kurulacak)
apache-airflow>=2.8.0
apache-airflow-providers-google
apache-airflow-providers-apache-spark

# Visualization
matplotlib>=3.8.0
seaborn>=0.13.0

# Utils
python-dotenv>=1.0.0
pyyaml>=6.0.0
```

---

## Kritik Kararlar & Notlar

### 1. Kafka Client → kafka-python ✅
- Pure Python, kurulumu kolay, öğrenme amaçlı ideal

### 2. Feature Store → Parquet ✅
- Basit, hızlı, columnar format. İhtiyaç olursa Delta Lake'e geçilebilir.

### 3. Mesaj Formatı → JSON ✅
- Basit, okunabilir, debug kolay. Production'da Avro'ya geçilebilir.

### 4. Orchestration → Airflow ✅
- Endüstri standardı, CV için en değerli

### 5. Monitoring → Grafana + Prometheus ✅ (baştan dahil)
- Docker Compose'a baştan eklenecek, tüm servisler izlenecek
