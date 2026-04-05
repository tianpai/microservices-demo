import importlib.util
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient


ROOT_DIR = Path(__file__).resolve().parents[1]


def load_service_module(relative_path: str):
    module_path = ROOT_DIR / relative_path
    module_name = f"test_module_{module_path.stem}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def disable_startup_side_effects(module, monkeypatch: pytest.MonkeyPatch) -> None:
    for function_name in (
        "initialize_database",
        "register_service_with_consul",
        "deregister_service_from_consul",
    ):
        if hasattr(module, function_name):
            monkeypatch.setattr(module, function_name, lambda *args, **kwargs: None)


def make_token(secret: str, algorithm: str, user_id: int, role: str, email: str) -> str:
    payload = {
        "userId": user_id,
        "role": role,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


class FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeAuthCursor:
    def __init__(self, store: dict):
        self.store = store
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.split()).lower()

        if normalized.startswith("select 1"):
            self.result = {"value": 1}
            return

        if normalized.startswith("insert into users"):
            name, email, password_hash, role = params
            if any(user["email"] == email for user in self.store["users"]):
                raise psycopg.IntegrityError("duplicate email")

            user = {
                "id": self.store["next_id"],
                "name": name,
                "email": email,
                "password_hash": password_hash,
                "role": role,
                "created_at": datetime.now(timezone.utc),
            }
            self.store["next_id"] += 1
            self.store["users"].append(user)
            self.result = {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"],
                "role": user["role"],
                "created_at": user["created_at"],
            }
            return

        if "from users" in normalized and "where email = %s" in normalized:
            email = params[0]
            self.result = next(
                (user.copy() for user in self.store["users"] if user["email"] == email),
                None,
            )
            return

        raise AssertionError(f"Unexpected auth query: {query}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        if self.result is None:
            return []
        return list(self.result)


class FakeAuthConnection(FakeConnection):
    def __init__(self, store: dict):
        self.store = store

    def cursor(self):
        return FakeAuthCursor(self.store)


def build_auth_connection_factory():
    store = {"users": [], "next_id": 1}

    def factory():
        return FakeAuthConnection(store)

    return store, factory


class FakeBookCursor:
    def __init__(self, store: dict):
        self.store = store
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.split()).lower()

        if normalized.startswith("select 1"):
            self.result = {"value": 1}
            return

        if normalized.startswith("insert into books"):
            title, author, price, stock = params
            book = {
                "id": self.store["next_id"],
                "title": title,
                "author": author,
                "price": Decimal(str(price)),
                "stock": stock,
                "created_at": datetime.now(timezone.utc),
            }
            self.store["next_id"] += 1
            self.store["books"].append(book)
            self.result = book.copy()
            return

        if "from books where id = %s" in normalized and normalized.startswith("select"):
            book_id = params[0]
            self.result = next(
                (book.copy() for book in self.store["books"] if book["id"] == book_id),
                None,
            )
            return

        if normalized.startswith("select") and "from books" in normalized:
            self.result = [book.copy() for book in self.store["books"]]
            return

        if normalized.startswith("update books"):
            title, author, price, stock, book_id = params
            book = next((book for book in self.store["books"] if book["id"] == book_id), None)
            if book is None:
                self.result = None
                return

            book.update(
                {
                    "title": title,
                    "author": author,
                    "price": Decimal(str(price)),
                    "stock": stock,
                }
            )
            self.result = book.copy()
            return

        if normalized.startswith("delete from books"):
            book_id = params[0]
            book = next((book for book in self.store["books"] if book["id"] == book_id), None)
            if book is None:
                self.result = None
                return

            self.store["books"] = [
                current_book
                for current_book in self.store["books"]
                if current_book["id"] != book_id
            ]
            self.result = {"id": book_id}
            return

        raise AssertionError(f"Unexpected book query: {query}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        if self.result is None:
            return []
        if isinstance(self.result, list):
            return self.result
        return [self.result]


class FakeBookConnection(FakeConnection):
    def __init__(self, store: dict):
        self.store = store

    def cursor(self):
        return FakeBookCursor(self.store)


def build_book_connection_factory():
    store = {"books": [], "next_id": 1}

    def factory():
        return FakeBookConnection(store)

    return store, factory


class FakeOrderCursor:
    def __init__(self, store: dict):
        self.store = store
        self.result = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params=None) -> None:
        normalized = " ".join(query.split()).lower()

        if normalized.startswith("select 1"):
            self.result = {"value": 1}
            return

        if normalized.startswith("insert into orders"):
            customer_id, book_id, quantity = params
            order = {
                "id": self.store["next_id"],
                "customer_id": customer_id,
                "book_id": book_id,
                "quantity": quantity,
                "status": "created",
                "created_at": datetime.now(timezone.utc),
            }
            self.store["next_id"] += 1
            self.store["orders"].append(order)
            self.result = order.copy()
            return

        if normalized.startswith("select") and "from orders where id = %s and customer_id = %s" in normalized:
            order_id, customer_id = params
            self.result = next(
                (
                    order.copy()
                    for order in self.store["orders"]
                    if order["id"] == order_id and order["customer_id"] == customer_id
                ),
                None,
            )
            return

        if normalized.startswith("select") and "from orders where id = %s" in normalized:
            order_id = params[0]
            self.result = next(
                (order.copy() for order in self.store["orders"] if order["id"] == order_id),
                None,
            )
            return

        if normalized.startswith("select") and "from orders where customer_id = %s" in normalized:
            customer_id = params[0]
            self.result = [
                order.copy()
                for order in self.store["orders"]
                if order["customer_id"] == customer_id
            ]
            return

        if normalized.startswith("select") and "from orders" in normalized:
            self.result = [order.copy() for order in self.store["orders"]]
            return

        raise AssertionError(f"Unexpected order query: {query}")

    def fetchone(self):
        return self.result

    def fetchall(self):
        if self.result is None:
            return []
        if isinstance(self.result, list):
            return self.result
        return [self.result]


class FakeOrderConnection(FakeConnection):
    def __init__(self, store: dict):
        self.store = store

    def cursor(self):
        return FakeOrderCursor(self.store)


def build_order_connection_factory():
    store = {"orders": [], "next_id": 1}

    def factory():
        return FakeOrderConnection(store)

    return store, factory


def build_book_service_http_get(book_client: TestClient):
    def fake_get(url: str, headers=None, timeout=None, params=None):
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return book_client.get(path, headers=headers)

    return fake_get
