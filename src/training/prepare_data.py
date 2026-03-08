"""
Historical Data Preparation - ML eğitimi için veri hazırlama pipeline'ı.

Bu modül:
  1. TransactionGenerator ile büyük ölçekli labeled veri üretir
  2. Spark ile feature engineering uygular
  3. Train/validation/test split yapar (stratified)
  4. Class imbalance'ı raporlar
  5. Parquet olarak kaydeder

Kullanım:
    python -m src.training.prepare_data

Mülakat notu:
  "Neden stratified split?" → Fraud oranı %2. Rastgele split yapsan
  test set'te hiç fraud olmayabilir. Stratified split her set'te
  oranı korur.

  "Neden Parquet?" → Columnar format, Pandas/Spark hızlı okur,
  sıkıştırılmış. CSV'den 5-10x daha hızlı.
"""

import os
from pathlib import Path

import pandas as pd
import numpy as np
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from sklearn.model_selection import train_test_split

from src.data_generator.transaction_generator import TransactionGenerator
from src.streaming.feature_engineering import (
    compute_transaction_features,
    compute_location_features,
)


DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
FEATURES_DIR = DATA_DIR / "features_historical"
SPLITS_DIR = DATA_DIR / "splits"


def generate_historical_data(
    num_transactions: int = 100_000,
    num_users: int = 1000,
    fraud_rate: float = 0.02,
    seed: int = 42,
) -> pd.DataFrame:
    """
    TransactionGenerator ile labeled historical veri üretir.

    Args:
        num_transactions: Üretilecek transaction sayısı
        num_users: Kullanıcı sayısı
        fraud_rate: Fraud oranı
        seed: Reproducibility için

    Returns:
        pandas DataFrame
    """
    print(f"  {num_transactions:,} transaction üretiliyor...")
    gen = TransactionGenerator(num_users=num_users, fraud_rate=fraud_rate, seed=seed)
    transactions = gen.generate_batch(num_transactions)
    df = pd.DataFrame(transactions)

    fraud_count = df["is_fraud"].sum()
    print(f"  Toplam: {len(df):,} | Fraud: {fraud_count:,} ({fraud_count/len(df)*100:.1f}%)")

    return df


def compute_features_with_spark(df: pd.DataFrame) -> pd.DataFrame:
    """
    Spark ile feature engineering uygular (batch mode).

    Pipeline:
      Raw DataFrame → Transaction Features → Location Features → Pandas
    """
    print("  Spark ile feature engineering başlatılıyor...")

    import pyspark
    spark_version = pyspark.__version__
    spark = (
        SparkSession.builder
        .appName("FraudDetection-DataPrep")
        .master("local[*]")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.driver.memory", "2g")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    # Pandas → Spark DataFrame
    spark_df = spark.createDataFrame(df)

    # Timestamp string → proper timestamp
    spark_df = spark_df.withColumn("event_time", F.to_timestamp("timestamp"))

    # Feature engineering
    spark_df = compute_transaction_features(spark_df)
    spark_df = compute_location_features(spark_df)

    # Spark → Pandas
    result_df = spark_df.toPandas()
    spark.stop()

    # Feature sayısını raporla
    new_cols = set(result_df.columns) - set(df.columns)
    print(f"  {len(new_cols)} yeni feature eklendi: {sorted(new_cols)}")

    return result_df


def split_data(
    df: pd.DataFrame,
    test_size: float = 0.2,
    val_size: float = 0.1,
    seed: int = 42,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Veriyi train/validation/test olarak böler.

    Stratified split: Her set'te fraud oranı korunur.
    Oranlar: %70 train, %10 validation, %20 test

    Mülakat notu:
      "Validation neden ayrı?" → Hyperparameter tuning validation set'te yapılır.
      Test set'e sadece en son, model seçildikten sonra bakılır.
      Yoksa test set'e overfit olursun.
    """
    y = df["is_fraud"]

    # İlk split: train+val (%80) vs test (%20)
    train_val_df, test_df = train_test_split(
        df, test_size=test_size, random_state=seed, stratify=y
    )

    # İkinci split: train (%70) vs validation (%10)
    y_train_val = train_val_df["is_fraud"]
    relative_val_size = val_size / (1 - test_size)  # 0.1 / 0.8 = 0.125

    train_df, val_df = train_test_split(
        train_val_df, test_size=relative_val_size, random_state=seed, stratify=y_train_val
    )

    print(f"  Train:      {len(train_df):>7,} ({train_df['is_fraud'].mean()*100:.1f}% fraud)")
    print(f"  Validation: {len(val_df):>7,} ({val_df['is_fraud'].mean()*100:.1f}% fraud)")
    print(f"  Test:       {len(test_df):>7,} ({test_df['is_fraud'].mean()*100:.1f}% fraud)")

    return train_df, val_df, test_df


def save_splits(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame):
    """Veri setlerini Parquet olarak kaydeder."""
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)

    train_path = SPLITS_DIR / "train.parquet"
    val_path = SPLITS_DIR / "val.parquet"
    test_path = SPLITS_DIR / "test.parquet"

    train_df.to_parquet(train_path, index=False)
    val_df.to_parquet(val_path, index=False)
    test_df.to_parquet(test_path, index=False)

    print(f"  Kaydedildi:")
    print(f"    {train_path} ({train_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"    {val_path} ({val_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"    {test_path} ({test_path.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    """Ana veri hazırlama pipeline'ı."""
    print("=" * 60)
    print("Historical Data Preparation Pipeline")
    print("=" * 60)

    # 1. Veri üret
    print("\n[1/4] Veri üretimi")
    df = generate_historical_data(
        num_transactions=100_000,
        num_users=1000,
        fraud_rate=0.02,
        seed=42,
    )

    # 2. Feature engineering
    print("\n[2/4] Feature Engineering")
    df = compute_features_with_spark(df)

    # 3. Train/val/test split
    print("\n[3/4] Data Split (stratified)")
    train_df, val_df, test_df = split_data(df)

    # 4. Kaydet
    print("\n[4/4] Parquet olarak kaydet")
    save_splits(train_df, val_df, test_df)

    print("\n" + "=" * 60)
    print("Veri hazırlama tamamlandı!")
    print("=" * 60)


if __name__ == "__main__":
    main()
