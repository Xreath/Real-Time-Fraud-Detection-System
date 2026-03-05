"""
Transaction Data Generator - Gerçekçi kredi kartı işlemleri üretir.

Bu modül hem normal hem de sahte (fraud) işlemler üretir.
Fraud pattern'leri gerçek dünya senaryolarını simüle eder:
  - Velocity attack: Kısa sürede çok fazla işlem
  - Impossible travel: Coğrafi olarak imkansız hız
  - Unusual amount: Anormal tutarlar
  - Late night: Gece yarısı işlemleri
  - Foreign country: Yabancı ülke işlemleri

Mülakat notu:
  "Neden Faker kullanıyoruz?" → Gerçek veri kullanamayız (GDPR/PCI-DSS),
  ama model gerçekçi pattern'lere ihtiyaç duyar. Faker ile kontrollü
  fraud pattern'leri inject edebiliyoruz.
"""

import uuid
import random
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

from faker import Faker

fake = Faker()

# ============================================================
# Sabit veriler - Gerçekçi merchant ve konum bilgileri
# ============================================================

MERCHANTS = [
    {"name": "Amazon", "category": "online_shopping", "country": "US"},
    {"name": "Walmart", "category": "grocery", "country": "US"},
    {"name": "Shell Gas Station", "category": "gas_station", "country": "US"},
    {"name": "Starbucks", "category": "food_drink", "country": "US"},
    {"name": "Netflix", "category": "subscription", "country": "US"},
    {"name": "Apple Store", "category": "electronics", "country": "US"},
    {"name": "Uber", "category": "transport", "country": "US"},
    {"name": "Target", "category": "retail", "country": "US"},
    {"name": "McDonalds", "category": "food_drink", "country": "US"},
    {"name": "Best Buy", "category": "electronics", "country": "US"},
    {"name": "Zara", "category": "clothing", "country": "US"},
    {"name": "Home Depot", "category": "home_improvement", "country": "US"},
    {"name": "CVS Pharmacy", "category": "pharmacy", "country": "US"},
    {"name": "Spotify", "category": "subscription", "country": "US"},
    {"name": "Nike Store", "category": "clothing", "country": "US"},
]

# Yabancı merchant'lar (fraud sinyali olabilir)
FOREIGN_MERCHANTS = [
    {"name": "AliExpress", "category": "online_shopping", "country": "CN"},
    {"name": "Booking.com", "category": "travel", "country": "NL"},
    {"name": "Shein", "category": "clothing", "country": "CN"},
    {"name": "Temu", "category": "online_shopping", "country": "CN"},
    {"name": "Rakuten", "category": "online_shopping", "country": "JP"},
]

# ABD şehirleri ve yaklaşık koordinatları
US_LOCATIONS = [
    {"city": "New York", "lat": 40.7128, "lon": -74.0060},
    {"city": "Los Angeles", "lat": 34.0522, "lon": -118.2437},
    {"city": "Chicago", "lat": 41.8781, "lon": -87.6298},
    {"city": "Houston", "lat": 29.7604, "lon": -95.3698},
    {"city": "Phoenix", "lat": 33.4484, "lon": -112.0740},
    {"city": "San Francisco", "lat": 37.7749, "lon": -122.4194},
    {"city": "Seattle", "lat": 47.6062, "lon": -122.3321},
    {"city": "Miami", "lat": 25.7617, "lon": -80.1918},
    {"city": "Denver", "lat": 39.7392, "lon": -104.9903},
    {"city": "Atlanta", "lat": 33.7490, "lon": -84.3880},
]

# Uzak konumlar (impossible travel fraud için)
DISTANT_LOCATIONS = [
    {"city": "London", "lat": 51.5074, "lon": -0.1278},
    {"city": "Tokyo", "lat": 35.6762, "lon": 139.6503},
    {"city": "Moscow", "lat": 55.7558, "lon": 37.6173},
    {"city": "Lagos", "lat": 6.5244, "lon": 3.3792},
    {"city": "Sydney", "lat": -33.8688, "lon": 151.2093},
]

CARD_TYPES = ["visa", "mastercard", "amex"]


