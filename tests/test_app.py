import time
from decimal import Decimal

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine, db_session_scope
from app.main import app
from app.models import Product, Rule


@pytest.fixture(scope="session", autouse=True)
def setup_db():
	Base.metadata.drop_all(bind=engine)
	Base.metadata.create_all(bind=engine)
	with db_session_scope() as s:
		p = Product(name="Widget", base_price=Decimal("100.00"), attributes_schema=None)
		s.add(p)
		s.flush()
		# config adjustment: if color == 'red', +$10
		s.add(
			Rule(
				name="Red color markup",
				rule_type="config_adjustment",
				condition={"product_id": p.id},
				parameters={"attribute": "color", "equals": "red", "amount": 10},
				priority=10,
			)
		)
		# order discount: 10% off for orders >= 5000
		s.add(
			Rule(
				name="High value discount",
				rule_type="order_discount",
				condition={"product_id": p.id, "min_order_total": 5000},
				parameters={"percentage": 10},
				priority=20,
			)
		)
		# tiered: qty>=10 -> 5%, qty>=50 -> 12%
		s.add(
			Rule(
				name="Volume tier",
				rule_type="tiered_discount",
				condition={"product_id": p.id},
				parameters={"tiers": [{"min_qty": 10, "percent_off": 5}, {"min_qty": 50, "percent_off": 12}]},
				priority=30,
			)
		)
		# approval threshold (override default 10000)
		s.add(
			Rule(
				name="Approval threshold",
				rule_type="approval_threshold",
				condition={"product_id": p.id},
				parameters={"threshold": 10000},
				priority=5,
			)
		)
		s.commit()
	yield


def test_configure():
	client = TestClient(app)
	resp = client.post("/configure", json={"product_id": 1, "attributes": {"color": "red"}})
	assert resp.status_code == 200
	data = resp.json()
	assert data["base_price"] == 100.0
	assert data["adjustments"] == 10.0


def test_quote_under_threshold():
	client = TestClient(app)
	resp = client.post(
		"/quote",
		json={"product_id": 1, "quantity": 5, "attributes": {"color": "red"}},
	)
	assert resp.status_code == 200
	data = resp.json()
	assert data["approval_status"] == "auto_approved"
	br = data["breakdown"]
	assert br["subtotal"] == 510.0  # (100*5)+10
	# No tier applicable at qty 5; discount should be 0
	assert br["discount_total"] == 0.0
	assert br["final_total"] == 510.0


def test_quote_over_value_discount_and_approval():
	client = TestClient(app)
	resp = client.post(
		"/quote",
		json={"product_id": 1, "quantity": 60, "attributes": {"color": "red"}},
	)
	assert resp.status_code == 200
	data = resp.json()
	br = data["breakdown"]
	assert br["subtotal"] == 6010.0  # (100*60)+10
	# Best discount is tiered 12% (721.2)
	assert br["discount_total"] == 721.2
	# Final below 10k after discount => auto approved
	assert data["approval_status"] == "auto_approved"


def test_get_rules():
	client = TestClient(app)
	resp = client.get("/rules")
	assert resp.status_code == 200
	rules = resp.json()
	assert len(rules) >= 3


def test_latency_under_200ms():
	client = TestClient(app)
	start = time.perf_counter()
	resp = client.post(
		"/quote",
		json={"product_id": 1, "quantity": 10, "attributes": {"color": "red"}},
	)
	elapsed_ms = (time.perf_counter() - start) * 1000
	assert resp.status_code == 200
	assert elapsed_ms < 200
