"""
Model Training - Fraud detection modeli eğitimi ve MLflow tracking.

Bu modül:
  1. Hazırlanan historical veriyi okur
  2. 4 farklı model eğitir (Logistic Regression, Random Forest, XGBoost, LightGBM)
  3. Her model için metrikleri MLflow'a loglar
  4. En iyi modeli MLflow Model Registry'ye kaydeder

Kullanım:
    python -m src.training.train_model

Mülakat notu:
  "Neden birden fazla model?" → Baseline (LogReg) ile gelişmiş modelleri
  (XGBoost) karşılaştırmak için. MLflow UI'da hepsini yan yana görebilirsin.

  "Neden XGBoost genelde kazanır?" → Tabular veride gradient boosting
  çok güçlü. Feature interaction'ları otomatik yakalar.
  Deep learning tabular veride nadiren XGBoost'u geçer.

  "Imbalanced data nasıl handle ediyorsun?" → İki strateji:
  1. class_weight / scale_pos_weight → Fraud sample'lara daha fazla ağırlık
  2. SMOTE → Sentetik fraud sample'lar üretir
  Biz class_weight kullanıyoruz çünkü daha basit ve genelde yeterli.
"""

import os
import warnings
from pathlib import Path

import pandas as pd
import numpy as np
import mlflow
import mlflow.sklearn
import mlflow.xgboost
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    classification_report,
)
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend (server/CI ortamları için)
import matplotlib.pyplot as plt
import seaborn as sns
import shap
import xgboost as xgb
import lightgbm as lgb
from mlflow.models import infer_signature

from src.config import MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT_NAME

warnings.filterwarnings("ignore")

SPLITS_DIR = Path("data/splits")

# Model eğitiminde kullanılacak feature'lar
# Kategorik ve ID kolonları hariç
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

# Kategorik feature'lar → Label Encoding
CATEGORICAL_COLUMNS = [
    "merchant_category",
    "card_type",
    "country",
]

TARGET = "is_fraud"


# ============================================================
# Veri Yükleme & Preprocessing
# ============================================================

