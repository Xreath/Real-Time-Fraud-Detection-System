"""
Model Evaluation - Eğitilmiş modeli detaylı değerlendirir.

Bu modül MLflow'dan production modeli çeker ve detaylı analiz yapar:
  - Classification report
  - Confusion matrix
  - Feature importance
  - Threshold analizi (recall vs precision trade-off)

Kullanım:
    python -m src.training.evaluate

Mülakat notu:
  "Threshold nedir?" → Model 0-1 arası bir olasılık verir (fraud probability).
  Default threshold 0.5: prob > 0.5 → fraud. Ama fraud detection'da
  threshold'u düşürmek (0.3 gibi) recall'u artırır — daha fazla fraud yakalar
  ama daha fazla yanlış alarm da olur.
"""

import pandas as pd
import numpy as np
import mlflow
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    precision_recall_curve,
    roc_curve,
)
from pathlib import Path

from src.config import MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT_NAME


SPLITS_DIR = Path("data/splits")


def load_production_model(model_name: str = "fraud-detection-model"):
    """MLflow Model Registry'den production modeli yükler."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    # En son versiyonu al
    client = mlflow.MlflowClient()
    versions = client.search_model_versions(f"name='{model_name}'")
    if not versions:
        print(f"HATA: '{model_name}' modeli bulunamadı.")
        return None, None

    latest = max(versions, key=lambda v: int(v.version))
    model_uri = f"models:/{model_name}/{latest.version}"
    model = mlflow.pyfunc.load_model(model_uri)

    print(f"Model yüklendi: {model_name} v{latest.version}")
    print(f"  Run ID: {latest.run_id}")

    return model, latest


def threshold_analysis(y_true, y_prob):
    """
    Farklı threshold değerleri için precision/recall trade-off analizi.

    Fraud detection'da threshold seçimi kritik:
      - Düşük threshold (0.3) → yüksek recall, düşük precision (çok yanlış alarm)
      - Yüksek threshold (0.7) → düşük recall, yüksek precision (fraud kaçırma riski)
      - Optimal: F1-score'u maksimize eden threshold
    """
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)

    print("\nThreshold Analizi:")
    print(f"{'Threshold':>10} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 42)

    best_f1 = 0
    best_threshold = 0.5

    for t in [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
        idx = np.searchsorted(thresholds, t)
        if idx < len(precisions):
            p = precisions[idx]
            r = recalls[idx]
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
            print(f"{t:>10.1f} {p:>10.3f} {r:>10.3f} {f1:>10.3f}")

            if f1 > best_f1:
                best_f1 = f1
                best_threshold = t

    print(f"\nOptimal threshold: {best_threshold} (F1={best_f1:.3f})")
    return best_threshold


def main():
    """Ana evaluation pipeline'ı."""
    print("=" * 60)
    print("Model Evaluation")
    print("=" * 60)

    # Model yükle
    model, version_info = load_production_model()
    if model is None:
        return

    # Test verisi yükle
    test_df = pd.read_parquet(SPLITS_DIR / "test.parquet")
    print(f"Test verisi: {len(test_df):,} satır")

    # Preprocessing — eğitimdeki kaydedilmiş artifacts kullanılır
    # BUG FIX: Önceden yeni scaler/encoder oluşturuluyordu (fit_transform).
    # Bu, eğitimdekinden farklı dönüşüm verir → yanlış sonuçlar.
    # Doğrusu: data/artifacts/'teki scaler ve label_encoders'ı yükle.
    from src.training.train_model import FEATURE_COLUMNS, CATEGORICAL_COLUMNS, TARGET
    import joblib

    artifacts_dir = Path("data/artifacts")
    scaler = joblib.load(artifacts_dir / "scaler.joblib")
    label_encoders = joblib.load(artifacts_dir / "label_encoders.joblib")

    for col in CATEGORICAL_COLUMNS:
        le = label_encoders[col]
        test_df[col] = le.transform(test_df[col].astype(str))

    feature_names = FEATURE_COLUMNS + CATEGORICAL_COLUMNS
    X_test = test_df[feature_names].fillna(0).values
    y_test = test_df[TARGET].values

    X_test = scaler.transform(X_test)

    # Tahmin
    X_test_df = pd.DataFrame(X_test, columns=feature_names)
    y_prob = model.predict(X_test_df)

    # Eğer model direkt sınıf döndürüyorsa prob yerine
    if isinstance(y_prob, np.ndarray) and y_prob.ndim == 1:
        if set(np.unique(y_prob)).issubset({0, 1}):
            y_pred = y_prob.astype(int)
            print("\nClassification Report:")
            print(classification_report(y_test, y_pred, target_names=["Normal", "Fraud"]))
            return

    # Threshold ile sınıflandırma
    y_pred = (y_prob > 0.5).astype(int)

    # Classification report
    print("\nClassification Report (threshold=0.5):")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Fraud"]))

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = cm.ravel()
    print(f"Confusion Matrix:")
    print(f"  True Negative:  {tn:>6,} (doğru normal)")
    print(f"  False Positive: {fp:>6,} (yanlış alarm)")
    print(f"  False Negative: {fn:>6,} (kaçırılan fraud)")
    print(f"  True Positive:  {tp:>6,} (yakalanan fraud)")

    # Threshold analizi
    optimal_threshold = threshold_analysis(y_test, y_prob)


if __name__ == "__main__":
    main()
