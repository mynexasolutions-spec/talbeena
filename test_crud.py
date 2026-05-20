"""
test_crud.py — CRUD test suite for Talbeena admin.
Run: python test_crud.py
"""
import os, sys, io, uuid, shutil

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "talbeena.db")
DB_BACKUP = os.path.join(BASE_DIR, "talbeena.db.backup")

print("=" * 60)
print("TALBEENA CRUD TEST SUITE")
print("=" * 60)

# ── 0. Fresh DB ───────────────────────────────────────────────────────────────
if os.path.exists(DB_PATH):
    shutil.copy2(DB_PATH, DB_BACKUP)
    os.remove(DB_PATH)
    print("[SETUP] Fresh database.")

os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from app import create_app

app = create_app()
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False
app.config["SERVER_NAME"] = "localhost"

import db as db_module
db_module.migrate()
print("[SETUP] Migrations complete.")

client = app.test_client()

# ── 1. Helpers ────────────────────────────────────────────────────────────────
passed = 0
failed = 0

def ok(name):
    global passed
    passed += 1
    print(f"  ✅ {name}")

def fail(name, reason=""):
    global failed
    msg = f"  ❌ {name}"
    if reason:
        msg += f" — {reason}"
    print(msg)

def post(url, data=None, **kw):
    return client.post(url, data=data or {}, **kw)

def get(url):
    return client.get(url)

def login_as_admin():
    import bcrypt
    pw = bcrypt.hashpw("TestPass123!".encode(), bcrypt.gensalt()).decode()
    uid = str(uuid.uuid4())
    db_module.execute(
        "INSERT OR IGNORE INTO users (id, first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?,?)",
        [uid, "Admin", "User", "admin@talbeena.com", pw, "admin"]
    )
    user = db_module.query_one("SELECT * FROM users WHERE email=?", ["admin@talbeena.com"])
    with client.session_transaction() as sess:
        sess["user"] = dict(user)

login_as_admin()
print("[SETUP] Admin logged in.\n")

from routes.admin import generate_variations

# ── 2. Phase 1: Categories ────────────────────────────────────────────────────
print("── Phase 1: Categories ──")

r = post("/admin/categories/new", {"name": "Barley-Based", "slug": "barley-based"})
cat = db_module.query_one("SELECT * FROM categories WHERE slug='barley-based'")
if cat: ok("T1: Create category")
else: fail("T1: Create category")

if cat:
    post(f"/admin/categories/{cat['id']}/edit", {"name": "Barley Products", "slug": "barley-products"})
    updated = db_module.query_one("SELECT * FROM categories WHERE id=?", [cat["id"]])
    if updated and updated["name"] == "Barley Products":
        ok("T2: Edit category")
    else:
        fail("T2: Edit category")

    post(f"/admin/categories/{cat['id']}/delete")
    deleted = db_module.query_one("SELECT * FROM categories WHERE id=?", [cat["id"]])
    if deleted is None:
        ok("T3: Delete category")
    else:
        fail("T3: Delete category")

# ── 3. Phase 2: Brands ────────────────────────────────────────────────────────
print("\n── Phase 2: Brands ──")

brand_id = str(uuid.uuid4())
db_module.execute("INSERT INTO brands (id, name, slug) VALUES (?,?,?)",
    [brand_id, "Talbeena Originals", "talbeena-originals"])
brand = db_module.query_one("SELECT * FROM brands WHERE slug='talbeena-originals'")
ok("T4: Create brand") if brand else fail("T4: Create brand")

if brand:
    post(f"/admin/brands/{brand_id}/edit", {"name": "TBO", "slug": "tbo"})
    updated = db_module.query_one("SELECT * FROM brands WHERE id=?", [brand_id])
    ok("T5: Edit brand") if updated and updated["name"] == "TBO" else fail("T5: Edit brand")

    post(f"/admin/brands/{brand_id}/delete")
    deleted = db_module.query_one("SELECT * FROM brands WHERE id=?", [brand_id])
    ok("T6: Delete brand") if deleted is None else fail("T6: Delete brand")

# Recreate brand for product tests
brand_id = str(uuid.uuid4())
db_module.execute("INSERT INTO brands (id, name, slug) VALUES (?,?,?)",
    [brand_id, "Talbeena Originals", "talbeena-originals"])

# Create a category for product tests
cat_id = str(uuid.uuid4())
db_module.execute("INSERT INTO categories (id, name, slug) VALUES (?,?,?)",
    [cat_id, "Porridge", "porridge"])

# ── 4. Phase 3: Attributes & Values ───────────────────────────────────────────
print("\n── Phase 3: Attributes & Values ──")

flavor_id = str(uuid.uuid4())
db_module.execute("INSERT INTO attributes (id, name, slug, variation_type) VALUES (?,?,?,?)",
    [flavor_id, "Flavor", "flavor", "primary"])
ok("T7: Create Flavor attribute") if db_module.query_one("SELECT * FROM attributes WHERE slug='flavor'") else fail("T7")

