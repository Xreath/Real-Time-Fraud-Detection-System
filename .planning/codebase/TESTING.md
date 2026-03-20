# Testing Patterns

**Analysis Date:** 2026-03-20

## Test Framework

**Status:**
- No formal testing framework configured
- No `pytest.ini`, `tox.ini`, or `setup.cfg` found
- No test dependencies in `requirements.txt` (pytest, unittest, etc. not listed)
- Tests directory exists (`tests/`) but is empty

**Assertion Library:**
- Not configured for formal testing

**Run Commands:**
```bash
# No test runner commands available
# Manual testing patterns use module-level __main__ blocks
python -m src.data_generator.transaction_generator  # Run module tests
python -m src.serving.model_scorer --test           # Run scorer test
```

## Test File Organization

**Location:**
- No dedicated test files; tests are co-located within modules using `if __name__ == "__main__"` blocks
- Test directory exists but empty: `tests/`
- Modules with test code:
  - `src/data_generator/transaction_generator.py` (lines 307-336)
  - `src/serving/model_scorer.py` (lines 209-229)

**Naming:**
- Test code in main module: wrapped in `if __name__ == "__main__":` block
- Test functions: `test_*()` convention (e.g., `test_scorer()` in `model_scorer.py`)
- No `.test.py` or `.spec.py` suffix pattern used

**Structure:**
```
Module (e.g., transaction_generator.py)
├── Docstring
├── Imports
├── Constants/Classes/Functions
└── if __name__ == "__main__":
    └── Test code (inline)
```

## Test Structure

**Suite Organization:**

In `src/data_generator/transaction_generator.py`:
```python
if __name__ == "__main__":
    import json

    gen = TransactionGenerator(num_users=100, fraud_rate=0.02, seed=42)

    print("=== Örnek Normal Transaction ===")
    for _ in range(3):
        tx = gen.generate_transaction()
        if tx["is_fraud"] == 0:
            print(json.dumps(tx, indent=2))
            break

    print("\n=== Örnek Fraud Transaction ===")
    gen_fraud = TransactionGenerator(num_users=10, fraud_rate=1.0, seed=42)
    tx = gen_fraud.generate_transaction()
    print(json.dumps(tx, indent=2))

    print("\n=== 10000 Transaction İstatistikleri ===")
    gen_test = TransactionGenerator(num_users=100, fraud_rate=0.02, seed=123)
    txs = gen_test.generate_batch(10000)
    fraud_count = sum(1 for t in txs if t["is_fraud"] == 1)
    print(f"Toplam: {len(txs)}")
    print(f"Fraud:  {fraud_count} ({fraud_count/len(txs)*100:.1f}%)")
```

In `src/serving/model_scorer.py`:
```python
def test_scorer():
    """Scorer'ı test verisinden birkaç satırla test eder."""
    print("\n" + "=" * 55)
    print("FraudScorer Test")
    print("=" * 55)

    scorer = FraudScorer()

    # Test verisinden sample
    test_df = pd.read_parquet(SPLITS_DIR / "test.parquet")
    sample = test_df.sample(n=10, random_state=42)

    result = scorer.score(sample)

    print("\nSonuclar:")
    print(result[["transaction_id", "amount", "is_fraud", "fraud_score", "fraud_prediction"]].to_string(index=False))

    # Accuracy check
    correct = (result["fraud_prediction"] == result["is_fraud"]).sum()
    print(f"\nDogruluk: {correct}/{len(result)} ({correct/len(result)*100:.0f}%)")
    print("Test PASSED" if correct >= 7 else "Test FAILED (düşük doğruluk)")
```

**Patterns:**
- Setup: Create test instance and load test data
- Execution: Call functions with known inputs
- Verification: Print-based assertions comparing actual vs expected
- Teardown: Implicit (no cleanup code)

## Mocking

**Framework:**
- No mocking library configured (unittest.mock, pytest-mock not in requirements)

**Patterns:**
- Not applicable due to lack of formal testing framework
- Manual data generation used instead of mocks (e.g., `TransactionGenerator` creates synthetic test data)

**What to Mock (if testing framework added):**
- External services: Kafka broker, MLflow server (would use fixtures with test containers)
- Database connections: Would mock Parquet file operations
- Model loading: Would mock MLflow model registry calls

**What NOT to Mock:**
- Business logic generators: `TransactionGenerator` intentionally used as-is for realistic data
- Preprocessing functions: Data transformation logic should be tested with real data
- Feature engineering: Window operations and aggregations need actual data structures

## Fixtures and Factories

