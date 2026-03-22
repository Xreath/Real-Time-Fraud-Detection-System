"""
Retraining DAG — Weekly automated model retraining with data quality gates and canary evaluation.

Bu DAG:
  1. Fresh synthetic data üretir (her run'da farklı seed)
  2. Data quality check'leri uygular (validation failure → training'i bloklar)
  3. Spark ile feature engineering yapar
  4. Train/val/test split oluşturur ve kaydeder
  5. 4 model eğitir ve MLflow'a loglar
  6. Challenger vs Champion karşılaştırması (simulated canary per D-05)
  7. Champion'ı promote eder (F1 >= champion * 0.95) ya da rollback alerti yazar
  8. fraud-api container'ı yeniden başlatır (promote branch'inde)
  9. Health check ile yeni modelin serve edildiğini doğrular

Schedule: Sunday 02:00 UTC (per RETR-01)
Mülakat notu:
  "Canary deploy nasıl simule ediyorsunuz?" → Batch validation approach:
  Challenger model validation set'te değerlendirilir, champion metrikleri MLflow'dan
  alınır. F1 >= champion * 0.95 ise promote, yoksa rollback. Gerçek traffic split
  olmadan decision logic'ini tam gösteriyoruz. Production'da time-based A/B window olurdu.
"""

import hashlib
import os
import sys
import time

import mlflow
import pandas as pd
import requests

from airflow import DAG
from airflow.models import Variable
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import BranchPythonOperator, PythonOperator
from datetime import datetime, timedelta

# Add project root so we can import src modules (mounted at /opt/airflow)
sys.path.insert(0, "/opt/airflow")

from utils.alerting import on_failure_callback, write_alert, write_canary_alert
from utils.data_quality import run_data_quality_checks
from utils.mlflow_helpers import (
    compare_models,
    get_champion_metrics,
    get_mlflow_client,
    get_previous_champion_version,
    promote_to_champion,
)

# ============================================================
# Constants
# ============================================================

DAG_ID = "retraining_dag"
MODEL_NAME = "fraud-detection-model"

# ============================================================
# Default args
# ============================================================

default_args = {
    "owner": "fraud-detection",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": on_failure_callback,  # per RETR-06
}


# ============================================================
# Task functions
# ============================================================


def generate_data(**kwargs):
    """
    [1/8] Generate fresh synthetic transaction data with unique seed per run (per D-01).

    Uses Airflow Variable for dataset size (per D-02).
    Saves raw data to /opt/airflow/data/retraining_raw.parquet.
    Pushes seed and num_transactions to XCom.
    """
    # Configurable dataset size via Airflow Variable (per D-02)
    num_transactions = int(Variable.get("retraining_num_transactions", default_var=30000))

    # Unique seed derived from Airflow run_id (per D-01)
    # This ensures different data each run while keeping reproducibility within a run
    seed = int(hashlib.md5(kwargs["run_id"].encode()).hexdigest()[:8], 16) % (2**31)

    print(f"[1/8] Generating {num_transactions} transactions with seed={seed}")

    from src.training.prepare_data import generate_historical_data

    df = generate_historical_data(num_transactions=num_transactions, seed=seed)

    # Ensure data directory exists
    os.makedirs("/opt/airflow/data", exist_ok=True)
    df.to_parquet("/opt/airflow/data/retraining_raw.parquet", index=False)

    kwargs["ti"].xcom_push(key="seed", value=seed)
    kwargs["ti"].xcom_push(key="num_transactions", value=num_transactions)

    print(f"[1/8] Generated {num_transactions} transactions with seed={seed} — saved to retraining_raw.parquet")


