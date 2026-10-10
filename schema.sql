-- =====================================================================
-- Techno Vender: database setup
-- Paste this whole file into Neon's SQL Editor and click Run.
--
-- WARNING: the first line deletes these five tables if they already
-- exist, so running it again resets everything to the sample data.
-- =====================================================================

DROP TABLE IF EXISTS purchases, payment_methods, members, products, membership_plans CASCADE;


-- ---------------------------------------------------------------------
-- 1. membership_plans: the membership levels a customer can be on
-- ---------------------------------------------------------------------
CREATE TABLE membership_plans (
    plan_id          SERIAL PRIMARY KEY,
    plan_name        VARCHAR(20)  NOT NULL UNIQUE,
    monthly_fee      NUMERIC(6,2) NOT NULL CHECK (monthly_fee >= 0),
    discount_percent NUMERIC(4,1) NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
    description      TEXT
);


-- ---------------------------------------------------------------------
-- 2. members: the customers
--    Each member is on exactly one plan (plan_id).
--    A plan that still has members can't be deleted (RESTRICT).
-- ---------------------------------------------------------------------
CREATE TABLE members (
    member_id    SERIAL PRIMARY KEY,
    first_name   VARCHAR(50)  NOT NULL,
    last_name    VARCHAR(50)  NOT NULL,
    email        VARCHAR(120) NOT NULL UNIQUE,
    phone        VARCHAR(20),
    plan_id      INT          NOT NULL REFERENCES membership_plans (plan_id) ON DELETE RESTRICT,
    status       VARCHAR(10)  NOT NULL DEFAULT 'Active'
                 CHECK (status IN ('Active', 'Paused', 'Cancelled')),
    start_date   DATE         NOT NULL DEFAULT CURRENT_DATE,
    renewal_date DATE         NOT NULL,
    CONSTRAINT renewal_after_start CHECK (renewal_date >= start_date)
);


-- ---------------------------------------------------------------------
-- 3. payment_methods: saved ways to pay (simulated, no real money)
--    Only the last four digits are stored. Never a full card number or CVV.
--    Deleting a member deletes their payment methods too (CASCADE).
-- ---------------------------------------------------------------------
CREATE TABLE payment_methods (
    payment_method_id SERIAL PRIMARY KEY,
    member_id         INT         NOT NULL REFERENCES members (member_id) ON DELETE CASCADE,
    method_type       VARCHAR(12) NOT NULL
                      CHECK (method_type IN ('Credit', 'Debit', 'Gift card', 'Wallet')),
    nickname          VARCHAR(40),
    card_brand        VARCHAR(20) NOT NULL,
    last_four         CHAR(4)     NOT NULL CHECK (last_four ~ '^[0-9]{4}$'),
    expiry_month      SMALLINT    NOT NULL CHECK (expiry_month BETWEEN 1 AND 12),
    expiry_year       SMALLINT    NOT NULL CHECK (expiry_year BETWEEN 2024 AND 2100),
    is_default        BOOLEAN     NOT NULL DEFAULT FALSE
);

-- A member can have only one default payment method.
CREATE UNIQUE INDEX one_default_per_member ON payment_methods (member_id) WHERE is_default;


-- ---------------------------------------------------------------------
-- 4. products: what's in the machine (one product per slot)
-- ---------------------------------------------------------------------
CREATE TABLE products (
    product_id   SERIAL PRIMARY KEY,
    slot_code    CHAR(2)      NOT NULL UNIQUE CHECK (slot_code ~ '^[A-C][1-3]$'),
    product_name VARCHAR(80)  NOT NULL,
    category     VARCHAR(30)  NOT NULL,
    price        NUMERIC(6,2) NOT NULL CHECK (price > 0),
    stock_qty    INT          NOT NULL DEFAULT 0 CHECK (stock_qty >= 0),
    image        VARCHAR(255),          -- an emoji, or a link to a picture
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE
);


-- ---------------------------------------------------------------------
-- 5. purchases: one row per vend
--    unit_price and discount_percent are copied in at the moment of sale,
--    so a later price change doesn't rewrite old receipts.
--    Members and products with purchases can't be deleted (RESTRICT).
--    Deleting a payment method keeps the purchase but empties the link (SET NULL).
-- ---------------------------------------------------------------------
CREATE TABLE purchases (
    purchase_id       SERIAL PRIMARY KEY,
    member_id         INT          NOT NULL REFERENCES members (member_id)  ON DELETE RESTRICT,
    product_id        INT          NOT NULL REFERENCES products (product_id) ON DELETE RESTRICT,
    payment_method_id INT          REFERENCES payment_methods (payment_method_id) ON DELETE SET NULL,
    quantity          SMALLINT     NOT NULL CHECK (quantity BETWEEN 1 AND 10),
    unit_price        NUMERIC(6,2) NOT NULL CHECK (unit_price > 0),
    discount_percent  NUMERIC(4,1) NOT NULL CHECK (discount_percent BETWEEN 0 AND 100),
    total_amount      NUMERIC(8,2) NOT NULL CHECK (total_amount >= 0),
    status            VARCHAR(10)  NOT NULL DEFAULT 'Completed'
                      CHECK (status IN ('Completed', 'Refunded', 'Cancelled')),
    purchased_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);


