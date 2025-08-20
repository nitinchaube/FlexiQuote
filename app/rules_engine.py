from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from .models import Product, Rule


@dataclass
class AppliedRule:
	id: int
	name: str
	rule_type: str
	amount: float
	details: Dict[str, Any]


def _to_decimal(value: float | int) -> Decimal:
	return Decimal(str(value))


def _round_currency(value: Decimal) -> Decimal:
	return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class PricingEngine:
	def __init__(self, db: Session):
		self.db = db

	def load_active_rules(self) -> List[Rule]:
		return (
			self.db.query(Rule)
			.filter(Rule.is_active == True)  # noqa: E712
			.order_by(Rule.priority.asc(), Rule.id.asc())
			.all()
		)

	def compute_config_adjustments(self, product: Product, attributes: Dict[str, Any]) -> Tuple[Decimal, List[AppliedRule]]:
		applied: List[AppliedRule] = []
		total_adjustment = Decimal("0")
		for rule in self.load_active_rules():
			if rule.rule_type != "config_adjustment":
				continue
			if not self._matches_condition(rule, product_id=product.id, attributes=attributes):
				continue
			params = rule.parameters or {}
			attribute_key = params.get("attribute")
			attribute_value_expected = params.get("equals")
			if attribute_key is None:
				continue
			if attribute_value_expected is not None:
				if attributes.get(attribute_key) != attribute_value_expected:
					continue
			amount = Decimal(str(params.get("amount", 0)))
			percentage = Decimal(str(params.get("percentage", 0)))
			increment = amount
			if percentage:
				increment += _to_decimal(product.base_price) * (percentage / Decimal("100"))
			increment = _round_currency(increment)
			total_adjustment += increment
			applied.append(
				AppliedRule(
					id=rule.id,
					name=rule.name,
					rule_type=rule.rule_type,
					amount=float(increment),
					details={"attribute": attribute_key, "percentage": float(percentage), "amount": float(amount)},
				)
			)
		return _round_currency(total_adjustment), applied

	def compute_discounts(self, product: Product, quantity: int, subtotal: Decimal, attributes: Dict[str, Any]) -> Tuple[Decimal, List[AppliedRule]]:
		# Collect all candidate discounts, then choose the single best one
		candidates: List[AppliedRule] = []
		for rule in self.load_active_rules():
			if rule.rule_type not in ("order_discount", "tiered_discount"):
				continue
			if not self._matches_condition(rule, product_id=product.id, attributes=attributes, quantity=quantity, order_total=float(subtotal)):
				continue
			params = rule.parameters or {}
			if rule.rule_type == "order_discount":
				min_total = Decimal(str(params.get("min_total", 0)))
				if subtotal < min_total:
					continue
				percentage = Decimal(str(params.get("percentage", 0)))
				amount = Decimal(str(params.get("amount", 0)))
				discount_value = amount
				if percentage:
					discount_value += subtotal * (percentage / Decimal("100"))
				discount_value = _round_currency(discount_value)
				if discount_value > 0:
					candidates.append(
						AppliedRule(
							id=rule.id,
							name=rule.name,
							rule_type=rule.rule_type,
							amount=float(discount_value),
							details={"percentage": float(percentage), "amount": float(amount)},
						)
					)
			elif rule.rule_type == "tiered_discount":
				tiers: List[Dict[str, Any]] = params.get("tiers", [])
				best_percent = Decimal("0")
				for tier in tiers:
					min_qty = int(tier.get("min_qty", 0))
					percent_off = Decimal(str(tier.get("percent_off", 0)))
					if quantity >= min_qty and percent_off > best_percent:
						best_percent = percent_off
					# continue scanning tiers to find the best
				if best_percent > 0:
					discount_value = _round_currency(subtotal * (best_percent / Decimal("100")))
					candidates.append(
						AppliedRule(
							id=rule.id,
							name=rule.name,
							rule_type=rule.rule_type,
							amount=float(discount_value),
							details={"applied_percent": float(best_percent)},
						)
					)

		if not candidates:
			return Decimal("0"), []

		best = max(candidates, key=lambda r: Decimal(str(r.amount)))
		return _round_currency(Decimal(str(best.amount))), [best]

	def approval_status(self, final_total: Decimal) -> Tuple[str, Optional[int]]:
		threshold = Decimal("10000")
		for rule in self.load_active_rules():
			if rule.rule_type == "approval_threshold" and rule.parameters:
				thr = rule.parameters.get("threshold")
				if thr is not None:
					threshold = Decimal(str(thr))
					break
		if final_total >= threshold:
			return "manager_required", int(threshold)
		return "auto_approved", int(threshold)

	def _matches_condition(
		self,
		rule: Rule,
		*,
		product_id: Optional[int] = None,
		attributes: Optional[Dict[str, Any]] = None,
		quantity: Optional[int] = None,
		order_total: Optional[float] = None,
	) -> bool:
		cond = rule.condition or {}
		if product_id is not None and "product_id" in cond and cond["product_id"] != product_id:
			return False
		if quantity is not None and "min_qty" in cond and quantity < int(cond["min_qty"]):
			return False
		if order_total is not None and "min_order_total" in cond and order_total < float(cond["min_order_total"]):
			return False
		if attributes is not None:
			attr_conds: Dict[str, Any] = cond.get("attributes", {})
			for k, expected in attr_conds.items():
				if attributes.get(k) != expected:
					return False
		return True
