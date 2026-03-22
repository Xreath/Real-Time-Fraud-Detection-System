"""
Airflow DAG alerting utilities — per D-13, D-14, D-15, D-16.

Dual-channel alerting:
  1. Airflow task logs (print statements for immediate visibility)
  2. Structured JSON alert files in alerts/ directory for persistence
"""
import json
import os
from datetime import datetime
from pathlib import Path

ALERTS_DIR = Path(os.getenv("ALERTS_DIR", "/opt/airflow/alerts"))


def write_alert(
    alert_type: str,
    message: str,
    dag_id: str = "",
    task_id: str = "",
    metrics: dict | None = None,
    model_versions: dict | None = None,
    mlflow_run_id: str = "",
) -> str:
    """
    Write a structured JSON alert to the alerts/ directory (per D-14).

    Args:
        alert_type: e.g. 'dag_failure', 'canary_rollback', 'retraining_trigger', 'data_quality_failure'
        message: Human-readable description
        dag_id: Airflow DAG ID
        task_id: Airflow task ID
        metrics: Dict of relevant metrics (F1, AUC-PR, etc.)
        model_versions: Dict with 'champion' and/or 'challenger' version info
        mlflow_run_id: Associated MLflow run ID

    Returns:
        Path to the written alert file.
    """
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{alert_type}.json"
    filepath = ALERTS_DIR / filename

    alert = {
        "alert_type": alert_type,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "message": message,
        "dag_id": dag_id,
        "task_id": task_id,
        "metrics": metrics or {},
        "model_versions": model_versions or {},
        "mlflow_run_id": mlflow_run_id,
    }

    filepath.write_text(json.dumps(alert, indent=2, default=str))
    print(f"[ALERT] {alert_type}: {message}")
    print(f"[ALERT] Written to: {filepath}")
    return str(filepath)


def write_canary_alert(
    action: str,
    champion_metrics: dict,
    challenger_metrics: dict,
    champion_version: str,
    challenger_version: str,
    threshold: float = 0.95,
    mlflow_run_id: str = "",
) -> str:
    """
    Write canary evaluation alert with side-by-side comparison (per D-16).

    Args:
        action: 'promoted' or 'rolled_back'
        champion_metrics: dict with f1, precision, recall, auc_pr
        challenger_metrics: dict with f1, precision, recall, auc_pr
        champion_version: MLflow model version string
        challenger_version: MLflow model version string
        threshold: F1 threshold ratio (default 0.95 per CNRY-02)
        mlflow_run_id: Associated MLflow run ID
    """
    comparison = {
        "champion": {
            "version": champion_version,
            **{k: round(v, 4) for k, v in champion_metrics.items()},
        },
        "challenger": {
            "version": challenger_version,
            **{k: round(v, 4) for k, v in challenger_metrics.items()},
        },
        "threshold": threshold,
        "decision": action,
    }

    message = (
        f"Canary {action}: challenger v{challenger_version} vs champion v{champion_version}. "
        f"Challenger F1={challenger_metrics.get('f1', 0):.4f}, "
        f"Champion F1={champion_metrics.get('f1', 0):.4f}, "
        f"Threshold={threshold}"
    )

    return write_alert(
        alert_type=f"canary_{action}",
        message=message,
        dag_id="retraining_dag",
        metrics=comparison,
        model_versions={"champion": champion_version, "challenger": challenger_version},
        mlflow_run_id=mlflow_run_id,
    )


def on_failure_callback(context: dict) -> None:
    """
    Airflow on_failure_callback — logs error and writes alert file (per RETR-06, D-13).

    Args:
        context: Airflow callback context dict with 'dag', 'task_instance', 'exception', etc.
    """
    dag_id = context.get("dag", {}).dag_id if hasattr(context.get("dag", {}), "dag_id") else str(context.get("dag", "unknown"))
    task_id = context.get("task_instance", {}).task_id if hasattr(context.get("task_instance", {}), "task_id") else str(context.get("task_instance", "unknown"))
    exception = str(context.get("exception", "Unknown error"))
    execution_date = str(context.get("execution_date", ""))

    message = f"Task {task_id} in DAG {dag_id} failed: {exception}"
    print(f"[FAILURE] {message}")
    print(f"[FAILURE] Execution date: {execution_date}")

    write_alert(
        alert_type="dag_failure",
        message=message,
        dag_id=dag_id,
        task_id=task_id,
        metrics={"execution_date": execution_date, "exception": exception},
    )