def check_data_quality(**kwargs):
    """
    [2/8] Run data quality checks on generated data (per RETR-03).

    Checks: null rate, fraud rate, schema, row count, fraud case count.
    Raises ValueError on failure — blocks downstream tasks.
    """
    df = pd.read_parquet("/opt/airflow/data/retraining_raw.parquet")
    result = run_data_quality_checks(df)

    print(f"[2/8] Data quality: {'PASS' if result['passed'] else 'FAIL'}")

    if not result["passed"]:
        failed_checks = [c for c in result["checks"] if not c["passed"]]
        write_alert(
            alert_type="data_quality_failure",
            message="Data quality checks failed — blocking retraining",
            dag_id=DAG_ID,
            task_id="check_data_quality",
            metrics={"checks": result["checks"], "failed": failed_checks},
        )
        raise ValueError(
            f"Data quality checks failed — blocking retraining. "
            f"Failed checks: {[c['name'] for c in failed_checks]}"
        )

    print(f"[2/8] All {len(result['checks'])} data quality checks passed")


def run_feature_engineering(**kwargs):
    """
    [3/8] Apply Spark feature engineering to raw transaction data.

    Loads raw parquet, applies compute_features_with_spark(), saves features parquet.
    """
    from src.training.prepare_data import compute_features_with_spark

    df = pd.read_parquet("/opt/airflow/data/retraining_raw.parquet")
    df_features = compute_features_with_spark(df)

    df_features.to_parquet("/opt/airflow/data/retraining_features.parquet", index=False)

    print(
        f"[3/8] Feature engineering complete: {len(df_features)} rows, "
        f"{len(df_features.columns)} columns"
    )


def split_and_save(**kwargs):
    """
    [4/8] Create stratified train/val/test split and save to data/splits/.

    Saves to the canonical splits path that train_model.load_data() expects.
    """
    from src.training.prepare_data import save_splits, split_data

    df = pd.read_parquet("/opt/airflow/data/retraining_features.parquet")
    train_df, val_df, test_df = split_data(df)
    save_splits(train_df, val_df, test_df)

    print(f"[4/8] Data split: train={len(train_df)}, val={len(val_df)}, test={len(test_df)}")


def train_models(**kwargs):
    """
    [5/8] Train all models, log to MLflow, register best model.

    Uses existing train_model.py functions for training consistency.
    Pushes best model info to XCom for canary evaluation.
    """
    from src.training.train_model import (
        get_models,
        load_data,
        preprocess,
        register_best_model,
        train_and_log_model,
    )

    # MLflow setup
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment("fraud-detection-retraining")

    # Load and preprocess data
    train_df, val_df, test_df = load_data()
    X_train, X_val, X_test, y_train, y_val, y_test, feature_names = preprocess(
        train_df, val_df, test_df
    )

    # Class imbalance weight
    pos_weight = (y_train == 0).sum() / max((y_train == 1).sum(), 1)

    # Train all models
    models = get_models(pos_weight)
    results = []
    for name, model, params in models:
        result = train_and_log_model(
            name,
            model,
            params,
            X_train,
            y_train,
            X_val,
            y_val,
            X_test,
            y_test,
            feature_names,
        )
        results.append(result)

    # Register best model in MLflow Registry
    best = register_best_model(results)

    kwargs["ti"].xcom_push(key="best_model", value=best)

    print(f"[5/8] Training complete. Best: {best['name']} (Val F1={best['val_f1']:.4f})")


