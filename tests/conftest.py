import pytest
import pandas as pd


@pytest.fixture
def sample_transaction():
    """Single valid transaction matching the expected feature schema."""
    return pd.DataFrame([{
        "amount": 150.75,
        "merchant_category": "grocery",
        "card_type": "visa",
        "country": "TR",
        "latitude": 41.01,
        "longitude": 28.97,
        "is_weekend": 0,
        "is_night": 0,
        "is_foreign": 0,
        "hour_of_day": 14,
        "day_of_week": 1,
        "amount_log": 5.02,
        "is_high_amount": 0,
        "is_round_amount": 0,
        "distance_km": 0.0,
        "time_diff_hours": 0.0,
        "speed_kmh": 0.0,
    }])


@pytest.fixture
def sample_transactions_batch():
    """Batch of 3 transactions: 1 normal, 1 suspicious (high amount), 1 with unknown category."""
    return pd.DataFrame([
        {
            "amount": 50.0, "merchant_category": "grocery", "card_type": "visa",
            "country": "TR", "latitude": 41.01, "longitude": 28.97,
            "is_weekend": 0, "is_night": 0, "is_foreign": 0,
            "hour_of_day": 10, "day_of_week": 2, "amount_log": 3.91,
            "is_high_amount": 0, "is_round_amount": 1, "distance_km": 0.0,
            "time_diff_hours": 0.0, "speed_kmh": 0.0,
        },
        {
            "amount": 9999.99, "merchant_category": "electronics", "card_type": "mastercard",
            "country": "US", "latitude": 40.71, "longitude": -74.01,
            "is_weekend": 1, "is_night": 1, "is_foreign": 1,
            "hour_of_day": 3, "day_of_week": 6, "amount_log": 9.21,
            "is_high_amount": 1, "is_round_amount": 0, "distance_km": 8000.0,
            "time_diff_hours": 1.0, "speed_kmh": 8000.0,
        },
        {
            "amount": 200.0, "merchant_category": "UNKNOWN_CATEGORY", "card_type": "amex",
            "country": "UNKNOWN_COUNTRY", "latitude": 35.0, "longitude": 33.0,
            "is_weekend": 0, "is_night": 0, "is_foreign": 0,
            "hour_of_day": 12, "day_of_week": 3, "amount_log": 5.30,
            "is_high_amount": 0, "is_round_amount": 1, "distance_km": 0.0,
            "time_diff_hours": 0.0, "speed_kmh": 0.0,
        },
    ])