weight_id = str(uuid.uuid4())
db_module.execute("INSERT INTO attributes (id, name, slug, variation_type) VALUES (?,?,?,?)",
    [weight_id, "Weight", "weight", "secondary"])
ok("T8: Create Weight attribute") if db_module.query_one("SELECT * FROM attributes WHERE slug='weight'") else fail("T8")

# Add values
choc_id = str(uuid.uuid4())
vanilla_id = str(uuid.uuid4())
g500_id = str(uuid.uuid4())
kg1_id = str(uuid.uuid4())

db_module.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [choc_id, flavor_id, "Chocolate"])
db_module.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [vanilla_id, flavor_id, "Vanilla"])
db_module.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [g500_id, weight_id, "500g"])
db_module.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [kg1_id, weight_id, "1kg"])

flavor_vals = len(db_module.query("SELECT * FROM attribute_values WHERE attribute_id=?", [flavor_id]))
weight_vals = len(db_module.query("SELECT * FROM attribute_values WHERE attribute_id=?", [weight_id]))
ok("T9: Add attribute values") if flavor_vals == 2 and weight_vals == 2 else fail("T9", f"flavor={flavor_vals}, weight={weight_vals}")

# Bulk edit
db_module.execute("UPDATE attribute_values SET value='500 gm' WHERE id=?", [g500_id])
v = db_module.query_one("SELECT value FROM attribute_values WHERE id=?", [g500_id])
ok("T10: Bulk edit value") if v and v["value"] == "500 gm" else fail("T10")

# ── 5. Phase 4: Simple Product ────────────────────────────────────────────────
print("\n── Phase 4: Simple Product ──")

simple_id = str(uuid.uuid4())
db_module.execute(
    """INSERT INTO products (id, name, slug, sku, type, price, stock_quantity, category_id, brand_id, is_active)
       VALUES (?,?,?,?,?,?,?,?,?,1)""",
    [simple_id, "Talbeena Starter Kit", "starter-kit", "TSK-001", "simple", 499, 100, cat_id, brand_id])
p = db_module.query_one("SELECT * FROM products WHERE slug='starter-kit'")
ok("T11: Create simple product") if p else fail("T11")

# Edit via admin route
post(f"/admin/products/{simple_id}/edit", {
    "name": "Talbeena Starter Kit", "slug": "starter-kit", "type": "simple",
    "price": "599", "stock_quantity": "80", "stock_status": "in_stock"
})
p2 = db_module.query_one("SELECT price FROM products WHERE id=?", [simple_id])
ok("T12: Edit product price") if p2 and float(p2["price"]) == 599.0 else fail("T12", f"price={p2}")

# ── 6. Phase 5: Variable Product ──────────────────────────────────────────────
print("\n── Phase 5: Variable Product + Variations ──")

var_id = str(uuid.uuid4())
db_module.execute(
    """INSERT INTO products (id, name, slug, sku, type, price, stock_quantity, category_id, brand_id, is_active)
       VALUES (?,?,?,?,?,?,?,?,?,1)""",
    [var_id, "Talbeena Porridge", "talbeena-porridge", "TP-001", "variable", 299, 200, cat_id, brand_id])
ok("T13: Create variable product") if db_module.query_one("SELECT * FROM products WHERE slug='talbeena-porridge'") else fail("T13")

# Link attributes and values
db_module.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)",
    [str(uuid.uuid4()), var_id, flavor_id])
db_module.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)",
    [str(uuid.uuid4()), var_id, weight_id])
for v in [choc_id, vanilla_id, g500_id, kg1_id]:
    db_module.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)",
        [str(uuid.uuid4()), var_id, v])

ok("T14: Link attributes to product") if len(db_module.query(
    "SELECT * FROM product_attribute_values WHERE product_id=?", [var_id])) == 4 else fail("T14")

# Generate variations
generate_variations(var_id)
variations = db_module.query("SELECT * FROM product_variations WHERE product_id=?", [var_id])
ok("T15: Generate variations (4 expected)") if len(variations) == 4 else fail("T15", f"got {len(variations)}")

if variations:
    # Each variation should have 2 attribute links
    link_counts = [len(db_module.query(
        "SELECT * FROM variation_attribute_values WHERE variation_id=?", [v["id"]]
    )) for v in variations]
    ok("T16: Variation attribute links") if all(c == 2 for c in link_counts) else fail("T16", str(link_counts))

    # Bulk update first variation
    v0 = variations[0]
    post(f"/admin/products/{var_id}/variations/bulk_update", {
        f"price_{v0['id']}": "349",
        f"stock_{v0['id']}": "60",
        f"sku_{v0['id']}": "TP-CHOC-500",
        f"name_{v0['id']}": "Chocolate 500g"
    })
    v0u = db_module.query_one("SELECT price, stock_quantity, name, sku FROM product_variations WHERE id=?", [v0["id"]])
    if v0u and float(v0u["price"]) == 349.0 and int(v0u["stock_quantity"]) == 60 and v0u["name"] == "Chocolate 500g":
        ok("T17: Bulk update variation")
    else:
        fail("T17", str(v0u))

