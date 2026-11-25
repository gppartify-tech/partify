"""Test setup: a separate PostgreSQL database, created fresh for every test session.

    createdb -U partify partify_test        (once)
    pytest                                  (from the backend/ folder)

Override the database with TEST_DATABASE_URL if needed.
"""
import os
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal

os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://partify:partify@localhost:5432/partify_test"
)
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="partify-uploads-")
os.environ["ADMIN_EMAIL"] = ""
os.environ["SEED_DEMO_USERS"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Offer, PriceHistory, Product, Store  # noqa: E402
from app.services.catalog import refresh_products  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        names = ", ".join(t.name for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def client():
    return TestClient(app)


STORES = [
    ("igeek", "iGeek Megastore", "https://igeekjo.com", "#2a78d6"),
    ("compujordan", "CompuJordan", "https://compujordan.com", "#eb6834"),
    ("oriental", "Oriental Store", "https://os-jo.com", "#1baf7a"),
]

# A small but complete catalog: enough parts to build a PC.
# (category, brand, name, specs, offers) - each offer: (store, sku, price, in_stock, store's "was" price)
CATALOG = [
    ("cpu", "AMD", "AMD Ryzen 5 7600",
     {"socket": "AM5", "cores": 6, "threads": 12, "tdp_w": 88, "igpu": True, "gaming_score": 71, "multi_score": 33},
     [("igeek", "c1", 149, True, None), ("compujordan", "100", 145, True, None)]),
    ("cpu", "AMD", "AMD Ryzen 7 7800X3D",
     {"socket": "AM5", "cores": 8, "threads": 16, "tdp_w": 120, "igpu": True, "gaming_score": 90, "multi_score": 42},
     [("igeek", "c2", 299, True, None)]),
    ("cpu", "Intel", "Intel Core i5-14400F",
     {"socket": "LGA1700", "cores": 10, "threads": 16, "tdp_w": 148, "igpu": False, "gaming_score": 68, "multi_score": 40},
     [("igeek", "c3", 139, True, None)]),
    ("gpu", "ASUS", "ASUS Dual GeForce RTX 5060 8GB GDDR7",
     {"chip": "RTX 5060", "vram_gb": 8, "tdp_w": 145, "score": 28, "chip_maker": "nvidia"},
     [("igeek", "g1", 469, True, None), ("compujordan", "101", 479, False, None)]),
    ("gpu", "Sapphire", "Sapphire PULSE Radeon RX 9070 XT 16GB",
     {"chip": "RX 9070 XT", "vram_gb": 16, "tdp_w": 304, "score": 55, "chip_maker": "amd"},
     [("igeek", "g2", 899, True, 999)]),
    ("motherboard", "MSI", "MSI B650M GAMING PLUS WIFI",
     {"socket": "AM5", "chipset": "B650", "memory_type": "DDR5", "form_factor": "Micro-ATX", "wifi": True},
     [("igeek", "m1", 129, True, None)]),
    ("motherboard", "Gigabyte", "Gigabyte B760M DS3H DDR4",
     {"socket": "LGA1700", "chipset": "B760", "memory_type": "DDR4", "form_factor": "Micro-ATX", "wifi": False},
     [("igeek", "m2", 99, True, None)]),
    ("ram", "Corsair", "Corsair Vengeance 32GB (2x16GB) DDR5 6000",
     {"memory_type": "DDR5", "capacity_gb": 32, "modules": 2, "speed_mhz": 6000},
     [("igeek", "r1", 189, True, None)]),
    ("ram", "Kingston", "Kingston FURY Beast 16GB (2x8GB) DDR4 3200",
     {"memory_type": "DDR4", "capacity_gb": 16, "modules": 2, "speed_mhz": 3200},
     [("igeek", "r2", 79, True, None)]),
    ("storage", "Kingston", "Kingston NV3 1TB NVMe SSD",
     {"storage_type": "NVMe SSD", "capacity_gb": 1000},
     [("igeek", "s1", 89, True, None), ("compujordan", "102", 85, True, None)]),
    ("psu", "Corsair", "Corsair RM750e 750W",
     {"wattage": 750, "efficiency": "80+ Gold", "modular": "Full", "form_factor": "ATX"},
     [("igeek", "p1", 99, True, None)]),
    ("case", "Lian Li", "Lian Li LANCOOL 216",
     {"form_factor": "Mid Tower", "supports": ["ATX", "Micro-ATX", "Mini-ITX"]},
     [("igeek", "k1", 85, True, None)]),
    ("cooler", "DeepCool", "DeepCool AK400",
     {"cooler_type": "Air", "tdp_rating_w": 220},
     [("igeek", "f1", 29, True, None)]),
]


def add_catalog(db, catalog=CATALOG):
    """Insert stores, products, offers and one price-history point per offer, like the real data."""
    now = datetime.now(UTC) - timedelta(hours=1)
    stores = {}
    for slug, name, url, color in STORES:
        stores[slug] = Store(slug=slug, name=name, base_url=url, color=color, prices_updated_at=now)
        db.add(stores[slug])
    db.flush()
    product_ids = set()
    for category, brand, name, specs, offers in catalog:
        product = Product(category=category, brand=brand, name=name, specs=specs)
        db.add(product)
        db.flush()
        product_ids.add(product.id)
        for store, sku, price, in_stock, old_price in offers:
            offer = Offer(
                product_id=product.id, store_id=stores[store].id, store_sku=sku, category=category,
                url=f"https://example.com/p/{sku}", title=name, price=Decimal(price), in_stock=in_stock,
                old_price=Decimal(old_price) if old_price else None, price_changed_at=now,
                first_seen_at=now, last_seen_at=now,
            )
            db.add(offer)
            db.flush()
            db.add(PriceHistory(offer_id=offer.id, price=offer.price, in_stock=in_stock, recorded_at=now))
    refresh_products(db, product_ids)
    db.commit()


@pytest.fixture
def catalog(db):
    add_catalog(db)
    return db


def register(client, username="sami", email=None, password="supersecret1"):
    resp = client.post("/api/auth/register", json={
        "email": email or f"{username}@example.com", "username": username, "password": password,
    })
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
