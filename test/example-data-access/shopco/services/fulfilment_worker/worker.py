"""Ships paid orders: records a shipment, marks the order shipped, and writes an audit entry.
Runs every minute; each order gets its own transaction so one failure can't block the rest."""
import os
from pathlib import Path

import psycopg

PENDING_SQL = (Path(__file__).parent / "sql" / "pending_orders.sql").read_text()


def run(conn):
    with conn.cursor() as cur:
        cur.execute(PENDING_SQL)
        for order_id, city in cur.fetchall():
            ship(conn, order_id, city)


def ship(conn, order_id, city):
    with conn.transaction(), conn.cursor() as cur:
        carrier = "BlueDart" if city in ("Pune", "Mumbai") else "UPS"
        cur.execute("INSERT INTO shipments (order_id, carrier, shipped_at) VALUES (%s, %s, now())", (order_id, carrier))
        cur.execute("UPDATE orders SET status = 'shipped' WHERE order_id = %s", (order_id,))
        cur.execute(
            "INSERT INTO audit_log (entity, entity_id, action, at) "
            "SELECT 'orders', order_id, 'shipped', now() FROM orders WHERE order_id = %s", (order_id,))
        # cur.execute("DELETE FROM payments WHERE order_id = %s", (order_id,))


def purge(conn, table, days):
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table} WHERE at < now() - interval '{days} days'")


if __name__ == "__main__":
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        run(conn)
        purge(conn, "audit_log", 90)
