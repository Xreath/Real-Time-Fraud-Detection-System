"""
MLflow helper functions for DAG operations.

Provides:
  - Champion model metric retrieval
  - Model comparison logic (challenger vs champion)
  - Champion alias promotion
  - Pyfunc re-registration after promotion
"""
import os
import mlflow
import mlflow.pyfunc
from mlflow.tracking import MlflowClient

MODEL_NAME = "fraud-detection-model"
CHAMPION_ALIAS = "champion"
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")


def get_mlflow_client() -> MlflowClient:
    """Get configured MLflow client."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    return MlflowClient(MLFLOW_TRACKING_URI)


def get_champion_metrics(model_name: str = MODEL_NAME) -> dict:
    """
    Retrieve metrics for the current champion model from MLflow.

    Returns:
        dict with keys: version, run_id, f1, precision, recall, auc_pr
        Returns empty dict if no champion alias exists.
    """
    client = get_mlflow_client()
    try:
        mv = client.get_model_version_by_alias(model_name, CHAMPION_ALIAS)
        run = client.get_run(mv.run_id)
        metrics = run.data.metrics
        return {
            "version": mv.version,
            "run_id": mv.run_id,
            "f1": metrics.get("val_f1", metrics.get("f1", 0.0)),
            "precision": metrics.get("val_precision", metrics.get("precision", 0.0)),
            "recall": metrics.get("val_recall", metrics.get("recall", 0.0)),
            "auc_pr": metrics.get("val_auc_pr", metrics.get("auc_pr", 0.0)),
        }
    except Exception as e:
        print(f"[WARNING] Could not retrieve champion metrics: {e}")
        return {}


def compare_models(
    champion_metrics: dict,
    challenger_metrics: dict,
    threshold: float = 0.95,
) -> dict:
    """
    Compare challenger vs champion using F1 as primary gate (per D-08, CNRY-02).

    The challenger must achieve F1 >= champion_F1 * threshold to be promoted.

    Args:
        champion_metrics: dict with f1, precision, recall, auc_pr
        challenger_metrics: dict with f1, precision, recall, auc_pr
        threshold: F1 ratio threshold (default 0.95 per CNRY-02)

    Returns:
        dict with: should_promote (bool), reason (str), comparison (dict)
    """
    champ_f1 = champion_metrics.get("f1", 0.0)
    chall_f1 = challenger_metrics.get("f1", 0.0)
    min_f1 = champ_f1 * threshold

    should_promote = chall_f1 >= min_f1

    comparison = {
        "champion_f1": round(champ_f1, 4),
        "challenger_f1": round(chall_f1, 4),
        "min_required_f1": round(min_f1, 4),
        "threshold": threshold,
        "f1_ratio": round(chall_f1 / champ_f1, 4) if champ_f1 > 0 else 0.0,
    }

    # Also compare on secondary metrics for logging (per D-08)
    for metric in ["precision", "recall", "auc_pr"]:
        comparison[f"champion_{metric}"] = round(champion_metrics.get(metric, 0.0), 4)
        comparison[f"challenger_{metric}"] = round(challenger_metrics.get(metric, 0.0), 4)

    if should_promote:
        reason = f"Challenger F1={chall_f1:.4f} >= {min_f1:.4f} (champion * {threshold}). Promoting."
    else:
        reason = f"Challenger F1={chall_f1:.4f} < {min_f1:.4f} (champion * {threshold}). Rolling back."

    print(f"[COMPARE] {reason}")
    return {"should_promote": should_promote, "reason": reason, "comparison": comparison}


def promote_to_champion(
    model_name: str,
    version: str,
    model_name_registry: str = MODEL_NAME,
) -> None:
    """
    Set the @champion alias to the given model version in MLflow Registry (per RETR-05).

    Args:
        model_name: The registered model name
        version: The version string to promote
        model_name_registry: Registry name (default: fraud-detection-model)
    """
    client = get_mlflow_client()
    client.set_registered_model_alias(
        name=model_name_registry,
        alias=CHAMPION_ALIAS,
        version=version,
    )
    print(f"[PROMOTE] Set @champion alias to v{version} for {model_name_registry}")


def get_previous_champion_version(model_name: str = MODEL_NAME) -> str | None:
    """
    Get the current champion version BEFORE promotion (for rollback reference per CNRY-03).

    Returns:
        Version string or None if no champion exists.
    """
    client = get_mlflow_client()
    try:
        mv = client.get_model_version_by_alias(model_name, CHAMPION_ALIAS)
        return mv.version
    except Exception:
        return None
