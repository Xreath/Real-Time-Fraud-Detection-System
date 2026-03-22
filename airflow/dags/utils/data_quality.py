"""
Data quality checks for retraining pipeline (per RETR-03).

Checks before training proceeds:
  1. Null rate < 5% across all columns
  2. Fraud rate within tolerance of expected ~2% (1.0% - 4.0% range)
  3. Schema matches expected columns
  4. Minimum 1000 rows total
  5. Minimum 10 fraud cases
"""
import pandas as pd

EXPECTED_COLUMNS = [
    "transaction_id", "user_id", "amount", "merchant", "merchant_category",
    "card_type", "latitude", "longitude", "is_weekend", "is_night",
    "is_foreign", "is_fraud",
]

FRAUD_RATE_MIN = 0.01  # 1%
FRAUD_RATE_MAX = 0.04  # 4%
NULL_RATE_THRESHOLD = 0.05  # 5%
MIN_ROWS = 1000
MIN_FRAUD_CASES = 10


def run_data_quality_checks(df: pd.DataFrame) -> dict:
    """
    Run all data quality checks on the generated DataFrame.

    Args:
        df: DataFrame with transaction data (post-generation, pre-feature-engineering)

    Returns:
        dict with keys:
            - passed: bool (True if ALL checks pass)
            - checks: list of dicts, each with {name, passed, value, threshold, message}
    """
    checks = []

    # 1. Row count check
    row_count = len(df)
    checks.append({
        "name": "min_rows",
        "passed": row_count >= MIN_ROWS,
        "value": row_count,
        "threshold": MIN_ROWS,
        "message": f"Row count: {row_count} (min: {MIN_ROWS})",
    })

    # 2. Null rate check
    null_rate = df.isnull().mean().max()  # worst column
    worst_col = df.isnull().mean().idxmax()
    checks.append({
        "name": "null_rate",
        "passed": null_rate < NULL_RATE_THRESHOLD,
        "value": round(float(null_rate), 4),
        "threshold": NULL_RATE_THRESHOLD,
        "message": f"Max null rate: {null_rate:.2%} in column '{worst_col}' (threshold: {NULL_RATE_THRESHOLD:.0%})",
    })

    # 3. Fraud rate check
    if "is_fraud" in df.columns:
        fraud_rate = df["is_fraud"].mean()
        fraud_in_range = FRAUD_RATE_MIN <= fraud_rate <= FRAUD_RATE_MAX
        checks.append({
            "name": "fraud_rate",
            "passed": fraud_in_range,
            "value": round(float(fraud_rate), 4),
            "threshold": f"{FRAUD_RATE_MIN}-{FRAUD_RATE_MAX}",
            "message": f"Fraud rate: {fraud_rate:.2%} (expected: {FRAUD_RATE_MIN:.0%}-{FRAUD_RATE_MAX:.0%})",
        })
    else:
        checks.append({
            "name": "fraud_rate",
            "passed": False,
            "value": None,
            "threshold": f"{FRAUD_RATE_MIN}-{FRAUD_RATE_MAX}",
            "message": "Column 'is_fraud' not found in DataFrame",
        })

    # 4. Fraud case count
    if "is_fraud" in df.columns:
        fraud_count = int(df["is_fraud"].sum())
        checks.append({
            "name": "min_fraud_cases",
            "passed": fraud_count >= MIN_FRAUD_CASES,
            "value": fraud_count,
            "threshold": MIN_FRAUD_CASES,
            "message": f"Fraud cases: {fraud_count} (min: {MIN_FRAUD_CASES})",
        })
    else:
        checks.append({
            "name": "min_fraud_cases",
            "passed": False,
            "value": 0,
            "threshold": MIN_FRAUD_CASES,
            "message": "Column 'is_fraud' not found",
        })

    # 5. Schema check — verify expected columns exist
    missing_cols = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    checks.append({
        "name": "schema_match",
        "passed": len(missing_cols) == 0,
        "value": missing_cols,
        "threshold": "all expected columns present",
        "message": f"Missing columns: {missing_cols}" if missing_cols else "All expected columns present",
    })

    all_passed = all(c["passed"] for c in checks)

    # Log results
    for c in checks:
        status = "PASS" if c["passed"] else "FAIL"
        print(f"[DQ {status}] {c['message']}")

    return {"passed": all_passed, "checks": checks}
