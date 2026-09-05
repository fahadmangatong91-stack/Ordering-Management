CREATE TABLE IF NOT EXISTS customers (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    phone TEXT,
    address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price > 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    reorder_level INTEGER NOT NULL DEFAULT 5 CHECK (reorder_level >= 0),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    order_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    status TEXT NOT NULL DEFAULT 'confirmed'
        CHECK (status IN ('draft', 'confirmed', 'packing', 'shipped', 'delivered', 'cancelled')),
    subtotal NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (subtotal >= 0),
    tax NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (tax >= 0),
    total NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (total >= 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price > 0),
    line_total NUMERIC(12, 2) NOT NULL CHECK (line_total >= 0)
);

CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'staff', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_products_active_stock ON products(is_active, stock_quantity);
CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email_lower ON app_users (lower(email));

INSERT INTO customers (name, email, phone, address)
VALUES
    ('Northwind Market', 'orders@northwind.example', '+1 555-0184', '215 Harbor Street, Seattle, WA'),
    ('Summit Office Supply', 'buying@summit.example', '+1 555-0139', '88 Union Avenue, Denver, CO'),
    ('Lakeside Cafe', 'manager@lakeside.example', '+1 555-0166', '19 Lake Road, Madison, WI')
ON CONFLICT (email) DO NOTHING;

INSERT INTO products (sku, name, price, stock_quantity, reorder_level)
VALUES
    ('DRK-ESP-001', 'Espresso Beans 1 lb', 14.50, 42, 12),
    ('DRK-TEA-014', 'Jasmine Tea Case', 36.00, 18, 8),
    ('KIT-CUP-100', 'Compostable Cups 100 ct', 11.75, 55, 20),
    ('KIT-NAP-250', 'Recycled Napkins 250 ct', 8.20, 9, 15),
    ('SVC-DEL-STD', 'Standard Delivery', 7.50, 999, 0)
ON CONFLICT (sku) DO NOTHING;
