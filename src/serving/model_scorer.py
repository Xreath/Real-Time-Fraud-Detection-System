"""
Real-Time Fraud Scorer - MLflow modeli + preprocessing artifacts ile scoring.

Bu modül:
  1. Eğitim verisinden preprocessing artifact'larını oluşturur (scaler, label_encoders)
  2. MLflow Model Registry'den en iyi modeli yükler
  3. Gelen transaction'ları preprocess edip fraud skoru verir

Kullanım (artifact hazırlama):
    python -m src.serving.model_scorer --prepare

Kullanım (test):
    python -m src.serving.model_scorer --test

Mülakat notu:
  "Scoring pipeline'ında preprocessing nasıl?" → Training'deki aynı
  preprocessing (scaler, encoder) scoring'de de kullanılmalı. Aksi halde
  model yanlış input alır → yanlış tahmin. Bu yüzden preprocessing
  artifact'larını kayıt edip scoring sırasında yüklüyoruz.

  "Training-serving skew nedir?" → Training'de farklı, serving'de farklı
  preprocessing uygulanırsa model performansı düşer. Bunu önlemek için
  aynı artifact'ları (scaler, encoder) her iki tarafta kullanıyoruz.
"""

import os
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn

from src.config import MLFLOW_TRACKING_URI

warnings.filterwarnings("ignore")

ARTIFACTS_DIR = Path("data/artifacts")
SPLITS_DIR = Path("data/splits")

# train_model.py ile aynı feature tanımları — training-serving skew'u önler
FEATURE_COLUMNS = [
    "amount",
    "latitude",
    "longitude",
    "is_weekend",
    "is_night",
    "is_foreign",
    "hour_of_day",
    "day_of_week",
    "amount_log",
    "is_high_amount",
    "is_round_amount",
    "distance_km",
    "time_diff_hours",
    "speed_kmh",
]

CATEGORICAL_COLUMNS = [
    "merchant_category",
    "card_type",
    "country",
]


def prepare_scoring_artifacts():
    """
    Eğitim verisinden preprocessing artifact'larını oluşturur ve kaydeder.

    Kaydedilen dosyalar:
      - data/artifacts/scaler.joblib     → StandardScaler (fitted)
      - data/artifacts/label_encoders.joblib → {col: LabelEncoder} dict

    Bu fonksiyon bir kez çalıştırılır; scoring sırasında sadece load edilir.
    """
    from sklearn.preprocessing import StandardScaler, LabelEncoder

    print("Preprocessing artifact'ları hazırlanıyor...")
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Eğitim verisini yükle
    train = pd.read_parquet(SPLITS_DIR / "train.parquet")
    val = pd.read_parquet(SPLITS_DIR / "val.parquet")
    test = pd.read_parquet(SPLITS_DIR / "test.parquet")

    # Label Encoders — train_model.py ile aynı mantık
    label_encoders = {}
    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()
        all_values = pd.concat([train[col], val[col], test[col]]).astype(str)
        le.fit(all_values)
        label_encoders[col] = le
        print(f"  LabelEncoder[{col}]: {len(le.classes_)} sınıf")

    # Scaler — train_model.py ile aynı mantık
    for col in CATEGORICAL_COLUMNS:
        train[col] = label_encoders[col].transform(train[col].astype(str))

    feature_names = FEATURE_COLUMNS + CATEGORICAL_COLUMNS
    X_train = train[feature_names].fillna(0).values

    scaler = StandardScaler()
    scaler.fit(X_train)
    print(f"  StandardScaler: {len(feature_names)} feature")

    # Kaydet
    joblib.dump(scaler, ARTIFACTS_DIR / "scaler.joblib")
    joblib.dump(label_encoders, ARTIFACTS_DIR / "label_encoders.joblib")
    joblib.dump(feature_names, ARTIFACTS_DIR / "feature_names.joblib")

    print(f"Artifact'lar kaydedildi: {ARTIFACTS_DIR}/")
    return scaler, label_encoders, feature_names


