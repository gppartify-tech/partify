"""HTTP API tests (auth, catalog, wishlist, notifications, marketplace, builder, admin, seed data)."""
import io
import json

from PIL import Image

from tests.conftest import register


def test_register_login_me(client):
    headers = register(client, "layla")
    me = client.get("/api/auth/me", headers=headers).json()
    assert me["username"] == "layla" and me["is_admin"] is False
    assert client.post("/api/auth/login", json={"login": "LAYLA", "password": "supersecret1"}).status_code == 200
    assert client.post("/api/auth/login", json={"login": "layla", "password": "wrong"}).status_code == 401
    dup = client.post("/api/auth/register", json={"email": "layla@example.com", "username": "other", "password": "supersecret1"})
    assert dup.status_code == 409
    assert client.get("/api/auth/me").status_code == 401


def test_catalog_endpoints(client, catalog):
    cats = {c["slug"]: c for c in client.get("/api/categories").json()}
    assert cats["cpu"]["product_count"] == 3 and cats["cpu"]["min_price"] == 139
    page = client.get("/api/products", params={"category": "cpu", "sort": "price_asc"}).json()
    assert [p["best_price"] for p in page["items"]] == [139, 145, 299]
    search = client.get("/api/products", params={"q": "8-core plus"}).json()
    assert search["total"] == 1
    am5 = client.get("/api/products", params={"category": "cpu", "spec_socket": "AM5"}).json()
    assert am5["total"] == 2
    facets = client.get("/api/products/facets", params={"category": "cpu"}).json()
    assert {f["value"] for f in facets["specs"]["socket"]} == {"AM5", "LGA1700"}
    pid = search["items"][0]["id"]
    detail = client.get(f"/api/products/{pid}").json()
    assert detail["offers"][0]["store"]["slug"] == "store-a"
    history = client.get(f"/api/products/{pid}/history").json()
    assert history["series"][0]["points"]
    stores = client.get("/api/stores").json()
    assert [s["slug"] for s in stores] == ["store-a", "store-b", "store-c"]
    assert stores[0]["prices_updated_at"] is not None


def test_best_price_across_stores(client, catalog):
    # the 6-core CPU is sold by two stores: Store B (145) is cheaper than Store A (149)
    cpu = client.get("/api/products", params={"q": "6-core (am5)"}).json()["items"][0]
    assert cpu["offer_count"] == 2 and cpu["best_price"] == 145 and cpu["best_store"]["slug"] == "store-b"
    # the out-of-stock 479 offer is ignored for the 8GB graphics card's best price
    gpu = client.get("/api/products", params={"q": "graphics card 8gb"}).json()["items"][0]
    assert gpu["best_price"] == 469 and gpu["in_stock"] is True


def test_deals_show_store_sales(client, catalog):
    deals = client.get("/api/deals").json()
    assert [d["product"]["name"] for d in deals] == ["Test Graphics Card 16GB"]
    assert deals[0]["kind"] == "store_sale" and deals[0]["reference_price"] == 999 and deals[0]["drop_pct"] == 10.0


def test_wishlist_target_notification_flow(client, catalog):
    headers = register(client, "omar")
    gpu = client.get("/api/products", params={"q": "graphics card 8gb"}).json()["items"][0]
    # target above the current price -> already reached -> immediate notification
    resp = client.post("/api/wishlist", json={"product_id": gpu["id"], "target_price": 500}, headers=headers)
    assert resp.status_code == 201 and resp.json()["target_reached"] is True
    assert client.get("/api/notifications/unread-count", headers=headers).json()["unread"] == 1
    note = client.get("/api/notifications", headers=headers).json()[0]
    assert note["kind"] == "target_reached" and note["link"] == f"/product/{gpu['id']}"
    item_id = resp.json()["id"]
    patched = client.patch(f"/api/wishlist/{item_id}", json={"target_price": 300}, headers=headers).json()
    assert patched["target_price"] == 300 and patched["target_reached"] is False
    client.post("/api/notifications/read-all", headers=headers)
    assert client.get("/api/notifications/unread-count", headers=headers).json()["unread"] == 0
    assert client.delete(f"/api/wishlist/{item_id}", headers=headers).status_code == 204
    assert client.get("/api/wishlist", headers=headers).json() == []


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "purple").save(buf, "PNG")
    return buf.getvalue()


def test_marketplace_listing_lifecycle(client, catalog):
    seller = register(client, "hamza")
    buyer = register(client, "noor")
    body = {"title": "Used graphics card 8GB", "description": "Works great", "category": "gpu",
            "condition": "good", "price": 160, "city": "Irbid"}
    created = client.post("/api/listings", json=body, headers=seller)
    assert created.status_code == 201
    lid = created.json()["id"]

    up = client.post(f"/api/listings/{lid}/images", files={"file": ("a.png", _png(), "image/png")}, headers=seller)
    assert up.status_code == 201 and up.json()["images"][0]["url"].endswith(".webp")
    bad = client.post(f"/api/listings/{lid}/images", files={"file": ("x.png", b"not an image", "image/png")}, headers=seller)
    assert bad.status_code == 400

    anon = client.get(f"/api/listings/{lid}").json()
    assert anon["seller_contact"] is None  # contact only for logged-in users
    assert client.get(f"/api/listings/{lid}", headers=buyer).json()["seller_contact"]["email"] == "hamza@example.com"

    assert client.patch(f"/api/listings/{lid}", json={"price": 1}, headers=buyer).status_code == 403
    assert client.patch(f"/api/listings/{lid}", json={"status": "sold"}, headers=seller).json()["status"] == "sold"
    assert client.get("/api/listings").json()["total"] == 0  # sold ads leave the main list
    profile = client.get("/api/users/hamza").json()
    assert profile["sold_listings"] == 1
    assert client.post("/api/listings", json={**body, "city": "Paris"}, headers=seller).status_code == 422


