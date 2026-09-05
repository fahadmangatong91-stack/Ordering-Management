import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.rows import dict_row


os.environ.setdefault("AUTH_SECRET_KEY", "test-secret-key")
os.environ.setdefault("PASSWORD_ITERATIONS", "1000")


ROOT_DIR = Path(__file__).resolve().parents[2]


def reset_database() -> None:
    from app.auth import ensure_auth_schema
    from app.db import DATABASE_URL, apply_schema, wait_for_database

    wait_for_database(retries=30, delay_seconds=1)
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute(
            """
            DROP TABLE IF EXISTS order_items, orders, products, customers, app_users CASCADE
            """
        )
        apply_schema(conn)
        ensure_auth_schema(conn)
        conn.commit()


@pytest.fixture()
def client():
    reset_database()
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def first_customer_id(client: TestClient, headers: dict[str, str]) -> int:
    response = client.get("/api/customers", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()[0]["id"]


def product_by_sku(client: TestClient, headers: dict[str, str], sku: str) -> dict:
    response = client.get("/api/products", headers=headers)
    assert response.status_code == 200, response.text
    return next(product for product in response.json() if product["sku"] == sku)


def create_order(
    client: TestClient,
    headers: dict[str, str],
    customer_id: int,
    product_id: int,
    quantity: int,
):
    return client.post(
        "/api/orders",
        headers=headers,
        json={
            "customer_id": customer_id,
            "tax_rate": 0.12,
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
    )


def test_login_and_protected_routes(client: TestClient):
    unauthenticated = client.get("/api/dashboard")
    assert unauthenticated.status_code == 401

    headers = auth_headers(client, "admin@example.com", "admin123")
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "admin"

    bad_login = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401


def test_role_permissions(client: TestClient):
    admin_headers = auth_headers(client, "admin@example.com", "admin123")
    staff_headers = auth_headers(client, "staff@example.com", "staff123")
    viewer_headers = auth_headers(client, "viewer@example.com", "viewer123")

    assert client.get("/api/users", headers=admin_headers).status_code == 200
    assert client.get("/api/users", headers=staff_headers).status_code == 403
    assert client.get("/api/users", headers=viewer_headers).status_code == 403

    product_payload = {
        "sku": "TST-ROLE-001",
        "name": "Role Test Product",
        "price": 9.99,
        "stock_quantity": 5,
        "reorder_level": 2,
    }
    assert client.post("/api/products", headers=admin_headers, json=product_payload).status_code == 201
    assert client.post(
        "/api/products",
        headers=staff_headers,
        json={**product_payload, "sku": "TST-ROLE-002"},
    ).status_code == 403

    customer_payload = {
        "name": "Role Test Customer",
        "email": "role-test@example.com",
        "phone": "555-0100",
        "address": "100 Test Lane",
    }
    assert client.post("/api/customers", headers=staff_headers, json=customer_payload).status_code == 201
    assert client.post(
        "/api/customers",
        headers=viewer_headers,
        json={**customer_payload, "email": "viewer-denied@example.com"},
    ).status_code == 403

    customer_id = first_customer_id(client, staff_headers)
    product = product_by_sku(client, staff_headers, "DRK-ESP-001")
    assert create_order(client, staff_headers, customer_id, product["id"], 1).status_code == 201
    assert create_order(client, viewer_headers, customer_id, product["id"], 1).status_code == 403


def test_admin_can_create_user_and_duplicate_email_is_blocked(client: TestClient):
    admin_headers = auth_headers(client, "admin@example.com", "admin123")
    payload = {
        "name": "Warehouse Admin",
        "email": "warehouse-admin@example.com",
        "password": "warehouse123",
        "role": "admin",
        "is_active": True,
    }

    created = client.post("/api/users", headers=admin_headers, json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["role"] == "admin"

    duplicate = client.post("/api/users", headers=admin_headers, json=payload)
    assert duplicate.status_code == 409

    new_user_headers = auth_headers(client, "warehouse-admin@example.com", "warehouse123")
    assert client.get("/api/users", headers=new_user_headers).status_code == 200


def test_order_creation_deducts_stock_and_cancel_restores_stock(client: TestClient):
    headers = auth_headers(client, "staff@example.com", "staff123")
    customer_id = first_customer_id(client, headers)
    product = product_by_sku(client, headers, "DRK-ESP-001")

    created = create_order(client, headers, customer_id, product["id"], 3)
    assert created.status_code == 201, created.text
    order = created.json()
    assert order["status"] == "confirmed"
    assert order["subtotal"] == 43.5
    assert order["tax"] == 5.22
    assert order["total"] == 48.72

    after_order = product_by_sku(client, headers, "DRK-ESP-001")
    assert after_order["stock_quantity"] == product["stock_quantity"] - 3

    cancelled = client.patch(
        f"/api/orders/{order['id']}/status",
        headers=headers,
        json={"status": "cancelled"},
    )
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    after_cancel = product_by_sku(client, headers, "DRK-ESP-001")
    assert after_cancel["stock_quantity"] == product["stock_quantity"]


def test_order_rejects_combined_duplicate_lines_over_available_stock(client: TestClient):
    headers = auth_headers(client, "staff@example.com", "staff123")
    customer_id = first_customer_id(client, headers)
    product = product_by_sku(client, headers, "DRK-ESP-001")

    rejected = client.post(
        "/api/orders",
        headers=headers,
        json={
            "customer_id": customer_id,
            "tax_rate": 0.12,
            "items": [
                {"product_id": product["id"], "quantity": 30},
                {"product_id": product["id"], "quantity": 20},
            ],
        },
    )
    assert rejected.status_code == 409

    after_rejection = product_by_sku(client, headers, "DRK-ESP-001")
    assert after_rejection["stock_quantity"] == product["stock_quantity"]


def test_delivered_orders_are_locked(client: TestClient):
    headers = auth_headers(client, "staff@example.com", "staff123")
    customer_id = first_customer_id(client, headers)
    product = product_by_sku(client, headers, "DRK-ESP-001")

    created = create_order(client, headers, customer_id, product["id"], 1)
    assert created.status_code == 201, created.text
    order_id = created.json()["id"]

    delivered = client.patch(
        f"/api/orders/{order_id}/status",
        headers=headers,
        json={"status": "delivered"},
    )
    assert delivered.status_code == 200, delivered.text

    blocked = client.patch(
        f"/api/orders/{order_id}/status",
        headers=headers,
        json={"status": "packing"},
    )
    assert blocked.status_code == 409
