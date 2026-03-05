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
| 4. Spark Streaming & Features | ⬜ pending | |
| 5. ML Training & MLflow | ⬜ pending | |
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

## Errors & Issues
| Error | Resolution |
|-------|------------|
| XGBoost: `libomp.dylib` not found | `brew install libomp` ile çözüldü |
| bitnami/spark:3.5 not found | `apache/spark:3.5.4` ile değiştirildi |
| Port 5000 zaten kullanımda (AirPlay) | MLflow portu 5001'e taşındı |
| Zookeeper healthcheck `ruok` disabled | `srvr` komutu kullanıldı |
| MLflow `psycopg2` missing | Custom Dockerfile.mlflow ile çözüldü |
