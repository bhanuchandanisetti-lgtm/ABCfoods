-- Drop tables if re-running during development
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customer_special_price;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS payments;

-- 1) Admin users (only admin is needed now)
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2) Customers (with opening balance)
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT,
    email TEXT,
    notes TEXT,
    status TEXT DEFAULT 'active',
    opening_balance REAL DEFAULT 0 -- INR carried forward
);

-- 3) Products
CREATE TABLE products (
    product_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    base_price REAL NOT NULL, -- INR
    image_path TEXT,          -- e.g. 'static/images/prawns.jpg'
    is_active INTEGER DEFAULT 1
);

-- 4) Special price per customer (discounts)
CREATE TABLE customer_special_price (
    csp_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    special_price REAL NOT NULL,
    UNIQUE(customer_id, product_id),
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id)
);

-- 5) Orders (a confirmed cart)
CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_by INTEGER NOT NULL, -- which admin recorded it
    total_amount REAL NOT NULL,  -- final INR for this order
    status TEXT DEFAULT 'finalized',
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY(created_by) REFERENCES users(user_id)
);

-- 6) Order line items
CREATE TABLE order_items (
    item_id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL NOT NULL,   -- price used for THIS customer NOW
    line_total REAL NOT NULL,   -- quantity * unit_price
    FOREIGN KEY(order_id) REFERENCES orders(order_id),
    FOREIGN KEY(product_id) REFERENCES products(product_id)
);

-- 7) Payments (money received from a customer)
CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    amount REAL NOT NULL,
    method TEXT NOT NULL, -- 'cash', 'card', 'online'
    reference_note TEXT,
    recorded_by INTEGER NOT NULL,
    FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY(recorded_by) REFERENCES users(user_id)
);

----------------------------------------------------------------
-- SEED DATA
----------------------------------------------------------------

-- Admin user placeholder (we'll insert hash from Python later)
INSERT INTO users (username, password_hash)
VALUES ('admin', 'TO_BE_SET_BY_APP_INIT');

-- 10 demo customers with opening balances in INR
INSERT INTO customers (name, phone, email, opening_balance) VALUES
('Coastal Fresh Retail',        '+91 9000000001', 'coastal@example.com',      0),
('BlueWave Restaurants',        '+91 9000000002', 'bluewave@example.com', 12000),
('Harbor Grill',                '+91 9000000003', 'harbor@example.com',    8000),
('Ocean Basket',                '+91 9000000004', 'oceanbasket@example.com', 0),
('Pearl Seafood Mart',          '+91 9000000005', 'pearl@example.com',     4500),
('Seaside Catering',            '+91 9000000006', 'seaside@example.com',      0),
('Coral Hotels Kitchen',        '+91 9000000007', 'coralhotels@example.com', 15000),
('Tidal Foods Supply',          '+91 9000000008', 'tidal@example.com',     2000),
('DeepCatch Exports',           '+91 9000000009', 'deepcatch@example.com',    0),
('Lighthouse Cafe',             '+91 9000000010', 'lighthouse@example.com',  7000);

-- Products with base prices (INR/kg or pack)
INSERT INTO products (name, description, base_price, image_path) VALUES
('Tiger Prawns (1kg)',          'Fresh tiger prawns, cleaned',                     650,  'static/images/prawns.jpg'),
('Atlantic Salmon Fillet (1kg)','Premium salmon fillet, skinless',                 900,  'static/images/salmon.jpg'),
('Crab Meat (500g)',            'Hand-picked crab meat, ready to cook',            480,  'static/images/crab.jpg'),
('Calamari Rings (1kg)',        'Cleaned squid rings, ready to fry',               520,  'static/images/calamari.jpg'),
('Basa Fillet (1kg)',           'Boneless basa fillet',                            350,  'static/images/basa.jpg'),
('Mixed Seafood Pack (2kg)',    'Assorted prawns/squid/fish for hotels & catering',1200, 'static/images/mixedpack.jpg');

-- Special prices for loyal/high-volume customers
-- BlueWave Restaurants gets discount on Tiger Prawns
INSERT INTO customer_special_price (customer_id, product_id, special_price)
VALUES
(2, 1, 600); -- BlueWave Restaurants pays 600 instead of 650 for Tiger Prawns

-- Harbor Grill gets discount on Salmon
INSERT INTO customer_special_price (customer_id, product_id, special_price)
VALUES
(3, 2, 850); -- Harbor Grill pays 850 instead of 900 for Salmon
