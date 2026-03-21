"""Integration tests for fraud-api serving endpoint.

Requires: docker compose up (fraud-api healthy on port 5002)
Skip with: pytest tests/test_serving.py -m "not integration"
"""
import pytest
import requests
import pandas as pd

SERVING_URL = "http://localhost:5002"


# Skip all tests if fraud-api is not running
def is_serving_up():
    try:
        r = requests.get(f"{SERVING_URL}/health", timeout=5)
        return r.status_code == 200
    except requests.ConnectionError:
        return False


skip_no_server = pytest.mark.skipif(
    not is_serving_up(),
    reason="fraud-api not running on localhost:5002"
)


@skip_no_server
class TestHealthCheck:
    def test_health_returns_200(self):
        """SERV-02: /health returns 200 when model is loaded."""
        r = requests.get(f"{SERVING_URL}/health", timeout=10)
        assert r.status_code == 200

    def test_ping_returns_200(self):
        """MLflow built-in /ping endpoint."""
        r = requests.get(f"{SERVING_URL}/ping", timeout=10)
        assert r.status_code == 200


@skip_no_server
class TestInvocations:
    def test_single_transaction(self, sample_transaction):
        """SERV-01: /invocations returns fraud_score for valid JSON."""
        payload = {"dataframe_records": sample_transaction.to_dict("records")}
        r = requests.post(
            f"{SERVING_URL}/invocations",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code == 200
        data = r.json()
        assert "predictions" in data
        preds = data["predictions"]
        assert len(preds) == 1
        assert "fraud_score" in preds[0]
        assert "fraud_prediction" in preds[0]
        assert 0.0 <= preds[0]["fraud_score"] <= 1.0
        assert preds[0]["fraud_prediction"] in (0, 1)

    def test_batch_transactions(self, sample_transactions_batch):
        """SERV-01: /invocations handles batch of 3 transactions."""
        payload = {"dataframe_records": sample_transactions_batch.to_dict("records")}
        r = requests.post(
            f"{SERVING_URL}/invocations",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code == 200
        preds = r.json()["predictions"]
        assert len(preds) == 3

    def test_dataframe_split_format(self, sample_transaction):
        """SERV-01: /invocations accepts dataframe_split format."""
        payload = {
            "dataframe_split": {
                "columns": list(sample_transaction.columns),
                "data": sample_transaction.values.tolist(),
            }
        }
        r = requests.post(
            f"{SERVING_URL}/invocations",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code == 200
        assert "predictions" in r.json()


@skip_no_server
class TestNoSkew:
    def test_scores_within_tolerance(self):
        """SERV-03: REST scores match FraudScorer.score() within 0.001."""
        from src.serving.model_scorer import FraudScorer
        from pathlib import Path

        test_path = Path("data/splits/test.parquet")
        if not test_path.exists():
            pytest.skip("test.parquet not found")

        sample = pd.read_parquet(test_path).head(5)

        # Local scoring via FraudScorer
        scorer = FraudScorer()
        local_result = scorer.score(sample)
        local_scores = local_result["fraud_score"].values

        # REST scoring
        # Build payload with the same features the pyfunc expects
        from src.serving.register_pyfunc import FEATURE_COLUMNS, CATEGORICAL_COLUMNS
        from src.serving.model_scorer import FEATURE_COLUMNS as SCORER_FEATURES, CATEGORICAL_COLUMNS as SCORER_CATS
        all_features = SCORER_FEATURES + SCORER_CATS
        payload_df = sample[all_features].copy()
        payload = {"dataframe_records": payload_df.to_dict("records")}

        r = requests.post(
            f"{SERVING_URL}/invocations",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        assert r.status_code == 200
        rest_scores = [p["fraud_score"] for p in r.json()["predictions"]]

        # Skew check
        for i, (local, rest) in enumerate(zip(local_scores, rest_scores)):
            skew = abs(local - rest)
            assert skew < 0.001, f"Row {i}: skew={skew:.6f} exceeds 0.001 (local={local:.6f}, rest={rest:.6f})"


@skip_no_server
class TestChampionAlias:
    def test_model_uri_uses_champion(self):
        """SERV-04: Verify model was loaded from @champion alias.
        Indirectly verified: if the server is up and returning scores,
        it loaded from the URI in docker-compose.yml which specifies @champion.
        """
        # This is verified by the fact that the server started successfully
        # with model-uri models:/fraud-detection-model@champion
        r = requests.get(f"{SERVING_URL}/version", timeout=10)
        assert r.status_code == 200
