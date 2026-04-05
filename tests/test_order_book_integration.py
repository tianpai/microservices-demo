from fastapi.testclient import TestClient

from tests.conftest import (
    build_book_connection_factory,
    build_book_service_http_get,
    build_order_connection_factory,
    disable_startup_side_effects,
    load_service_module,
    make_token,
)


def test_order_service_creates_order_after_book_service_verification(monkeypatch):
    book_module = load_service_module("services/book-service/app.py")
    order_module = load_service_module("services/order-service/app.py")

    disable_startup_side_effects(book_module, monkeypatch)
    disable_startup_side_effects(order_module, monkeypatch)

    _, book_connection_factory = build_book_connection_factory()
    order_store, order_connection_factory = build_order_connection_factory()
    monkeypatch.setattr(book_module, "get_connection", book_connection_factory)
    monkeypatch.setattr(order_module, "get_connection", order_connection_factory)

    staff_token = make_token(
        book_module.JWT_SECRET,
        book_module.JWT_ALGORITHM,
        user_id=1,
        role="staff",
        email="staff@example.com",
    )
    customer_token = make_token(
        order_module.JWT_SECRET,
        order_module.JWT_ALGORITHM,
        user_id=2,
        role="customer",
        email="customer@example.com",
    )

    with TestClient(book_module.app) as book_client:
        create_book_response = book_client.post(
            "/books",
            json={
                "title": "Distributed Systems",
                "author": "Demo Author",
                "price": 42.50,
                "stock": 7,
            },
            headers={"Authorization": f"Bearer {staff_token}"},
        )
        assert create_book_response.status_code == 201
        book_id = create_book_response.json()["id"]

        monkeypatch.setattr(
            order_module.httpx, "get", build_book_service_http_get(book_client)
        )

        with TestClient(order_module.app) as order_client:
            create_order_response = order_client.post(
                "/orders",
                json={"book_id": book_id, "quantity": 2},
                headers={"Authorization": f"Bearer {customer_token}"},
            )

    assert create_order_response.status_code == 201
    assert create_order_response.json()["book_id"] == book_id
    assert len(order_store["orders"]) == 1


def test_order_service_returns_400_when_book_service_reports_missing_book(monkeypatch):
    book_module = load_service_module("services/book-service/app.py")
    order_module = load_service_module("services/order-service/app.py")

    disable_startup_side_effects(book_module, monkeypatch)
    disable_startup_side_effects(order_module, monkeypatch)

    _, book_connection_factory = build_book_connection_factory()
    order_store, order_connection_factory = build_order_connection_factory()
    monkeypatch.setattr(book_module, "get_connection", book_connection_factory)
    monkeypatch.setattr(order_module, "get_connection", order_connection_factory)

    customer_token = make_token(
        order_module.JWT_SECRET,
        order_module.JWT_ALGORITHM,
        user_id=2,
        role="customer",
        email="customer@example.com",
    )

    with TestClient(book_module.app) as book_client:
        monkeypatch.setattr(
            order_module.httpx, "get", build_book_service_http_get(book_client)
        )

        with TestClient(order_module.app) as order_client:
            create_order_response = order_client.post(
                "/orders",
                json={"book_id": 999, "quantity": 1},
                headers={"Authorization": f"Bearer {customer_token}"},
            )

    assert create_order_response.status_code == 400
    assert create_order_response.json()["detail"] == "Book not found"
    assert order_store["orders"] == []
