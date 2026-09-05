# Ordering Management System

A small full-stack ordering app built with a Python API, JavaScript frontend, and PostgreSQL database.

## Features

- Customer records with contact details
- Product catalog with SKU, price, active state, stock, and reorder level
- Order creation with multiple line items
- Automatic stock reduction when an order is created
- Stock restoration when an order is cancelled
- Order status tracking from confirmed through delivered or cancelled
- Dashboard for revenue, open orders, status counts, recent orders, and low stock
- Login with admin, staff, and viewer roles
- Admin user management
- Automated backend tests for authentication, permissions, and order rules

## Default Login Accounts

The app creates these development users on startup if they do not already exist:

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@example.com` | `admin123` |
| Staff | `staff@example.com` | `staff123` |
| Viewer | `viewer@example.com` | `viewer123` |

Role access:

- Admin can manage users, products, customers, and orders.
- Staff can manage customers and orders, and can view products.
- Viewer can view dashboards, customers, products, and orders.

For production, change `AUTH_SECRET_KEY` and all default passwords in your environment.

## Run With Docker

1. Start the system:

```bash
docker compose up --build
```

2. Open the app:

```text
http://localhost:8000
```

The PostgreSQL database is initialized from `database/init.sql` the first time the database volume is created.

## Run Automated Tests

Run the backend test suite against a separate PostgreSQL test database:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
```

Clean up the test containers afterward:

```bash
docker compose -f docker-compose.test.yml down -v
```

## Hosting Checklist

Recommended prototype hosting:

- Web app: Render Docker Web Service
- Database: Neon PostgreSQL or Render PostgreSQL

Before deploying, set these environment variables in the hosting dashboard:

```text
DATABASE_URL=your hosted PostgreSQL connection string
AUTH_SECRET_KEY=a long random private value
ENVIRONMENT=production
ACCESS_TOKEN_TTL_SECONDS=28800
DEFAULT_ADMIN_EMAIL=admin@example.com
DEFAULT_ADMIN_PASSWORD=your private admin password
DEFAULT_STAFF_EMAIL=staff@example.com
DEFAULT_STAFF_PASSWORD=your private staff password
DEFAULT_VIEWER_EMAIL=viewer@example.com
DEFAULT_VIEWER_PASSWORD=your private viewer password
```

Do not use `admin123`, `staff123`, or `viewer123` on a public hosted site.

The app applies `database/init.sql` on startup, so a new hosted PostgreSQL database will automatically receive the required tables and sample records.

## Run Without Docker

1. Create a PostgreSQL database and user matching `.env.example`, or update `DATABASE_URL`.
2. Apply the schema:

```bash
psql "$DATABASE_URL" -f database/init.sql
```

3. Install Python dependencies:

```bash
pip install -r backend/requirements.txt
```

4. Start the API and frontend:

```bash
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On Windows PowerShell:

```powershell
$env:PYTHONPATH="backend"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## API

- `GET /api/dashboard`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `GET /api/users`
- `POST /api/users`
- `PATCH /api/users/{user_id}`
- `GET /api/customers`
- `POST /api/customers`
- `GET /api/products`
- `POST /api/products`
- `PATCH /api/products/{product_id}`
- `DELETE /api/products/{product_id}`
- `GET /api/orders`
- `GET /api/orders/{order_id}`
- `POST /api/orders`
- `PATCH /api/orders/{order_id}/status`
