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


# The tests use their own small catalog (not the bundled test_catalog.json), so that editing
# the demo data never breaks them.
STORES = [
    ("store-a", "Test Store A", "https://example.com", "#2a78d6"),
    ("store-b", "Test Store B", "https://example.com", "#eb6834"),
    ("store-c", "Test Store C", "https://example.com", "#1baf7a"),
]

# A small but complete catalog: enough parts to build a PC.
# (category, brand, name, specs, offers) - each offer: (store, sku, price, in_stock, store's "was" price)
CATALOG = [
    ("cpu", "AMD", "Test Processor 6-Core (AM5)",
     {"socket": "AM5", "cores": 6, "threads": 12, "tdp_w": 88, "igpu": True, "gaming_score": 71, "multi_score": 33},
     [("store-a", "c1", 149, True, None), ("store-b", "c1b", 145, True, None)]),
    ("cpu", "AMD", "Test Processor 8-Core Plus (AM5)",
     {"socket": "AM5", "cores": 8, "threads": 16, "tdp_w": 120, "igpu": True, "gaming_score": 90, "multi_score": 42},
     [("store-a", "c2", 299, True, None)]),
    ("cpu", "Intel", "Test Processor 10-Core (LGA1700)",
     {"socket": "LGA1700", "cores": 10, "threads": 16, "tdp_w": 148, "igpu": False, "gaming_score": 68, "multi_score": 40},
     [("store-a", "c3", 139, True, None)]),
    ("gpu", "TestBrand", "Test Graphics Card 8GB",
     {"chip": "Test Chip 8", "vram_gb": 8, "tdp_w": 145, "score": 28, "chip_maker": "nvidia"},
     [("store-a", "g1", 469, True, None), ("store-b", "g1b", 479, False, None)]),
    ("gpu", "TestBrand", "Test Graphics Card 16GB",
     {"chip": "Test Chip 16", "vram_gb": 16, "tdp_w": 304, "score": 55, "chip_maker": "amd"},
     [("store-a", "g2", 899, True, 999)]),
    ("motherboard", "TestBrand", "Test Motherboard AM5 DDR5",
     {"socket": "AM5", "chipset": "B650", "memory_type": "DDR5", "form_factor": "Micro-ATX", "wifi": True},
     [("store-a", "m1", 129, True, None)]),
    ("motherboard", "TestBrand", "Test Motherboard LGA1700 DDR4",
     {"socket": "LGA1700", "chipset": "B760", "memory_type": "DDR4", "form_factor": "Micro-ATX", "wifi": False},
     [("store-a", "m2", 99, True, None)]),
    ("ram", "TestBrand", "Test Memory 32GB (2x16GB) DDR5-6000",
     {"memory_type": "DDR5", "capacity_gb": 32, "modules": 2, "speed_mhz": 6000},
     [("store-a", "r1", 189, True, None)]),
    ("ram", "TestBrand", "Test Memory 16GB (2x8GB) DDR4-3200",
     {"memory_type": "DDR4", "capacity_gb": 16, "modules": 2, "speed_mhz": 3200},
     [("store-a", "r2", 79, True, None)]),
    ("storage", "TestBrand", "Test NVMe SSD 1TB",
     {"storage_type": "NVMe SSD", "capacity_gb": 1000},
     [("store-a", "s1", 89, True, None), ("store-b", "s1b", 85, True, None)]),
    ("psu", "TestBrand", "Test Power Supply 750W",
     {"wattage": 750, "efficiency": "80+ Gold", "modular": "Full", "form_factor": "ATX"},
     [("store-a", "p1", 99, True, None)]),
    ("case", "TestBrand", "Test Mid-Tower Case",
     {"form_factor": "Mid Tower", "supports": ["ATX", "Micro-ATX", "Mini-ITX"]},
     [("store-a", "k1", 85, True, None)]),
    ("cooler", "TestBrand", "Test CPU Air Cooler",
     {"cooler_type": "Air", "tdp_rating_w": 220},
     [("store-a", "f1", 29, True, None)]),
]


def add_catalog(db, catalog=CATALOG):
    """Insert stores, products, offers and one price-history point per offer."""
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
                url=f"https://example.com/?sku={sku}", title=name, price=Decimal(price), in_stock=in_stock,
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
