# Findings & Research Notes

> **Bu bir öğrenme projesidir.** Her karar ve notun yanında "neden bu seçimi yaptık" açıklaması bulunur. Mülakat soruları ve cevapları da bu dosyada toplanır.

## Architecture Decisions

### Kafka Configuration
- Topic partitioning by user_id ensures transaction ordering per user
- Retention: 7 days for transactions, 30 days for fraud-alerts
- Replication factor: 1 (dev), 3 (prod)

### Spark Streaming Strategy
- Structured Streaming (not DStreams - deprecated)
- Watermark: 10 minutes for late data
  - Neden 10dk? → Gerçek dünyada network gecikmeleri, batch delays olabilir
  - 10dk'dan eski veriler drop edilir (memory koruması)
  - Mülakat cevabı: "Watermark ile geç gelen veriyi tolere ediyoruz ama sonsuz state tutmuyoruz"
- Trigger: processingTime="10 seconds" for micro-batches
- Checkpoint location for fault tolerance
- Output: Kafka "features" topic + Parquet dosyaları (ekrana basma değil!)

### ML Model Considerations
- Class imbalance: ~2% fraud rate → need SMOTE or class weights
- Key metric: **Precision-Recall AUC** (not ROC-AUC, due to imbalance)
- Recall is more important than precision (missing fraud is costly)
- XGBoost typically performs best for tabular fraud detection

### Feature Engineering Insights
- Velocity features (tx count in time window) are strongest fraud signals
- Impossible travel detection: if speed > 500 km/h between transactions → suspicious
- Amount deviation from user's historical average is a strong signal
- Time-of-day features capture unusual spending patterns

### MLflow Logging Strategy (Faz 5)
- Her run'da loglanacaklar:
  - Hyperparameters (learning_rate, max_depth, n_estimators vb.)
  - Metrics: precision, recall, F1, AUC-ROC, AUC-PR
  - **SHAP values** → model-agnostic feature importance (explainability)
  - **XGBoost feature importance** → gain, weight, cover
  - Confusion matrix plot (artifact)
  - Precision-Recall curve plot (artifact)
  - Model artifact (.pkl veya native format)
- "Neden fraud?" sorusuna cevap verebilmek için SHAP kritik
  - Örnek: "Son 1 saatte 15 işlem (velocity) + konum 2000km uzakta (impossible travel)"

### Zookeeper vs KRaft
- Bu projede Zookeeper kullanılıyor (Confluent 7.6.0)
- Kafka 3.0+ ile KRaft modu: Zookeeper'sız, Kafka kendi metadata'sını yönetiyor
- KRaft avantajları: 1 container az, daha hızlı startup, daha az kaynak
- Neden Zookeeper'da kaldık: Confluent Stack ile uyumluluk, öğrenme sürecinde tanıdık setup
- Mülakat cevabı: "KRaft'ın farkındayım, prod'da KRaft tercih edilir. Bu setup'ta Confluent ecosystem uyumluluğu öncelikli."

### Parquet vs Delta Lake
- Seçim: **Düz Parquet** (Delta Lake yok)
- Parquet: columnar storage, hızlı okuma, basit. Transaction/schema evolution yok.
- Delta Lake: Parquet üzerine ACID, time-travel, schema enforcement ekler. Spark + Delta connector gerektirir.
- Bu proje için Parquet yeterli: batch training, append-only writes, schema sabit
- Mülakat cevabı: "Production'da Delta Lake düşünürdük özellikle feature backfill ve time-travel için. Bu scope için Parquet yeterli."

### Feature Store Kararı
- **Seçim: Parquet tabanlı basit feature store** (Feast yok)
- Neden Feast değil? → Fazladan infra (Redis/online store, feature registry), bu projenin scope'unu aşıyor
- Parquet yeterli çünkü: batch training için offline store yeterli, online serving Spark'tan yapılıyor
- Mülakat cevabı: "Production'da Feast düşünürdük, ama bu projede complexity-value tradeoff'u Parquet lehine"

### Rollback Mekanizması
- MLflow her model versiyonunu saklar → önceki "Production" stage'deki model her zaman erişilebilir
- Strateji: Canary deploy (%10 trafik) → 1 saat izle → iyi ise %100, kötü ise rollback
- Vertex AI'da traffic splitting native destekleniyor (`--traffic-split`)
- Rollback komutu: `mlflow models set-model-version-tag` + Vertex AI endpoint update
- Mülakat cevabı: "MLflow'da version history tutuyoruz, Vertex AI'da traffic split ile canary deploy sonrası otomatik rollback yapıyoruz"

### Retraining Strategy (Faz 7) - HYBRID
- **Scheduled**: Her Pazar gecesi 02:00'de otomatik retrain
  - Haftalık biriken yeni verilerle model güncellenir
  - Fraud pattern'leri değişse bile max 1 hafta gecikme
- **Triggered**: F1-score < 0.85 olursa anında retrain tetiklenir
  - Monitoring DAG günlük olarak validation set üzerinde F1 kontrol eder
  - Eşik altına düşerse → Slack/email alert + otomatik retrain
- **Airflow DAG Akışı**:
  1. Validation set üzerinde mevcut modeli test et
  2. F1 < 0.85 VEYA Pazar gecesi ise → devam et
  3. Yeni veriyi feature store'dan çek
  4. Model retrain (aynı hyperparameter search)
  5. Yeni model daha iyiyse → MLflow Registry'de promote
  6. Vertex AI endpoint güncelle
  7. Sonuç raporu logla

### Model Drift Detection
- Data drift: Feature dağılımlarını karşılaştır (KS test, PSI)
- Concept drift: F1-score trendi izle (sliding window)
- Alert: Drift tespit edilirse Slack notification

## Technical Notes
- (To be updated as we build)

## Issues & Blockers
- (To be updated as we encounter issues)