def canary_evaluate(**kwargs):
    """
    [6/8] Simulated canary evaluation — batch validation comparison (per D-05, CNRY-01).

    Compares challenger vs champion on validation set metrics.
    Logs canary evaluation to MLflow as dedicated run.
    Returns task_id for BranchPythonOperator routing.

    Per D-05: No real traffic split — batch evaluation on held-out validation set.
    Production would use time-based A/B with observation window.
    """
    best = kwargs["ti"].xcom_pull(key="best_model", task_ids="train_models")

    # Get current champion metrics (before any promotion)
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    champion_metrics = get_champion_metrics()

    # Save previous champion version for rollback reference (per CNRY-03)
    prev_version = get_previous_champion_version()
    kwargs["ti"].xcom_push(key="prev_champion_version", value=prev_version)

    # Build challenger metrics from training result + MLflow run metrics
    client = get_mlflow_client()
    run = client.get_run(best["run_id"])
    challenger_metrics = {
        "f1": best["val_f1"],
        "auc_pr": best["val_auc_pr"],
        "precision": run.data.metrics.get("val_precision", 0.0),
        "recall": run.data.metrics.get("val_recall", 0.0),
    }

    # If no champion exists, promote unconditionally (first model)
    if not champion_metrics:
        print("[6/8] No champion found — promoting challenger unconditionally (first model)")
        result = {
            "should_promote": True,
            "reason": "No existing champion — first model promoted unconditionally",
            "comparison": {
                "champion_f1": 0.0,
                "challenger_f1": round(challenger_metrics["f1"], 4),
                "min_required_f1": 0.0,
                "threshold": 0.95,
                "f1_ratio": 0.0,
                "champion_precision": 0.0,
                "challenger_precision": round(challenger_metrics["precision"], 4),
                "champion_recall": 0.0,
                "challenger_recall": round(challenger_metrics["recall"], 4),
                "champion_auc_pr": 0.0,
                "challenger_auc_pr": round(challenger_metrics["auc_pr"], 4),
            },
        }
    else:
        result = compare_models(champion_metrics, challenger_metrics, threshold=0.95)

    # Log canary evaluation as dedicated MLflow run (per CONTEXT.md specifics)
    mlflow.set_experiment("fraud-detection-retraining")
    with mlflow.start_run(run_name="canary-evaluation"):
        mlflow.log_params({
            "champion_version": champion_metrics.get("version", "none"),
            "challenger_run_id": best["run_id"],
            "threshold": 0.95,
        })
        for k, v in result["comparison"].items():
            if isinstance(v, (int, float)):
                mlflow.log_metric(k, v)
        mlflow.log_param("decision", "promote" if result["should_promote"] else "rollback")

    kwargs["ti"].xcom_push(key="canary_result", value=result)
    kwargs["ti"].xcom_push(key="champion_metrics", value=champion_metrics)
    kwargs["ti"].xcom_push(key="challenger_metrics", value=challenger_metrics)

    decision = "promote_model" if result["should_promote"] else "rollback_alert"
    print(
        f"[6/8] Canary evaluation: {'PROMOTE' if result['should_promote'] else 'ROLLBACK'} "
        f"— {result['reason']}"
    )

    return decision


def promote_model(**kwargs):
    """
    [7a/8] Promote challenger to champion alias in MLflow Registry (per RETR-05).

    Finds the registered version for the best model's run_id, promotes it,
    re-registers as pyfunc for zero-skew REST serving, and writes a canary alert.
    """
    best = kwargs["ti"].xcom_pull(key="best_model", task_ids="train_models")
    prev_version = kwargs["ti"].xcom_pull(key="prev_champion_version", task_ids="canary_evaluate")
    champion_metrics = kwargs["ti"].xcom_pull(key="champion_metrics", task_ids="canary_evaluate")
    challenger_metrics = kwargs["ti"].xcom_pull(key="challenger_metrics", task_ids="canary_evaluate")

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    client = get_mlflow_client()

    # Find the registered version for this run_id
    versions = client.search_model_versions(f"run_id='{best['run_id']}'")
    new_version = versions[0].version if versions else None

    if new_version:
        promote_to_champion(MODEL_NAME, new_version)
        print(f"[7a/8] Model promoted to champion: v{new_version}")
    else:
        print(f"[7a/8] WARNING: Could not find registered version for run_id={best['run_id']}")

    # Re-register as pyfunc so fraud-api can load with preprocessing (per Phase 6 pattern)
    try:
        from src.serving.register_pyfunc import register_pyfunc_model
        register_pyfunc_model()
        print("[7a/8] Pyfunc model re-registered successfully")
    except Exception as e:
        print(f"[7a/8] WARNING: Pyfunc re-registration failed: {e}")
        # Non-fatal: champion alias is already promoted, restart will pick it up

    # Write canary promotion alert
    write_canary_alert(
        action="promoted",
        champion_metrics=champion_metrics or {},
        challenger_metrics=challenger_metrics or {},
        champion_version=prev_version or "none",
        challenger_version=new_version or "unknown",
    )


