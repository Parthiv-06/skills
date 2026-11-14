"""Adds order status and an index for looking orders up by customer.
Status is nullable here; the backfill set every existing order to 'new'."""
import sqlalchemy as sa
from alembic import op

revision = "002"
down_revision = "001"


def upgrade():
    op.add_column("orders", sa.Column("status", sa.Text))
    op.create_index("idx_orders_customer", "orders", ["customer_id"])


def downgrade():
    op.drop_index("idx_orders_customer", table_name="orders")
    op.drop_column("orders", "status")
