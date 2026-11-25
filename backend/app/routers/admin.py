"""Admin dashboard: database statistics (admins only)."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Listing, Offer, PriceHistory, Product, Store, User, WishlistItem
from app.schemas import AdminStatsOut, StoreStatsOut
from app.security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("/stats", response_model=AdminStatsOut)
def stats(db: Session = Depends(get_db)):
    def count(model) -> int:
        return db.scalar(select(func.count()).select_from(model)) or 0

    per_store = []
    for store in db.scalars(select(Store).order_by(Store.id)):
        active, in_stock = db.execute(
            select(func.count(Offer.id), func.count(Offer.id).filter(Offer.in_stock.is_(True)))
            .where(Offer.store_id == store.id, Offer.is_active.is_(True))
        ).one()
        per_store.append(StoreStatsOut(store=store, active_offers=active, in_stock_offers=in_stock))
    return AdminStatsOut(
        users=count(User), products=count(Product), offers=count(Offer), price_points=count(PriceHistory),
        wishlist_items=count(WishlistItem), listings=count(Listing), stores=per_store,
    )
