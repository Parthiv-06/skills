"""Orders repository: the only code that creates orders or records payments.
Callers own the transaction: nothing here commits."""
from libs.shopdb.models import Order, OrderLine, Payment


def create_order(session, customer_id, address_id, items):
    order = Order(customer_id=customer_id, shipping_address_id=address_id, status="new")
    session.add(order)
    session.flush()
    for n, (product_id, qty) in enumerate(items, 1):
        session.add(OrderLine(order_id=order.order_id, line_no=n, product_id=product_id, quantity=qty))
    return order


def get_order(session, order_id):
    return session.get(Order, order_id)


def mark_paid(session, order_id, amount_cents):
    order = session.get(Order, order_id)
    order.status = "paid"
    session.add(Payment(order_id=order_id, amount_cents=amount_cents))
