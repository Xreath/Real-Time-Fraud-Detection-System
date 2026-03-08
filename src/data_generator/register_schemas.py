"""
Schema Registry'ye JSON Schema'ları kaydeder.

Schema Registry, mesaj formatının tutarlı olmasını garanti eder.
Producer schema'ya uymayan mesaj gönderirse hata alır.

Kullanım:
    python -m src.data_generator.register_schemas

Mülakat notu:
  "Neden Schema Registry?" → Microservice mimarisinde farklı takımlar
  aynı topic'e yazıyor. Schema Registry olmadan biri field ekler,
  diğer taraf patlar. Schema Registry bunu önler.

  "Schema evolution nedir?" → Schema'yı değiştirmen gerektiğinde
  (yeni field ekleme, field silme) geriye uyumluluğu kontrol eder.
  BACKWARD (consumer eskiyi okuyabilir), FORWARD (producer eskiye uyumlu),
  FULL (ikisi de) modları var.
"""

import json
import sys
from pathlib import Path

import requests

SCHEMA_REGISTRY_URL = "http://localhost:8085"
SCHEMAS_DIR = Path(__file__).parent.parent.parent / "configs" / "schemas"


def register_schema(subject: str, schema_path: Path) -> dict:
    """
    Bir JSON Schema'yı Schema Registry'ye kaydeder.

    Args:
        subject: Schema subject adı (genelde topic-value)
        schema_path: JSON Schema dosyasının yolu

    Returns:
        Registry cevabı (id içerir)
    """
    schema_str = schema_path.read_text()

    # Schema Registry'ye gönderilecek payload
    # schemaType: JSON → JSON Schema kullanıyoruz (Avro değil)
    payload = {
        "schemaType": "JSON",
        "schema": schema_str,
    }

    url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions"
    resp = requests.post(
        url,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        json=payload,
    )

    if resp.status_code == 200:
        result = resp.json()
        print(f"  Schema kayıt edildi: {subject} → id={result['id']}")
        return result
    else:
        print(f"  HATA: {subject} → {resp.status_code}: {resp.text}")
        return {}


def set_compatibility(subject: str, level: str = "BACKWARD"):
    """
    Schema compatibility seviyesini ayarlar.

    BACKWARD: Yeni schema, eski veriyi okuyabilir (varsayılan)
    FORWARD:  Eski schema, yeni veriyi okuyabilir
    FULL:     İkisi de
    NONE:     Kontrol yok
    """
    url = f"{SCHEMA_REGISTRY_URL}/config/{subject}"
    resp = requests.put(
        url,
        headers={"Content-Type": "application/vnd.schemaregistry.v1+json"},
        json={"compatibility": level},
    )
    if resp.status_code == 200:
        print(f"  Compatibility: {subject} → {level}")


def check_registry_health() -> bool:
    """Schema Registry erişilebilir mi kontrol eder."""
    try:
        resp = requests.get(f"{SCHEMA_REGISTRY_URL}/subjects", timeout=5)
        return resp.status_code == 200
    except requests.ConnectionError:
        return False


def main():
    print("=" * 50)
    print("Schema Registry - JSON Schema Kaydı")
    print("=" * 50)

    # Bağlantı kontrolü
    if not check_registry_health():
        print(f"\nHATA: Schema Registry erişilemez: {SCHEMA_REGISTRY_URL}")
        print("  docker compose up -d ile servisleri başlatın.")
        sys.exit(1)

    print(f"\nRegistry: {SCHEMA_REGISTRY_URL}")

    # Transaction schema kaydı
    schema_file = SCHEMAS_DIR / "transaction_value.json"
    if not schema_file.exists():
        print(f"HATA: Schema dosyası bulunamadı: {schema_file}")
        sys.exit(1)

    print("\nSchema'lar kaydediliyor...")
    register_schema("transactions-value", schema_file)
    set_compatibility("transactions-value", "BACKWARD")

    # Kayıtlı schema'ları listele
    resp = requests.get(f"{SCHEMA_REGISTRY_URL}/subjects")
    if resp.status_code == 200:
        print(f"\nKayıtlı subject'ler: {resp.json()}")

    print("\nTamamlandı.")


if __name__ == "__main__":
    main()
