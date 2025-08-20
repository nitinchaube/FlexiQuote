from decimal import Decimal
from typing import List

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .db import Base, engine, get_db
from .models import Product, Rule, Quote
from .rules_engine import PricingEngine
from .schemas import ConfigureRequest, ConfigureResponse, QuoteRequest, QuoteResponse, PriceBreakdown, RuleOut

app = FastAPI(title="FlexiQuote API")

# Create tables at startup (simple dev approach; in prod use migrations)
Base.metadata.create_all(bind=engine)


@app.post("/configure", response_model=ConfigureResponse)
def configure(req: ConfigureRequest, db: Session = Depends(get_db)):
	product = db.query(Product).filter(Product.id == req.product_id).first()
	if not product:
		raise HTTPException(status_code=404, detail="Product not found")

	engine_ = PricingEngine(db)
	adjustments, applied_rules = engine_.compute_config_adjustments(product, req.attributes)
	return ConfigureResponse(
		product_id=product.id,
		attributes=req.attributes,
		base_price=float(product.base_price),
		adjustments=float(adjustments),
		message="Configuration valid",
	)


@app.post("/quote", response_model=QuoteResponse)
def quote(req: QuoteRequest, db: Session = Depends(get_db)):
	product = db.query(Product).filter(Product.id == req.product_id).first()
	if not product:
		raise HTTPException(status_code=404, detail="Product not found")

	engine_ = PricingEngine(db)
	adjustments, applied_config_rules = engine_.compute_config_adjustments(product, req.attributes)
	subtotal = Decimal(str(product.base_price)) * Decimal(str(req.quantity)) + adjustments
	discount, applied_discount_rules = engine_.compute_discounts(product, req.quantity, subtotal, req.attributes)
	final_total = subtotal - discount
	approval, threshold = engine_.approval_status(final_total)

	breakdown = PriceBreakdown(
		subtotal=float(subtotal),
		adjustments_total=float(adjustments),
		discount_total=float(discount),
		final_total=float(final_total),
		applied_rules=[r.__dict__ for r in (applied_config_rules + applied_discount_rules)],
	)

	quote_row = Quote(
		product_id=product.id,
		quantity=req.quantity,
		attributes=req.attributes,
		subtotal=subtotal,
		adjustments_total=adjustments,
		discount_total=discount,
		final_total=final_total,
		approval_status=approval,
		breakdown=breakdown.model_dump(),
	)
	db.add(quote_row)
	db.commit()
	db.refresh(quote_row)

	return QuoteResponse(
		quote_id=quote_row.id,
		product_id=product.id,
		quantity=req.quantity,
		attributes=req.attributes,
		approval_status=approval,
		breakdown=breakdown,
	)


@app.get("/rules", response_model=List[RuleOut])
def get_rules(db: Session = Depends(get_db)):
	rules = db.query(Rule).order_by(Rule.priority.asc(), Rule.id.asc()).all()
	return [
		RuleOut(
			id=r.id,
			name=r.name,
			rule_type=r.rule_type,
			condition=r.condition,
			parameters=r.parameters,
			is_active=r.is_active,
			priority=r.priority,
		)
		for r in rules
	]