def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Train/val/test Parquet dosyalarını yükler."""
    train = pd.read_parquet(SPLITS_DIR / "train.parquet")
    val = pd.read_parquet(SPLITS_DIR / "val.parquet")
    test = pd.read_parquet(SPLITS_DIR / "test.parquet")
    print(f"Veri yüklendi → Train: {len(train):,} | Val: {len(val):,} | Test: {len(test):,}")
    return train, val, test


def preprocess(
    train: pd.DataFrame,
    val: pd.DataFrame,
    test: pd.DataFrame,
) -> tuple:
    """
    Feature preprocessing pipeline.

    1. Kategorik → Label Encoding (string → int)
    2. Numerik → StandardScaler (ortalama=0, std=1)
    3. NaN'leri doldur

    Returns:
        X_train, X_val, X_test, y_train, y_val, y_test, feature_names
    """
    # Kategorik encoding
    label_encoders = {}
    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()
        # Tüm veriyi fit et (train+val+test'teki tüm unique değerler)
        all_values = pd.concat([train[col], val[col], test[col]]).astype(str)
        le.fit(all_values)
        train[col] = le.transform(train[col].astype(str))
        val[col] = le.transform(val[col].astype(str))
        test[col] = le.transform(test[col].astype(str))
        label_encoders[col] = le

    feature_names = FEATURE_COLUMNS + CATEGORICAL_COLUMNS

    X_train = train[feature_names].fillna(0).values
    X_val = val[feature_names].fillna(0).values
    X_test = test[feature_names].fillna(0).values
    y_train = train[TARGET].values
    y_val = val[TARGET].values
    y_test = test[TARGET].values

    # Scaling
    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    print(f"Feature sayısı: {len(feature_names)}")
    print(f"Train fraud: {y_train.sum():,}/{len(y_train):,} ({y_train.mean()*100:.1f}%)")

    return X_train, X_val, X_test, y_train, y_val, y_test, feature_names


# ============================================================
# Metrik hesaplama
# ============================================================

def compute_metrics(y_true, y_pred, y_prob) -> dict:
    """
    Tüm metrikleri hesaplar.

    Precision: "Fraud dediğimin kaçı gerçekten fraud?"
    Recall:    "Gerçek fraud'ların kaçını yakaladım?"
    F1:        Precision-Recall dengesi
    AUC-ROC:   Genel sınıflandırma performansı
    AUC-PR:    Imbalanced data için daha güvenilir metrik

    Mülakat notu:
      Fraud detection'da Recall daha önemli. Bir fraud'u kaçırmak
      (false negative) → müşteri para kaybeder.
      Yanlış alarm (false positive) → sadece kartı geçici bloklar.
    """
    metrics = {
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "auc_roc": roc_auc_score(y_true, y_prob),
        "auc_pr": average_precision_score(y_true, y_prob),
    }
    return metrics


def log_confusion_matrix(y_true, y_pred, prefix: str = "val"):
    """Confusion matrix'i hem metrik hem plot olarak MLflow'a loglar."""
    cm = confusion_matrix(y_true, y_pred)
    tn, fp, fn, tp = cm.ravel()
    mlflow.log_metrics({
        f"{prefix}_true_negative": tn,
        f"{prefix}_false_positive": fp,
        f"{prefix}_false_negative": fn,
        f"{prefix}_true_positive": tp,
    })

    # Confusion matrix plot → MLflow artifact
    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(cm, annot=True, fmt="d", cmap="Blues",
                xticklabels=["Normal", "Fraud"],
                yticklabels=["Normal", "Fraud"], ax=ax)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(f"Confusion Matrix ({prefix})")
    plt.tight_layout()
    plot_path = f"/tmp/confusion_matrix_{prefix}.png"
    fig.savefig(plot_path, dpi=100)
    plt.close(fig)
    mlflow.log_artifact(plot_path, "plots")


def log_shap_importance(model, X_sample, feature_names, model_name: str):
    """
    SHAP feature importance plot'unu MLflow'a loglar.

    SHAP (SHapley Additive exPlanations): Her feature'ın tahmine
    ne kadar katkı yaptığını gösterir. "Neden fraud?" sorusuna cevap verir.

    Mülakat notu:
      "SHAP ne işe yarıyor?" → Model-agnostic explainability.
      Örnek output: "Bu işlem fraud çünkü: son 1 saatte 15 işlem (yüksek velocity)
      + konum 2000km uzakta (impossible travel) + gece 3'te (unusual time)"
    """
    try:
        # Tree-based modeller için hızlı TreeExplainer kullan
        if hasattr(model, "feature_importances_"):
            explainer = shap.TreeExplainer(model)
        else:
            explainer = shap.LinearExplainer(model, X_sample)

        shap_values = explainer.shap_values(X_sample)

        # Binary classification: shap_values list ise [class_0, class_1]
        if isinstance(shap_values, list):
            shap_values = shap_values[1]  # Fraud class

        # Summary plot
        fig, ax = plt.subplots(figsize=(10, 6))
        shap.summary_plot(shap_values, X_sample,
                          feature_names=feature_names,
                          show=False, max_display=15)
        plt.tight_layout()
        plot_path = f"/tmp/shap_summary_{model_name}.png"
        plt.savefig(plot_path, dpi=100, bbox_inches="tight")
        plt.close("all")
        mlflow.log_artifact(plot_path, "plots")
        print(f"  SHAP summary plot logged.")
    except Exception as e:
        print(f"  SHAP skipped ({type(e).__name__}: {e})")


# ============================================================
# Model tanımları
# ============================================================

def get_models(pos_weight: float) -> list[tuple]:
    """
    Eğitilecek modelleri döndürür.

    pos_weight: Fraud class'ın ağırlığı (= normal_count / fraud_count)
    Bu şekilde model fraud sample'lara daha fazla önem verir.

    Returns:
        [(model_name, model_object, params_dict), ...]
    """
    models = [
        (
            "LogisticRegression",
            LogisticRegression(
                class_weight="balanced",
                max_iter=1000,
                random_state=42,
            ),
            {"model_type": "logistic_regression", "class_weight": "balanced"},
        ),
        (
            "RandomForest",
            RandomForestClassifier(
                n_estimators=200,
                max_depth=10,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            ),
            {"model_type": "random_forest", "n_estimators": 200, "max_depth": 10},
        ),
        (
            "XGBoost",
            xgb.XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.1,
                scale_pos_weight=pos_weight,
                eval_metric="aucpr",
                random_state=42,
                n_jobs=-1,
            ),
            {"model_type": "xgboost", "n_estimators": 300, "max_depth": 6, "learning_rate": 0.1},
        ),
        (
            "LightGBM",
            lgb.LGBMClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.1,
                scale_pos_weight=pos_weight,
                random_state=42,
                n_jobs=-1,
                verbose=-1,
            ),
            {"model_type": "lightgbm", "n_estimators": 300, "max_depth": 6, "learning_rate": 0.1},
        ),
    ]
    return models


# ============================================================
# Model eğitimi ve MLflow logging
# ============================================================

def train_and_log_model(
    name: str,
    model,
    params: dict,
    X_train, y_train,
    X_val, y_val,
    X_test, y_test,
    feature_names: list[str],
):
    """
    Tek bir modeli eğitir, değerlendirir ve MLflow'a loglar.

    MLflow'a loglanan bilgiler:
      - Hyperparameters (model_type, n_estimators, max_depth vb.)
      - Validation metrikleri (precision, recall, F1, AUC-ROC, AUC-PR)
      - Test metrikleri
      - Confusion matrix
      - Feature importance (varsa)
      - Model artifact
    """
    with mlflow.start_run(run_name=name):
        # Parametreleri logla
        mlflow.log_params(params)
        mlflow.log_param("num_features", len(feature_names))
        mlflow.log_param("train_size", len(y_train))
        mlflow.log_param("fraud_rate", float(y_train.mean()))

        # Eğit
        print(f"\n{'='*50}")
        print(f"Eğitiliyor: {name}")
        print(f"{'='*50}")
        model.fit(X_train, y_train)

        # Validation metrikleri
        y_val_pred = model.predict(X_val)
        y_val_prob = model.predict_proba(X_val)[:, 1]
        val_metrics = compute_metrics(y_val, y_val_pred, y_val_prob)

        for metric_name, value in val_metrics.items():
            mlflow.log_metric(f"val_{metric_name}", value)
        log_confusion_matrix(y_val, y_val_pred, prefix="val")

        # Test metrikleri
        y_test_pred = model.predict(X_test)
        y_test_prob = model.predict_proba(X_test)[:, 1]
        test_metrics = compute_metrics(y_test, y_test_pred, y_test_prob)

        for metric_name, value in test_metrics.items():
            mlflow.log_metric(f"test_{metric_name}", value)
        log_confusion_matrix(y_test, y_test_pred, prefix="test")

        # Feature importance (tree-based modeller için)
        if hasattr(model, "feature_importances_"):
            importance = dict(zip(feature_names, model.feature_importances_))
            # Top 10 feature
            sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
            for i, (feat, imp) in enumerate(sorted_imp[:10]):
                mlflow.log_metric(f"importance_top{i+1}", imp)
                mlflow.log_param(f"top_feature_{i+1}", feat)

        # SHAP explainability (validation sample üzerinde)
        shap_sample = pd.DataFrame(X_val[:500], columns=feature_names)
        log_shap_importance(model, shap_sample, feature_names, name)

        # Model signature: input/output schema'sını otomatik çıkar
        # Mülakat: "Model signature nedir?" → Model'in beklediği input
        # ve döndürdüğü output'un şeması. Serving sırasında input validation sağlar.
        signature = infer_signature(
            pd.DataFrame(X_val[:5], columns=feature_names),
            y_val_pred[:5],
        )
        input_example = pd.DataFrame(X_val[:3], columns=feature_names)

        # Model artifact kaydet (signature + input_example ile)
        if "xgboost" in name.lower():
            mlflow.xgboost.log_model(model, "model", signature=signature, input_example=input_example)
        else:
            mlflow.sklearn.log_model(model, "model", signature=signature, input_example=input_example)

        # Sonuçları yazdır
        print(f"\n  Validation: P={val_metrics['precision']:.3f} R={val_metrics['recall']:.3f} "
              f"F1={val_metrics['f1']:.3f} AUC-PR={val_metrics['auc_pr']:.3f}")
        print(f"  Test:       P={test_metrics['precision']:.3f} R={test_metrics['recall']:.3f} "
              f"F1={test_metrics['f1']:.3f} AUC-PR={test_metrics['auc_pr']:.3f}")

        return {
            "name": name,
            "val_f1": val_metrics["f1"],
            "val_auc_pr": val_metrics["auc_pr"],
            "test_f1": test_metrics["f1"],
            "test_auc_pr": test_metrics["auc_pr"],
            "run_id": mlflow.active_run().info.run_id,
        }


# ============================================================
# Model Registry - En iyi modeli kaydet
# ============================================================

def register_best_model(results: list[dict], model_name: str = "fraud-detection-model"):
    """
    En iyi modeli MLflow Model Registry'ye kaydeder.

    Seçim kriteri: validation AUC-PR (imbalanced data için en güvenilir metrik)

    Mülakat notu:
      "Neden AUC-PR?" → Imbalanced data'da AUC-ROC yanıltıcı olabilir.
      %2 fraud → model hep "normal" dese bile AUC-ROC yüksek çıkar.
      AUC-PR, pozitif sınıf (fraud) performansına odaklanır.
    """
    best = max(results, key=lambda x: x["val_auc_pr"])
    print(f"\nEn iyi model: {best['name']} (Val AUC-PR: {best['val_auc_pr']:.4f})")

    # Model Registry'ye kaydet
    model_uri = f"runs:/{best['run_id']}/model"
    registered = mlflow.register_model(model_uri, model_name)

    print(f"Model Registry'ye kaydedildi: {model_name} v{registered.version}")

    # Model alias'ını "champion" olarak set et
    # MLflow 3.x'te transition_model_version_stage deprecated.
    # Yerine alias sistemi kullanılıyor: "champion" = production modeli.
    # Mülakat: "Neden alias?" → Stage (Production/Staging) sabitti,
    # alias (champion/challenger) daha esnek ve birden fazla olabilir.
    client = mlflow.tracking.MlflowClient()
    client.set_registered_model_alias(
        name=model_name,
        alias="champion",
        version=registered.version,
    )
    print(f"Model alias: champion → v{registered.version}")

    return best


# ============================================================
# Ana eğitim pipeline'ı
# ============================================================

def main():
    """Tüm modelleri eğitir, karşılaştırır, en iyiyi kaydeder."""
    print("=" * 60)
    print("Fraud Detection - Model Training Pipeline")
    print("=" * 60)

    # MLflow setup
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)
    print(f"MLflow: {MLFLOW_TRACKING_URI}")
    print(f"Experiment: {MLFLOW_EXPERIMENT_NAME}")

    # Veri yükle
    print("\n[1/4] Veri yükleniyor...")
    train_df, val_df, test_df = load_data()

    # Preprocessing
    print("\n[2/4] Preprocessing...")
    X_train, X_val, X_test, y_train, y_val, y_test, feature_names = preprocess(
        train_df, val_df, test_df
    )

    # Class imbalance ağırlığı
    neg_count = (y_train == 0).sum()
    pos_count = (y_train == 1).sum()
    pos_weight = neg_count / pos_count
    print(f"  Class weight (neg/pos): {pos_weight:.1f}")

    # Model eğitimi
    print("\n[3/4] Model eğitimi...")
    models = get_models(pos_weight)
    results = []

    for name, model, params in models:
        result = train_and_log_model(
            name, model, params,
            X_train, y_train,
            X_val, y_val,
            X_test, y_test,
            feature_names,
        )
        results.append(result)

    # En iyi model seçimi ve kayıt
    print("\n[4/4] En iyi model seçimi...")
    best = register_best_model(results)

    # Sonuç tablosu
    print("\n" + "=" * 60)
    print("MODEL KARŞILAŞTIRMA TABLOSU")
    print("=" * 60)
    print(f"{'Model':<20} {'Val F1':>8} {'Val AUC-PR':>12} {'Test F1':>8} {'Test AUC-PR':>12}")
    print("-" * 60)
    for r in sorted(results, key=lambda x: x["val_auc_pr"], reverse=True):
        marker = " ★" if r["name"] == best["name"] else ""
        print(f"{r['name']:<20} {r['val_f1']:>8.4f} {r['val_auc_pr']:>12.4f} "
              f"{r['test_f1']:>8.4f} {r['test_auc_pr']:>12.4f}{marker}")

    print(f"\nMLflow UI: {MLFLOW_TRACKING_URI}")
    print("=" * 60)


if __name__ == "__main__":
    main()
