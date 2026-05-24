# ORM Migration Plan — Talbeena

## Goal
Replace raw SQL (`db.py` + `queries.py`) with **SQLAlchemy ORM** so database changes become a single `flask db upgrade` command — no more manual SQL rewriting.

---

## Phase 1: Infrastructure (~15 min)

### 1.1 Install packages
```bash
pip install flask-sqlalchemy flask-migrate
```

### 1.2 Add to `extensions.py`
```python
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db_sql = SQLAlchemy()
migrate = Migrate()
```

### 1.3 Connect in `app.py`
```python
from extensions import db_sql, migrate

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db_sql.init_app(app)
migrate.init_app(app, db_sql)
```

### 1.4 Initialize Alembic
```bash
flask db init
flask db migrate -m "initial models"
flask db upgrade
```

This creates a `migrations/` folder. Future schema changes: just edit models → `flask db migrate -m "what changed"` → `flask db upgrade`.

---

## Phase 2: Models (~1 hour)

Create `models/` folder with model classes. The 22 existing tables become:

### `models/user.py`
- User, UserAddress

### `models/product.py`
- Category, Brand, Product, ProductImage, ProductVariation, VariationAttributeValue, ProductAttribute, ProductAttributeValue, Media, VariationImage

### `models/order.py`
- Order, OrderItem, Coupon, CouponUsage

### `models/blog.py`
- BlogPost

### `models/store.py`
- StoreSetting, NewsletterSubscriber

### `models/review.py`
- ProductReview

Each model maps to the existing PostgreSQL table (set `__tablename__` to match). No data migration needed since the schema is already deployed.

---

## Phase 3: Gradual Query Rewrite (~1-2 hours)

**Strategy:** Keep existing `db.py` + `queries.py` running alongside SQLAlchemy. Rewrite one module at a time.

| Priority | Module | Why First |
|----------|--------|-----------|
| 1 | `admin.py` routes | Most complex queries, biggest benefit |
| 2 | `queries.py` (shop/product listing) | Core customer-facing queries |
| 3 | `cart.py` + `checkout.py` | Order operations need reliability |
| 4 | `auth.py` | Simple queries, low risk |
| 5 | `blog.py` | Simplest, do last |

### Example rewrite
**Before (raw SQL):**
```python
db.query("SELECT * FROM products WHERE is_active = ? ORDER BY created_at DESC", [1])
```

**After (ORM):**
```python
Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).all()
```

---

## Phase 4: Cleanup (~30 min)

- Remove `db.py` raw SQL helper once all queries are migrated
- Remove `queries.py` or convert remaining functions
- Remove `db.migrate()` startup code
- Remove `test_crud.py` (replace with proper fixture-based tests)

---

## Timeline

| Phase | Time | Who |
|-------|------|-----|
| 1. Infrastructure | 15 min | Me |
| 2. Models | 1 hour | Me |
| 3. Query rewrite | 1-2 hours | You + Me |
| 4. Cleanup | 30 min | Me |

**Total: ~3-4 hours**, can be split across multiple sessions.

---

## Benefits
- **Zero migration pain** — switching DB is a one-line config change
- **No more `?` vs `%s`**, no `GROUP_CONCAT` vs `STRING_AGG`
- **Relationships auto-loaded** — `product.images`, `order.items` without writing JOINs
- **Alembic migrations** — schema versions tracked, rollbacks possible
- **Validation** — model-level type checking catches bugs early

## Drawbacks
- Learning curve (SQLAlchemy has its own quirks)
- Existing raw SQL works alongside ORM during migration (two ways to do the same thing temporarily)
