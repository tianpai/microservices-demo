import os
import time

import httpx
import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, status
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


app = FastAPI(title="order-service")

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/order_db"
)
JWT_SECRET = os.getenv("JWT_SECRET", "demo-jwt-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
CONSUL_ENABLED = os.getenv("CONSUL_ENABLED", "false").lower() == "true"
CONSUL_URL = os.getenv("CONSUL_URL", "http://localhost:8500").rstrip("/")
SERVICE_NAME = os.getenv("SERVICE_NAME", "order-service")
SERVICE_ID = os.getenv("SERVICE_ID", SERVICE_NAME)
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8003"))
SERVICE_HEALTH_PATH = os.getenv("SERVICE_HEALTH_PATH", "/orders/health")
BOOK_SERVICE_NAME = os.getenv("BOOK_SERVICE_NAME", "book-service")
BOOK_SERVICE_URL = os.getenv("BOOK_SERVICE_URL", "http://localhost:8002")

CREATE_ORDERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    book_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class OrderRequest(BaseModel):
    book_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def initialize_database(max_attempts: int = 15, delay_seconds: int = 2) -> None:
    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_ORDERS_TABLE_SQL)
            return
        except Exception as exc:  # pragma: no cover - startup retry path
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError("order-service failed to initialize database") from last_error


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc

    if "userId" not in payload or "role" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is invalid",
        )

    return payload


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    return decode_token(authorization.split(" ", 1)[1])


def ensure_customer(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "customer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Customer role required",
        )

    return current_user


def register_service_with_consul(
    max_attempts: int = 15, delay_seconds: int = 2
) -> None:
    if not CONSUL_ENABLED:
        return

    registration_payload = {
        "ID": SERVICE_ID,
        "Name": SERVICE_NAME,
        "Address": SERVICE_HOST,
        "Port": SERVICE_PORT,
        "Check": {
            "HTTP": f"http://{SERVICE_HOST}:{SERVICE_PORT}{SERVICE_HEALTH_PATH}",
            "Interval": "10s",
            "Timeout": "5s",
        },
    }
    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            response = httpx.put(
                f"{CONSUL_URL}/v1/agent/service/register",
                json=registration_payload,
                timeout=5.0,
            )
            response.raise_for_status()
            return
        except httpx.HTTPError as exc:  # pragma: no cover - startup retry path
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError("order-service failed to register with Consul") from last_error


def deregister_service_from_consul() -> None:
    if not CONSUL_ENABLED:
        return

    try:
        httpx.put(
            f"{CONSUL_URL}/v1/agent/service/deregister/{SERVICE_ID}",
            timeout=5.0,
        ).raise_for_status()
    except httpx.HTTPError:  # pragma: no cover - shutdown path
        pass


def resolve_service_url(service_name: str) -> str:
    if not CONSUL_ENABLED:
        return BOOK_SERVICE_URL

    try:
        response = httpx.get(
            f"{CONSUL_URL}/v1/health/service/{service_name}",
            params={"passing": "true"},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Consul is unavailable",
        ) from exc

    services = response.json()
    if not services:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{service_name} is not registered in Consul",
        )

    service = services[0].get("Service", {})
    node = services[0].get("Node", {})
    address = service.get("Address") or node.get("Address")
    port = service.get("Port")

    if not address or not port:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"{service_name} has no usable Consul address",
        )

    return f"http://{address}:{port}"


def verify_book_exists(book_id: int, authorization: str) -> None:
    book_service_url = resolve_service_url(BOOK_SERVICE_NAME)

    try:
        response = httpx.get(
            f"{book_service_url}/books/{book_id}",
            headers={"Authorization": authorization},
            timeout=5.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="book-service is unavailable",
        ) from exc

    if response.status_code == status.HTTP_404_NOT_FOUND:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Book not found",
        )

    if response.status_code != status.HTTP_200_OK:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="book-service returned an unexpected response",
        )


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()
    register_service_with_consul()


@app.on_event("shutdown")
def on_shutdown() -> None:
    deregister_service_from_consul()


@app.get("/orders/health")
def health_check() -> dict[str, str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"service": "order-service", "status": "ok"}
    except Exception as exc:  # pragma: no cover - operational path
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc


@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(
    request: OrderRequest,
    current_user: dict = Depends(ensure_customer),
    authorization: str | None = Header(default=None),
) -> dict:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    verify_book_exists(request.book_id, authorization)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO orders (customer_id, book_id, quantity)
                VALUES (%s, %s, %s)
                RETURNING id, customer_id, book_id, quantity, status, created_at
                """,
                (current_user["userId"], request.book_id, request.quantity),
            )
            order = cur.fetchone()

    return order


@app.get("/orders")
def list_orders(current_user: dict = Depends(get_current_user)) -> list[dict]:
    query = """
        SELECT id, customer_id, book_id, quantity, status, created_at
        FROM orders
    """
    params: tuple = ()

    if current_user["role"] == "customer":
        query += " WHERE customer_id = %s"
        params = (current_user["userId"],)

    query += " ORDER BY id"

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            orders = cur.fetchall()

    return orders


@app.get("/orders/{order_id}")
def get_order(order_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    query = """
        SELECT id, customer_id, book_id, quantity, status, created_at
        FROM orders
        WHERE id = %s
    """
    params: tuple = (order_id,)

    if current_user["role"] == "customer":
        query += " AND customer_id = %s"
        params = (order_id, current_user["userId"])

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            order = cur.fetchone()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    return order
