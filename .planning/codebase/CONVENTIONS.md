# Coding Conventions

**Analysis Date:** 2026-03-20

## Naming Patterns

**Files:**
- Module/script names: `snake_case` (e.g., `kafka_producer.py`, `transaction_generator.py`, `model_scorer.py`)
- Package directories: `snake_case` (e.g., `data_generator/`, `streaming/`, `training/`, `serving/`)

**Functions:**
- All functions: `snake_case` (e.g., `generate_transaction()`, `compute_metrics()`, `train_and_log_model()`)
- Private methods: prefix with underscore (e.g., `_create_producer()`, `_on_success()`, `_generate_fraud_transaction()`)
- Callback methods: descriptive names with action prefix (e.g., `_on_success()`, `_on_error()`, `_shutdown()`)
- Utility functions at module level: lowercase, snake_case
- Type hints used for function parameters and returns (e.g., `def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`)

**Variables:**
- Constants (module-level): `SCREAMING_SNAKE_CASE` (e.g., `KAFKA_BROKER`, `FEATURE_COLUMNS`, `TRANSACTIONS_SCHEMA`)
- Instance variables: `snake_case` (e.g., `self.sent_count`, `self.fraud_rate`, `self.scaler`)
- Local variables: `snake_case` (e.g., `fraud_count`, `train_df`, `X_train`)
- Dataframe variables: suffix with `_df` (e.g., `train_df`, `test_df`, `spark_df`)
- Dictionary/mapping variables: end with `_dict` or descriptive names (e.g., `label_encoders`, `MERCHANTS`, `FOREIGN_MERCHANTS`)

**Types:**
- Dataclasses for structured data: `@dataclass` decorator with field names in `snake_case` (e.g., `Transaction` dataclass in `src/data_generator/transaction_generator.py`)
- Classes: `PascalCase` (e.g., `TransactionGenerator`, `FraudTransactionProducer`, `FraudScorer`)

## Code Style

**Formatting:**
- No automatic formatter configured (no Black, ruff, or Prettier in requirements)
- Manual style follows PEP 8 conventions:
  - Line length: ~120 characters (inferred from code observation)
  - Indentation: 4 spaces (consistently applied)
  - Two blank lines between top-level definitions
  - One blank line between methods in classes

**Linting:**
- No linting configuration detected (no `.pylintrc`, `.flake8`, or ESLint config)
- Code follows implicit PEP 8 style guidelines

## Import Organization

**Order:**
1. Standard library imports (e.g., `os`, `sys`, `json`, `time`, `signal`, `math`, `pathlib`)
2. Third-party library imports (e.g., `pandas`, `numpy`, `sklearn`, `pyspark`, `mlflow`, `kafka`, `faker`)
3. Local application imports (e.g., `from src.config import ...`, `from src.data_generator import ...`)

**Path Aliases:**
- No aliases configured; all imports use absolute module paths from project root
- Standard imports: `from src.config import KAFKA_BROKER, KAFKA_TOPIC_TRANSACTIONS`
- Submodule imports: `from src.data_generator.transaction_generator import TransactionGenerator`
- Framework-specific imports group multiple functions: `from sklearn.metrics import precision_score, recall_score, f1_score, ...`

## Error Handling

**Patterns:**
- Try-except blocks for external integration points (Kafka connection, MLflow model loading)
- Retry logic with exponential backoff for Kafka broker connection: `_create_producer()` in `src/data_generator/kafka_producer.py` retries up to 5 times with increasing wait periods
- Generic exception handling in streaming loops with logged errors: `except Exception as e: print(f"Error: {e}")`
- Graceful shutdown using signal handlers: `signal.signal(signal.SIGINT, self._shutdown)` in producer
- Validation before processing (e.g., check if DataFrame columns exist before transformation)
- Direct exception raising for critical failures: `raise RuntimeError(f"Kafka connection failed: {broker}")` when max retries exceeded
- Fallback values for unknown categorical values in scoring: `le.transform([x])[0] if x in le.classes_ else 0` in `src/serving/model_scorer.py`

## Logging

**Framework:** `print()` statements (no logging module configured)