def test_profile_settings_and_password(client):
    headers = register(client, "rana")
    me = client.patch("/api/users/me", json={"display_name": "Rana A.", "city": "Aqaba", "bio": "hi"}, headers=headers).json()
    assert (me["display_name"], me["city"], me["bio"]) == ("Rana A.", "Aqaba", "hi")
    assert client.patch("/api/users/me", json={"city": "Paris"}, headers=headers).status_code == 422
    wrong = client.post("/api/users/me/password", json={"current_password": "nope", "new_password": "newsecret1"}, headers=headers)
    assert wrong.status_code == 400
    ok = client.post("/api/users/me/password", json={"current_password": "supersecret1", "new_password": "newsecret1"}, headers=headers)
    assert ok.status_code == 204
    assert client.post("/api/auth/login", json={"login": "rana", "password": "newsecret1"}).status_code == 200


def test_builder_check_and_recommend(client, catalog):
    items = client.get("/api/products", params={"page_size": 60}).json()["items"]
    intel = next(p["id"] for p in items if p["category"] == "cpu" and "LGA1700" in p["name"])
    am5_board = next(p["id"] for p in items if p["category"] == "motherboard" and "AM5" in p["name"])
    report = client.post("/api/builds/check", json={"product_ids": [intel, am5_board]}).json()
    assert report["compatible"] is False
    assert any("socket" in i["message"] for i in report["issues"])

    rec = client.post("/api/builds/recommend", json={"budget": 2000, "use_case": "gaming"}).json()
    cats = {p["category"] for p in rec["parts"]}
    assert {"cpu", "gpu", "motherboard", "ram", "storage", "psu", "case", "cooler"} <= cats
    assert rec["compatible"] is True and rec["total_price"] <= 2000


def test_admin_stats(client, catalog):
    from app.database import SessionLocal
    from app.seed import create_admin

    headers = register(client, "regular")
    assert client.get("/api/admin/stats", headers=headers).status_code == 403
    with SessionLocal() as db:
        create_admin(db, "boss@example.com", "supersecret1", "boss")
        db.commit()
    token = client.post("/api/auth/login", json={"login": "boss", "password": "supersecret1"}).json()["access_token"]
    stats = client.get("/api/admin/stats", headers={"Authorization": f"Bearer {token}"}).json()
    assert stats["products"] == 13 and stats["offers"] == 16 and stats["users"] == 2
    assert stats["stores"][0]["store"]["slug"] == "store-a" and stats["stores"][0]["active_offers"] == 13


# ----------------------------------------------------------------------------- the bundled demo data
def test_seed_loads_the_test_catalog(client, db):
    """app/data/test_catalog.json loads into an empty database (and only once), and everything in it
    is clearly test data: no pictures, no real store links."""
    from app.seed import CATALOG_PATH, import_catalog

    raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    offers = [o for p in raw["products"] for o in p["offers"]]
    expected = {
        "stores": len(raw["stores"]), "products": len(raw["products"]), "offers": len(offers),
        "price_points": sum(len(o["history"]) for o in offers),
    }
    assert import_catalog(db) == expected
    db.commit()
    assert import_catalog(db) == {"skipped": "catalog is not empty"}

    stores = client.get("/api/stores").json()
    assert [s["name"] for s in stores] == [s["name"] for s in raw["stores"]]
    assert all(s["name"].startswith("Test Store") for s in stores)
    cats = {c["slug"]: c for c in client.get("/api/categories").json()}
    assert all(c["product_count"] >= 1 for c in cats.values())  # every category page has something to show
    products = client.get("/api/products", params={"page_size": 60}).json()["items"]
    assert len(products) == expected["products"]
    assert all(p["name"].startswith("Test ") and p["image_url"] is None for p in products)
    first = client.get(f"/api/products/{products[0]['id']}").json()
    assert all(o["url"].startswith("https://example.com") for o in first["offers"])
    assert client.get("/api/deals").json()  # the home page's "Best deals" has something to show


def test_seed_data_supports_the_home_page_build_presets(client, db):
    """The four one-click presets on the home page all give a compatible build inside the budget."""
    from app.seed import import_catalog

    import_catalog(db)
    db.commit()
    for budget, use, res in [(900, "gaming", "1080p"), (1500, "gaming", "1440p"), (2000, "creator", None), (550, "office", None)]:
        rec = client.post("/api/builds/recommend", json={"budget": budget, "use_case": use, "resolution": res}).json()
        assert rec["compatible"] is True, (budget, use, rec["issues"])
        assert rec["total_price"] <= budget, (budget, use, rec["total_price"])
        assert len(rec["parts"]) >= (7 if use == "office" else 8)


def test_seed_demo_users_link_listings_to_catalog_products(client, db):
    from app.seed import DEMO_PASSWORD, import_catalog, seed_demo_users

    import_catalog(db)
    report = seed_demo_users(db)
    db.commit()
    assert report["users"] == 3 and report["listings"] == 5
    assert seed_demo_users(db) == {"skipped": "marketplace is not empty"}
    listings = client.get("/api/listings").json()["items"]
    assert len(listings) == 5
    linked = [client.get(f"/api/listings/{l['id']}").json() for l in listings]
    assert sum(1 for l in linked if l["product"]) == 2  # the two graphics-card ads show "compare with new"
    assert client.post("/api/auth/login", json={"login": "sami", "password": DEMO_PASSWORD}).status_code == 200
