"""
Spark Structured Streaming Consumer - Kafka'dan transaction okur ve feature hesaplar.

Bu modül Kafka "transactions" topic'ini dinler, JSON mesajları parse eder,
feature engineering uygular ve sonuçları Parquet + Kafka'ya yazar.

Kullanım:
    python -m src.streaming.spark_consumer

Akış:
    Kafka (transactions) → JSON Parse → Feature Engineering → Parquet + Kafka (features)

Mülakat notu:
  "Neden Structured Streaming?" → SQL-benzeri API ile stream processing.
  DStreams'den (eski API) farkı: exactly-once semantics, watermark desteği,
  daha güçlü optimizasyon (Catalyst optimizer). Spark 3.0+ için standart.

  "Micro-batch vs continuous?" → Micro-batch modunda belirli aralıklarla
  (10 saniye) küçük batch'ler işlenir. Continuous mode Spark'ta experimental.
  10 saniye gecikme fraud tespiti için kabul edilebilir.
"""

import os
import sys
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from src.streaming.feature_engineering import (
    compute_transaction_features,
    compute_windowed_features,
)


# ============================================================
# Transaction JSON Schema - Kafka mesajlarını parse etmek için
# ============================================================

TRANSACTION_SCHEMA = T.StructType([
    T.StructField("transaction_id", T.StringType(), False),
    T.StructField("user_id", T.StringType(), False),
    T.StructField("amount", T.DoubleType(), False),
    T.StructField("merchant_name", T.StringType(), False),
    T.StructField("merchant_category", T.StringType(), False),
    T.StructField("card_type", T.StringType(), False),
    T.StructField("latitude", T.DoubleType(), False),
    T.StructField("longitude", T.DoubleType(), False),
    T.StructField("city", T.StringType(), False),
    T.StructField("country", T.StringType(), False),
    T.StructField("timestamp", T.StringType(), False),
    T.StructField("is_weekend", T.BooleanType(), False),
    T.StructField("is_night", T.BooleanType(), False),
    T.StructField("is_foreign", T.BooleanType(), False),
    T.StructField("is_fraud", T.IntegerType(), False),
])


# ============================================================
# Spark Session oluşturma
# ============================================================

def create_spark_session() -> SparkSession:
    """
    PySpark session oluşturur.

    local[*] → Host makinede çalıştır (tüm CPU core'ları kullan)
    spark-sql-kafka → Kafka'dan okumak için gerekli connector JAR

    Not: Docker Spark cluster'ına submit etmek için master URL değiştirilir.
    Ama local mode öğrenme için daha pratik — debugging kolay.
    """
    # PySpark versiyonuna göre Kafka connector seçimi
    import pyspark
    spark_version = pyspark.__version__
    # Spark 4.x Scala 2.13, Spark 3.x Scala 2.12 kullanır
    if spark_version.startswith("4"):
        scala_version = "2.13"
    else:
        scala_version = "2.12"
    kafka_package = f"org.apache.spark:spark-sql-kafka-0-10_{scala_version}:{spark_version}"

    spark = (
        SparkSession.builder
        .appName("FraudDetectionStreaming")
        .master("local[*]")
        .config("spark.jars.packages", kafka_package)
        .config("spark.sql.streaming.checkpointLocation", "data/checkpoints")
        .config("spark.sql.shuffle.partitions", "4")
        # Kafka consumer lag uyarılarını azalt
        .config("spark.streaming.kafka.consumer.cache.enabled", "false")
        .getOrCreate()
    )

    spark.sparkContext.setLogLevel("WARN")
    print(f"Spark Session oluşturuldu (v{spark_version}, Kafka connector: {kafka_package})")
    return spark


# ============================================================
# Kafka'dan Okuma
# ============================================================

def read_from_kafka(spark: SparkSession, broker: str = "localhost:9092", topic: str = "transactions", starting_offsets: str = "latest"):
    """
    Kafka topic'inden streaming okuma başlatır.

    startingOffsets="latest"   → Sadece yeni mesajları oku (production default)
    startingOffsets="earliest" → Tüm geçmiş mesajları da oku (test için)
    """
    raw_stream = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", broker)
        .option("subscribe", topic)
        .option("startingOffsets", starting_offsets)
        .option("failOnDataLoss", "false")  # Topic silinirse crash olmasın
        .load()
    )

    print(f"Kafka stream başlatıldı: {broker}/{topic} (offsets={starting_offsets})")
    return raw_stream


# ============================================================
# JSON Parse
# ============================================================