**Patterns:**
- Print progression messages for multi-step processes (e.g., `print("[1/4] Loading data...")`)
- Use `print(f"...")` for formatted output with variables
- Section separators: `print("=" * 60)` for major workflow boundaries
- Status messages with timestamps: `print(f"[{datetime.now().strftime('%H:%M:%S')}] Message")`
- Metrics reporting: Print counts and percentages (e.g., `f"Sent: {self.sent_count} | Error: {self.error_count}"`)
- Progress updates at intervals (e.g., every 100 messages in producer): `if total > 0 and total % 100 == 0`
- Muted library logging: `matplotlib.use("Agg")` (non-interactive backend), `spark.sparkContext.setLogLevel("WARN")`

## Comments

**When to Comment:**
- Module docstrings: Always present, explain purpose and usage (e.g., in `kafka_producer.py`, `train_model.py`)
- Function docstrings: Comprehensive docstrings for public functions with Args, Returns, and usage notes
- "Mülakat notu" (interview notes): Custom sections in docstrings explaining design decisions and answers to common questions
- Section separators: Comment blocks marking pipeline phases (`# ============================================================`)
- Complex algorithms: Comments explaining why, not what (e.g., Haversine formula explanation in `feature_engineering.py`)
- Configuration rationale: Comments explaining non-obvious settings (e.g., `acks='all'` for Kafka producer guarantees)
- Data/constant definitions: Comments for large static data structures explaining purpose (e.g., `MERCHANTS`, `FOREIGN_MERCHANTS`)

**JSDoc/TSDoc:**
- Not used (Python project, not TypeScript/JavaScript)
- Python docstrings follow Google/NumPy-style format implicitly

## Function Design

**Size:**
- Functions range from 5-50 lines typically
- Single-responsibility principle observed (e.g., `_create_producer()` only creates producer, `preprocess()` only handles feature preprocessing)
- Complex workflows broken into multiple functions (e.g., `prepare_data.py` separates generation, feature engineering, splitting, and saving)

**Parameters:**
- Optional parameters with sensible defaults (e.g., `fraud_rate: float = 0.02`, `seed: Optional[int] = None`)
- Type hints for all parameters (e.g., `num_users: int`, `df: pd.DataFrame`, `spark: SparkSession`)
- Kwargs not commonly used; explicit named parameters preferred
- Dictionary unpacking for configuration (e.g., `**params` in MLflow logging)

**Return Values:**
- Explicit return types in function signatures
- Tuple returns for multiple values (e.g., `tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]`)
- Dictionary returns for structured results (e.g., `{"precision": ..., "recall": ...}` from `compute_metrics()`)
- None returns for side-effect functions (e.g., `def start(self)` in producer)

## Module Design

**Exports:**
- Main entry point: `if __name__ == "__main__"` pattern used for CLI invocation
- Public classes exported directly (e.g., `class TransactionGenerator`, `class FraudScorer`)
- Utility functions prefixed with underscore if for internal use only (e.g., `_create_producer()`)
- Module-level constants exported at top level (e.g., `FEATURE_COLUMNS`, `KAFKA_BROKER`)

**Barrel Files:**
- No barrel files (index.py) observed
- `__init__.py` files exist but are empty (`src/__init__.py`, `src/data_generator/__init__.py`)
- Direct imports from submodules required (e.g., `from src.training.train_model import main`)

## Special Patterns

**Dataclass Usage:**
- `@dataclass` decorator for immutable data containers (e.g., `Transaction` in `transaction_generator.py`)
- Field definitions with type hints
- Methods within dataclasses minimal; mostly data storage

**Context Managers:**
- MLflow context: `with mlflow.start_run(run_name=name):` for experiment tracking scopes
- File operations: Standard context managers not extensively shown but implicitly used

**Configuration Management:**
- Centralized config module: `src/config.py`
- Environment variables loaded with defaults: `os.getenv("VAR_NAME", "default_value")`
- Type conversions inline: `int(os.getenv("VAR", "10"))`, `float(os.getenv("VAR", "0.02"))`

---

*Convention analysis: 2026-03-20*
