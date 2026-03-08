# Öğrenme Takip Dosyası

## Yöntem
- Her konu anlatılır → soru-cevap → 4/5 ve üzeri → sonraki konuya geç
- Geçme puanı: **4/5**

---

## Konu Sırası & Durum

| # | Konu | Durum | Puan |
|---|------|-------|------|
| 1 | Docker & Servis Mimarisi | ✅ Geçti | 5/5 |
| 2 | Apache Kafka | ✅ Geçti | 5/5 |
| 3 | Transaction Generator & Fraud Pattern'leri | ✅ Geçti | 4.5/5 |
| 4 | Apache Spark Structured Streaming | ✅ Geçti | 5/5 |
| 5 | Feature Engineering | ✅ Geçti | 4.5/5 |
| 6 | ML & Imbalanced Data | ⬜ Bekliyor | - |
| 7 | MLflow | ⬜ Bekliyor | - |
| 8 | Airflow | ⬜ Bekliyor | - |

---

## Sonraki Konu: ML & Imbalanced Data

### Kapsam:
- Neden imbalanced data sorun?
- SMOTE nedir, nasıl çalışır?
- XGBoost neden seçtik?
- AUC-ROC vs AUC-PR — fraud için hangisi daha iyi?
- Precision vs Recall tradeoff — fraud'da hangisi önemli?
- class_weight parametresi

---

## Zayıf Noktalar (Tekrar Edilecek)

| Konu | Zayıf Nokta |
|------|-------------|
| Transaction Generator | is_fraud label'ının ne için kullanıldığı (supervised learning) |
| Feature Engineering | Feature'ların nereye kaydedildiği (Kafka features topic + Parquet) |
| Kafka | key=user_id → sıralama garantisi bağlantısı |

---

## Önemli Kavramlar (Özet)

### Docker
- Image = şablon, Container = çalışan kopya
- Dockerfile.mlflow → hazır image + psycopg2 + boto3 (PostgreSQL + MinIO için)
- depends_on + service_healthy → sıralama garantisi
- Volume → container silinse bile veri kalır
- Container'lar birbirini servis adıyla bulur (postgres:5432)
- localhost:9092 → host makine, kafka:29092 → container'lar arası

### Kafka
- Topic = posta kutusu (transactions, fraud-alerts, features)
- Partition = kutunun gözleri (3 partition = paralel okuma)
- key=user_id → aynı kullanıcı hep aynı partition → sıralama garantisi
- Consumer Group = takım halinde okuma, her partition sadece 1 worker
- Retention: transactions 7 gün, fraud-alerts 30 gün
- replication-factor 1 (local), production'da 3 olmalı
- Worker çökünce → 10sn heartbeat timeout → rebalance → kaldığı yerden devam

### Transaction Generator
- GDPR + PCI-DSS → gerçek veri kullanamayız → Faker
- 4 fraud pattern: Unusual Amount, Foreign, Impossible Travel, Late Night High
- Kullanıcı profili = normal davranış referansı
- %2 fraud rate → imbalanced data problemi

### Spark Structured Streaming
- Batch vs Streaming → fraud için Streaming şart (gecikme = para kaybı)
- Master = koordinatör, Worker = işi yapan
- Watermark → geç gelen veriyi kabul etme süresi
- Window → zaman penceresi aggregation (1 saatlik)
- Checkpoint → çökünce kaldığı yerden devam

### Feature Engineering
- Ham veri → anlamlı feature'lara dönüştürme
- Windowed: tx_count_1h, total_amount_1h, avg_amount_1h, unique_merchant_1h
- Location: distance_km (Haversine), speed_kmh, unique_loc_1h
- Transaction: amount_deviation, time_since_last, is_weekend, is_night, is_foreign
- Kaydediliyor: Kafka "features" topic (real-time) + Parquet (eğitim)
- Parquet: columnar, sıkıştırılmış, Pandas/Spark uyumlu
