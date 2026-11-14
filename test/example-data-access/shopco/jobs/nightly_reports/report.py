"""Nightly sales report: copies yesterday's order lines into BigQuery and rebuilds daily_sales.
Reads shopdb (Postgres); writes only to the acme.shop warehouse dataset."""
import os

import pandas as pd
import sqlalchemy
from google.cloud import bigquery

LINES_SQL = """
    SELECT oi.order_id, oi.product_id, oi.quantity, oi.unit_price_cents, o.placed_at
    FROM order_items oi JOIN orders o ON o.order_id = oi.order_id
    WHERE o.placed_at >= now() - interval '1 day'
"""


def extract(engine):
    lines = pd.read_sql(LINES_SQL, engine)
    products = pd.read_sql("products", engine)
    return lines.merge(products, on="product_id")


def load(client, df):
    client.load_table_from_dataframe(df, "acme.shop.sales_lines").result()
    client.query("""
        CREATE OR REPLACE TABLE `acme.shop.daily_sales` AS
        SELECT DATE(placed_at) AS day, SUM(quantity * unit_price_cents) AS revenue_cents
        FROM `acme.shop.sales_lines`
        GROUP BY day
    """).result()


def main():
    engine = sqlalchemy.create_engine(os.environ["DATABASE_URL"])
    load(bigquery.Client(), extract(engine))
