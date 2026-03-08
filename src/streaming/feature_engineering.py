"""
Feature Engineering - Transaction verilerinden fraud tespiti için özellik çıkarımı.

Bu modül Spark Structured Streaming ile kullanılmak üzere tasarlanmıştır.
Hem streaming (real-time) hem de batch (historical) modda çalışır.

Feature Kategorileri:
  1. Windowed Features  → Son 1 saatteki aktivite (velocity attack tespiti)
  2. Location Features  → Haversine mesafe, hız (impossible travel tespiti)
  3. Transaction Features→ Tutar sapması, zaman bazlı sinyaller

Mülakat notu:
  "Neden bu feature'ları seçtiniz?" → Her feature belirli bir fraud
  pattern'ine karşılık gelir. Velocity attack, impossible travel,
  unusual amount, late night spending gibi bilinen fraud senaryolarını
  yakalamak için tasarlanmışlardır.
"""

import math
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.window import Window


# ============================================================
# Haversine formülü - İki koordinat arasındaki mesafe (km)
# ============================================================

@F.udf(T.DoubleType())
def haversine_km(lat1, lon1, lat2, lon2):
    """
    İki GPS koordinatı arasındaki mesafeyi km olarak hesaplar.

    Haversine formülü dünya yüzeyindeki en kısa mesafeyi verir.
    Fraud tespitinde "impossible travel" pattern'ini yakalamak için kullanılır.

    Örnek:
      New York (40.71, -74.00) → Tokyo (35.68, 139.65) = 10,838 km
      5 dakikada gitmek imkansız → fraud sinyali
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return 0.0

    R = 6371.0  # Dünya yarıçapı (km)

    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# ============================================================
# Windowed Features - Son 1 saatteki aktivite
# ============================================================

def compute_windowed_features(df: DataFrame) -> DataFrame:
    """
    Her kullanıcı için 1 saatlik pencerede aggregation hesaplar.

    Features:
      tx_count_1h       → Son 1 saatteki işlem sayısı
      total_amount_1h   → Son 1 saatteki toplam tutar
      avg_amount_1h     → Son 1 saatteki ortalama tutar
      unique_merchant_1h→ Son 1 saatteki benzersiz merchant sayısı

    Neden 1 saat? → Velocity attack'lar genelde çalıntı kart ele
    geçirildikten sonraki 1-2 saat içinde gerçekleşir.
    """
    windowed = (
        df.withWatermark("event_time", "10 minutes")
        .groupBy(
            F.window("event_time", "1 hour", "10 minutes"),  # 1 saat, 10 dk kaydırma
            "user_id",
        )
        .agg(
            F.count("*").alias("tx_count_1h"),
            F.sum("amount").alias("total_amount_1h"),
            F.avg("amount").alias("avg_amount_1h"),
            F.countDistinct("merchant_name").alias("unique_merchant_1h"),
            F.countDistinct("city").alias("unique_locations_1h"),
        )
    )

    return windowed


# ============================================================
# Transaction-Level Features - Her işlem için hesaplanan
# ============================================================

def compute_transaction_features(df: DataFrame) -> DataFrame:
    """
    Her transaction satırına ek feature'lar ekler.

    Features:
      hour_of_day       → Saat (0-23)
      day_of_week       → Haftanın günü (0=Pazartesi, 6=Pazar)
      amount_log         → log(amount+1) — büyük tutarları normalize eder
      is_high_amount    → Tutar > 1000$ mı?
      is_round_amount   → Tutar yuvarlak sayı mı? (500, 1000 vb.)
    """
    return (
        df
        .withColumn("hour_of_day", F.hour("event_time"))
        .withColumn("day_of_week", F.dayofweek("event_time"))
        .withColumn("amount_log", F.log1p("amount"))
        .withColumn("is_high_amount", F.when(F.col("amount") > 1000, 1).otherwise(0))
        .withColumn(
            "is_round_amount",
            F.when(F.col("amount") % 100 == 0, 1).otherwise(0),
        )
    )


# ============================================================
# Location Features - Konum bazlı (batch mode)
# ============================================================

def compute_location_features(df: DataFrame) -> DataFrame:
    """
    Konum bazlı feature'lar hesaplar.
    Her kullanıcının bir önceki işlemiyle arasındaki mesafe ve hız.

    Features:
      prev_latitude     → Önceki işlemin enlemi
      prev_longitude    → Önceki işlemin boylamı
      prev_timestamp    → Önceki işlemin zamanı
      distance_km       → Önceki işlemden mesafe (Haversine km)
      time_diff_hours   → Önceki işlemden geçen süre (saat)
      speed_kmh         → Hız (km/saat) — >900 ise impossible travel

    Not: Bu fonksiyon Window + lag ile çalıştığı için streaming modda
    doğrudan kullanılamaz. Batch (historical) eğitim verisi için kullanılır.
    Streaming'de stateful processing ile uyarlanabilir.
    """
    # Kullanıcı bazında zaman sıralı pencere
    user_window = Window.partitionBy("user_id").orderBy("event_time")

    df = (
        df
        .withColumn("prev_latitude", F.lag("latitude").over(user_window))
        .withColumn("prev_longitude", F.lag("longitude").over(user_window))
        .withColumn("prev_timestamp", F.lag("event_time").over(user_window))
    )

    # Haversine mesafe hesabı
    df = df.withColumn(
        "distance_km",
        haversine_km("prev_latitude", "prev_longitude", "latitude", "longitude"),
    )

    # Zaman farkı (saat)
    df = df.withColumn(
        "time_diff_hours",
        (F.unix_timestamp("event_time") - F.unix_timestamp("prev_timestamp")) / 3600.0,
    )

    # Hız = mesafe / zaman
    # time_diff_hours == 0 ise division by zero → null yerine 0
    df = df.withColumn(
        "speed_kmh",
        F.when(
            (F.col("time_diff_hours") > 0) & (F.col("time_diff_hours").isNotNull()),
            F.col("distance_km") / F.col("time_diff_hours"),
        ).otherwise(0.0),
    )

    # time_since_last_tx: Dakika cinsinden (saat yerine daha okunur)
    df = df.withColumn(
        "time_since_last_tx",
        F.when(
            F.col("time_diff_hours").isNotNull(),
            F.col("time_diff_hours") * 60.0,
        ).otherwise(0.0),
    )

    # amount_deviation: Kullanıcının ortalama tutarından sapma
    # (amount - user_avg) / user_std → z-score benzeri
    user_stats_window = Window.partitionBy("user_id").orderBy("event_time").rowsBetween(
        Window.unboundedPreceding, Window.currentRow
    )
    user_avg = F.avg("amount").over(user_stats_window)
    user_std = F.stddev("amount").over(user_stats_window)
    df = df.withColumn(
        "amount_deviation",
        F.when(
            user_std > 0,
            (F.col("amount") - user_avg) / user_std,
        ).otherwise(0.0),
    )

    # İlk işlem için null'ları doldur
    fill_cols = [
        "prev_latitude", "prev_longitude", "distance_km",
        "time_diff_hours", "speed_kmh", "time_since_last_tx", "amount_deviation",
    ]
    df = df.fillna(0.0, subset=fill_cols)

    return df


# ============================================================
# Tüm feature'ları birleştir (Batch mode - historical data)
# ============================================================

def compute_all_features_batch(df: DataFrame) -> DataFrame:
    """
    Tüm feature'ları batch modda hesaplar.
    Historical eğitim verisi hazırlamak için kullanılır.

    Pipeline:
      Raw data → Transaction features → Location features → Windowed features (join)
    """
    # 1. Transaction-level features
    df = compute_transaction_features(df)

    # 2. Location features (lag-based)
    df = compute_location_features(df)

    return df
