# Partify 🇯🇴 — PC part price comparison for Jordan

Partify compares PC-part prices across three Jordanian stores, shows the price history of every
part, lets users track parts with a target price, plan a compatible build, and sell their own
used parts.

This version is a classic **three-tier web application**: a React **front-end**, a FastAPI
**back-end** and a PostgreSQL **database**. Every page reads from and writes to the database
through the back-end's REST API. There are no price scrapers, background jobs or AI chat.

![Home page](docs/screenshots/home.png)

| | |
|---|---|
| ![Product page](docs/screenshots/product.png) | ![PC builder](docs/screenshots/builder.png) |
| ![Marketplace listing](docs/screenshots/listing.png) | ![Home page in dark mode](docs/screenshots/home-dark.png) |

## Features

- **Price comparison** – one page per part with every store's price, stock status and a link to buy.
  2,300+ parts in 8 categories (CPU, GPU, motherboard, RAM, storage, PSU, case, cooler), with filters
  (socket, GPU chip, VRAM, DDR type, wattage…), sorting and search.
- **Price history** – every recorded price is stored; each product shows a per-store chart (and a table view).
- **Deals** – the biggest discounts on in-stock parts (the stores' own sale prices).
- **Wishlist & price alerts** – track a part with an optional target price. When the best in-stock
  price is at or below the target, the user gets an in-app notification (the bell icon).
- **PC builder** – pick parts with live compatibility checks (socket, DDR4/DDR5, case size, PSU
  wattage, graphics output) or auto-build for a budget and use case.
- **Marketplace & profiles** – users list items for sale with photos, condition, city and price;
  every user has a public profile with their listings. Linked catalog products show how much a buyer
  saves versus buying new.
- **Accounts** – register, log in (JWT), edit your profile and photo, change your password.
- **Admin dashboard** – what is in the database: products, offers, price points, users, listings, per store.
- **Dark mode** – follows your system setting; the sun/moon button in the header switches it and
  remembers your choice.

## Architecture

```mermaid
flowchart LR
    U["Browser<br/>React + Tailwind"] -->|"web pages"| N["nginx<br/>(front-end container)"]
    U -->|"/api, /uploads"| N
    N -->|"/api, /uploads"| A["FastAPI<br/>(back-end)"]
    A -->|"SQL via SQLAlchemy"| P[("PostgreSQL<br/>(database)")]
```

| Tier | Technology | Folder |
|---|---|---|
| Front-end | React 19, React Router, Tailwind CSS 4, Recharts, Vite; served by nginx | `frontend/` |
| Back-end | FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, JWT auth (Argon2 password hashing), Pillow for uploads | `backend/` |
| Database | PostgreSQL 16 (JSONB for part specs) | `docker-compose.yml` (`db` service) |

**How one page works – opening a product:**
1. React Router shows `ProductPage.jsx`, which calls `GET /api/products/123` and `GET /api/products/123/history`.
2. nginx forwards every `/api/...` request to FastAPI.
3. FastAPI (`backend/app/routers/catalog.py`) queries PostgreSQL with SQLAlchemy and returns JSON.
4. React draws the price table and the price chart from that JSON.

Writes work the same way in the other direction: for example "Track price" sends
`POST /api/wishlist`, and the back-end inserts a row into the `wishlist_items` table.

## Quick start (Docker)

You only need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
cp .env.example .env          # set SECRET_KEY and ADMIN_PASSWORD at least
docker compose up --build
```

| URL | What |
|---|---|
| http://localhost:8080 | the website |
| http://localhost:8000/docs | interactive API documentation (try every endpoint) |
| localhost:5433 | the database, for pgAdmin / DBeaver (user, password and database: `partify`) |

On first start the back-end creates the tables and fills the empty database with the product
catalog (3 stores, 2,387 products, 3,015 store offers), so the site works immediately – even offline.
The data stays in a Docker volume, so it survives restarts. To start again from an empty database:
`docker compose down -v`.

Admin account: the `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` (the admin page is `/admin`).
Demo accounts (when `SEED_DEMO_USERS=true`): `sami`, `lina`, `omar` – password `demo12345`.
Turn this off on any public server.

## Local development (without Docker)

You need Python 3.12+, Node 20+ and PostgreSQL 16 (or just `docker compose up db` for the database).

```bash
# 1. database (once)
sudo -u postgres psql -c "CREATE USER partify WITH PASSWORD 'partify' CREATEDB;"
sudo -u postgres psql -c "CREATE DATABASE partify OWNER partify;"
```

If you use `docker compose up db` instead, set `DATABASE_URL=postgresql+psycopg://partify:partify@localhost:5433/partify`
in `backend/.env` (the container's database is on port 5433).

```bash
# 2. back-end
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example .env                               # defaults point at localhost
python -m app.cli init                                # create tables + load the catalog
uvicorn app.main:app --reload                         # http://localhost:8000/docs
```

```bash
# 3. front-end (second terminal)
cd frontend
npm install
npm run dev                                           # http://localhost:5173
```

Useful commands (run in `backend/`):

| Command | What it does |
|---|---|
| `python -m app.cli init` | run the database migrations and fill an empty database (safe to run again) |
| `python -m app.cli create-admin --email you@x.com --password ...` | make an admin |
| `alembic revision --autogenerate -m "..."` | new migration after changing `models.py` |

## The database

```mermaid
erDiagram
    STORES ||--o{ OFFERS : "lists"
    PRODUCTS ||--o{ OFFERS : "is sold as"
    OFFERS ||--o{ PRICE_HISTORY : "records"
    STORES |o--o{ PRODUCTS : "has best price of"
    USERS ||--o{ WISHLIST_ITEMS : "tracks"
    PRODUCTS ||--o{ WISHLIST_ITEMS : "is tracked in"
    USERS ||--o{ NOTIFICATIONS : "receives"
    PRODUCTS |o--o{ NOTIFICATIONS : "is about"
    USERS ||--o{ LISTINGS : "sells"
    PRODUCTS |o--o{ LISTINGS : "is compared with"
    LISTINGS ||--o{ LISTING_IMAGES : "has"

    STORES {
        int id PK
        string slug UK
        string name
        string base_url
        datetime prices_updated_at
    }
    PRODUCTS {
        int id PK
        string category
        string brand
        string name
        jsonb specs
        numeric best_price
        int best_store_id FK
        bool in_stock
        int offer_count
    }
    OFFERS {
        int id PK
        int product_id FK
        int store_id FK
        string url
        numeric price
        numeric old_price
        bool in_stock
    }
    PRICE_HISTORY {
        bigint id PK
        int offer_id FK
        numeric price
        bool in_stock
        datetime recorded_at
    }
    USERS {
        int id PK
        string email UK
        string username UK
        string password_hash
        bool is_admin
    }
    WISHLIST_ITEMS {
        int id PK
        int user_id FK
        int product_id FK
        numeric target_price
    }
    NOTIFICATIONS {
        int id PK
        int user_id FK
        int product_id FK
        string title
        bool is_read
    }
    LISTINGS {
        int id PK
        int seller_id FK
        int product_id FK
        string title
        numeric price
        string status
    }
    LISTING_IMAGES {
        int id PK
        int listing_id FK
        string url
    }
```

| Table | What one row is |
|---|---|
| `stores` | one of the three stores (iGeek Megastore, CompuJordan, Oriental Store) |
| `products` | a part, e.g. "AMD Ryzen 7 7800X3D", with its specs (JSONB) and its best price across stores |
| `offers` | one store's listing of a product: price, stock, link |
| `price_history` | a recorded price/stock of an offer at a moment in time (the chart) |
| `users` | an account (password stored as an Argon2 hash) |
| `wishlist_items` | a product a user tracks, with an optional target price |
| `notifications` | in-app notifications (target price reached, …) |
| `listings`, `listing_images` | marketplace ads and their photos |

The table structure is defined in `backend/app/models.py` and created by the Alembic migration in
`backend/alembic/versions/`. The catalog data comes from `backend/app/data/catalog.json.gz`: real
prices from the three stores' public product pages, collected on 20 Nov 2026. Prices in this version
do not change by themselves; the site shows when each store's prices were last updated.

Looking inside the database:

```bash
docker compose exec db psql -U partify -d partify
```

```sql
\dt
SELECT name, best_price FROM products ORDER BY best_price DESC LIMIT 5;
\q
```

Making a backup: `docker compose exec -T db pg_dump -U partify partify > backup.sql`

## API overview
Full interactive docs at `/docs` (use **Authorize** to log in).

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Catalog | `GET /api/categories`, `GET /api/products` (filters `q`, `category`, `brand`, `store`, `min_price`, `max_price`, `in_stock`, `spec_<key>`, `sort`), `GET /api/products/facets`, `GET /api/products/{id}`, `GET /api/products/{id}/history`, `GET /api/products/{id}/similar`, `GET /api/deals`, `GET /api/stores`, `GET /api/meta` |
| Wishlist | `GET/POST /api/wishlist`, `PATCH/DELETE /api/wishlist/{id}` |
| Notifications | `GET /api/notifications`, `GET /api/notifications/unread-count`, `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all` |
| Builder | `POST /api/builds/check`, `POST /api/builds/recommend` |
| Marketplace | `GET/POST /api/listings`, `GET/PATCH/DELETE /api/listings/{id}`, `POST /api/listings/{id}/images`, `DELETE /api/listings/{id}/images/{image_id}` |
| Users | `GET /api/users/{username}`, `PATCH /api/users/me`, `POST /api/users/me/avatar`, `POST /api/users/me/password` |
| Admin | `GET /api/admin/stats` |

## How it works

### Best price
Each product can be sold by several stores (one `offers` row per store). The product's best price
is the cheapest **in-stock** offer; if no store has it in stock, the cheapest listed offer is shown
as the last known price. These values are stored on the product (`best_price`, `best_store_id`,
`in_stock`, `offer_count`) by `refresh_products()` in `app/services/catalog.py`, so sorting and
filtering thousands of products is one fast query.

### Price alerts
`app/services/alerts.py` – when a user tracks a part (or edits the alert), the back-end compares the
target with the best in-stock price in the database. A target-price alert fires once when the price
is at or below the target, then re-arms only when the price goes back above it, so nobody gets spammed.

### Build recommender & compatibility
`app/services/recommender.py` splits the budget by use case (a gaming PC spends ~40% on the GPU),
picks the best performance per JOD in dependency order (GPU → CPU → board with the same socket →
RAM of the board's DDR type → storage → PSU sized for CPU+GPU → case that fits the board → cooler for
the CPU's heat), then balances: over budget → cheapen the supporting parts first, then the less
important big part; money left → upgrade the part that matters most.
`app/services/compatibility.py` holds the rules shared by the builder and the recommender.

### Uploads
Marketplace photos and avatars are checked and re-encoded with Pillow (only real images are accepted,
GPS data is removed), saved under `uploads/` and served at `/uploads/...`.

## Tests

```bash
cd backend
createdb -U partify partify_test       # once (or set TEST_DATABASE_URL)
pytest                                 # 10 tests
```

They cover the HTTP API (auth, catalog and filters, best price across stores, deals, wishlist and
notifications, marketplace with image uploads, profile and password, builder, admin) and loading the
real catalog file into PostgreSQL.

## Project structure

```
backend/
  app/
    main.py              FastAPI app        models.py      database tables
    config.py            settings (.env)    schemas.py     API request/response shapes
    database.py          DB connection      security.py    passwords + JWT login
    cli.py               command line       seed.py        loads the catalog, admin, demo data
    routers/             HTTP endpoints (auth, users, catalog, wishlist, notifications, marketplace, builds, admin)
    services/            catalog queries, price alerts, recommender, compatibility, uploads
    data/                catalog.json.gz (stores, products, offers, price history)
  alembic/               database migrations
  tests/                 pytest suite
frontend/
  src/pages/             Home, Browse, ProductPage, Builder, Wishlist, Notifications,
                         Marketplace, ListingPage, ListingForm, Profile, Settings, Auth, Admin
  src/components/        Layout, ProductCard, PriceHistoryChart, WishlistButton, ui
  src/lib/               api client, auth, formatting, builder state, theme
docker-compose.yml       db (PostgreSQL), api (FastAPI), frontend (nginx + React)
```
