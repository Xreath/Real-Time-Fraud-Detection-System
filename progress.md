# Progress Tracker

> **Proje Tipi:** Öğrenme / Portfolio Projesi
> **Hedef:** Kafka, Spark, MLflow, Airflow, Vertex AI pratik deneyimi + mülakat için anlatılabilir proje

## Overall Status: IN PROGRESS

## Phase Progress
| Phase | Status | Notes |
|-------|--------|-------|
| 1. Project Setup & Infrastructure | ✅ complete | 2026-03-05 |
| 2. Data Generation (Faker) | ✅ complete | 2026-03-05 |
| 3. Kafka Streaming Layer | ✅ complete | 2026-03-05 |
| 4. Spark Streaming & Features | ✅ complete | 2026-03-06 |
| 5. ML Training & MLflow | ✅ complete | 2026-03-06 |
| 6. Model Deployment | ⬜ pending | |
| 7. Airflow Orchestration | ⬜ pending | |
| 8. Monitoring & Dashboard | ⬜ pending | |

## Session Log
- **2026-03-03**: Project planning started. Task plan, findings, and progress files created.
- **2026-03-05**: Phase 1 complete.
  - Proje dizin yapısı oluşturuldu (src/, configs/, tests/, notebooks/, airflow/)
  - Python 3.14 venv + tüm bağımlılıklar kuruldu
  - docker-compose.yml: Zookeeper, Kafka, Spark (master+worker), PostgreSQL, MinIO, MLflow
  - kafka-init: 3 topic otomatik oluşturma (transactions, fraud-alerts, features)
  - minio-init: mlflow-artifacts bucket otomatik oluşturma
  - .env, Makefile, .gitignore, src/config.py, kafka_config.yaml, spark_config.yaml
  - Issue: XGBoost/LightGBM için `brew install libomp` gerekti (resolved)
  - Docker Compose tüm servisler başarıyla ayağa kalktı
  - Issues resolved: bitnami/spark → apache/spark:3.5.4, port 5000→5001, zookeeper healthcheck, mlflow psycopg2
- **2026-03-05**: Phase 2 complete.
  - `src/data_generator/transaction_generator.py`: 15 merchant, 5 foreign merchant, 10 US lokasyon, 4 fraud pattern
  - `src/data_generator/kafka_producer.py`: JSON serialization, user_id partitioning, graceful shutdown, metrikler
  - Test: 113 tx gönderildi @ 9.5 tx/sn, 0 hata. Kafka'dan okundu ve doğrulandı.
  - Fraud oranı: ~2.4% (hedef: 2%)
- **2026-03-05**: Phase 3 complete.
  - Topic'ler doğrulandı: transactions (7d), fraud-alerts (30d), features (7d) - 3 partition
  - `kafka_consumer_debug.py`: Debug consumer, partition dağılımı, fraud raporlama
  - E2E pipeline testi başarılı: Producer → Kafka → Consumer (213 mesaj, 3 partition dağılımı)