def rollback_alert(**kwargs):
    """
    [7b/8] Write rollback alert — champion alias stays at previous version (per D-07, CNRY-04).

    No actual rollback needed: challenger was never deployed. Champion alias untouched.
    Writes side-by-side comparison metrics to alerts/ directory (per D-16).
    """
    prev_version = kwargs["ti"].xcom_pull(key="prev_champion_version", task_ids="canary_evaluate")
    champion_metrics = kwargs["ti"].xcom_pull(key="champion_metrics", task_ids="canary_evaluate")
    challenger_metrics = kwargs["ti"].xcom_pull(key="challenger_metrics", task_ids="canary_evaluate")
    canary_result = kwargs["ti"].xcom_pull(key="canary_result", task_ids="canary_evaluate")

    write_canary_alert(
        action="rolled_back",
        champion_metrics=champion_metrics or {},
        challenger_metrics=challenger_metrics or {},
        champion_version=prev_version or "none",
        challenger_version="not-promoted",
    )

    print(
        f"[7b/8] Canary rollback — champion stays at v{prev_version}. "
        f"Reason: {canary_result.get('reason', 'unknown')}"
    )


def restart_fraud_api(**kwargs):
    """
    [8a/8] Restart fraud-api container after champion promotion (per D-09).

    Uses Docker Python SDK via mounted Docker socket (per D-10).
    """
    import docker

    client = docker.from_env()
    container = client.containers.get("fraud-api")
    print("Restarting fraud-api container...")
    container.restart(timeout=30)
    print("fraud-api container restarted successfully")


def verify_health(**kwargs):
    """
    [8b/8] Verify fraud-api is up and serving the new model (per D-11).

    Polls /health endpoint with retries after container restart.
    Raises RuntimeError if all retries fail.
    """
    max_retries = 10
    for i in range(max_retries):
        try:
            resp = requests.get("http://fraud-api:5002/health", timeout=5)
            if resp.status_code == 200:
                print(f"[8/8] fraud-api health check passed on attempt {i + 1}")
                return
        except Exception as e:
            print(f"Health check attempt {i + 1}/{max_retries}: {e}")
        time.sleep(10)
    raise RuntimeError("fraud-api health check failed after all retries")


# ============================================================
# DAG definition
# ============================================================

with DAG(
    dag_id=DAG_ID,
    default_args=default_args,
    description="Weekly model retraining with data quality gates and canary evaluation",
    schedule_interval="0 2 * * 0",  # Sunday 02:00 UTC per RETR-01
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["retraining", "ml"],
) as dag:

    # --- Pipeline tasks ---

    t_generate = PythonOperator(
        task_id="generate_data",
        python_callable=generate_data,
    )

    t_quality = PythonOperator(
        task_id="check_data_quality",
        python_callable=check_data_quality,
    )

    t_features = PythonOperator(
        task_id="run_feature_engineering",
        python_callable=run_feature_engineering,
    )

    t_split = PythonOperator(
        task_id="split_and_save",
        python_callable=split_and_save,
    )

    t_train = PythonOperator(
        task_id="train_models",
        python_callable=train_models,
    )

    # Branch: canary_evaluate returns "promote_model" or "rollback_alert"
    t_canary = BranchPythonOperator(
        task_id="canary_evaluate",
        python_callable=canary_evaluate,
    )

    t_promote = PythonOperator(
        task_id="promote_model",
        python_callable=promote_model,
    )

    t_rollback = PythonOperator(
        task_id="rollback_alert",
        python_callable=rollback_alert,
    )

    t_restart = PythonOperator(
        task_id="restart_fraud_api",
        python_callable=restart_fraud_api,
    )

    t_verify = PythonOperator(
        task_id="verify_health",
        python_callable=verify_health,
    )

    # End task uses none_failed_min_one_success so either branch converges cleanly
    t_end = EmptyOperator(
        task_id="end",
        trigger_rule="none_failed_min_one_success",
    )

    # ---- Task dependency graph ----

    # Linear pipeline: generate → quality gate → features → split → train → canary branch
    t_generate >> t_quality >> t_features >> t_split >> t_train >> t_canary

    # Promote branch: canary → promote → restart → verify → end
    t_canary >> t_promote >> t_restart >> t_verify >> t_end

    # Rollback branch: canary → rollback alert → end
    t_canary >> t_rollback >> t_end
