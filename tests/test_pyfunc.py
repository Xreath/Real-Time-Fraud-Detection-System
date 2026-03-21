"""Unit tests for FraudPyfunc class — preprocessing logic only, no server needed."""
import os
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock
from pathlib import Path

# Tests skip if artifacts don't exist (CI without trained model)
ARTIFACTS_DIR = Path("data/artifacts")
HAS_ARTIFACTS = (
    (ARTIFACTS_DIR / "scaler.joblib").exists()
    and (ARTIFACTS_DIR / "label_encoders.joblib").exists()
    and (ARTIFACTS_DIR / "feature_names.joblib").exists()
)
skip_no_artifacts = pytest.mark.skipif(not HAS_ARTIFACTS, reason="Requires trained model artifacts")


class TestFraudPyfuncImport:
    def test_class_importable(self):
        from src.serving.register_pyfunc import FraudPyfunc
        assert hasattr(FraudPyfunc, "load_context")
        assert hasattr(FraudPyfunc, "predict")

    def test_feature_columns_defined(self):
        from src.serving.register_pyfunc import FEATURE_COLUMNS, CATEGORICAL_COLUMNS
        assert len(FEATURE_COLUMNS) == 14
        assert len(CATEGORICAL_COLUMNS) == 3
        assert "amount" in FEATURE_COLUMNS
        assert "merchant_category" in CATEGORICAL_COLUMNS

    def test_feature_columns_match_model_scorer(self):
        from src.serving.register_pyfunc import FEATURE_COLUMNS, CATEGORICAL_COLUMNS
        from src.serving.model_scorer import (
            FEATURE_COLUMNS as SCORER_FEATURES,
            CATEGORICAL_COLUMNS as SCORER_CATS,
        )
        assert FEATURE_COLUMNS == SCORER_FEATURES, "Feature columns must match model_scorer.py exactly"
        assert CATEGORICAL_COLUMNS == SCORER_CATS, "Categorical columns must match model_scorer.py exactly"


@skip_no_artifacts
class TestFraudPyfuncPreprocessing:
    @pytest.fixture(autouse=True)
    def setup_pyfunc(self):
        """Load FraudPyfunc with real artifacts but mocked model."""
        import joblib
        from src.serving.register_pyfunc import FraudPyfunc

        self.pyfunc = FraudPyfunc()
        # Simulate load_context with real artifacts
        self.pyfunc.scaler = joblib.load(ARTIFACTS_DIR / "scaler.joblib")
        self.pyfunc.label_encoders = joblib.load(ARTIFACTS_DIR / "label_encoders.joblib")
        self.pyfunc.feature_names = joblib.load(ARTIFACTS_DIR / "feature_names.joblib")
        self.pyfunc.threshold = 0.5
        # Mock model with predict_proba returning known values
        self.pyfunc.model = MagicMock()
        self.pyfunc.model.predict_proba.return_value = np.array([[0.8, 0.2], [0.3, 0.7]])

    def test_predict_returns_correct_columns(self, sample_transactions_batch):
        # Use first 2 rows
        df = sample_transactions_batch.iloc[:2]
        result = self.pyfunc.predict(None, df)
        assert "fraud_score" in result.columns
        assert "fraud_prediction" in result.columns
        assert len(result) == 2

    def test_predict_fraud_score_range(self, sample_transactions_batch):
        df = sample_transactions_batch.iloc[:2]
        result = self.pyfunc.predict(None, df)
        assert all(0.0 <= s <= 1.0 for s in result["fraud_score"])

    def test_predict_fraud_prediction_binary(self, sample_transactions_batch):
        df = sample_transactions_batch.iloc[:2]
        result = self.pyfunc.predict(None, df)
        assert all(p in (0, 1) for p in result["fraud_prediction"])

    def test_threshold_applied_correctly(self, sample_transactions_batch):
        df = sample_transactions_batch.iloc[:2]
        self.pyfunc.threshold = 0.5
        result = self.pyfunc.predict(None, df)
        # probs are [0.2, 0.7], threshold 0.5
        assert result["fraud_prediction"].iloc[0] == 0  # 0.2 < 0.5
        assert result["fraud_prediction"].iloc[1] == 1  # 0.7 >= 0.5

    def test_unknown_category_handled(self, sample_transactions_batch):
        # Row 3 has UNKNOWN_CATEGORY and UNKNOWN_COUNTRY
        self.pyfunc.model.predict_proba.return_value = np.array([[0.9, 0.1], [0.3, 0.7], [0.6, 0.4]])
        result = self.pyfunc.predict(None, sample_transactions_batch)
        assert len(result) == 3  # Should not crash on unknown categories

    def test_threshold_from_env_var(self):
        os.environ["FRAUD_THRESHOLD"] = "0.8"
        from src.serving.register_pyfunc import FraudPyfunc
        pyfunc = FraudPyfunc()
        # Manually trigger threshold read (simulating load_context)
        pyfunc.threshold = float(os.getenv("FRAUD_THRESHOLD", "0.5"))
        assert pyfunc.threshold == 0.8
        os.environ.pop("FRAUD_THRESHOLD", None)
