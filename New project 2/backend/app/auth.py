import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from collections.abc import Callable

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .db import get_connection


ROLES = {"admin", "staff", "viewer"}
TOKEN_TTL_SECONDS = int(os.getenv("ACCESS_TOKEN_TTL_SECONDS", str(8 * 60 * 60)))
PASSWORD_ITERATIONS = int(os.getenv("PASSWORD_ITERATIONS", "260000"))
AUTH_SECRET_KEY = os.getenv(
    "AUTH_SECRET_KEY",
    "development-only-change-this-secret-before-production",
)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development").lower()
DEFAULT_AUTH_SECRET_KEY = "development-only-change-this-secret-before-production"

security = HTTPBearer(auto_error=False)


def validate_auth_settings() -> None:
    if ENVIRONMENT != "production":
        return

    weak_values = {
        "AUTH_SECRET_KEY": AUTH_SECRET_KEY == DEFAULT_AUTH_SECRET_KEY,
        "DEFAULT_ADMIN_PASSWORD": os.getenv("DEFAULT_ADMIN_PASSWORD") in {None, "admin123"},
        "DEFAULT_STAFF_PASSWORD": os.getenv("DEFAULT_STAFF_PASSWORD") in {None, "staff123"},
        "DEFAULT_VIEWER_PASSWORD": os.getenv("DEFAULT_VIEWER_PASSWORD") in {None, "viewer123"},
    }
    invalid_names = [name for name, is_invalid in weak_values.items() if is_invalid]
    if invalid_names:
        joined_names = ", ".join(invalid_names)
        raise RuntimeError(f"Production auth settings are not configured: {joined_names}")


def _base64_url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64_url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            _base64_url_encode(salt),
            _base64_url_encode(password_hash),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected_hash = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        calculated_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _base64_url_decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_base64_url_encode(calculated_hash), expected_hash)
    except (TypeError, ValueError):
        return False


def create_access_token(user: dict) -> str:
    issued_at = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "iat": issued_at,
        "exp": issued_at + TOKEN_TTL_SECONDS,
    }
    encoded_payload = _base64_url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = hmac.new(
        AUTH_SECRET_KEY.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"oms1.{encoded_payload}.{_base64_url_encode(signature)}"


def decode_access_token(token: str) -> dict:
    try:
        version, encoded_payload, signature = token.split(".", 2)
        if version != "oms1":
            raise ValueError("Unsupported token version")
        expected_signature = hmac.new(
            AUTH_SECRET_KEY.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_base64_url_encode(expected_signature), signature):
            raise ValueError("Invalid signature")
        payload = json.loads(_base64_url_decode(encoded_payload))
    except (ValueError, json.JSONDecodeError):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if int(payload.get("exp", 0)) < int(time.time()):
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired login token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def ensure_auth_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('admin', 'staff', 'viewer')),
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email_lower
        ON app_users (lower(email))
        """
    )

    default_users = [
        (
            os.getenv("DEFAULT_ADMIN_NAME", "System Admin"),
            os.getenv("DEFAULT_ADMIN_EMAIL", "admin@example.com"),
            os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123"),
            "admin",
        ),
        (
            os.getenv("DEFAULT_STAFF_NAME", "Order Staff"),
            os.getenv("DEFAULT_STAFF_EMAIL", "staff@example.com"),
            os.getenv("DEFAULT_STAFF_PASSWORD", "staff123"),
            "staff",
        ),
        (
            os.getenv("DEFAULT_VIEWER_NAME", "Read Only Viewer"),
            os.getenv("DEFAULT_VIEWER_EMAIL", "viewer@example.com"),
            os.getenv("DEFAULT_VIEWER_PASSWORD", "viewer123"),
            "viewer",
        ),
    ]
    for name, email, password, role in default_users:
        conn.execute(
            """
            INSERT INTO app_users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO NOTHING
            """,
            (name, email.lower(), hash_password(password), role),
        )


def authenticate_user(email: str, password: str):
    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, name, email, password_hash, role, is_active, created_at, updated_at
            FROM app_users
            WHERE lower(email) = lower(%s)
            """,
            (email,),
        ).fetchone()

    if not user or not user["is_active"]:
        return None
    if not verify_password(password, user["password_hash"]):
        return None
    return user


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Login is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, name, email, role, is_active, created_at, updated_at
            FROM app_users
            WHERE id = %s AND is_active = true
            """,
            (payload["sub"],),
        ).fetchone()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Login is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*allowed_roles: str) -> Callable:
    def checker(current_user: dict = Depends(get_current_user)):
        if current_user["role"] not in allowed_roles:
            raise HTTPException(status_code=403, detail="You do not have permission for this action.")
        return current_user

    return checker
