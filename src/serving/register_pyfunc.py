"""
FraudPyfunc MLflow PythonModel - LightGBM modelini preprocessing artifact'lariyla sarar.

Bu modül:
  1. FraudPyfunc sinifini tanimlar: preprocessing + inference'i tek bir pyfunc'ta birlestirir
  2. register_pyfunc_model() fonksiyonu ile modeli MLflow Registry'ye kaydeder
  3. Mevcut @champion alias'ini yeni pyfunc versiyonuna tasir

Kullanim:
    python -m src.serving.register_pyfunc

Mulakat notu:
  "Training-serving skew nasil onluyorsunuz?" → mlflow.pyfunc.PythonModel kullaniyoruz.
  Preprocessing (scaler, label encoders, feature isimleri) model ile ayni artifact bundle'ina
  paketleniyor. REST endpoint'i dogrudan ham transaction JSON'u kabul edip scoring yapabiliyor,
  ayri bir preprocessing adimi gerektirmiyor.

  "Neden custom pyfunc?" → Standart mlflow.sklearn veya mlflow.lightgbm flavor'lari sadece
  modeli kaydeder. Preprocessing artifact'larini model ile birlestirmek icin PythonModel
  kullaniriz; bu sayede servis ortaminda training koduna bagimlilik kalmaz.
"""

import os
import tempfile
import warnings

import joblib
import numpy as np
import pandas as pd
import mlflow
import mlflow.pyfunc

from src.config import MLFLOW_TRACKING_URI

warnings.filterwarnings("ignore")

# ============================================================
# Feature tanimlari — src/serving/model_scorer.py ile birebir ayni
# Training-serving skew'u onlemek icin bu listeler degistirilmemeli.
# ============================================================

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

# model_scorer.py'deki ile ayni: FEATURE_COLUMNS + CATEGORICAL_COLUMNS = 17 feature toplam
FEATURE_NAMES = FEATURE_COLUMNS + CATEGORICAL_COLUMNS

MODEL_NAME = "fraud-detection-model"
EXPERIMENT_NAME = "fraud-detection"


# ============================================================
# FraudPyfunc - Ozel MLflow PythonModel
# ============================================================

class FraudPyfunc(mlflow.pyfunc.PythonModel):
    """
    Fraud Detection PythonModel — preprocessing + LightGBM inference'i sarmalayan pyfunc.

    load_context(): Artifact bundle'indan scaler, label_encoders, feature_names ve
                    LightGBM modelini yukler.

    predict(): Ham transaction DataFrame'ini alir, preprocessing uygular,
               fraud_score (float) ve fraud_prediction (int) kolonlarini dondurur.

    Mulakat notu:
      "Pyfunc'taki load_context ne zaman calisir?" → MLflow serving container'i baslattiginda
      bir kez calisir. Her predict() cagrisi model yukleme maliyeti olmadan calisir.
    """

    def load_context(self, context):
        """
        Model artifact bundle'indan tum bilesenleri yukler.

        Args:
            context: mlflow.pyfunc.PythonModelContext — artifacts dict'i icerir.
                     Anahtarlar: "scaler", "label_encoders", "feature_names", "lgbm_model"
        """
        # Preprocessing artifact'lari
        self.scaler = joblib.load(context.artifacts["scaler"])
        self.label_encoders = joblib.load(context.artifacts["label_encoders"])
        self.feature_names = joblib.load(context.artifacts["feature_names"])

        # Fraud threshold — environment variable ile override edilebilir (D-03)
        # Varsayilan: 0.5 (model egitimindeki esik degeri)
        self.threshold = float(os.getenv("FRAUD_THRESHOLD", "0.5"))

        # LightGBM modeli — joblib ile serile edilmis LGBMClassifier
        # lgbm_model artifact'i: MLflow'dan indirilen model klasoru veya joblib dosyasi
        lgbm_path = context.artifacts["lgbm_model"]
        # MLflow sklearn flavor: klasor icinde MLmodel dosyasi varsa mlflow.sklearn ile yukle
        import os as _os
        if _os.path.isdir(lgbm_path):
            self.model = mlflow.sklearn.load_model(lgbm_path)
        else:
            self.model = joblib.load(lgbm_path)

        print(f"[FraudPyfunc] Model yuklendi: {type(self.model).__name__}")
        print(f"[FraudPyfunc] Feature sayisi: {len(self.feature_names)}")
        print(f"[FraudPyfunc] Threshold: {self.threshold}")

    def predict(self, context, model_input: pd.DataFrame, params=None):
        """
        Ham transaction DataFrame'ini alir, preprocessing + scoring uygular.

        Preprocessing adimları FraudScorer.preprocess() ile birebir ayni:
          1. Kategorik encoding — bilinmeyen degerler icin fallback: index 0
          2. Onceki transaction alanlari — eksikse 0.0 ile doldur
          3. Feature secimi + NaN doldurma
          4. StandardScaler ile olcekleme
          5. LightGBM predict_proba ile fraud olasiligi

        Args:
            context: mlflow.pyfunc.PythonModelContext (bu metodda kullanilmiyor)
            model_input (pd.DataFrame): Ham transaction kolonlari
            params: Ek parametreler (kullanilmiyor, imza uyumlulugu icin)

        Returns:
            pd.DataFrame: "fraud_score" (float 0-1) ve "fraud_prediction" (int 0/1) kolonlari
        """
        df = model_input.copy()

        # ---- Kategorik encoding ----
        # FraudScorer.preprocess() ile birebir ayni mantik:
        # Bilinmeyen kategorik degerler → index 0 (en sik sinif)
        for col in CATEGORICAL_COLUMNS:
            if col in df.columns:
                le = self.label_encoders[col]
                df[col] = df[col].astype(str).apply(
                    lambda x: le.transform([x])[0] if x in le.classes_ else 0
                )

        # ---- Onceki transaction alanlari — opsiyonel, eksikse 0.0 ile doldur ----
        # Bu kolonlar feature_names'de yok; ama bazi kaynaklardan gelebilir.
        # Eger gelirse IgnoreError yerine gracefully handle et.
        for col in ["prev_latitude", "prev_longitude", "prev_timestamp"]:
            if col not in df.columns:
                df[col] = 0.0

        # ---- Feature secimi + NaN doldurma ----
        X = df[self.feature_names].fillna(0).values

        # ---- Scaling ----
        X = self.scaler.transform(X)

        # ---- Scoring ----
        probs = self.model.predict_proba(X)[:, 1]

        return pd.DataFrame({
            "fraud_score": probs.astype(float),
            "fraud_prediction": (probs >= self.threshold).astype(int),
        })