class FraudScorer:
    """
    Fraud scoring sınıfı. Model + preprocessing'i yükler, score verir.

    Kullanım:
        scorer = FraudScorer()
        scores = scorer.score(df)  # df: Pandas DataFrame
    """

    def __init__(
        self,
        model_name: str = "fraud-detection-model",
        model_version: str = "1",
        threshold: float = 0.5,
    ):
        self.model_name = model_name
        self.model_version = model_version
        self.threshold = threshold
        self.model = None
        self.scaler = None
        self.label_encoders = None
        self.feature_names = None
        self._load()

    def _load(self):
        """Model ve preprocessing artifact'larını yükler."""
        # Preprocessing artifacts
        self.scaler = joblib.load(ARTIFACTS_DIR / "scaler.joblib")
        self.label_encoders = joblib.load(ARTIFACTS_DIR / "label_encoders.joblib")
        self.feature_names = joblib.load(ARTIFACTS_DIR / "feature_names.joblib")

        # MLflow model — MinIO (S3) erişimi için env var'lar gerekli:
        #   MLFLOW_S3_ENDPOINT_URL=http://localhost:9000
        #   AWS_ACCESS_KEY_ID=minioadmin
        #   AWS_SECRET_ACCESS_KEY=minioadmin
        import os
        os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        model_uri = f"models:/{self.model_name}/{self.model_version}"
        # mlflow.sklearn.load_model → doğrudan LGBMClassifier döner (predict_proba var)
        self.model = mlflow.sklearn.load_model(model_uri)
        print(f"Model yüklendi: {model_uri} ({type(self.model).__name__})")
        print(f"Threshold: {self.threshold}")

    def preprocess(self, df: pd.DataFrame) -> np.ndarray:
        """
        Raw transaction DataFrame'ini model input'una dönüştürür.

        Training'deki aynı preprocessing adımları uygulanır.
        Bilinmeyen kategorik değerler için fallback: en sık sınıf (index 0).
        """
        df = df.copy()

        # Kategorik encoding
        for col in CATEGORICAL_COLUMNS:
            if col in df.columns:
                le = self.label_encoders[col]
                # Bilinmeyen değerler → 0 (en sık sınıf)
                df[col] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else 0
                )

        # Feature seçimi + NaN doldurma
        X = df[self.feature_names].fillna(0).values

        # Scaling
        X = self.scaler.transform(X)

        return X

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Transaction DataFrame'ini skorlar.

        Returns:
            Input df + fraud_score (0-1) + fraud_prediction (0/1) kolonları
        """
        X = self.preprocess(df)

        # sklearn-compatible model (LGBMClassifier) → predict_proba[:, 1] = fraud olasılığı
        probs = self.model.predict_proba(X)[:, 1]

        df = df.copy()
        df["fraud_score"] = probs
        df["fraud_prediction"] = (probs >= self.threshold).astype(int)

        return df


def test_scorer():
    """Scorer'ı test verisinden birkaç satırla test eder."""
    print("\n" + "=" * 55)
    print("FraudScorer Test")
    print("=" * 55)

    scorer = FraudScorer()

    # Test verisinden sample
    test_df = pd.read_parquet(SPLITS_DIR / "test.parquet")
    sample = test_df.sample(n=10, random_state=42)

    result = scorer.score(sample)

    print("\nSonuclar:")
    print(result[["transaction_id", "amount", "is_fraud", "fraud_score", "fraud_prediction"]].to_string(index=False))

    # Accuracy check
    correct = (result["fraud_prediction"] == result["is_fraud"]).sum()
    print(f"\nDogruluk: {correct}/{len(result)} ({correct/len(result)*100:.0f}%)")
    print("Test PASSED" if correct >= 7 else "Test FAILED (düşük doğruluk)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fraud Scorer")
    parser.add_argument("--prepare", action="store_true", help="Preprocessing artifact'larini olustur")
    parser.add_argument("--test", action="store_true", help="Scorer'i test et")
    args = parser.parse_args()

    if args.prepare:
        prepare_scoring_artifacts()
    if args.test:
        test_scorer()
    if not args.prepare and not args.test:
        print("Kullanım: --prepare (artifact olustur) ve/veya --test (test et)")