- **2026-03-06**: venv → uv + .venv migration
  - PySpark 4.1.1 → 3.5.8 downgrade (Java 11 uyumu + Docker Spark 3.5.4 eşleşmesi)
  - setuptools eklendi (Python 3.12'de distutils kaldırıldı)
  - PYSPARK_PYTHON/PYSPARK_DRIVER_PYTHON ayarlandı (worker Python versiyon uyumu)
- **2026-03-06**: Phase 4 feature engineering tamamlandı ve test edildi.
  - `src/streaming/feature_engineering.py`: Windowed, Location, Transaction features
  - `src/streaming/spark_consumer.py`: Kafka → Parse → Feature Eng → Parquet + Kafka output
    - `starting_offsets` parametresi eklendi ("latest"/"earliest")
    - `write_windowed_to_kafka()` eklendi → features-windowed topic
    - `compute_windowed_features` import edilerek pipeline'a dahil edildi
  - Schema Registry: container healthy (port 8085), transactions-value schema kaydedildi (id=1, BACKWARD compatibility)
  - `configs/schemas/transaction_value.json`: JSON Schema tanımı
  - `src/data_generator/register_schemas.py`: Schema registration script
  - features-windowed Kafka topic oluşturuldu (3 partition)
  - **Feature Engineering Unit Test PASSED** (Spark 3.5.8, local[2]):
    - compute_transaction_features: hour, day, amount_log, is_high_amount, is_round_amount ✓
    - compute_location_features: NY→LA 5dk = 47,232 km/h impossible travel tespit edildi ✓
    - compute_windowed_features: 1h sliding window, tx_count/total/avg/unique_merchant ✓
- **2026-03-06**: Phase 4 tamamlandı — Scoring + Error Handling eklendi.
  - `src/serving/model_scorer.py`: FraudScorer (MLflow model + preprocessing artifacts)
  - Preprocessing artifacts kaydedildi: `data/artifacts/` (scaler, label_encoders, feature_names)
  - Scoring pandas_udf: Spark streaming'de micro-batch scoring (LightGBM predict_proba)
  - Fraud alerts: fraud_score >= 0.5 olan tx → fraud-alerts topic'e yazılır
  - DLQ: parse edilemeyen mesajlar → transactions-dlq topic
  - Fallback: model hatası → score = -1 (manual review)
  - Eksik feature'lar eklendi: amount_deviation (z-score), time_since_last_tx (dk), unique_locations_1h
- **2026-03-06**: Phase 5 tamamlandı (tüm eksikler kapatıldı).
  - `src/training/prepare_data.py`: 100K tx, Spark feature eng, stratified split (70/10/20)
  - `src/training/train_model.py`: 4 model, MLflow tracking + Model Registry
  - `src/training/evaluate.py`: Detaylı evaluation + threshold analizi
  - Sonuçlar: LightGBM en iyi (Val AUC-PR=0.998, Test F1=0.982)
  - MLflow UI: http://localhost:5001 → 4 run, fraud-detection-model v1 kayıtlı
  - MLflow 3.x → 2.22 downgrade (Docker server 2.12 uyumu)
  - MLFLOW_S3_ENDPOINT_URL: minio → localhost:9000 (host erişimi)
  - Model stage: v1 → Production
  - Model signature + input example: train_model.py'ye eklendi (infer_signature)
  - Optuna tuning: `src/training/tune_hyperparams.py` → 20 trial, AUC-PR=0.9970
  - optuna paketi requirements.txt'e eklendi
- **2026-03-06**: Phase 5 denetim & fix (tüm eksikler kapatıldı).
  - Model stage fix: `transition_model_version_stage` (deprecated) → `set_registered_model_alias("champion")` (MLflow 3.x uyumu)
  - Docker MLflow: fraud-detection-model v2 registered, champion alias set
  - Local DB: champion alias + Production stage SQL ile set edildi
  - evaluate.py fix: Yeni scaler fit_transform yerine kaydedilmiş `data/artifacts/scaler.joblib` kullanılıyor
  - Confusion matrix plot: Test set CM heatmap → MLflow artifact (`plots/confusion_matrix_test.png`)
  - SHAP explainability: TreeExplainer + summary plot → MLflow artifact (`plots/shap_summary_LightGBM.png`)
  - train_model.py: matplotlib, seaborn, shap import eklendi; log_confusion_matrix plot kaydediyor; log_shap_importance fonksiyonu eklendi
  - Kafka ZK stale node fix: `docker restart zookeeper` → Kafka başarıyla başlatıldı

## Errors & Issues
| Error | Resolution |
|-------|------------|
| XGBoost: `libomp.dylib` not found | `brew install libomp` ile çözüldü |
| bitnami/spark:3.5 not found | `apache/spark:3.5.4` ile değiştirildi |
| Port 5000 zaten kullanımda (AirPlay) | MLflow portu 5001'e taşındı |
| Zookeeper healthcheck `ruok` disabled | `srvr` komutu kullanıldı |
| MLflow `psycopg2` missing | Custom Dockerfile.mlflow ile çözüldü |
| PySpark 4.1.1 + Java 11 | `UnsupportedClassVersionError` → PySpark 3.5.8'e downgrade |
| Python 3.14 vs 3.12 Spark worker | `PYSPARK_PYTHON=.venv/bin/python` ile çözüldü |
| `distutils` yok (Python 3.12) | `setuptools` kurularak çözüldü |
| MLflow client 3.x vs server 2.12 | `logged-models` 404 → MLflow 2.22.4'e downgrade |
| `minio:9000` host'tan erişilemez | `MLFLOW_S3_ENDPOINT_URL=http://localhost:9000` |
| Schema Registry image indirme yavaş | Arka planda devam, servisler ayrı başlatıldı |
| Model stage `None` (MLflow 3.x) | `transition_model_version_stage` deprecated → `set_registered_model_alias` kullanıldı |
| evaluate.py yanlış scaler | `fit_transform(test)` → `joblib.load(scaler.joblib).transform(test)` |
| Kafka ZK stale ephemeral node | `docker restart zookeeper` ile çözüldü |
| Docker MLflow model unregistered | `mlflow.register_model` + `set_registered_model_alias("champion")` |