@dataclass
class Transaction:
    """Tek bir kredi kartı işlemini temsil eder."""

    transaction_id: str
    user_id: str
    amount: float
    merchant_name: str
    merchant_category: str
    card_type: str
    latitude: float
    longitude: float
    city: str
    country: str
    timestamp: str  # ISO 8601 format
    is_weekend: bool
    is_night: bool  # 23:00-05:00 arası
    is_foreign: bool
    is_fraud: int  # 0 veya 1


class TransactionGenerator:
    """
    Gerçekçi transaction verileri üreten ana sınıf.

    Her kullanıcının bir "profili" var:
      - Ev şehri (normal işlemler burada olur)
      - Ortalama harcama tutarı
      - Kart tipi

    Fraud işlemleri belirli pattern'lere göre üretilir.
    """

    def __init__(
        self,
        num_users: int = 1000,
        fraud_rate: float = 0.02,
        seed: Optional[int] = None,
    ):
        """
        Args:
            num_users: Simüle edilecek kullanıcı sayısı
            fraud_rate: Fraud işlem oranı (0.02 = %2)
            seed: Reproducibility için random seed
        """
        if seed is not None:
            random.seed(seed)
            Faker.seed(seed)

        self.fraud_rate = fraud_rate
        self.users = self._create_user_profiles(num_users)

    def _create_user_profiles(self, num_users: int) -> list[dict]:
        """
        Her kullanıcı için sabit bir profil oluşturur.
        Bu profil, normal davranışı tanımlar - sapma fraud sinyali olur.
        """
        profiles = []
        for i in range(num_users):
            home_location = random.choice(US_LOCATIONS)
            profiles.append(
                {
                    "user_id": f"user_{i:04d}",
                    "home_city": home_location["city"],
                    "home_lat": home_location["lat"],
                    "home_lon": home_location["lon"],
                    "avg_amount": random.uniform(20, 200),
                    "card_type": random.choice(CARD_TYPES),
                }
            )
        return profiles

    def generate_transaction(self) -> dict:
        """
        Tek bir transaction üretir. fraud_rate olasılıkla fraud olur.

        Returns:
            Transaction verisi (dict)
        """
        user = random.choice(self.users)
        is_fraud = random.random() < self.fraud_rate

        if is_fraud:
            return self._generate_fraud_transaction(user)
        else:
            return self._generate_normal_transaction(user)

    def _generate_normal_transaction(self, user: dict) -> dict:
        """
        Normal (meşru) bir işlem üretir.
        - Tutar kullanıcı ortalaması etrafında
        - Konum ev şehri yakınında
        - Bilinen merchant'lardan
        """
        merchant = random.choice(MERCHANTS)

        # Tutar: kullanıcı ortalaması etrafında normal dağılım
        amount = max(0.50, random.gauss(user["avg_amount"], user["avg_amount"] * 0.3))
        amount = round(amount, 2)

        # Konum: ev şehri + küçük sapma
        lat = user["home_lat"] + random.uniform(-0.1, 0.1)
        lon = user["home_lon"] + random.uniform(-0.1, 0.1)

        now = datetime.now(timezone.utc)
        hour = now.hour

        return asdict(
            Transaction(
                transaction_id=str(uuid.uuid4()),
                user_id=user["user_id"],
                amount=amount,
                merchant_name=merchant["name"],
                merchant_category=merchant["category"],
                card_type=user["card_type"],
                latitude=round(lat, 4),
                longitude=round(lon, 4),
                city=user["home_city"],
                country=merchant["country"],
                timestamp=now.isoformat(),
                is_weekend=now.weekday() >= 5,
                is_night=hour >= 23 or hour < 5,
                is_foreign=False,
                is_fraud=0,
            )
        )

    def _generate_fraud_transaction(self, user: dict) -> dict:
        """
        Fraud işlem üretir. Rastgele bir fraud pattern seçer.

        Fraud pattern'leri:
          1. Unusual amount: Çok yüksek veya yuvarlak tutar
          2. Foreign transaction: Yabancı ülkeden işlem
          3. Impossible travel: Ev şehrinden çok uzak konum
          4. Late night + high amount: Gece yarısı yüksek tutar
        """
        fraud_type = random.choice(
            ["unusual_amount", "foreign", "impossible_travel", "late_night_high"]
        )

        now = datetime.now(timezone.utc)

        if fraud_type == "unusual_amount":
            # Kullanıcı ortalamasının 5-20 katı veya tam yuvarlak sayı
            if random.random() < 0.5:
                amount = round(user["avg_amount"] * random.uniform(5, 20), 2)
            else:
                amount = float(random.choice([500, 1000, 2000, 5000, 9999]))
            merchant = random.choice(MERCHANTS)
            lat = user["home_lat"] + random.uniform(-0.1, 0.1)
            lon = user["home_lon"] + random.uniform(-0.1, 0.1)
            city = user["home_city"]
            country = "US"
            is_foreign = False

        elif fraud_type == "foreign":
            amount = round(random.uniform(50, 2000), 2)
            merchant = random.choice(FOREIGN_MERCHANTS)
            distant = random.choice(DISTANT_LOCATIONS)
            lat = distant["lat"] + random.uniform(-1, 1)
            lon = distant["lon"] + random.uniform(-1, 1)
            city = distant["city"]
            country = merchant["country"]
            is_foreign = True

        elif fraud_type == "impossible_travel":
            # Ev şehrinden binlerce km uzakta bir işlem
            amount = round(random.uniform(100, 3000), 2)
            merchant = random.choice(MERCHANTS)
            distant = random.choice(DISTANT_LOCATIONS)
            lat = distant["lat"] + random.uniform(-1, 1)
            lon = distant["lon"] + random.uniform(-1, 1)
            city = distant["city"]
            country = "US"
            is_foreign = False

        else:  # late_night_high
            amount = round(random.uniform(500, 5000), 2)
            merchant = random.choice(MERCHANTS)
            lat = user["home_lat"] + random.uniform(-0.5, 0.5)
            lon = user["home_lon"] + random.uniform(-0.5, 0.5)
            city = user["home_city"]
            country = "US"
            is_foreign = False
            # Saati gece yarısına zorla (simülasyon amaçlı timestamp'a yansımaz,
            # ama is_night=True olarak işaretlenir)

        hour = now.hour
        is_night = hour >= 23 or hour < 5
        if fraud_type == "late_night_high":
            is_night = True

        return asdict(
            Transaction(
                transaction_id=str(uuid.uuid4()),
                user_id=user["user_id"],
                amount=amount,
                merchant_name=merchant["name"],
                merchant_category=merchant["category"],
                card_type=user["card_type"],
                latitude=round(lat, 4),
                longitude=round(lon, 4),
                city=city,
                country=country,
                timestamp=now.isoformat(),
                is_weekend=now.weekday() >= 5,
                is_night=is_night,
                is_foreign=is_foreign,
                is_fraud=1,
            )
        )

    def generate_batch(self, batch_size: int = 100) -> list[dict]:
        """Toplu transaction üretir. Historical data için kullanılır."""
        return [self.generate_transaction() for _ in range(batch_size)]


# ============================================================
# Test: Doğrudan çalıştırılırsa örnek çıktı üretir
# ============================================================
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
    # Fraud oranı düşük olduğu için birkaç deneme gerekebilir
    gen_fraud = TransactionGenerator(num_users=10, fraud_rate=1.0, seed=42)
    tx = gen_fraud.generate_transaction()
    print(json.dumps(tx, indent=2))

    # İstatistik testi
    print("\n=== 10000 Transaction İstatistikleri ===")
    gen_test = TransactionGenerator(num_users=100, fraud_rate=0.02, seed=123)
    txs = gen_test.generate_batch(10000)
    fraud_count = sum(1 for t in txs if t["is_fraud"] == 1)
    print(f"Toplam: {len(txs)}")
    print(f"Fraud:  {fraud_count} ({fraud_count/len(txs)*100:.1f}%)")
    print(f"Normal: {len(txs) - fraud_count}")
    amounts = [t["amount"] for t in txs]
    print(f"Tutar aralığı: ${min(amounts):.2f} - ${max(amounts):.2f}")
    print(f"Ortalama tutar: ${sum(amounts)/len(amounts):.2f}")
