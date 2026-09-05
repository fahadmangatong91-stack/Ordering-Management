from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .auth import (
    authenticate_user,
    create_access_token,
    ensure_auth_schema,
    get_current_user,
    hash_password,
    require_roles,
    validate_auth_settings,
)
from .db import apply_schema, get_connection, wait_for_database
from .schemas import (
    CustomerCreate,
    LoginRequest,
    OrderCreate,
    OrderStatusUpdate,
    ProductCreate,
    ProductUpdate,
    UserCreate,
    UserUpdate,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT_DIR / "frontend" / "static"
ORDER_STATUSES = {"draft", "confirmed", "packing", "shipped", "delivered", "cancelled"}

app = FastAPI(title="Ordering Management System", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    validate_auth_settings()
    wait_for_database()
    with get_connection() as conn:
        apply_schema(conn)
        ensure_auth_schema(conn)
        conn.commit()


def serialize(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value


def fetch_order_detail(conn, order_id: int):
    order = conn.execute(
        """
        SELECT o.*, c.name AS customer_name, c.email AS customer_email
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.id = %s
        """,
        (order_id,),
    ).fetchone()
    if not order:
        return None

    items = conn.execute(
        """
        SELECT oi.*, p.name AS product_name, p.sku
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        WHERE oi.order_id = %s
        ORDER BY oi.id
        """,
        (order_id,),
    ).fetchall()
    order["items"] = items
    return serialize(order)


def next_order_number() -> str:
    return f"ORD-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6].upper()}"


def cents(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def public_user(user: dict):
    return serialize(
        {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "is_active": user["is_active"],
            "created_at": user.get("created_at"),
            "updated_at": user.get("updated_at"),
        }
    )


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: LoginRequest):
    user = authenticate_user(payload.email, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": public_user(user),
    }


@app.get("/api/auth/me")
def get_me(current_user: dict = Depends(get_current_user)):
    return public_user(current_user)


@app.get("/api/users")
def list_users(current_user: dict = Depends(require_roles("admin"))):
    with get_connection() as conn:
        users = conn.execute(
            """
            SELECT id, name, email, role, is_active, created_at, updated_at
            FROM app_users
            ORDER BY is_active DESC, role ASC, name ASC
            """
        ).fetchall()
    return serialize(users)


@app.post("/api/users", status_code=201)
def create_user(payload: UserCreate, current_user: dict = Depends(require_roles("admin"))):
    try:
        with get_connection() as conn:
            user = conn.execute(
                """
                INSERT INTO app_users (name, email, password_hash, role, is_active)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, name, email, role, is_active, created_at, updated_at
                """,
                (
                    payload.name,
                    payload.email.lower(),
                    hash_password(payload.password),
                    payload.role,
                    payload.is_active,
                ),
            ).fetchone()
            conn.commit()
            return serialize(user)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A user with that email already exists.") from exc


@app.patch("/api/users/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user: dict = Depends(require_roles("admin")),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No user fields were provided.")
    if user_id == current_user["id"] and data.get("is_active") is False:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account.")
    if "email" in data and data["email"]:
        data["email"] = data["email"].lower()
    if "password" in data:
        data["password_hash"] = hash_password(data.pop("password"))

    assignments = ", ".join(f"{key} = %s" for key in data)
    values = list(data.values())
    values.append(user_id)

    try:
        with get_connection() as conn:
            user = conn.execute(
                f"""
                UPDATE app_users
                SET {assignments}, updated_at = now()
                WHERE id = %s
                RETURNING id, name, email, role, is_active, created_at, updated_at
                """,
                values,
            ).fetchone()
            conn.commit()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A user with that email already exists.") from exc

    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return serialize(user)


@app.get("/api/dashboard")
def get_dashboard(current_user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        summary = conn.execute(
            """
            SELECT
                COUNT(*)::int AS total_orders,
                COUNT(*) FILTER (WHERE status IN ('confirmed', 'packing', 'shipped'))::int AS open_orders,
                COALESCE(SUM(total) FILTER (WHERE status <> 'cancelled'), 0)::numeric(12,2) AS revenue,
                COALESCE(AVG(total) FILTER (WHERE status <> 'cancelled'), 0)::numeric(12,2) AS average_order_value
            FROM orders
            """
        ).fetchone()
        status_counts = conn.execute(
            """
            SELECT status, COUNT(*)::int AS count
            FROM orders
            GROUP BY status
            ORDER BY status
            """
        ).fetchall()
        low_stock = conn.execute(
            """
            SELECT id, sku, name, stock_quantity, reorder_level
            FROM products
            WHERE is_active = true AND stock_quantity <= reorder_level
            ORDER BY stock_quantity ASC, name ASC
            LIMIT 8
            """
        ).fetchall()
        recent_orders = conn.execute(
            """
            SELECT o.id, o.order_number, o.status, o.total, o.created_at, c.name AS customer_name
            FROM orders o
            JOIN customers c ON c.id = o.customer_id
            ORDER BY o.created_at DESC
            LIMIT 8
            """
        ).fetchall()

    return serialize(
        {
            "summary": summary,
            "status_counts": status_counts,
            "low_stock": low_stock,
            "recent_orders": recent_orders,
        }
    )


@app.get("/api/customers")
def list_customers(
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    query = """
        SELECT id, name, email, phone, address, created_at
        FROM customers
    """
    params: tuple[str, ...] = ()
    if search:
        query += " WHERE name ILIKE %s OR email ILIKE %s OR phone ILIKE %s"
        needle = f"%{search}%"
        params = (needle, needle, needle)
    query += " ORDER BY name ASC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return serialize(rows)


@app.post("/api/customers", status_code=201)
def create_customer(
    payload: CustomerCreate,
    current_user: dict = Depends(require_roles("admin", "staff")),
):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO customers (name, email, phone, address)
                VALUES (%s, %s, %s, %s)
                RETURNING id, name, email, phone, address, created_at
                """,
                (payload.name, payload.email, payload.phone, payload.address),
            ).fetchone()
            conn.commit()
            return serialize(row)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A customer with that email already exists.") from exc


@app.get("/api/products")
def list_products(
    active_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    query = """
        SELECT id, sku, name, price, stock_quantity, reorder_level, is_active, created_at
        FROM products
        WHERE (%s = false OR is_active = true)
    """
    params: list[object] = [active_only]
    if search:
        query += " AND (sku ILIKE %s OR name ILIKE %s)"
        needle = f"%{search}%"
        params.extend([needle, needle])
    query += " ORDER BY is_active DESC, name ASC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return serialize(rows)


@app.post("/api/products", status_code=201)
def create_product(payload: ProductCreate, current_user: dict = Depends(require_roles("admin"))):
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                INSERT INTO products (sku, name, price, stock_quantity, reorder_level)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, sku, name, price, stock_quantity, reorder_level, is_active, created_at
                """,
                (
                    payload.sku.upper(),
                    payload.name,
                    payload.price,
                    payload.stock_quantity,
                    payload.reorder_level,
                ),
            ).fetchone()
            conn.commit()
            return serialize(row)
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A product with that SKU already exists.") from exc


@app.patch("/api/products/{product_id}")
def update_product(
    product_id: int,
    payload: ProductUpdate,
    current_user: dict = Depends(require_roles("admin")),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No product fields were provided.")
    if "sku" in data and data["sku"]:
        data["sku"] = data["sku"].upper()

    assignments = ", ".join(f"{key} = %s" for key in data)
    values = list(data.values())
    values.append(product_id)

    try:
        with get_connection() as conn:
            row = conn.execute(
                f"""
                UPDATE products
                SET {assignments}
                WHERE id = %s
                RETURNING id, sku, name, price, stock_quantity, reorder_level, is_active, created_at
                """,
                values,
            ).fetchone()
            conn.commit()
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(status_code=409, detail="A product with that SKU already exists.") from exc

    if not row:
        raise HTTPException(status_code=404, detail="Product not found.")
    return serialize(row)


@app.delete("/api/products/{product_id}")
def deactivate_product(product_id: int, current_user: dict = Depends(require_roles("admin"))):
    with get_connection() as conn:
        row = conn.execute(
            """
            UPDATE products
            SET is_active = false
            WHERE id = %s
            RETURNING id, sku, name, price, stock_quantity, reorder_level, is_active, created_at
            """,
            (product_id,),
        ).fetchone()
        conn.commit()
    if not row:
        raise HTTPException(status_code=404, detail="Product not found.")
    return serialize(row)


@app.get("/api/orders")
def list_orders(
    status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    current_user: dict = Depends(get_current_user),
):
    if status and status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail="Unknown order status.")

    query = """
        SELECT
            o.id,
            o.order_number,
            o.status,
            o.subtotal,
            o.tax,
            o.total,
            o.created_at,
            o.updated_at,
            c.name AS customer_name,
            COUNT(oi.id)::int AS item_count
        FROM orders o
        JOIN customers c ON c.id = o.customer_id
        LEFT JOIN order_items oi ON oi.order_id = o.id
        WHERE (%s::text IS NULL OR o.status = %s)
    """
    params: list[object] = [status, status]
    if search:
        query += " AND (o.order_number ILIKE %s OR c.name ILIKE %s)"
        needle = f"%{search}%"
        params.extend([needle, needle])
    query += """
        GROUP BY o.id, c.name
        ORDER BY o.created_at DESC
    """

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return serialize(rows)


@app.get("/api/orders/{order_id}")
def get_order(order_id: int, current_user: dict = Depends(get_current_user)):
    with get_connection() as conn:
        order = fetch_order_detail(conn, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")
    return order


@app.post("/api/orders", status_code=201)
def create_order(
    payload: OrderCreate,
    current_user: dict = Depends(require_roles("admin", "staff")),
):
    with get_connection() as conn:
        with conn.transaction():
            customer = conn.execute(
                "SELECT id FROM customers WHERE id = %s",
                (payload.customer_id,),
            ).fetchone()
            if not customer:
                raise HTTPException(status_code=404, detail="Customer not found.")

            requested_quantities: dict[int, int] = {}
            for item in payload.items:
                requested_quantities[item.product_id] = requested_quantities.get(item.product_id, 0) + item.quantity

            subtotal = Decimal("0.00")
            prepared_items: list[dict] = []
            for product_id, quantity in requested_quantities.items():
                product = conn.execute(
                    """
                    SELECT id, sku, name, price, stock_quantity, is_active
                    FROM products
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (product_id,),
                ).fetchone()
                if not product or not product["is_active"]:
                    raise HTTPException(status_code=404, detail="Product not found or inactive.")
                if product["stock_quantity"] < quantity:
                    raise HTTPException(
                        status_code=409,
                        detail=f"Only {product['stock_quantity']} unit(s) of {product['name']} are in stock.",
                    )

                unit_price = Decimal(product["price"])
                line_total = cents(unit_price * quantity)
                subtotal += line_total
                prepared_items.append(
                    {
                        "product_id": product["id"],
                        "quantity": quantity,
                        "unit_price": unit_price,
                        "line_total": line_total,
                    }
                )

            subtotal = cents(subtotal)
            tax = cents(subtotal * payload.tax_rate)
            total = cents(subtotal + tax)
            order = conn.execute(
                """
                INSERT INTO orders (order_number, customer_id, status, subtotal, tax, total, notes)
                VALUES (%s, %s, 'confirmed', %s, %s, %s, %s)
                RETURNING id
                """,
                (next_order_number(), payload.customer_id, subtotal, tax, total, payload.notes),
            ).fetchone()

            for prepared in prepared_items:
                conn.execute(
                    """
                    INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        order["id"],
                        prepared["product_id"],
                        prepared["quantity"],
                        prepared["unit_price"],
                        prepared["line_total"],
                    ),
                )
                conn.execute(
                    """
                    UPDATE products
                    SET stock_quantity = stock_quantity - %s
                    WHERE id = %s
                    """,
                    (prepared["quantity"], prepared["product_id"]),
                )

        return fetch_order_detail(conn, order["id"])


@app.patch("/api/orders/{order_id}/status")
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    current_user: dict = Depends(require_roles("admin", "staff")),
):
    with get_connection() as conn:
        with conn.transaction():
            order = conn.execute(
                "SELECT id, status FROM orders WHERE id = %s FOR UPDATE",
                (order_id,),
            ).fetchone()
            if not order:
                raise HTTPException(status_code=404, detail="Order not found.")

            current_status = order["status"]
            if current_status == payload.status:
                return fetch_order_detail(conn, order_id)
            if current_status in {"cancelled", "delivered"}:
                raise HTTPException(
                    status_code=409,
                    detail="Cancelled or delivered orders cannot be changed.",
                )

            if payload.status == "cancelled":
                items = conn.execute(
                    """
                    SELECT product_id, quantity
                    FROM order_items
                    WHERE order_id = %s
                    """,
                    (order_id,),
                ).fetchall()
                for item in items:
                    conn.execute(
                        """
                        UPDATE products
                        SET stock_quantity = stock_quantity + %s
                        WHERE id = %s
                        """,
                        (item["quantity"], item["product_id"]),
                    )

            conn.execute(
                """
                UPDATE orders
                SET status = %s, updated_at = now()
                WHERE id = %s
                """,
                (payload.status, order_id),
            )

        return fetch_order_detail(conn, order_id)


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