-- =====================================================================
-- Sample data (made up). New tables number rows from 1, so the IDs
-- below line up with the order the rows are inserted.
-- =====================================================================

INSERT INTO membership_plans (plan_name, monthly_fee, discount_percent, description) VALUES
    ('Basic',  0.00,  0.0, 'Free. Standard prices.'),          -- plan_id 1
    ('Silver', 4.99,  5.0, '5% off every vend.'),              -- plan_id 2
    ('Gold',   9.99, 10.0, '10% off every vend.');             -- plan_id 3

INSERT INTO products (slot_code, product_name, category, price, stock_qty, image) VALUES
    ('A1', 'USB-C cable (1 m)',        'Cables',      12.99,  8, '🔌'),  -- product_id 1
    ('A2', 'Lightning cable (1 m)',    'Cables',      12.99,  8, '🔌'),  -- 2
    ('A3', 'HDMI adapter',             'Adapters',    19.99,  5, '🖥️'),  -- 3
    ('B1', 'Wall charger (20 W)',      'Chargers',    24.99,  7, '⚡'),  -- 4
    ('B2', 'Wireless earbuds',         'Audio',       39.99,  5, '🎧'),  -- 5
    ('B3', 'Wired earphones',          'Audio',       14.99,  9, '🎵'),  -- 6
    ('C1', 'Power bank (10,000 mAh)',  'Power',       34.99,  3, '🔋'),  -- 7
    ('C2', 'Screen cleaning kit',      'Accessories',  7.99, 11, '🧽'),  -- 8
    ('C3', 'microSD card (64 GB)',     'Storage',     16.99,  0, '💾');  -- 9 (sold out)

INSERT INTO members (first_name, last_name, email, phone, plan_id, status, start_date, renewal_date) VALUES
    ('Priya', 'Shah',     'priya.shah@example.com',    '403-555-0142', 3, 'Active',    '2026-09-01', '2026-11-01'),  -- member_id 1
    ('Liam',  'Tremblay', 'liam.tremblay@example.com', '587-555-0178', 2, 'Active',    '2026-08-15', '2026-11-15'),  -- 2
    ('Aisha', 'Okafor',   'aisha.okafor@example.com',  NULL,           1, 'Active',    '2026-10-02', '2026-11-02'),  -- 3
    ('Noah',  'Chen',     'noah.chen@example.com',     '403-555-0119', 1, 'Cancelled', '2026-06-10', '2026-09-10');  -- 4

INSERT INTO payment_methods (member_id, method_type, nickname, card_brand, last_four, expiry_month, expiry_year, is_default) VALUES
    (1, 'Credit',    'Work Visa',     'Visa',          '2048',  8, 2028, TRUE),   -- payment_method_id 1
    (1, 'Wallet',    'Phone wallet',  'Apple Pay',     '7731',  1, 2029, FALSE),  -- 2
    (2, 'Debit',     'Chequing',      'Interac',       '5519',  5, 2027, TRUE),   -- 3
    (3, 'Gift card', 'Birthday card', 'Techno Vender', '0091', 12, 2026, TRUE),   -- 4
    (4, 'Credit',    NULL,            'Mastercard',    '3360',  2, 2027, TRUE);   -- 5

-- total_amount = unit_price × quantity × (1 − discount_percent ÷ 100), rounded to the cent
INSERT INTO purchases (member_id, product_id, payment_method_id, quantity, unit_price, discount_percent, total_amount, status, purchased_at) VALUES
    (1, 5, 1, 1, 39.99, 10.0, 35.99, 'Completed', '2026-10-01 09:12'),  -- Priya, earbuds, Gold
    (2, 1, 3, 2, 12.99,  5.0, 24.68, 'Completed', '2026-10-03 13:40'),  -- Liam, 2 USB-C cables, Silver
    (3, 8, 4, 1,  7.99,  0.0,  7.99, 'Completed', '2026-10-05 16:05'),  -- Aisha, cleaning kit, Basic
    (4, 4, 5, 1, 24.99,  0.0, 24.99, 'Refunded',  '2026-08-20 11:30'),  -- Noah, charger, refunded
    (1, 7, 2, 1, 34.99, 10.0, 31.49, 'Completed', '2026-10-07 18:22');  -- Priya, power bank, Gold

-- Quick check: this should list the 5 tables with their row counts.
SELECT 'membership_plans' AS table_name, COUNT(*) AS rows FROM membership_plans
UNION ALL SELECT 'members',         COUNT(*) FROM members
UNION ALL SELECT 'payment_methods', COUNT(*) FROM payment_methods
UNION ALL SELECT 'products',        COUNT(*) FROM products
UNION ALL SELECT 'purchases',       COUNT(*) FROM purchases;
