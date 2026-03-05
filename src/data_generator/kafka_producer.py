"""
Kafka Producer - Transaction verilerini Kafka'ya gönderir.

Bu modül TransactionGenerator'dan aldığı verileri
"transactions" topic'ine JSON formatında yazar.

Kullanım:
    python -m src.data_generator.kafka_producer

Mülakat notu:
  "Neden Kafka?" → Mesaj kaybı olmadan yüksek throughput sağlar.
  Producer acks=all ile mesajın Kafka'ya yazıldığını garanti eder.
  Partition key olarak user_id kullanıyoruz → aynı kullanıcının
  işlemleri aynı partition'a gider → sıralama garantisi.
"""

import json
import time
import signal
import sys
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import KafkaError, NoBrokersAvailable

from src.config import (
    KAFKA_BROKER,
    KAFKA_TOPIC_TRANSACTIONS,
    GENERATOR_TRANSACTIONS_PER_SEC,
    GENERATOR_FRAUD_RATE,
)
from src.data_generator.transaction_generator import TransactionGenerator


class FraudTransactionProducer:
    """
    Kafka Producer wrapper - transaction verilerini Kafka'ya gönderir.

    Özellikler:
      - JSON serialization
      - user_id ile partitioning (sıralama garantisi)
      - Graceful shutdown (Ctrl+C)
      - Hız kontrolü (configurable TPS)
      - Basit metrikler (gönderilen/hata sayısı)
    """

    def __init__(
        self,
        broker: str = KAFKA_BROKER,
        topic: str = KAFKA_TOPIC_TRANSACTIONS,
        tps: int = GENERATOR_TRANSACTIONS_PER_SEC,
        fraud_rate: float = GENERATOR_FRAUD_RATE,
    ):
        self.topic = topic
        self.tps = tps
        self.running = False

        # Metrikler
        self.sent_count = 0
        self.error_count = 0
        self.start_time = None

        # Transaction generator
        self.generator = TransactionGenerator(
            num_users=1000, fraud_rate=fraud_rate, seed=None
        )

        # Kafka producer
        # acks='all' → Tüm replica'lara yazılmasını bekle (veri kaybı yok)
        # value_serializer → Python dict'i JSON bytes'a çevir
        # key_serializer → user_id string'i bytes'a çevir
        # retries → Geçici hatalarda otomatik tekrar dene
        self.producer = self._create_producer(broker)

    def _create_producer(self, broker: str, max_retries: int = 5) -> KafkaProducer:
        """
        Kafka bağlantısı kurar. Kafka hazır değilse bekler.
        """
        for attempt in range(1, max_retries + 1):
            try:
                producer = KafkaProducer(
                    bootstrap_servers=broker,
                    value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                    key_serializer=lambda k: k.encode("utf-8"),
                    acks="all",
                    retries=3,
                    max_block_ms=10000,
                )
                print(f"Kafka'ya baglanildi: {broker}")
                return producer
            except NoBrokersAvailable:
                if attempt < max_retries:
                    wait = attempt * 5
                    print(
                        f"Kafka henuz hazir degil. {wait}s bekleniyor... "
                        f"(deneme {attempt}/{max_retries})"
                    )
                    time.sleep(wait)
                else:
                    raise RuntimeError(
                        f"Kafka'ya baglanilamadi ({max_retries} deneme): {broker}"
                    )

    def _on_success(self, metadata):
        """Mesaj başarıyla gönderildi callback'i."""
        self.sent_count += 1

    def _on_error(self, exc):
        """Mesaj gönderme hatası callback'i."""
        self.error_count += 1
        print(f"HATA: Mesaj gonderilemedi: {exc}")

    def start(self):
        """
        Producer'ı başlatır. Ctrl+C ile durdurulur.
        Her saniye belirtilen sayıda (tps) transaction üretip gönderir.
        """
        self.running = True
        self.start_time = time.time()

        # Graceful shutdown: Ctrl+C
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        print(f"Producer baslatildi:")
        print(f"  Topic:      {self.topic}")
        print(f"  Hiz:        {self.tps} tx/sn")
        print(f"  Fraud orani: {self.generator.fraud_rate * 100:.1f}%")
        print(f"  Durdurmak icin: Ctrl+C")
        print("-" * 50)

        interval = 1.0 / self.tps  # Her transaction arası bekleme süresi

        while self.running:
            try:
                tx = self.generator.generate_transaction()

                # Mesajı Kafka'ya gönder
                # key=user_id → Aynı kullanıcının işlemleri aynı partition'a
                self.producer.send(
                    self.topic, key=tx["user_id"], value=tx
                ).add_callback(self._on_success).add_errback(self._on_error)

                # Her 100 mesajda bir durum raporu
                total = self.sent_count + self.error_count
                if total > 0 and total % 100 == 0:
                    elapsed = time.time() - self.start_time
                    actual_tps = self.sent_count / elapsed if elapsed > 0 else 0
                    print(
                        f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] "
                        f"Gonderilen: {self.sent_count} | "
                        f"Hata: {self.error_count} | "
                        f"Hiz: {actual_tps:.1f} tx/sn"
                    )

                time.sleep(interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Beklenmeyen hata: {e}")
                self.error_count += 1
                time.sleep(1)

    def _shutdown(self, signum, frame):
        """Graceful shutdown handler."""
        print(f"\nKapatiliyor...")
        self.running = False

    def stop(self):
        """Producer'ı durdurur ve sonuç raporu yazdırır."""
        self.running = False

        # Buffer'daki mesajları gönder
        if self.producer:
            self.producer.flush(timeout=10)
            self.producer.close()

        elapsed = time.time() - self.start_time if self.start_time else 0
        print("=" * 50)
        print("PRODUCER SONUC RAPORU")
        print("=" * 50)
        print(f"  Toplam gonderilen: {self.sent_count}")
        print(f"  Toplam hata:       {self.error_count}")
        print(f"  Calisma suresi:    {elapsed:.1f}s")
        if elapsed > 0:
            print(f"  Ortalama hiz:      {self.sent_count / elapsed:.1f} tx/sn")
        print("=" * 50)


# ============================================================
# Ana giriş noktası
# ============================================================
if __name__ == "__main__":
    producer = FraudTransactionProducer()
    try:
        producer.start()
    finally:
        producer.stop()
