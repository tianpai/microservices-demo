import os
import time
from decimal import Decimal

import httpx
import jwt
import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


app = FastAPI(title="book-service")

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/book_db"
)
JWT_SECRET = os.getenv("JWT_SECRET", "demo-jwt-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
CONSUL_ENABLED = os.getenv("CONSUL_ENABLED", "false").lower() == "true"
CONSUL_URL = os.getenv("CONSUL_URL", "http://localhost:8500").rstrip("/")
SERVICE_NAME = os.getenv("SERVICE_NAME", "book-service")
SERVICE_ID = os.getenv("SERVICE_ID", SERVICE_NAME)
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))
SERVICE_HEALTH_PATH = os.getenv("SERVICE_HEALTH_PATH", "/books/health")

CREATE_BOOKS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS books (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT NOT NULL,
    price NUMERIC(10, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class BookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    author: str = Field(min_length=1, max_length=255)
    price: float = Field(ge=0)
    stock: int = Field(ge=0)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def initialize_database(max_attempts: int = 15, delay_seconds: int = 2) -> None:
    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_BOOKS_TABLE_SQL)
            return
        except Exception as exc:  # pragma: no cover - startup retry path
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError("book-service failed to initialize database") from last_error


def serialize_book(book: dict | None) -> dict | None:
    if book is None:
        return None

    if isinstance(book.get("price"), Decimal):
        book["price"] = float(book["price"])

    return book


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


def require_staff(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "staff":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role required",
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

    raise RuntimeError("book-service failed to register with Consul") from last_error


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


@app.on_event("startup")
def on_startup() -> None:
    initialize_database()
    register_service_with_consul()


@app.on_event("shutdown")
def on_shutdown() -> None:
    deregister_service_from_consul()


@app.get("/books/health")
def health_check() -> dict[str, str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"service": "book-service", "status": "ok"}
    except Exception as exc:  # pragma: no cover - operational path
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc


@app.get("/books")
def list_books(current_user: dict = Depends(get_current_user)) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, author, price, stock, created_at
                FROM books
                ORDER BY id
                """
            )
            books = cur.fetchall()

    return [serialize_book(book) for book in books]


@app.get("/books/{book_id}")
def get_book(book_id: int, current_user: dict = Depends(get_current_user)) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, title, author, price, stock, created_at
                FROM books
                WHERE id = %s
                """,
                (book_id,),
            )
            book = cur.fetchone()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return serialize_book(book)


@app.post("/books", status_code=status.HTTP_201_CREATED)
def create_book(
    request: BookRequest, current_user: dict = Depends(require_staff)
) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO books (title, author, price, stock)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, author, price, stock, created_at
                """,
                (
                    request.title.strip(),
                    request.author.strip(),
                    request.price,
                    request.stock,
                ),
            )
            book = cur.fetchone()

    return serialize_book(book)


@app.put("/books/{book_id}")
def update_book(
    book_id: int, request: BookRequest, current_user: dict = Depends(require_staff)
) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE books
                SET title = %s, author = %s, price = %s, stock = %s
                WHERE id = %s
                RETURNING id, title, author, price, stock, created_at
                """,
                (
                    request.title.strip(),
                    request.author.strip(),
                    request.price,
                    request.stock,
                    book_id,
                ),
            )
            book = cur.fetchone()

    if not book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return serialize_book(book)


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    book_id: int, current_user: dict = Depends(require_staff)
) -> Response:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM books WHERE id = %s RETURNING id", (book_id,))
            deleted_book = cur.fetchone()

    if not deleted_book:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Book not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
