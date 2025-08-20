from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ConfigureRequest(BaseModel):
	product_id: int
	attributes: Dict[str, Any] = Field(default_factory=dict)


class ConfigureResponse(BaseModel):
	product_id: int
	attributes: Dict[str, Any]
	base_price: float
	adjustments: float
	message: str


class QuoteRequest(BaseModel):
	product_id: int
	quantity: int = Field(ge=1)
	attributes: Dict[str, Any] = Field(default_factory=dict)

	@field_validator("quantity")
	@classmethod
	def validate_qty(cls, v: int) -> int:
		if v < 1:
			raise ValueError("quantity must be >= 1")
		return v


class PriceBreakdown(BaseModel):
	subtotal: float
	adjustments_total: float
	discount_total: float
	final_total: float
	applied_rules: List[dict]


class QuoteResponse(BaseModel):
	quote_id: int
	product_id: int
	quantity: int
	attributes: Dict[str, Any]
	approval_status: str
	breakdown: PriceBreakdown


class RuleOut(BaseModel):
	id: int
	name: str
	rule_type: str
	condition: Optional[Dict[str, Any]]
	parameters: Optional[Dict[str, Any]]
	is_active: bool
	priority: int
