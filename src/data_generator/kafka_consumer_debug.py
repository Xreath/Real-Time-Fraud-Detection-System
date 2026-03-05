"""
Kafka Debug Consumer - Topic'leri dinleyip mesajları ekrana basar.

Debugging ve doğrulama amaçlıdır. Production'da kullanılmaz.

Kullanım:
    # transactions topic'ini dinle (varsayılan)
    python -m src.data_generator.kafka_consumer_debug

    # Belirli bir topic'i dinle
    python -m src.data_generator.kafka_consumer_debug --topic fraud-alerts

    # Baştan oku
    python -m src.data_generator.kafka_consumer_debug --from-beginning

Mülakat notu:
  "Consumer group nedir?" → Aynı topic'i okuyan consumer'ları gruplar.
  Kafka, partition'ları group içindeki consumer'lara dağıtır.
  Bu sayede yatay ölçekleme yapılır: 3 partition + 3 consumer = paralel okuma.
  Bir consumer çökerse, partition'ı başka consumer'a atanır (rebalance).
"""

import json
import sys
import signal
import argparse
from datetime import datetime, timezone
from collections import defaultdict

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from src.config import KAFKA_BROKER, KAFKA_TOPIC_TRANSACTIONS


def create_consumer(
    topic: str, broker: str, from_beginning: bool = False, group_id: str = "debug-consumer"
) -> KafkaConsumer:
    """Kafka consumer oluşturur."""
    offset_reset = "earliest" if from_beginning else "latest"
    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=broker,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            key_deserializer=lambda k: k.decode("utf-8") if k else None,
            auto_offset_reset=offset_reset,
            group_id=group_id,
            consumer_timeout_ms=1000,  # 1 saniye mesaj gelmezse StopIteration
            enable_auto_commit=True,
        )
        print(f"Kafka'ya baglanildi: {broker}")
        return consumer
    except NoBrokersAvailable:
        print(f"HATA: Kafka'ya baglanilamadi: {broker}")
        sys.exit(1)


def run_consumer(topic: str, broker: str, from_beginning: bool, max_messages: int):
    """
    Consumer'ı çalıştırır. Mesajları okuyup ekrana basar.
    İstatistik toplar: toplam mesaj, fraud sayısı, partition dağılımı.
    """
    consumer = create_consumer(topic, broker, from_beginning)
    running = True
    msg_count = 0
    fraud_count = 0
    partition_counts = defaultdict(int)

    def shutdown(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"Topic dinleniyor: {topic}")
    print(f"Offset: {'bastan' if from_beginning else 'son'}")
    print(f"Max mesaj: {max_messages if max_messages > 0 else 'sinirsiz'}")
    print("-" * 60)

    try:
        while running:
            if 0 < max_messages <= msg_count:
                break

            # poll() ile batch halinde mesaj al
            records = consumer.poll(timeout_ms=2000)

            if not records:
                continue

            for tp, messages in records.items():
                for msg in messages:
                    msg_count += 1
                    partition_counts[msg.partition] += 1
                    data = msg.value

                    # Fraud kontrolü (transactions topic için)
                    is_fraud = data.get("is_fraud", 0)
                    if is_fraud:
                        fraud_count += 1

                    # Kısa özet yazdır
                    fraud_marker = " ** FRAUD **" if is_fraud else ""
                    print(
                        f"[P{msg.partition}|O{msg.offset}] "
                        f"{data.get('user_id', '?'):>10} | "
                        f"${data.get('amount', 0):>8.2f} | "
                        f"{data.get('merchant_name', '?'):<20} | "
                        f"{data.get('city', '?'):<15}{fraud_marker}"
                    )

                    if 0 < max_messages <= msg_count:
                        break

    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()

    # Özet rapor
    print("\n" + "=" * 60)
    print("CONSUMER OZET RAPORU")
    print("=" * 60)
    print(f"  Toplam mesaj:      {msg_count}")
    print(f"  Fraud mesaj:       {fraud_count}")
    if msg_count > 0:
        print(f"  Fraud orani:       {fraud_count / msg_count * 100:.1f}%")
    print(f"  Partition dagilimi:")
    for p in sorted(partition_counts):
        print(f"    Partition {p}: {partition_counts[p]} mesaj")
    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kafka Debug Consumer")
    parser.add_argument(
        "--topic", default=KAFKA_TOPIC_TRANSACTIONS, help="Dinlenecek topic"
    )
    parser.add_argument(
        "--broker", default=KAFKA_BROKER, help="Kafka broker adresi"
    )
    parser.add_argument(
        "--from-beginning", action="store_true", help="Topic'i bastan oku"
    )
    parser.add_argument(
        "--max-messages", type=int, default=0, help="Maksimum mesaj sayisi (0=sinirsiz)"
    )
    args = parser.parse_args()

    run_consumer(args.topic, args.broker, args.from_beginning, args.max_messages)
