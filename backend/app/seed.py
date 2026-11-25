"""Filling the database: the test catalog, the admin account and optional demo users.

The catalog (app/data/test_catalog.json) is HAND-WRITTEN TEST DATA: made-up stores, parts,
prices and price history, not copied from any real store. It is loaded once into an empty
database by `python -m app.cli init`, so the website has something to show the moment it starts.
Edit that file to change the data, then reset the database (docker compose down -v).
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Listing, Offer, PriceHistory, Product, Store, User
from app.security import hash_password
from app.services.catalog import refresh_products

log = logging.getLogger(__name__)
CATALOG_PATH = Path(__file__).parent / "data" / "test_catalog.json"


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


def _money(value) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def import_catalog(db: Session, path: Path = CATALOG_PATH) -> dict:
    """Load stores, products, offers and price history from the JSON file into an EMPTY catalog.
    Does nothing when products already exist, so it is safe to run on every start.

    In the file every offer has a `history` list (oldest first, `days_ago` counted back from now).
    The LAST entry is the offer's current price and stock; the entry before it gives the previous
    price. An optional `old_price` is the store's own "was" price (a store sale)."""
    if db.scalar(select(func.count(Product.id))):
        return {"skipped": "catalog is not empty"}
    data = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(UTC)

    stores: dict[str, Store] = {}
    for s in data["stores"]:
        stores[s["slug"]] = Store(
            slug=s["slug"], name=s["name"], base_url=s["base_url"], color=s.get("color"), prices_updated_at=now
        )
    db.add_all(stores.values())
    db.flush()

    n_offers = n_points = 0
    product_ids: set[int] = set()
    for p in data["products"]:
        product = Product(
            category=p["category"], brand=p.get("brand"), name=p["name"], specs=p.get("specs", {}),
            image_url=p.get("image_url"),
        )
        db.add(product)
        db.flush()
        product_ids.add(product.id)

        lowest: Decimal | None = None  # lowest in-stock price ever recorded for this product
        for o in p["offers"]:
            store = stores.get(o["store"])
            if store is None:
                raise ValueError(f"{p['name']}: offer for unknown store {o['store']!r}")
            if not o.get("history"):
                raise ValueError(f"{p['name']} / {o['store']}: an offer needs at least one history entry")
            points = sorted(o["history"], key=lambda h: -h["days_ago"])  # oldest first
            times = [now - timedelta(days=h["days_ago"]) for h in points]
            prices = [_money(h.get("price")) for h in points]
            stock = [bool(h.get("in_stock", True)) for h in points]

            # when did the current price start, and what was the price before it?
            changed_at, previous = times[0], None
            for i in range(1, len(points)):
                if prices[i] != prices[i - 1]:
                    changed_at, previous = times[i], prices[i - 1]

            offer = Offer(
                product_id=product.id, store_id=store.id, store_sku=o["sku"],
                url=o.get("url") or f"{store.base_url}/?sku={o['sku']}", title=o.get("title", p["name"]),
                category=p["category"], price=prices[-1], old_price=_money(o.get("old_price")),
                previous_price=previous, price_changed_at=changed_at, in_stock=stock[-1], is_active=True,
                first_seen_at=times[0], last_seen_at=now,
            )
            db.add(offer)
            db.flush()
            db.add_all(
                PriceHistory(offer_id=offer.id, price=price, in_stock=in_stock, recorded_at=at)
                for price, in_stock, at in zip(prices, stock, times, strict=True)
            )
            n_offers += 1
            n_points += len(points)
            in_stock_prices = [pr for pr, st in zip(prices, stock, strict=True) if st and pr is not None]
            if in_stock_prices:
                lowest = min(in_stock_prices + ([lowest] if lowest is not None else []))
        product.lowest_price_ever = lowest

    db.flush()
    refresh_products(db, product_ids)  # best price, best store, stock, offer count
    db.flush()
    return {"stores": len(stores), "products": len(product_ids), "offers": n_offers, "price_points": n_points}


DEMO_PASSWORD = "demo12345"
DEMO_USERS = [
    ("sami", "Sami H.", "Amman", "Upgrading my PC and selling my old parts. Everything tested, original boxes.", [
        ("Used Test Graphics Card 8GB - works great", "gpu", "good", 190, "Test Chip 8",
         "Used for 2 years, never overclocked. Runs cool and quiet. Original box included."),
        ("Test Memory 16GB (2x8GB) DDR4-3200 kit", "ram", "good", 25, None, "Two sticks, tested with XMP at 3200 MHz."),
    ]),
    ("lina", "Lina K.", "Irbid", "I sell the parts I replace.", [
        ("Complete test PC: 6-core CPU, 8GB graphics card, 1TB NVMe", "pc", "good", 520, None,
         "Complete tower, Windows installed, plays recent games at 1080p. Can show it running before you buy."),
        ("Test NVMe SSD 1TB", "storage", "like_new", 45, None, "95% health, moved to a bigger drive."),
    ]),
    ("omar", "Omar N.", "Zarqa", "PC builder and tinkerer.", [
        ("Test Graphics Card 16GB - like new, with invoice", "gpu", "like_new", 520, "Test Chip 16",
         "Bought from a local store, invoice included. Selling because I upgraded."),
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
