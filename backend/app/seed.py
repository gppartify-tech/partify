"""Filling the database: the product catalog, the admin account and optional demo data.

The catalog (app/data/catalog.json.gz) holds the stores, products, store offers and price
history - real prices from iGeek Megastore, CompuJordan and Oriental Store collected on
20 Nov 2026. It is loaded once into an empty database by `python -m app.cli init`, so the
website has data the moment it starts, with no internet connection needed.
"""
from __future__ import annotations

import gzip
import json
import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Listing, Offer, PriceHistory, Product, Store, User
from app.security import hash_password
from app.services.catalog import refresh_products

log = logging.getLogger(__name__)
CATALOG_PATH = Path(__file__).parent / "data" / "catalog.json.gz"


def create_admin(db: Session, email: str, password: str, username: str = "admin") -> User:
    user = db.scalar(select(User).where((User.email == email.lower()) | (User.username == username)))
    if user is None:
        user = User(email=email.lower(), username=username, display_name="Administrator",
                    password_hash=hash_password(password), is_admin=True)
        db.add(user)
    else:
        user.is_admin = True
    db.flush()
    return user


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _dec(value: str | None) -> Decimal | None:
    return Decimal(value) if value else None


def import_catalog(db: Session, path: Path = CATALOG_PATH) -> dict:
    """Load stores, products, offers and price history into an EMPTY catalog.
    Does nothing when products already exist, so it is safe to run on every start."""
    if db.scalar(select(func.count(Product.id))):
        return {"skipped": "catalog is not empty"}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)

    stores = {s.slug: s for s in db.scalars(select(Store))}
    for s in data["stores"]:
        store = stores.get(s["slug"])
        if store is None:
            store = stores[s["slug"]] = Store(slug=s["slug"])
            db.add(store)
        store.name, store.base_url, store.color = s["name"], s["base_url"], s["color"]
        store.prices_updated_at = _dt(s["prices_updated_at"])
    db.flush()

    # The ids in the file only link its rows together; the database assigns its own ids.
    products = {
        p["id"]: Product(
            category=p["category"], brand=p["brand"], name=p["name"], specs=p["specs"],
            image_url=p["image_url"], lowest_price_ever=_dec(p["lowest_price_ever"]),
            created_at=_dt(p["created_at"]),
        )
        for p in data["products"]
    }
    db.add_all(products.values())
    db.flush()  # one batched INSERT; afterwards every product has its database id

    offers = {
        o["id"]: Offer(
            product_id=products[o["product_id"]].id, store_id=stores[o["store"]].id,
            store_sku=o["store_sku"], url=o["url"], title=o["title"], image_url=o["image_url"],
            category=o["category"], price=_dec(o["price"]), old_price=_dec(o["old_price"]),
            previous_price=_dec(o["previous_price"]), price_changed_at=_dt(o["price_changed_at"]),
            in_stock=o["in_stock"], is_active=o["is_active"],
            first_seen_at=_dt(o["first_seen_at"]), last_seen_at=_dt(o["last_seen_at"]),
        )
        for o in data["offers"]
    }
    db.add_all(offers.values())
    db.flush()

    db.add_all(
        PriceHistory(offer_id=offers[offer_id].id, price=_dec(price), in_stock=in_stock, recorded_at=_dt(at))
        for offer_id, price, in_stock, at in data["history"]
    )
    db.flush()
    refresh_products(db, {p.id for p in products.values()})  # best price, best store, stock, offer count
    db.flush()
    return {"stores": len(data["stores"]), "products": len(products), "offers": len(offers),
            "price_points": len(data["history"])}


DEMO_PASSWORD = "demo12345"
DEMO_USERS = [
    ("sami", "Sami H.", "Amman", "Upgrading to AM5, selling my old parts. Everything tested, original boxes.", [
        ("MSI RTX 3060 Ventus 2X 12GB", "gpu", "good", 165, "rtx 3060", "Used for 2 years for gaming only, never mined. Runs cool, no coil whine. Original box included."),
        ("Ryzen 5 5600 + B550M motherboard combo", "other", "good", 120, None, "AMD Ryzen 5 5600 with an MSI B550M PRO-VDH board. BIOS updated, perfect for a budget AM4 build."),
        ("Corsair Vengeance LPX 16GB (2x8) DDR4 3200", "ram", "good", 25, None, "Two sticks, XMP stable at 3200 MHz."),
    ]),
    ("lina", "Lina K.", "Irbid", "Content creator - I sell the parts I replace.", [
        ("Gaming PC: i5-12400F + RTX 3060 Ti, 16GB RAM, 1TB NVMe", "pc", "good", 520, None, "Complete tower, Windows activated, plays everything at 1080p high. Can show it running before you buy."),
        ("Samsung 970 EVO Plus 1TB NVMe", "storage", "like_new", 45, None, "95% health, moved to a 2TB drive."),
    ]),
    ("omar", "Omar N.", "Zarqa", "PC builder and tinkerer.", [
        ("ASUS TUF RTX 4070 Super OC 12GB - warranty until 2027", "gpu", "like_new", 520, "rtx 4070 super", "Bought from a local store, invoice included. Selling because I moved to a 5080."),
        ("Cooler Master MWE 650 Bronze V2", "psu", "fair", 30, None, "Works fine, fan slightly louder than new."),
    ]),
]


def seed_demo_users(db: Session) -> dict:
    """Demo accounts with marketplace listings (for presentations). Never enable in production:
    the accounts share a public password."""
    if db.scalar(select(func.count(Listing.id))):
        return {"skipped": "marketplace is not empty"}
    created = 0
    for username, name, city, bio, listings in DEMO_USERS:
        user = db.scalar(select(User).where(User.username == username))
        if user is None:
            user = User(email=f"{username}@demo.partify.local", username=username, display_name=name,
                        city=city, bio=bio, password_hash=hash_password(DEMO_PASSWORD))
            db.add(user)
            db.flush()
        for title, category, condition, price, chip, description in listings:
            product_id = None
            if chip:  # link to the catalog so buyers can compare with the new price
                product_id = db.scalar(
                    select(Product.id).where(Product.category == category, Product.specs["chip"].astext.ilike(chip))
                    .order_by(Product.in_stock.desc(), Product.best_price).limit(1)
                )
            db.add(Listing(seller_id=user.id, title=title, description=description, category=category,
                           condition=condition, price=Decimal(price), city=city, product_id=product_id))
            created += 1
    db.flush()
    return {"users": len(DEMO_USERS), "listings": created, "password": DEMO_PASSWORD}


def seed(db: Session) -> dict:
    """Idempotent start-up seed: catalog, optional admin, optional demo data."""
    report: dict = {"catalog": import_catalog(db)}
    if settings.admin_email and settings.admin_password:
        create_admin(db, settings.admin_email, settings.admin_password, settings.admin_username)
        report["admin"] = settings.admin_email
    if settings.seed_demo_users:
        report["demo_users"] = seed_demo_users(db)
    return report
