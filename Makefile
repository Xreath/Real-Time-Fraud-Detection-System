# ============================================
# Real-Time Fraud Detection - Makefile
# ============================================
# Sık kullanılan komutları kısayol olarak tanımlar.
# Kullanım: make <komut>

.PHONY: help up down restart logs status kafka-topics \
        venv install producer spark-submit mlflow-ui clean \
        register-schemas prepare-data train stream register-pyfunc

# Varsayılan: help
help:
	@echo ""
	@echo "📋 Kullanılabilir komutlar:"
	@echo ""
	@echo "  Docker:"
	@echo "    make up              - Tüm servisleri başlat"
	@echo "    make down            - Tüm servisleri durdur"
	@echo "    make restart         - Servisleri yeniden başlat"
	@echo "    make logs            - Tüm servis loglarını göster"
	@echo "    make logs-kafka      - Kafka loglarını göster"
	@echo "    make logs-spark      - Spark loglarını göster"
	@echo "    make logs-mlflow     - MLflow loglarını göster"
	@echo "    make status          - Servis durumlarını göster"
	@echo ""
	@echo "  Kafka:"
	@echo "    make kafka-topics    - Kafka topic listesini göster"
	@echo ""
	@echo "  Python:"
	@echo "    make venv            - Virtual environment oluştur"
	@echo "    make install         - Python bağımlılıklarını kur"
	@echo ""
	@echo "  Application:"
	@echo "    make producer        - Transaction producer başlat"
	@echo "    make register-pyfunc - Pyfunc modeli MLflow'a kaydet"
	@echo ""
	@echo "  Cleanup:"
	@echo "    make clean           - Docker volume ve cache temizle"
	@echo ""

# --- Docker ---
up:
	docker compose up -d
	@echo "✅ Servisler başlatıldı. Kontrol: make status"

down:
	docker compose down

restart:
	docker compose down && docker compose up -d

logs:
	docker compose logs -f --tail=50

logs-kafka:
	docker compose logs -f kafka --tail=50

logs-spark:
	docker compose logs -f spark-master spark-worker --tail=50

logs-mlflow:
	docker compose logs -f mlflow --tail=50

status:
	docker compose ps

# --- Kafka ---
kafka-topics:
	docker compose exec kafka kafka-topics --list --bootstrap-server localhost:9092

# --- Python ---
venv:
	uv venv .venv
	@echo "✅ Virtual environment oluşturuldu."
	@echo "   Aktifleştirmek için: source .venv/bin/activate"

install: venv
	uv pip install -r requirements.txt
	@echo "✅ Bağımlılıklar kuruldu."

# --- Application ---
producer:
	. .venv/bin/activate && python -m src.data_generator.kafka_producer

consumer-debug:
	. .venv/bin/activate && python -m src.data_generator.kafka_consumer_debug --from-beginning --max-messages 50

register-schemas:
	. .venv/bin/activate && python -m src.data_generator.register_schemas

stream:
	. .venv/bin/activate && python -m src.streaming.spark_consumer --debug

prepare-data:
	. .venv/bin/activate && python -m src.training.prepare_data

train:
	. .venv/bin/activate && python -m src.training.train_model

register-pyfunc:
	. .venv/bin/activate && python -m src.serving.register_pyfunc

# --- Cleanup ---
clean:
	docker compose down -v
	rm -rf __pycache__ src/__pycache__ .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "🧹 Temizlik tamamlandı."
