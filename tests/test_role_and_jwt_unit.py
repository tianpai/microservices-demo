import pytest
from fastapi import HTTPException

from tests.conftest import disable_startup_side_effects, load_service_module, make_token


def test_book_require_staff_rejects_customer(monkeypatch):
    module = load_service_module("services/book-service/app.py")
    disable_startup_side_effects(module, monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        module.require_staff({"userId": 2, "role": "customer"})

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Staff role required"


def test_order_ensure_customer_rejects_staff(monkeypatch):
    module = load_service_module("services/order-service/app.py")
    disable_startup_side_effects(module, monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        module.ensure_customer({"userId": 1, "role": "staff"})

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Customer role required"


def test_book_decode_token_accepts_valid_jwt(monkeypatch):
    module = load_service_module("services/book-service/app.py")
    disable_startup_side_effects(module, monkeypatch)
    token = make_token(
        module.JWT_SECRET,
        module.JWT_ALGORITHM,
        user_id=10,
        role="staff",
        email="staff@example.com",
    )

    payload = module.decode_token(token)

    assert payload["userId"] == 10
    assert payload["role"] == "staff"
    assert payload["email"] == "staff@example.com"
