"""Checkout: price a cart, place an order, and record the card payment.
All order writes go through libs.shopdb.orders_repo so an order and its lines commit together."""
from sqlalchemy import select

from libs.shopdb import orders_repo
from libs.shopdb.models import Address, Customer, Product


def price_cart(session, product_ids):
    rows = session.scalars(select(Product).where(Product.product_id.in_(product_ids))).all()
    return sum(p.price_cents for p in rows)


def place_order(session, customer_id, address_id, items):
    customer = session.get(Customer, customer_id)
    address = session.get(Address, address_id)
    order = orders_repo.create_order(session, customer.customer_id, address.address_id, items)
    session.commit()
    return order.order_id


def pay(session, order_id, amount_cents):
    orders_repo.mark_paid(session, order_id, amount_cents)
    session.commit()
