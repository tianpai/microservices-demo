import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import psycopg
from fastapi import FastAPI, HTTPException, status
from passlib.context import CryptContext
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


app = FastAPI(title="auth-service")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/auth_db"
)
JWT_SECRET = os.getenv("JWT_SECRET", "demo-jwt-secret")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
TOKEN_EXPIRE_HOURS = int(os.getenv("TOKEN_EXPIRE_HOURS", "24"))
CONSUL_ENABLED = os.getenv("CONSUL_ENABLED", "false").lower() == "true"
CONSUL_URL = os.getenv("CONSUL_URL", "http://localhost:8500").rstrip("/")
SERVICE_NAME = os.getenv("SERVICE_NAME", "auth-service")
SERVICE_ID = os.getenv("SERVICE_ID", SERVICE_NAME)
SERVICE_HOST = os.getenv("SERVICE_HOST", "localhost")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
SERVICE_HEALTH_PATH = os.getenv("SERVICE_HEALTH_PATH", "/auth/health")

ALLOWED_ROLES = {"customer", "staff"}

CREATE_USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('customer', 'staff')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    role: str = Field(min_length=4, max_length=20)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)


def get_connection() -> psycopg.Connection:
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def initialize_database(max_attempts: int = 15, delay_seconds: int = 2) -> None:
    last_error: Exception | None = None

    for _ in range(max_attempts):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(CREATE_USERS_TABLE_SQL)
            return
        except Exception as exc:  # pragma: no cover - startup retry path
            last_error = exc
            time.sleep(delay_seconds)

    raise RuntimeError("auth-service failed to initialize database") from last_error


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_token(user_id: int, email: str, role: str) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "userId": user_id,
        "email": email,
        "role": role,
        "exp": expires_at,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


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

    raise RuntimeError("auth-service failed to register with Consul") from last_error


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


@app.get("/auth/health")
def health_check() -> dict[str, str]:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return {"service": "auth-service", "status": "ok"}
    except Exception as exc:  # pragma: no cover - operational path
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Database unavailable: {exc}",
        ) from exc


@app.post("/auth/register", status_code=status.HTTP_201_CREATED)
def register_user(request: RegisterRequest) -> dict:
    role = request.role.strip().lower()

    if role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be either customer or staff",
        )

    hashed_password = pwd_context.hash(request.password)
    email = normalize_email(request.email)

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO users (name, email, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, name, email, role, created_at
                    """,
                    (request.name.strip(), email, hashed_password, role),
                )
                user = cur.fetchone()
    except psycopg.IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from exc

    return {"message": "User registered successfully", "user": user}


@app.post("/auth/login")
def login_user(request: LoginRequest) -> dict:
    email = normalize_email(request.email)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, email, password_hash, role, created_at
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            user = cur.fetchone()

    if not user or not pwd_context.verify(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(user["id"], user["email"], user["role"])

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "created_at": user["created_at"],
        },
    }
