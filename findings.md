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
