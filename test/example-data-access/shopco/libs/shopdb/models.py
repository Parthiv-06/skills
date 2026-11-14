"""SQLAlchemy models for the shopdb tables the services use through the ORM.
Class names are singular; the real table name is always __tablename__."""
from sqlalchemy import Integer, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    customer_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(Text)


class Address(Base):
    __tablename__ = "addresses"
    address_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer)
    city: Mapped[str] = mapped_column(Text)


class Product(Base):
    __tablename__ = "products"
    product_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    price_cents: Mapped[int] = mapped_column(Integer)


class Order(Base):
    __tablename__ = "orders"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(Integer)
    shipping_address_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text)


class OrderLine(Base):
    __tablename__ = "order_items"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_no: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)


class Payment(Base):
    __tablename__ = "payments"
    order_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
