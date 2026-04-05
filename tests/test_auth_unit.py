import jwt
from fastapi.testclient import TestClient

from tests.conftest import (
    build_auth_connection_factory,
    disable_startup_side_effects,
    load_service_module,
)


def test_auth_register_and_login_round_trip(monkeypatch):
    module = load_service_module("services/auth-service/app.py")
    disable_startup_side_effects(module, monkeypatch)
    _, connection_factory = build_auth_connection_factory()
    monkeypatch.setattr(module, "get_connection", connection_factory)

    with TestClient(module.app) as client:
        register_response = client.post(
            "/auth/register",
            json={
                "name": "Staff User",
                "email": "staff@example.com",
                "password": "password123",
                "role": "staff",
            },
        )
        assert register_response.status_code == 201

        login_response = client.post(
            "/auth/login",
            json={"email": "staff@example.com", "password": "password123"},
        )
        assert login_response.status_code == 200

    payload = jwt.decode(
        login_response.json()["access_token"],
        module.JWT_SECRET,
        algorithms=[module.JWT_ALGORITHM],
    )
    assert payload["userId"] == 1
    assert payload["role"] == "staff"
    assert payload["email"] == "staff@example.com"


def test_auth_login_rejects_invalid_password(monkeypatch):
    module = load_service_module("services/auth-service/app.py")
    disable_startup_side_effects(module, monkeypatch)
    _, connection_factory = build_auth_connection_factory()
    monkeypatch.setattr(module, "get_connection", connection_factory)

    with TestClient(module.app) as client:
        client.post(
            "/auth/register",
            json={
                "name": "Customer User",
                "email": "customer@example.com",
                "password": "password123",
                "role": "customer",
            },
        )
        login_response = client.post(
            "/auth/login",
            json={"email": "customer@example.com", "password": "wrongpass"},
        )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"
