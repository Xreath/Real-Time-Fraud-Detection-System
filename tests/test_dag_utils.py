"""Unit tests for airflow/dags/utils/ modules."""
import json
import os
import sys
import tempfile
import pytest
import pandas as pd
import numpy as np

# Add DAG utils to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "airflow", "dags"))

from utils.data_quality import run_data_quality_checks, EXPECTED_COLUMNS, MIN_ROWS
from utils.mlflow_helpers import compare_models


def _make_valid_df(n_rows=2000, fraud_rate=0.02):
    """Create a valid DataFrame that passes all DQ checks."""
    np.random.seed(42)
    n_fraud = int(n_rows * fraud_rate)
    n_normal = n_rows - n_fraud
    df = pd.DataFrame({
        "transaction_id": [f"tx_{i}" for i in range(n_rows)],
        "user_id": [f"user_{i % 100}" for i in range(n_rows)],
        "amount": np.random.uniform(1, 1000, n_rows),
        "merchant": [f"merchant_{i % 50}" for i in range(n_rows)],
        "merchant_category": [f"cat_{i % 10}" for i in range(n_rows)],
        "card_type": ["visa"] * n_rows,
        "latitude": np.random.uniform(30, 45, n_rows),
        "longitude": np.random.uniform(-120, -70, n_rows),
        "is_weekend": np.random.randint(0, 2, n_rows),
        "is_night": np.random.randint(0, 2, n_rows),
        "is_foreign": np.random.randint(0, 2, n_rows),
        "is_fraud": [1] * n_fraud + [0] * n_normal,
    })
    return df


class TestDataQuality:

    def test_data_quality_all_pass(self):
        df = _make_valid_df()
        result = run_data_quality_checks(df)
        assert result["passed"] == True
        assert all(c["passed"] for c in result["checks"])

    def test_data_quality_too_few_rows(self):
        df = _make_valid_df(n_rows=500)
        result = run_data_quality_checks(df)
        assert result["passed"] == False
        min_rows_check = [c for c in result["checks"] if c["name"] == "min_rows"][0]
        assert min_rows_check["passed"] == False

    def test_data_quality_high_null_rate(self):
        df = _make_valid_df()
        df.loc[:199, "amount"] = None  # 10% nulls
        result = run_data_quality_checks(df)
        assert result["passed"] == False
        null_check = [c for c in result["checks"] if c["name"] == "null_rate"][0]
        assert null_check["passed"] == False

    def test_data_quality_no_fraud_column(self):
        df = _make_valid_df()
        df = df.drop(columns=["is_fraud"])
        result = run_data_quality_checks(df)
        assert result["passed"] == False
        schema_check = [c for c in result["checks"] if c["name"] == "schema_match"][0]
        assert schema_check["passed"] == False


class TestCompareModels:

    def test_compare_models_promote(self):
        result = compare_models({"f1": 0.95}, {"f1": 0.96})
        assert result["should_promote"] is True

    def test_compare_models_rollback(self):
        result = compare_models({"f1": 0.95}, {"f1": 0.80})
        assert result["should_promote"] is False

    def test_compare_models_edge_threshold(self):
        # Exactly at threshold: 0.95 * 0.95 = 0.9025
        result = compare_models({"f1": 0.95}, {"f1": 0.9025})
        assert result["should_promote"] is True

    def test_compare_models_below_threshold(self):
        # Just below threshold: challenger F1 < champion * 0.95
        result = compare_models({"f1": 0.95}, {"f1": 0.9024})
        assert result["should_promote"] is False


class TestAlerting:

    def test_write_alert_creates_file(self, tmp_path):
        """write_alert should create a JSON file with correct content."""
        import utils.alerting as alerting_module
        # Override the module-level ALERTS_DIR to use tmp_path
        original_alerts_dir = alerting_module.ALERTS_DIR
        alerting_module.ALERTS_DIR = tmp_path
        try:
            path = alerting_module.write_alert(
                alert_type="test_alert",
                message="Test message",
                dag_id="test_dag",
            )
            assert os.path.exists(path)
            with open(path) as f:
                data = json.load(f)
            assert data["alert_type"] == "test_alert"
            assert data["message"] == "Test message"
        finally:
            alerting_module.ALERTS_DIR = original_alerts_dir

    def test_write_canary_alert_has_comparison(self, tmp_path):
        """write_canary_alert should write a JSON file with champion/challenger metrics."""
        import utils.alerting as alerting_module
        original_alerts_dir = alerting_module.ALERTS_DIR
        alerting_module.ALERTS_DIR = tmp_path
        try:
            path = alerting_module.write_canary_alert(
                action="rolled_back",
                champion_metrics={"f1": 0.95, "precision": 0.90, "recall": 0.88, "auc_pr": 0.97},
                challenger_metrics={"f1": 0.80, "precision": 0.75, "recall": 0.70, "auc_pr": 0.82},
                champion_version="5",
                challenger_version="6",
            )
            with open(path) as f:
                data = json.load(f)
            assert "champion" in str(data["metrics"])
            assert "challenger" in str(data["metrics"])
        finally:
            alerting_module.ALERTS_DIR = original_alerts_dir
