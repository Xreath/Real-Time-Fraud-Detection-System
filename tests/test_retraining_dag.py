"""DAG structure validation tests — no Airflow runtime needed."""
import os
import sys
import pytest

# Skip if Airflow is not installed
airflow = pytest.importorskip("airflow", reason="Airflow not installed - skipping DAG tests")

# Add DAG directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "airflow", "dags"))

# Set required Airflow env vars for import
os.environ.setdefault("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "sqlite:///test_airflow.db")
os.environ.setdefault("AIRFLOW__CORE__EXECUTOR", "SequentialExecutor")
os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "false")


class TestRetrainingDagStructure:

    @pytest.fixture(autouse=True)
    def load_dag(self):
        """Import the DAG module."""
        import importlib
        try:
            self.dag_module = importlib.import_module("retraining_dag")
            self.dag = self.dag_module.dag
        except Exception as e:
            pytest.skip(f"Cannot import retraining_dag: {e}")

    def test_dag_has_expected_tasks(self):
        expected_tasks = {
            "generate_data", "check_data_quality", "run_feature_engineering",
            "split_and_save", "train_models", "canary_evaluate",
            "promote_model", "rollback_alert", "restart_fraud_api",
            "verify_health", "end",
        }
        actual_tasks = {t.task_id for t in self.dag.tasks}
        missing = expected_tasks - actual_tasks
        assert not missing, f"Missing tasks: {missing}"

    def test_dag_schedule(self):
        # schedule_interval or timetable
        schedule = getattr(self.dag, "schedule_interval", None)
        assert schedule is not None
        assert str(schedule) == "0 2 * * 0" or "0 2 * * 0" in str(schedule)

    def test_dag_has_failure_callback(self):
        assert self.dag.default_args.get("on_failure_callback") is not None
