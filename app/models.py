from datetime import datetime
from typing import Optional

from sqlalchemy import (
	JSON,
	Boolean,
	DateTime,
	ForeignKey,
	Integer,
	Numeric,
	String,
)
from sqlalchemy.orm import relationship, Mapped, mapped_column

from .db import Base


class Product(Base):
	__tablename__ = "products"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
	base_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
	attributes_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

	quotes: Mapped[list["Quote"]] = relationship("Quote", back_populates="product")


class Rule(Base):
	__tablename__ = "rules"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	name: Mapped[str] = mapped_column(String(255), nullable=False)
	rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
	condition: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
	parameters: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
	is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
	priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class Quote(Base):
	__tablename__ = "quotes"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
	product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
	quantity: Mapped[int] = mapped_column(Integer, nullable=False)
	attributes: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

	subtotal: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
	adjustments_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
	discount_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
	final_total: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

	approval_status: Mapped[str] = mapped_column(String(32), nullable=False)
	breakdown: Mapped[dict] = mapped_column(JSON, nullable=False)

	created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

	product: Mapped["Product"] = relationship("Product", back_populates="quotes")