def parse_transactions(raw_stream):
    """
    Kafka'dan gelen raw byte mesajları JSON'a parse eder.

    Kafka mesajı: key (bytes) + value (bytes) + metadata
    Biz value'yu JSON'a çevirip DataFrame'e dönüştürüyoruz.

    Parse edilemeyen mesajlar → DLQ (Dead Letter Queue) için ayrılır.
    data == null → JSON geçersiz veya schema uyumsuz demektir.
    """
    with_json = (
        raw_stream
        # Kafka value byte → string
        .selectExpr("CAST(value AS STRING) as json_str", "timestamp as kafka_timestamp")
        # JSON string → struct (şemaya göre parse)
        .withColumn("data", F.from_json("json_str", TRANSACTION_SCHEMA))
    )

    # Başarılı parse → transaction DataFrame
    parsed = (
        with_json
        .filter(F.col("data").isNotNull())
        .select("data.*", "kafka_timestamp")
        .withColumn("event_time", F.to_timestamp("timestamp"))
    )

    # Başarısız parse → DLQ'ya yazılacak satırlar
    dlq = with_json.filter(F.col("data").isNull()).select("json_str", "kafka_timestamp")

    return parsed, dlq


def write_dlq_to_kafka(dlq_df, broker: str = "localhost:9092", topic: str = "transactions-dlq"):
    """
    Parse edilemeyen mesajları Dead Letter Queue topic'ine yazar.

    DLQ neden önemli?
      Mesaj kaybolmaz — sonradan inceleme ve debug için saklanır.
      Production'da DLQ boyutu monitör edilir; ani artış → schema sorunu sinyali.
    """
    kafka_output = (
        dlq_df
        .withColumn("key", F.lit("parse_error"))
        .withColumn("value", F.col("json_str"))
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
    )

    query = (
        kafka_output
        .writeStream
        .format("kafka")
        .outputMode("append")
        .option("kafka.bootstrap.servers", broker)
        .option("topic", topic)
        .option("checkpointLocation", "data/checkpoints/kafka_dlq")
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"DLQ writer başlatıldı: {broker}/{topic}")
    return query


# ============================================================
# Feature'ları Parquet'e yaz (streaming)
# ============================================================

def write_features_to_parquet(featured_df, output_path: str = "data/features"):
    """
    Feature'ları Parquet dosyalarına yazar.

    append mode → Her micro-batch yeni dosyalar ekler
    Partitioning by date → Günlük klasörlere böler (verimli okuma)
    """
    query = (
        featured_df
        .withColumn("date", F.to_date("event_time"))
        .writeStream
        .format("parquet")
        .outputMode("append")
        .option("path", output_path)
        .option("checkpointLocation", f"data/checkpoints/parquet")
        .partitionBy("date")
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"Parquet writer başlatıldı: {output_path}")
    return query


# ============================================================
# Feature'ları Kafka'ya yaz (streaming)
# ============================================================

def write_features_to_kafka(featured_df, broker: str = "localhost:9092", topic: str = "features"):
    """
    Hesaplanan feature'ları Kafka "features" topic'ine yazar.

    Real-time scoring servisi bu topic'i dinleyerek tahmin yapar.
    """
    # Kafka'ya yazmak için tüm kolonları JSON'a çevir
    kafka_output = (
        featured_df
        .withColumn("key", F.col("user_id"))
        .withColumn("value", F.to_json(F.struct("*")))
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
    )

    query = (
        kafka_output
        .writeStream
        .format("kafka")
        .outputMode("append")
        .option("kafka.bootstrap.servers", broker)
        .option("topic", topic)
        .option("checkpointLocation", f"data/checkpoints/kafka_features")
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"Kafka features writer başlatıldı: {broker}/{topic}")
    return query


# ============================================================
# Console Output - Debug amaçlı
# ============================================================

def write_to_console(featured_df):
    """Debug: Feature'ları konsola yazdırır."""
    query = (
        featured_df
        .select(
            "transaction_id", "user_id", "amount",
            "merchant_name", "city",
            "fraud_score", "fraud_prediction",
            "is_fraud",
        )
        .writeStream
        .format("console")
        .outputMode("append")
        .option("truncate", "false")
        .option("numRows", 10)
        .trigger(processingTime="10 seconds")
        .start()
    )

    print("Console writer başlatıldı (debug)")
    return query


# ============================================================
# Ana Pipeline
# ============================================================

# ============================================================
# Real-Time Scoring - Model ile fraud tahmini
# ============================================================