**Test Data:**

`TransactionGenerator` serves as primary test data factory:
```python
# Generate realistic test transactions
gen = TransactionGenerator(num_users=1000, fraud_rate=0.02, seed=42)
transactions = gen.generate_batch(10000)
df = pd.DataFrame(transactions)

# Generate single transactions for unit testing
tx_normal = gen.generate_transaction()
tx_fraud = TransactionGenerator(num_users=10, fraud_rate=1.0).generate_transaction()
```

Sample data loading for scorer tests:
```python
test_df = pd.read_parquet(SPLITS_DIR / "test.parquet")
sample = test_df.sample(n=10, random_state=42)
result = scorer.score(sample)
```

**Location:**
- Test data generation: `src/data_generator/transaction_generator.py` (factory)
- Historical splits: `data/splits/train.parquet`, `data/splits/val.parquet`, `data/splits/test.parquet`
- Scoring artifacts: `data/artifacts/scaler.joblib`, `data/artifacts/label_encoders.joblib`

## Coverage

**Requirements:**
- No coverage configuration found
- No test coverage enforcement (.coverage, pytest.ini with coverage settings)

**View Coverage:**
- Not configured; would require pytest-cov or similar

## Test Types

**Unit Tests:**
- Minimal formal unit tests
- Module-level `if __name__ == "__main__":` blocks serve as basic smoke tests
- Typical scope: Single class or function with synthetic data
- Example: `test_scorer()` validates fraud scoring correctness with 10 samples

**Integration Tests:**
- Data pipeline tests (not formal; embedded in pipeline scripts)
- Example: `prepare_data.py` main function tests full data preparation pipeline:
  - Generates transactions
  - Applies feature engineering
  - Splits data
  - Saves outputs
  - Validates split ratios

**E2E Tests:**
- No E2E framework configured
- Manual testing via Docker Compose and Makefile commands:
  ```bash
  make up              # Start all services
  make producer        # Start data producer
  make stream          # Run streaming consumer
  make train           # Train models
  ```

**Validation Tests:**
- Data validation embedded in pipeline steps:
  - `prepare_data.py`: Prints fraud counts and percentages by split
  - `model_scorer.py`: Accuracy check: `correct >= 7 / 10`
  - Transaction generator: Statistical checks on batch (fraud rate, amount ranges)

## Common Patterns

**Assertions in Print-Based Testing:**

Transaction generator statistical validation:
```python
txs = gen_test.generate_batch(10000)
fraud_count = sum(1 for t in txs if t["is_fraud"] == 1)
print(f"Fraud:  {fraud_count} ({fraud_count/len(txs)*100:.1f}%)")
# Visual inspection verifies ~2% fraud rate
```

Scorer accuracy check:
```python
correct = (result["fraud_prediction"] == result["is_fraud"]).sum()
print("Test PASSED" if correct >= 7 else "Test FAILED (düşük doğruluk)")
```

**Reproducibility:**
- Seeding for deterministic test data: `seed=42` in `TransactionGenerator`, `train_test_split`, Spark operations
- Explicit random state parameters: `random_state=42` in sklearn and pandas operations
- Ensures tests produce consistent results across runs

**Data Validation Patterns:**
- Shape validation: Check DataFrame dimensions after operations
- Type validation: Verify column types after transformations
- Range validation: Ensure numeric values in expected bounds (fraud_rate between 0-1)
- Distribution validation: Print statistics for manual inspection

## Manual Testing Workflow

**Integration Testing via Command Line:**

1. **Data Generation Test:**
   ```bash
   python -m src.data_generator.transaction_generator
   # Output: Example normal/fraud transactions + statistics
   ```

2. **Producer-Consumer Test:**
   ```bash
   make up                    # Start Docker services
   make producer              # Start producing transactions
   make consumer-debug        # Consume and validate messages
   ```

3. **Data Preparation Test:**
   ```bash
   make prepare-data
   # Output: Validates generated data splits with fraud rate breakdown
   ```

4. **Model Training Test:**
   ```bash
   make train
   # Output: Trains 4 models, logs metrics, validates best model
   ```

5. **Scorer Test:**
   ```bash
   python -m src.serving.model_scorer --prepare  # Create artifacts
   python -m src.serving.model_scorer --test     # Run accuracy check
   ```

**Output Validation:**
- Print-based: Logs compared visually for correctness
- Metric-based: MLflow UI shows model performance (validation/test metrics)
- File-based: Check existence and format of output files (Parquet, joblib artifacts)

---

*Testing analysis: 2026-03-20*
