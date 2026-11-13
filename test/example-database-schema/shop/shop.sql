-- Online shop schema with declared foreign keys and a little sample data.
-- Test fixture: junction table, self-references, two FKs to one table, a 1:1, views on views.
PRAGMA foreign_keys = ON;

CREATE TABLE customers (
  customer_id INTEGER PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE addresses (
  address_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  line1 TEXT NOT NULL,
  city TEXT NOT NULL,
  country TEXT NOT NULL
);

CREATE TABLE categories (
  category_id INTEGER PRIMARY KEY,
  parent_category_id INTEGER REFERENCES categories(category_id),
  name TEXT NOT NULL
);

CREATE TABLE products (
  product_id INTEGER PRIMARY KEY,
  sku TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  category_id INTEGER NOT NULL REFERENCES categories(category_id),
  price_cents INTEGER NOT NULL
);

CREATE TABLE tags (
  tag_id INTEGER PRIMARY KEY,
  label TEXT NOT NULL UNIQUE
);

CREATE TABLE product_tags (
  product_id INTEGER NOT NULL REFERENCES products(product_id),
  tag_id INTEGER NOT NULL REFERENCES tags(tag_id),
  PRIMARY KEY (product_id, tag_id)
);

CREATE TABLE orders (
  order_id INTEGER PRIMARY KEY,
  customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
  billing_address_id INTEGER REFERENCES addresses(address_id),
  shipping_address_id INTEGER NOT NULL REFERENCES addresses(address_id),
  status TEXT NOT NULL,
  placed_at TEXT NOT NULL
);

CREATE TABLE order_items (
  order_id INTEGER NOT NULL REFERENCES orders(order_id),
  line_no INTEGER NOT NULL,
  product_id INTEGER NOT NULL REFERENCES products(product_id),
  quantity INTEGER NOT NULL,
  unit_price_cents INTEGER NOT NULL,
  PRIMARY KEY (order_id, line_no)
);

CREATE TABLE payments (
  order_id INTEGER PRIMARY KEY REFERENCES orders(order_id),
  amount_cents INTEGER NOT NULL,
  method TEXT NOT NULL,
  paid_at TEXT NOT NULL
);

CREATE TABLE employees (
  employee_id INTEGER PRIMARY KEY,
  manager_id INTEGER REFERENCES employees(employee_id),
  name TEXT NOT NULL
);

CREATE TABLE shipments (
  shipment_id INTEGER PRIMARY KEY,
  order_id INTEGER NOT NULL REFERENCES orders(order_id),
  handled_by INTEGER REFERENCES employees(employee_id),
  carrier TEXT NOT NULL,
  shipped_at TEXT
);

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY,
  entity TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  at TEXT NOT NULL
);

CREATE INDEX idx_orders_customer ON orders(customer_id);
CREATE INDEX idx_items_product ON order_items(product_id);

CREATE VIEW v_order_totals AS
SELECT o.order_id, o.customer_id, SUM(oi.quantity * oi.unit_price_cents) AS total_cents
FROM orders o
JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.customer_id;

CREATE VIEW v_customer_ltv AS
SELECT c.customer_id, c.email, COALESCE(SUM(t.total_cents), 0) AS lifetime_cents
FROM customers c
LEFT JOIN v_order_totals t ON t.customer_id = c.customer_id
GROUP BY c.customer_id, c.email;

INSERT INTO customers VALUES (1, 'ana@example.com', 'Ana', '2026-01-02'), (2, 'raj@example.com', 'Raj', '2026-02-11');
INSERT INTO addresses VALUES (1, 1, '1 Main St', 'Austin', 'US'), (2, 1, '9 Oak Ave', 'Austin', 'US'), (3, 2, '4 Ring Rd', 'Pune', 'IN');
INSERT INTO categories VALUES (1, NULL, 'Kitchen'), (2, 1, 'Knives');
INSERT INTO products VALUES (1, 'KN-01', 'Chef knife', 2, 5900), (2, 'PN-02', 'Pan', 1, 3400);
INSERT INTO tags VALUES (1, 'gift'), (2, 'bestseller');
INSERT INTO product_tags VALUES (1, 1), (1, 2), (2, 2);
INSERT INTO orders VALUES (1, 1, 1, 2, 'paid', '2026-10-01'), (2, 2, NULL, 3, 'shipped', '2026-10-03');
INSERT INTO order_items VALUES (1, 1, 1, 1, 5900), (1, 2, 2, 2, 3400), (2, 1, 2, 1, 3400);
INSERT INTO payments VALUES (1, 12700, 'card', '2026-10-01'), (2, 3400, 'upi', '2026-10-03');
INSERT INTO employees VALUES (1, NULL, 'Mia'), (2, 1, 'Leo');
INSERT INTO shipments VALUES (1, 2, 2, 'BlueDart', '2026-10-04');
INSERT INTO audit_log VALUES (1, 'orders', 1, 'create', '2026-10-01'), (2, 'products', 2, 'update', '2026-10-02');