def create_scoring_udf(threshold: float = 0.5):
    """
    Model scoring için Pandas UDF oluşturur.

    Scoring pipeline:
      1. Transaction feature'ları Pandas DataFrame'e dönüşür (micro-batch)
      2. Preprocessing (LabelEncoder + StandardScaler) uygulanır
      3. LightGBM model ile fraud_score (0-1) hesaplanır
      4. Threshold üzerindekiler fraud_prediction=1 olarak işaretlenir

    Pandas UDF neden? → Row-by-row Python UDF yerine vectorized (batch)
    işlem. 10-100x daha hızlı. Arrow serialization kullanır.
    """
    import pandas as pd

    # Lazy-load: Scorer'ı ilk çağrıda yükle, sonra cache'le
    scorer_cache = {}

    @F.pandas_udf(T.DoubleType())
    def score_fraud(
        amount: pd.Series, latitude: pd.Series, longitude: pd.Series,
        is_weekend: pd.Series, is_night: pd.Series, is_foreign: pd.Series,
        hour_of_day: pd.Series, day_of_week: pd.Series,
        amount_log: pd.Series, is_high_amount: pd.Series, is_round_amount: pd.Series,
        merchant_category: pd.Series, card_type: pd.Series, country: pd.Series,
    ) -> pd.Series:
        if "scorer" not in scorer_cache:
            from src.serving.model_scorer import FraudScorer
            scorer_cache["scorer"] = FraudScorer(threshold=threshold)

        scorer = scorer_cache["scorer"]

        df = pd.DataFrame({
            "amount": amount, "latitude": latitude, "longitude": longitude,
            "is_weekend": is_weekend.astype(int), "is_night": is_night.astype(int),
            "is_foreign": is_foreign.astype(int),
            "hour_of_day": hour_of_day, "day_of_week": day_of_week,
            "amount_log": amount_log, "is_high_amount": is_high_amount,
            "is_round_amount": is_round_amount,
            # Location features — streaming'de lag yok, 0 olarak set
            "distance_km": 0.0, "time_diff_hours": 0.0, "speed_kmh": 0.0,
            "merchant_category": merchant_category,
            "card_type": card_type, "country": country,
        })

        try:
            X = scorer.preprocess(df)
            probs = scorer.model.predict_proba(X)[:, 1]
            return pd.Series(probs)
        except Exception:
            # Fallback: model hatası → score=-1 (manual review gerektirir)
            return pd.Series([-1.0] * len(amount))

    return score_fraud


def apply_scoring(featured_df, threshold: float = 0.5):
    """
    Feature-enriched DataFrame'e fraud scoring uygular.

    Returns:
        DataFrame with fraud_score (float) and fraud_prediction (int) columns
    """
    score_udf = create_scoring_udf(threshold)

    scored = (
        featured_df
        .withColumn(
            "fraud_score",
            score_udf(
                F.col("amount"), F.col("latitude"), F.col("longitude"),
                F.col("is_weekend"), F.col("is_night"), F.col("is_foreign"),
                F.col("hour_of_day"), F.col("day_of_week"),
                F.col("amount_log"), F.col("is_high_amount"), F.col("is_round_amount"),
                F.col("merchant_category"), F.col("card_type"), F.col("country"),
            ),
        )
        .withColumn(
            "fraud_prediction",
            F.when(F.col("fraud_score") >= threshold, 1).otherwise(0),
        )
    )

    return scored


# ============================================================
# Fraud Alerts - Yüksek skorlu işlemleri Kafka'ya yaz
# ============================================================

def write_fraud_alerts_to_kafka(scored_df, broker: str = "localhost:9092", topic: str = "fraud-alerts", threshold: float = 0.5):
    """
    Fraud olarak tespit edilen işlemleri fraud-alerts topic'ine yazar.

    Sadece fraud_score >= threshold olan işlemler yazılır.
    Downstream sistemler (alert servisi, dashboard) bu topic'i dinler.
    """
    alerts = scored_df.filter(F.col("fraud_score") >= threshold)

    kafka_output = (
        alerts
        .withColumn("key", F.col("user_id"))
        .withColumn("value", F.to_json(F.struct(
            "transaction_id", "user_id", "amount",
            "merchant_name", "merchant_category", "city", "country",
            "fraud_score", "fraud_prediction",
            "is_high_amount", "is_round_amount", "is_night", "is_foreign",
            "event_time",
        )))
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
    )

    query = (
        kafka_output
        .writeStream
        .format("kafka")
        .outputMode("append")
        .option("kafka.bootstrap.servers", broker)
        .option("topic", topic)
        .option("checkpointLocation", "data/checkpoints/kafka_fraud_alerts")
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"Fraud alerts writer başlatıldı: {broker}/{topic} (threshold={threshold})")
    return query


