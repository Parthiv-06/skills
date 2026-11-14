"""Checkout tests against a throwaway SQLite database seeded by raw SQL.
Seeding writes here are test-only and never run against shopdb."""


def test_pay(conn):
    conn.execute("INSERT INTO customers (customer_id, email) VALUES (1, 'a@b.c')")
    conn.execute("INSERT INTO orders (order_id, customer_id, status) VALUES (1, 1, 'new')")
    conn.execute("DELETE FROM payments")
