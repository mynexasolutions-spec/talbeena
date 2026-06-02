"""
db.py — PostgreSQL connection management and schema migrations.
Uses psycopg2 with a ThreadedConnectionPool for efficient connection reuse.
"""
import os
import threading
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

_pool = None
_pool_lock = threading.Lock()


def _parse_url(url):
    from urllib.parse import urlparse, unquote
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": unquote(parsed.username),
        "password": unquote(parsed.password),
        "connect_timeout": 15,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                if not DATABASE_URL:
                    raise RuntimeError("DATABASE_URL is not set.")
                params = _parse_url(DATABASE_URL)
                _pool = pg_pool.ThreadedConnectionPool(
                    minconn=2,
                    maxconn=10,
                    **params,
                )
    return _pool


def get_conn():
    conn = _get_pool().getconn()
    conn.autocommit = False
    return conn


def _release(conn):
    try:
        _get_pool().putconn(conn)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass


def _pg(sql):
    return sql.replace("?", "%s")


def _as_dict(cursor):
    cols = [desc[0] for desc in cursor.description] if cursor.description else []
    return [dict(zip(cols, row)) for row in cursor.fetchall()]


def query(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_pg(sql), params or ())
        return _as_dict(cur)
    finally:
        _release(conn)


def query_one(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_pg(sql), params or ())
        rows = _as_dict(cur)
        return rows[0] if rows else None
    finally:
        _release(conn)


def execute(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_pg(sql), params or ())
        conn.commit()
        return cur.rowcount
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


def execute_returning(sql, params=None):
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(_pg(sql), params or ())
        rows = _as_dict(cur)
        conn.commit()
        return rows[0] if rows else None
    except Exception:
        conn.rollback()
        raise
    finally:
        _release(conn)


# ═══════════════════════════════════════════════════════════════════════════════
# Schema migrations (PostgreSQL syntax)
# ═══════════════════════════════════════════════════════════════════════════════

