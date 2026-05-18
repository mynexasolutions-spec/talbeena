"""
db.py — Connection management and schema migrations for SQLite.
"""
import os
import sqlite3
from dotenv import load_dotenv

load_dotenv()

# Default to talbeena.db if no URL is provided
DATABASE_URL = os.getenv("DATABASE_URL", os.path.join(os.path.dirname(__file__), "talbeena.db"))

def get_conn():
    conn = sqlite3.connect(DATABASE_URL, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable foreign keys
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def query(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()

def query_one(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def execute(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def execute_returning(sql, params=None):
    # SQLite doesn't have a direct RETURNING for all cases like Postgres,
    # but for INSERT it has lastrowid. For complex ones, we'll need to query.
    # However, since some queries might use RETURNING, we'll try to emulate or adjust.
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(sql, params or ())
        conn.commit()
        row = cur.fetchone()
        return dict(row) if row else None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# ─── Schema migrations (SQLite Syntax) ────────────────────────────────────────

_MIGRATIONS = [
    # ── Core Tables ─────────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'customer',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS categories (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        parent_id TEXT REFERENCES categories(id),
        image_url TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        is_featured INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS brands (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        image_url TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS attributes (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS attribute_values (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        attribute_id TEXT NOT NULL REFERENCES attributes(id),
        value TEXT NOT NULL,
        image_url TEXT DEFAULT '',
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS media (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        file_url TEXT NOT NULL,
        alt_text TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS products (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        sku TEXT UNIQUE,
        type TEXT DEFAULT 'simple',
        short_description TEXT DEFAULT '',
        description TEXT DEFAULT '',
        price DECIMAL(10,2) DEFAULT 0,
        sale_price DECIMAL(10,2),
        stock_quantity INTEGER DEFAULT 0,
        stock_status TEXT DEFAULT 'in_stock',
        category_id TEXT REFERENCES categories(id),
        brand_id TEXT REFERENCES brands(id),
        is_active INTEGER DEFAULT 1,
        is_featured INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS product_images (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        product_id TEXT NOT NULL REFERENCES products(id),
        media_id TEXT NOT NULL REFERENCES media(id),
        is_primary INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS product_variations (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        product_id TEXT NOT NULL REFERENCES products(id),
        sku TEXT,
        price DECIMAL(10,2) DEFAULT 0,
        sale_price DECIMAL(10,2),
        stock_quantity INTEGER DEFAULT 0,
        stock_status TEXT DEFAULT 'in_stock',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS variation_attribute_values (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        variation_id TEXT NOT NULL REFERENCES product_variations(id),
        attribute_value_id TEXT NOT NULL REFERENCES attribute_values(id)
    )""",

    """CREATE TABLE IF NOT EXISTS product_attributes (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        product_id TEXT NOT NULL REFERENCES products(id),
        attribute_id TEXT NOT NULL REFERENCES attributes(id),
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS product_attribute_values (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        product_id TEXT NOT NULL REFERENCES products(id),
        attribute_value_id TEXT NOT NULL REFERENCES attribute_values(id)
    )""",

    """CREATE TABLE IF NOT EXISTS product_reviews (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        product_id TEXT NOT NULL REFERENCES products(id),
        user_id TEXT REFERENCES users(id),
        rating INTEGER DEFAULT 5,
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        is_approved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        user_id TEXT REFERENCES users(id),
        status TEXT DEFAULT 'pending',
        total_amount DECIMAL(10,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS order_items (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        order_id TEXT NOT NULL REFERENCES orders(id),
        product_id TEXT REFERENCES products(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS coupons (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        code TEXT UNIQUE NOT NULL,
        type TEXT DEFAULT 'percent',
        value DECIMAL(10,2) DEFAULT 0,
        min_order DECIMAL(10,2) DEFAULT 0,
        max_uses INTEGER DEFAULT 0,
        per_user INTEGER DEFAULT 1,
        is_active INTEGER DEFAULT 1,
        expires_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 1. Base settings table

    """CREATE TABLE IF NOT EXISTS store_settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT '',
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 2. User addresses
    """CREATE TABLE IF NOT EXISTS user_addresses (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        user_id TEXT NOT NULL,
        label TEXT DEFAULT 'Home',
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        address_line1 TEXT NOT NULL DEFAULT '',
        address_line2 TEXT DEFAULT '',
        city TEXT DEFAULT '',
        state TEXT DEFAULT '',
        pincode TEXT DEFAULT '',
        country TEXT DEFAULT 'India',
        is_default BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 3. Add columns to orders (SQLite doesn't support IF NOT EXISTS in ADD COLUMN)
    # We wrap these in try-except in the migrate() function anyway.
    "ALTER TABLE orders ADD COLUMN payment_method TEXT DEFAULT 'cod'",
    "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'pending'",
    "ALTER TABLE orders ADD COLUMN order_number TEXT",
    "ALTER TABLE orders ADD COLUMN cancelled_at TIMESTAMP",
    "ALTER TABLE orders ADD COLUMN cancel_reason TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN shipping_address_json TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN customer_name TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN customer_email TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN customer_phone TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN notes TEXT DEFAULT ''",

    # 4. Order items updates
    "ALTER TABLE order_items ADD COLUMN variation_id TEXT",
    "ALTER TABLE order_items ADD COLUMN quantity INTEGER DEFAULT 1",
    "ALTER TABLE order_items ADD COLUMN unit_price DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE order_items ADD COLUMN total_price DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE order_items ADD COLUMN product_name_snapshot TEXT DEFAULT ''",

    # 5. Data updates
    """UPDATE orders
       SET order_number = 'ORD-' || UPPER(SUBSTR(REPLACE(id, '-', ''), 1, 12))
       WHERE order_number IS NULL OR order_number = ''""",

    # 6. Triggers (SQLite syntax)
    """CREATE TRIGGER IF NOT EXISTS trg_sync_variation_pricing
       AFTER INSERT ON product_variations
       FOR EACH ROW
       BEGIN
           UPDATE product_variations
              SET price = (SELECT COALESCE(price, 0) FROM products WHERE id = NEW.product_id),
                  sale_price = (SELECT sale_price FROM products WHERE id = NEW.product_id),
                  stock_quantity = (SELECT COALESCE(stock_quantity, 0) FROM products WHERE id = NEW.product_id)
            WHERE id = NEW.id;
       END;""",

    """CREATE TRIGGER IF NOT EXISTS trg_sync_variations_from_product
       AFTER UPDATE OF price, sale_price, stock_quantity ON products
       FOR EACH ROW
       BEGIN
           UPDATE product_variations
              SET price = COALESCE(NEW.price, 0),
                  sale_price = NEW.sale_price,
                  stock_quantity = COALESCE(NEW.stock_quantity, 0)
            WHERE product_id = NEW.id;
       END;""",

    """CREATE TRIGGER IF NOT EXISTS trg_set_order_number_if_missing
       AFTER INSERT ON orders
       FOR EACH ROW
       WHEN NEW.order_number IS NULL OR NEW.order_number = ''
       BEGIN
           UPDATE orders
              SET order_number = 'ORD-' || UPPER(SUBSTR(hex(randomblob(6)), 1, 12))
            WHERE id = NEW.id;
       END;""",

    # 7. Initial Settings
    """INSERT OR IGNORE INTO store_settings (key, value) VALUES
         ('cod_enabled','true'), ('online_payment_enabled','false'),
         ('upi_id',''), ('bank_name',''), ('bank_account',''), ('bank_ifsc',''),
         ('razorpay_key_id',''), ('razorpay_key_secret','')""",

    """INSERT OR IGNORE INTO store_settings (key, value) VALUES
         ('shipping_fee','99'),
         ('free_shipping_threshold','999'),
         ('free_shipping_enabled','true'),
         ('free_shipping_all','false')""",

    # 8. Coupons
    "ALTER TABLE orders ADD COLUMN coupon_code TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN discount_amount DECIMAL(10,2) DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS coupon_usages (
        id         TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        coupon_id  TEXT NOT NULL,
        user_id    TEXT NOT NULL,
        order_id   TEXT NOT NULL,
        used_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 9. Indexes
    "CREATE INDEX IF NOT EXISTS idx_products_is_active       ON products(is_active)",
    "CREATE INDEX IF NOT EXISTS idx_products_category_id     ON products(category_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_brand_id        ON products(brand_id)",
    "CREATE INDEX IF NOT EXISTS idx_products_is_featured     ON products(is_featured) WHERE is_featured = 1",
    "CREATE INDEX IF NOT EXISTS idx_products_created_at      ON products(created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_products_price           ON products(price)",
    "CREATE INDEX IF NOT EXISTS idx_product_images_prod_pri  ON product_images(product_id, is_primary)",
    "CREATE INDEX IF NOT EXISTS idx_product_variations_pid   ON product_variations(product_id)",
    "CREATE INDEX IF NOT EXISTS idx_vav_variation_id         ON variation_attribute_values(variation_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_user_id           ON orders(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_orders_status            ON orders(status)",
    "CREATE INDEX IF NOT EXISTS idx_order_items_order_id     ON order_items(order_id)",
    "CREATE INDEX IF NOT EXISTS idx_user_addresses_user_id   ON user_addresses(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_categories_slug          ON categories(slug)",
    "CREATE INDEX IF NOT EXISTS idx_brands_slug              ON brands(slug)",
    "CREATE INDEX IF NOT EXISTS idx_attributes_slug          ON attributes(slug)",

    # 10. Newsletter
    """CREATE TABLE IF NOT EXISTS newsletter_subscribers (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        email TEXT UNIQUE NOT NULL,
        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 11. Variation system — type classification for attributes
    "ALTER TABLE attributes ADD COLUMN variation_type TEXT DEFAULT 'secondary'",

    # 12. Product family grouping (for primary variations like flavours)
    "ALTER TABLE products ADD COLUMN family_id TEXT REFERENCES products(id)",
    "CREATE INDEX IF NOT EXISTS idx_products_family_id ON products(family_id)",

    # 13. Variation-level images
    """CREATE TABLE IF NOT EXISTS variation_images (
        id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
        variation_id TEXT NOT NULL REFERENCES product_variations(id),
        media_id TEXT NOT NULL REFERENCES media(id),
        is_primary INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_variation_images_var ON variation_images(variation_id)",

    # 14. Per-variation product details
    "ALTER TABLE product_variations ADD COLUMN name TEXT DEFAULT ''",
    "ALTER TABLE product_variations ADD COLUMN short_description TEXT DEFAULT ''",
    "ALTER TABLE product_variations ADD COLUMN description TEXT DEFAULT ''",
]

def migrate():
    for sql in _MIGRATIONS:
        try:
            execute(sql, [])
        except Exception as e:
            # We ignore errors for duplicate columns/indexes since SQLite 
            # doesn't support IF NOT EXISTS for ADD COLUMN
            pass
