"""Back-office API: look up orders, change product prices, list top customers by spend.
Staff only. Order reads go through the shared repo; price edits write products directly."""
from sqlalchemy import text, update

from libs.shopdb.models import Product
from libs.shopdb.orders_repo import get_order


def order_detail(session, order_id):
    return get_order(session, order_id)


def set_price(session, product_id, cents):
    session.execute(update(Product).where(Product.product_id == product_id).values(price_cents=cents))
    session.commit()


def top_customers(session, limit=20):
    sql = text("SELECT customer_id, email, lifetime_cents FROM v_customer_ltv ORDER BY lifetime_cents DESC LIMIT :n")
    return session.execute(sql, {"n": limit}).all()