_MIGRATIONS = [
    # ── Enable pgcrypto for gen_random_uuid() ─────────────────────────────────
    'CREATE EXTENSION IF NOT EXISTS "pgcrypto"',

    # ── Core Tables ───────────────────────────────────────────────────────────
    """CREATE TABLE IF NOT EXISTS users (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        first_name TEXT DEFAULT '',
        last_name TEXT DEFAULT '',
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT DEFAULT 'customer',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS categories (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        parent_id UUID REFERENCES categories(id),
        image_url TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        is_featured INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS brands (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        image_url TEXT DEFAULT '',
        is_active INTEGER DEFAULT 1,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS attributes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS attribute_values (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        attribute_id UUID NOT NULL REFERENCES attributes(id),
        value TEXT NOT NULL,
        image_url TEXT DEFAULT '',
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS media (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        file_url TEXT NOT NULL,
        alt_text TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS products (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        category_id UUID REFERENCES categories(id),
        brand_id UUID REFERENCES brands(id),
        is_active INTEGER DEFAULT 1,
        is_featured INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS product_images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id),
        media_id UUID NOT NULL REFERENCES media(id),
        is_primary INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS product_variations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id),
        sku TEXT,
        price DECIMAL(10,2) DEFAULT 0,
        sale_price DECIMAL(10,2),
        stock_quantity INTEGER DEFAULT 0,
        stock_status TEXT DEFAULT 'in_stock',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS variation_attribute_values (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        variation_id UUID NOT NULL REFERENCES product_variations(id),
        attribute_value_id UUID NOT NULL REFERENCES attribute_values(id)
    )""",

    """CREATE TABLE IF NOT EXISTS product_attributes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id),
        attribute_id UUID NOT NULL REFERENCES attributes(id),
        display_order INTEGER DEFAULT 0
    )""",

    """CREATE TABLE IF NOT EXISTS product_attribute_values (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id),
        attribute_value_id UUID NOT NULL REFERENCES attribute_values(id)
    )""",

    """CREATE TABLE IF NOT EXISTS product_reviews (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        product_id UUID NOT NULL REFERENCES products(id),
        user_id UUID REFERENCES users(id),
        rating INTEGER DEFAULT 5,
        title TEXT DEFAULT '',
        body TEXT DEFAULT '',
        is_approved INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS orders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id),
        status TEXT DEFAULT 'pending',
        total_amount DECIMAL(10,2) DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS order_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        order_id UUID NOT NULL REFERENCES orders(id),
        product_id UUID REFERENCES products(id),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    """CREATE TABLE IF NOT EXISTS coupons (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        is_default INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 3. Add columns to orders
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_method TEXT DEFAULT 'cod'",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'pending'",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS order_number TEXT",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMP",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancel_reason TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_address_json TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_name TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_email TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS customer_phone TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",

    # 4. Order items updates
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS variation_id TEXT",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS quantity INTEGER DEFAULT 1",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS unit_price DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS total_price DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE order_items ADD COLUMN IF NOT EXISTS product_name_snapshot TEXT DEFAULT ''",

    # 5. Data updates
    """UPDATE orders
       SET order_number = 'ORD-' || UPPER(SUBSTRING(encode(gen_random_bytes(6), 'hex'), 1, 12))
       WHERE order_number IS NULL OR order_number = ''""",

    # 6. Triggers (PostgreSQL PL/pgSQL)
    """CREATE OR REPLACE FUNCTION trg_sync_variation_pricing_fn()
       RETURNS TRIGGER AS $$
       BEGIN
           UPDATE product_variations
              SET price = (SELECT COALESCE(price, 0) FROM products WHERE id = NEW.product_id),
                  sale_price = (SELECT sale_price FROM products WHERE id = NEW.product_id),
                  stock_quantity = (SELECT COALESCE(stock_quantity, 0) FROM products WHERE id = NEW.product_id)
            WHERE id = NEW.id;
           RETURN NEW;
       END;
       $$ LANGUAGE plpgsql;

       DROP TRIGGER IF EXISTS trg_sync_variation_pricing ON product_variations;
       CREATE TRIGGER trg_sync_variation_pricing
           AFTER INSERT ON product_variations
           FOR EACH ROW
           EXECUTE FUNCTION trg_sync_variation_pricing_fn();""",

    """CREATE OR REPLACE FUNCTION trg_sync_variations_from_product_fn()
       RETURNS TRIGGER AS $$
       BEGIN
           UPDATE product_variations
              SET price = COALESCE(NEW.price, 0),
                  sale_price = NEW.sale_price,
                  stock_quantity = COALESCE(NEW.stock_quantity, 0)
            WHERE product_id = NEW.id;
           RETURN NEW;
       END;
       $$ LANGUAGE plpgsql;

       DROP TRIGGER IF EXISTS trg_sync_variations_from_product ON products;
       CREATE TRIGGER trg_sync_variations_from_product
           AFTER UPDATE OF price, sale_price, stock_quantity ON products
           FOR EACH ROW
           EXECUTE FUNCTION trg_sync_variations_from_product_fn();""",

    """CREATE OR REPLACE FUNCTION trg_set_order_number_if_missing_fn()
       RETURNS TRIGGER AS $$
       BEGIN
           IF NEW.order_number IS NULL OR NEW.order_number = '' THEN
               UPDATE orders
                  SET order_number = 'ORD-' || UPPER(SUBSTRING(encode(gen_random_bytes(6), 'hex'), 1, 12))
                WHERE id = NEW.id;
           END IF;
           RETURN NEW;
       END;
       $$ LANGUAGE plpgsql;

       DROP TRIGGER IF EXISTS trg_set_order_number_if_missing ON orders;
       CREATE TRIGGER trg_set_order_number_if_missing
           AFTER INSERT ON orders
           FOR EACH ROW
           WHEN (NEW.order_number IS NULL OR NEW.order_number = '')
           EXECUTE FUNCTION trg_set_order_number_if_missing_fn();""",

    # 7. Initial Settings
    """INSERT INTO store_settings (key, value) VALUES
         ('cod_enabled','true'), ('online_payment_enabled','false'),
         ('upi_id',''), ('bank_name',''), ('bank_account',''), ('bank_ifsc',''),
         ('razorpay_key_id',''), ('razorpay_key_secret','')
         ON CONFLICT (key) DO NOTHING""",

    """INSERT INTO store_settings (key, value) VALUES
         ('shipping_fee','99'),
         ('free_shipping_threshold','999'),
         ('free_shipping_enabled','true'),
         ('free_shipping_all','false')
         ON CONFLICT (key) DO NOTHING""",

    # 8. Coupons — add columns the admin route expects
    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS min_order_amount DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS usage_limit INTEGER",
    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS usage_limit_per_user INTEGER DEFAULT 1",
    "ALTER TABLE coupons ADD COLUMN IF NOT EXISTS max_discount DECIMAL(10,2)",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS coupon_code TEXT DEFAULT ''",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS discount_amount DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal DECIMAL(10,2) DEFAULT 0",
    "ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_amount DECIMAL(10,2) DEFAULT 0",
    """CREATE TABLE IF NOT EXISTS coupon_usages (
        id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
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
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        email TEXT UNIQUE NOT NULL,
        subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 11. Variation system — type classification for attributes
    "ALTER TABLE attributes ADD COLUMN IF NOT EXISTS variation_type TEXT DEFAULT 'secondary'",

    # 12. Product family grouping (for primary variations like flavours)
    "ALTER TABLE products ADD COLUMN IF NOT EXISTS family_id UUID REFERENCES products(id)",
    "CREATE INDEX IF NOT EXISTS idx_products_family_id ON products(family_id)",

    # 13. Variation-level images
    """CREATE TABLE IF NOT EXISTS variation_images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        variation_id UUID NOT NULL REFERENCES product_variations(id),
        media_id UUID NOT NULL REFERENCES media(id),
        is_primary INTEGER DEFAULT 0,
        display_order INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_variation_images_var ON variation_images(variation_id)",

    # 14. Per-variation product details
    "ALTER TABLE product_variations ADD COLUMN IF NOT EXISTS name TEXT DEFAULT ''",
    "ALTER TABLE product_variations ADD COLUMN IF NOT EXISTS short_description TEXT DEFAULT ''",
    "ALTER TABLE product_variations ADD COLUMN IF NOT EXISTS description TEXT DEFAULT ''",

    # 15. Blog
    """CREATE TABLE IF NOT EXISTS blog_posts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        title TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        excerpt TEXT DEFAULT '',
        content TEXT DEFAULT '',
        image_url TEXT DEFAULT '',
        author TEXT DEFAULT 'Admin',
        published INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",
    "CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug)",
    "CREATE INDEX IF NOT EXISTS idx_blog_posts_published ON blog_posts(published)",

    # 16. Contact messages
    """CREATE TABLE IF NOT EXISTS contact_messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        message TEXT NOT NULL,
        is_read INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""",

    # 17. Google OAuth support
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_id TEXT UNIQUE",
    "ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL",

    # 18. Password reset OTPs
    """CREATE TABLE IF NOT EXISTS password_reset_otps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL REFERENCES users(id),
        otp TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        is_used INTEGER DEFAULT 0
    )""",
    "CREATE INDEX IF NOT EXISTS idx_password_reset_user_id ON password_reset_otps(user_id)",
]

def migrate():
    for sql in _MIGRATIONS:
        try:
            execute(sql, [])
        except Exception as e:
            # Ignore errors gracefully (duplicate columns, etc.)
            pass
