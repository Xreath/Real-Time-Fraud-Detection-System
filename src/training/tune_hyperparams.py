"""
Hyperparameter Tuning - Optuna ile LightGBM optimizasyonu.

Optuna, Bayesian optimization kullanarak en iyi hyperparameter
kombinasyonunu arar. Grid search'ten daha verimli: kotu parametreleri
erken keser (pruning), iyi yonlerde derinlesir.

Kullanim:
    python -m src.training.tune_hyperparams [--n-trials 50]

Mulakat notu:
  "Neden Optuna?" -> Grid Search: tum kombinasyonlari dener (N^k).
  Random Search: rastgele dener. Optuna: TPE (Tree-structured Parzen
  Estimator) ile onceki sonuclara bakarak akilli arama yapar.
  Ayrica MedianPruner ile kotu denemeler erken kesilir.
"""

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import optuna
import lightgbm as lgb
import mlflow
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import f1_score, average_precision_score

from src.config import MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT_NAME

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

SPLITS_DIR = Path("data/splits")

FEATURE_COLUMNS = [
    "amount", "latitude", "longitude",
    "is_weekend", "is_night", "is_foreign",
    "hour_of_day", "day_of_week", "amount_log",
    "is_high_amount", "is_round_amount",
    "distance_km", "time_diff_hours", "speed_kmh",
]

CATEGORICAL_COLUMNS = ["merchant_category", "card_type", "country"]
TARGET = "is_fraud"


def load_and_preprocess():
    """Veriyi yukle ve preprocess et."""
    train = pd.read_parquet(SPLITS_DIR / "train.parquet")
    val = pd.read_parquet(SPLITS_DIR / "val.parquet")

    # Label encoding
    label_encoders = {}
    for col in CATEGORICAL_COLUMNS:
        le = LabelEncoder()
        all_values = pd.concat([train[col], val[col]]).astype(str)
        le.fit(all_values)
        train[col] = le.transform(train[col].astype(str))
        val[col] = le.transform(val[col].astype(str))
        label_encoders[col] = le

    feature_names = FEATURE_COLUMNS + CATEGORICAL_COLUMNS
    X_train = train[feature_names].fillna(0).values
    X_val = val[feature_names].fillna(0).values
    y_train = train[TARGET].values
    y_val = val[TARGET].values

    scaler = StandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)

    pos_weight = (y_train == 0).sum() / (y_train == 1).sum()

    return X_train, X_val, y_train, y_val, feature_names, pos_weight


def objective(trial, X_train, X_val, y_train, y_val, pos_weight):
    """
    Optuna objective fonksiyonu.

    Her trial icin bir LightGBM modeli egitir ve AUC-PR dondurur.
    Optuna bu degeri maximize etmeye calisir.

    Hyperparameter arama uzayi:
      n_estimators:   100-1000  (agac sayisi)
      max_depth:      3-12      (agac derinligi)
      learning_rate:  0.01-0.3  (ogrenme hizi)
      num_leaves:     15-127    (yaprak sayisi)
      min_child_samples: 5-100  (minimum yaprak ornegi)
      subsample:      0.5-1.0   (satir ornekleme)
      colsample_bytree: 0.5-1.0 (feature ornekleme)
      reg_alpha:      1e-8-10   (L1 regularization)
      reg_lambda:     1e-8-10   (L2 regularization)
    """
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 1000),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "num_leaves": trial.suggest_int("num_leaves", 15, 127),
        "min_child_samples": trial.suggest_int("min_child_samples", 5, 100),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10.0, log=True),
        "scale_pos_weight": pos_weight,
        "random_state": 42,
        "n_jobs": -1,
        "verbose": -1,
    }

    model = lgb.LGBMClassifier(**params)
    model.fit(X_train, y_train)

    y_val_prob = model.predict_proba(X_val)[:, 1]
    auc_pr = average_precision_score(y_val, y_val_prob)

    return auc_pr


def main(n_trials: int = 50):
    print("=" * 60)
    print("Hyperparameter Tuning - Optuna + LightGBM")
    print("=" * 60)

    # Veri yukle
    print("\n[1/3] Veri yukleniyor...")
    X_train, X_val, y_train, y_val, feature_names, pos_weight = load_and_preprocess()
    print(f"  Train: {len(y_train):,} | Val: {len(y_val):,}")
    print(f"  pos_weight: {pos_weight:.1f}")

    # Optuna study
    print(f"\n[2/3] Optuna arama basliyor ({n_trials} trial)...")
    study = optuna.create_study(direction="maximize", study_name="lgbm-tuning")
    study.optimize(
        lambda trial: objective(trial, X_train, X_val, y_train, y_val, pos_weight),
        n_trials=n_trials,
    )

    # Sonuclar
    best = study.best_trial
    print(f"\nEn iyi AUC-PR: {best.value:.6f}")
    print(f"En iyi parametreler:")
    for k, v in best.params.items():
        print(f"  {k}: {v}")

    # En iyi model ile final training + MLflow log
    print(f"\n[3/3] En iyi parametrelerle final model egitiliyor...")
    import os
    os.environ.setdefault("MLFLOW_S3_ENDPOINT_URL", "http://localhost:9000")
    os.environ.setdefault("AWS_ACCESS_KEY_ID", "minioadmin")
    os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "minioadmin")

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    final_params = best.params.copy()
    final_params["scale_pos_weight"] = pos_weight
    final_params["random_state"] = 42
    final_params["n_jobs"] = -1
    final_params["verbose"] = -1

    final_model = lgb.LGBMClassifier(**final_params)
    final_model.fit(X_train, y_train)

    y_val_pred = final_model.predict(X_val)
    y_val_prob = final_model.predict_proba(X_val)[:, 1]
    f1 = f1_score(y_val, y_val_pred)
    auc_pr = average_precision_score(y_val, y_val_prob)

    with mlflow.start_run(run_name="LightGBM-Optuna-Tuned"):
        mlflow.log_params(best.params)
        mlflow.log_param("model_type", "lightgbm_optuna")
        mlflow.log_param("n_trials", n_trials)
        mlflow.log_metric("val_f1", f1)
        mlflow.log_metric("val_auc_pr", auc_pr)

        from mlflow.models import infer_signature
        signature = infer_signature(
            pd.DataFrame(X_val[:5], columns=feature_names),
            y_val_pred[:5],
        )
        mlflow.sklearn.log_model(
            final_model, "model",
            signature=signature,
            input_example=pd.DataFrame(X_val[:3], columns=feature_names),
        )

        run_id = mlflow.active_run().info.run_id

    print(f"\n  Val F1:     {f1:.4f}")
    print(f"  Val AUC-PR: {auc_pr:.4f}")
    print(f"  MLflow run: {run_id}")

    # Eger baseline'dan iyiyse register et
    print(f"\nOptuna tuning tamamlandi.")
    print(f"  Iyilestirme varsa: MLflow UI'dan modeli 'fraud-detection-model' olarak register edin")
    print(f"  MLflow UI: {MLFLOW_TRACKING_URI}")

    return study


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Optuna Hyperparameter Tuning")
    parser.add_argument("--n-trials", type=int, default=50, help="Optuna trial sayisi")
    args = parser.parse_args()
    main(n_trials=args.n_trials)