# ============================================================
# Kayit fonksiyonu
# ============================================================

def register_pyfunc_model():
    """
    Mevcut @champion LightGBM modelini FraudPyfunc olarak yeniden kaydeder.

    Adimlar:
      1. MLflow Registry'den mevcut @champion versiyonunu bul
      2. Champion run'dan LightGBM model artifact'ini gecici dizine indir
      3. Yeni bir MLflow run'da pyfunc olarak log_model() cagir
         (scaler, label_encoders, feature_names preprocessing artifact'lariyla birlikte)
      4. Yeni versiyona @champion alias'ini tasi

    Mulakat notu:
      "Neden champion'i yeniden kayit ediyoruz?" → Eski versiyon ham LightGBM idi,
      REST servis edemezdik cunku preprocessing icermiyordu. Pyfunc wrapper sayesinde
      /invocations endpoint'i dogrudan ham JSON kabul edip scoring yapabiliyor.
    """
    # ---- Ortam degiskenleri ----
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")

    client = mlflow.tracking.MlflowClient()

    # ---- Mevcut champion'i bul ----
    print("[1/5] Mevcut @champion versiyonu aliniyor...")
    mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
    champion_run_id = mv.run_id
    champion_version = mv.version
    print(f"      Champion: v{champion_version} (run_id={champion_run_id})")

    # ---- Champion LightGBM model artifact'ini indir ----
    print("[2/5] Champion model artifact'i indiriliyor...")
    tmpdir = tempfile.mkdtemp(prefix="fraud_pyfunc_")
    model_local_path = mlflow.artifacts.download_artifacts(
        run_id=champion_run_id,
        artifact_path="model",
        dst_path=tmpdir,
    )
    print(f"      Model indirildi: {model_local_path}")

    # ---- Pyfunc model'i log et ----
    print("[3/5] FraudPyfunc model'i log ediliyor...")
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="register-pyfunc") as run:
        result = mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=FraudPyfunc(),
            artifacts={
                "scaler": "data/artifacts/scaler.joblib",
                "label_encoders": "data/artifacts/label_encoders.joblib",
                "feature_names": "data/artifacts/feature_names.joblib",
                "lgbm_model": model_local_path,
            },
            pip_requirements=[
                "mlflow==2.12.2",
                "lightgbm>=4.0.0",
                "scikit-learn>=1.4.0",
                "joblib>=1.3.0",
                "pandas>=2.2.0",
                "numpy>=1.26.0",
                "boto3>=1.34.0",
            ],
            registered_model_name=MODEL_NAME,
        )

    # ---- Yeni versiyon numarasini al ----
    new_version = result.registered_model_version
    print(f"[4/5] Yeni pyfunc versiyonu kaydedildi: v{new_version} (run_id={run.info.run_id})")

    # ---- Champion alias'ini yeni versiyona tasi ----
    print("[5/5] @champion alias'i yeni versiyona tasiniyor...")
    client.set_registered_model_alias(
        name=MODEL_NAME,
        alias="champion",
        version=new_version,
    )
    print(f"      @champion → v{new_version} (onceki: v{champion_version})")

    print("=" * 60)
    print(f"FraudPyfunc basariyla kaydedildi!")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Versiyon: v{new_version}")
    print(f"  Alias: @champion → v{new_version}")
    print(f"  REST servis: mlflow models serve -m 'models:/{MODEL_NAME}@champion'")
    print("=" * 60)

    return new_version


# ============================================================
# Ana giris noktasi
# ============================================================

if __name__ == "__main__":
    register_pyfunc_model()