def write_windowed_to_kafka(windowed_df, broker: str = "localhost:9092", topic: str = "features-windowed"):
    """
    Windowed aggregation'ları Kafka'ya yazar.

    Windowed features (tx_count_1h, total_amount_1h vs.) real-time
    velocity attack tespiti için downstream servisler tarafından tüketilir.

    outputMode="update" → Sadece değişen window'ları yaz (complete yerine verimli)
    """
    kafka_output = (
        windowed_df
        .withColumn("key", F.col("user_id"))
        .withColumn("value", F.to_json(F.struct(
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            "user_id", "tx_count_1h", "total_amount_1h",
            "avg_amount_1h", "unique_merchant_1h", "unique_locations_1h",
        )))
        .selectExpr("CAST(key AS STRING)", "CAST(value AS STRING)")
    )

    query = (
        kafka_output
        .writeStream
        .format("kafka")
        .outputMode("update")
        .option("kafka.bootstrap.servers", broker)
        .option("topic", topic)
        .option("checkpointLocation", "data/checkpoints/kafka_windowed")
        .trigger(processingTime="10 seconds")
        .start()
    )

    print(f"Windowed features writer başlatıldı: {broker}/{topic}")
    return query


def run_streaming_pipeline(
    broker: str = "localhost:9092",
    topic: str = "transactions",
    output_parquet: str = "data/features",
    output_topic: str = "features",
    starting_offsets: str = "latest",
    debug: bool = False,
):
    """
    Ana streaming pipeline'ını çalıştırır.

    Akış:
      Kafka → Parse → Feature Engineering → Parquet + Kafka

    Args:
        broker: Kafka broker adresi
        topic: Dinlenecek topic
        output_parquet: Parquet çıktı klasörü
        output_topic: Feature'ların yazılacağı Kafka topic
        starting_offsets: "latest" (prod) veya "earliest" (test)
        debug: True ise konsola da yazar
    """
    print("=" * 60)
    print("Fraud Detection - Spark Streaming Pipeline")
    print("=" * 60)

    # 1. Spark Session
    spark = create_spark_session()

    # 2. Kafka'dan oku
    raw_stream = read_from_kafka(spark, broker, topic, starting_offsets)

    # 3. JSON parse (başarısız olanlar → DLQ)
    parsed, dlq = parse_transactions(raw_stream)

    # 4a. Transaction-level feature engineering
    featured = compute_transaction_features(parsed)

    # 4b. Windowed features (1 saatlik velocity sinyalleri)
    windowed = compute_windowed_features(parsed)

    # 4c. Real-time scoring (model ile fraud tahmini)
    scored = apply_scoring(featured, threshold=0.5)

    # 5. Output'lar
    queries = []

    # Scored features → Parquet (fraud_score dahil)
    q_parquet = write_features_to_parquet(scored, output_parquet)
    queries.append(q_parquet)

    # Scored features → Kafka
    q_kafka = write_features_to_kafka(scored, broker, output_topic)
    queries.append(q_kafka)

    # Fraud alerts → Kafka (sadece fraud_score >= threshold)
    q_alerts = write_fraud_alerts_to_kafka(scored, broker, "fraud-alerts")
    queries.append(q_alerts)

    # Windowed features → Kafka (features-windowed topic)
    q_windowed = write_windowed_to_kafka(windowed, broker, f"{output_topic}-windowed")
    queries.append(q_windowed)

    # DLQ → Parse edilemeyen mesajlar
    q_dlq = write_dlq_to_kafka(dlq, broker, "transactions-dlq")
    queries.append(q_dlq)

    # Debug: konsola yaz
    if debug:
        q_console = write_to_console(scored)
        queries.append(q_console)

    print("\n" + "=" * 60)
    print("Pipeline çalışıyor. Durdurmak için Ctrl+C")
    print("=" * 60)

    # Tüm stream query'lerini bekle
    try:
        spark.streams.awaitAnyTermination()
    except KeyboardInterrupt:
        print("\nPipeline durduruluyor...")
        for q in queries:
            q.stop()
        spark.stop()
        print("Pipeline durduruldu.")


# ============================================================
# Ana giriş noktası
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Spark Streaming Pipeline")
    parser.add_argument("--broker", default="localhost:9092", help="Kafka broker")
    parser.add_argument("--topic", default="transactions", help="Input topic")
    parser.add_argument("--output-parquet", default="data/features", help="Parquet output path")
    parser.add_argument("--output-topic", default="features", help="Output Kafka topic")
    parser.add_argument("--starting-offsets", default="latest", choices=["latest", "earliest"], help="Kafka başlangıç offset")
    parser.add_argument("--debug", action="store_true", help="Console output ekle")
    args = parser.parse_args()

    run_streaming_pipeline(
        broker=args.broker,
        topic=args.topic,
        output_parquet=args.output_parquet,
        output_topic=args.output_topic,
        starting_offsets=args.starting_offsets,
        debug=args.debug,
    )