# ── 7. Phase 6: Type Change ───────────────────────────────────────────────────
print("\n── Phase 6: Type Change ──")

# Variable → Simple
post(f"/admin/products/{var_id}/edit", {
    "name": "Talbeena Porridge", "slug": "talbeena-porridge", "type": "simple",
    "price": "299", "stock_quantity": "200", "stock_status": "in_stock"
})
var_count = len(db_module.query("SELECT * FROM product_variations WHERE product_id=?", [var_id]))
ok("T18: Variable → Simple deletes variations") if var_count == 0 else fail("T18", f"still {var_count} variations")

# Simple → Variable
post(f"/admin/products/{var_id}/edit", {
    "name": "Talbeena Porridge", "slug": "talbeena-porridge", "type": "variable",
    "price": "299", "stock_quantity": "200", "stock_status": "in_stock",
    "attribute_ids": [flavor_id, weight_id],
    "attribute_value_ids": [choc_id, vanilla_id, g500_id, kg1_id]
})
var_count2 = len(db_module.query("SELECT * FROM product_variations WHERE product_id=?", [var_id]))
ok("T19: Simple → Variable regenerates") if var_count2 == 4 else fail("T19", f"got {var_count2}")

# ── 8. Phase 7: Soft Delete ───────────────────────────────────────────────────
print("\n── Phase 7: Soft Delete ──")

post(f"/admin/products/{var_id}/delete")
p_del = db_module.query_one("SELECT is_active FROM products WHERE id=?", [var_id])
ok("T20: Soft delete product") if p_del and int(p_del["is_active"]) == 0 else fail("T20")

# ── 9. Phase 8: Cascade Delete ────────────────────────────────────────────────
print("\n── Phase 8: Cascade Delete ──")

post(f"/admin/attributes/values/{choc_id}/delete", {"attribute_id": flavor_id})
choc_exists = db_module.query_one("SELECT * FROM attribute_values WHERE id=?", [choc_id])
pav_links = len(db_module.query("SELECT * FROM product_attribute_values WHERE attribute_value_id=?", [choc_id]))
vav_links = len(db_module.query("SELECT * FROM variation_attribute_values WHERE attribute_value_id=?", [choc_id]))
ok("T21: Cascade delete attribute value") if (choc_exists is None and pav_links == 0 and vav_links == 0) else fail("T21")

# ── 10. Phase 9: Coupon Validation ────────────────────────────────────────────
print("\n── Phase 9: Coupon Validation ──")

r = post("/admin/coupons/new", {"code": "", "type": "percentage", "value": "10"})
ok("T22: Reject empty coupon code") if b"required" in r.data else fail("T22")

r = post("/admin/coupons/new", {"code": "TEST10", "type": "flat", "value": "10"})
ok("T23: Reject invalid type") if b"must be" in r.data else fail("T23")

post("/admin/coupons/new", {"code": "SAVE20", "type": "percentage", "value": "20",
    "min_order_amount": "500", "usage_limit_per_user": "1", "is_active": "on"})
ok("T24: Create valid coupon") if db_module.query_one("SELECT * FROM coupons WHERE code='SAVE20'") else fail("T24")

r = post("/admin/coupons/new", {"code": "SAVE20", "type": "percentage", "value": "15"})
ok("T25: Reject duplicate coupon") if b"already exists" in r.data else fail("T25")

# ── 11. Phase 10: Cache ───────────────────────────────────────────────────────
print("\n── Phase 10: Cache Invalidation ──")

from queries import get_products

# Use raw DB count since get_products expands variable products
before = db_module.query_one("SELECT COUNT(*) as cnt FROM products WHERE is_active=1")["cnt"]
get_products.cache_clear()
db_module.execute("INSERT INTO products (id, name, slug, sku, type, price, stock_quantity, is_active) VALUES (?,?,?,?,?,?,?,1)",
    [str(uuid.uuid4()), "Cache Test", "cache-test-final", "CT-099", "simple", 99, 10])
get_products.cache_clear()
after = db_module.query_one("SELECT COUNT(*) as cnt FROM products WHERE is_active=1")["cnt"]
if after == before + 1:
    ok("T26: Cache clears on new product")
else:
    fail("T26", f"{before}→{after}")

# ── 12. Summary ───────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
total = passed + failed
if failed == 0:
    print(f"RESULTS: {passed}/{total} passed — 🎉 ALL PASSED!")
else:
    print(f"RESULTS: {passed}/{total} passed — ⚠️  {failed} FAILED")
print("=" * 60)

# Restore original DB
if os.path.exists(DB_BACKUP):
    os.remove(DB_PATH)
    if os.path.exists(DB_BACKUP):
        os.rename(DB_BACKUP, DB_PATH)
        print("\n[CLEANUP] Restored original database.")

sys.exit(0 if failed == 0 else 1)
