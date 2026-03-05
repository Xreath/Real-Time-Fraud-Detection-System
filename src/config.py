"""
Merkezi konfigürasyon modülü.
Tüm ayarlar .env dosyasından okunur, böylece kod içinde hardcoded değer olmaz.
"""

import os
from dotenv import load_dotenv

load_dotenv()


# --- Kafka ---
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
KAFKA_TOPIC_TRANSACTIONS = os.getenv("KAFKA_TOPIC_TRANSACTIONS", "transactions")
KAFKA_TOPIC_FRAUD_ALERTS = os.getenv("KAFKA_TOPIC_FRAUD_ALERTS", "fraud-alerts")
KAFKA_TOPIC_FEATURES = os.getenv("KAFKA_TOPIC_FEATURES", "features")

# --- Spark ---
SPARK_MASTER_URL = os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")

# --- MLflow ---
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001")
MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "fraud-detection")

# --- Data Generator ---
GENERATOR_TRANSACTIONS_PER_SEC = int(
    os.getenv("GENERATOR_TRANSACTIONS_PER_SEC", "10")
)
GENERATOR_FRAUD_RATE = float(os.getenv("GENERATOR_FRAUD_RATE", "0.02"))
