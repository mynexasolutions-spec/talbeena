"""
seed.py — Populate the database with test data for Talbeena.
Run:    python seed.py
"""
import uuid
import bcrypt
import db

print("Seeding database...")

# ── 1. Admin user ─────────────────────────────────────────────────────────────
hashed = bcrypt.hashpw("admin123"[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
db.execute(
    "INSERT INTO users (id, first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?,?)",
    [str(uuid.uuid4()), "Admin", "User", "admin@talbeena.com", hashed, "admin"],
)
print("✓ Admin user created (admin@talbeena.com / admin123)")

# ── 2. Categories ─────────────────────────────────────────────────────────────
cat_barley  = str(uuid.uuid4())
cat_drinks  = str(uuid.uuid4())
cat_snacks  = str(uuid.uuid4())
db.execute("INSERT INTO categories (id, name, slug, is_active, is_featured, display_order) VALUES (?,?,?,1,1,1)", [cat_barley, "Barley Products", "barley-products"])
db.execute("INSERT INTO categories (id, name, slug, parent_id, is_active, display_order) VALUES (?,?,?,?,1,2)", [cat_drinks, "Talbeena Drinks", "talbeena-drinks", cat_barley])
db.execute("INSERT INTO categories (id, name, slug, parent_id, is_active, display_order) VALUES (?,?,?,?,1,3)", [cat_snacks, "Talbeena Snacks", "talbeena-snacks", cat_barley])
print("✓ Categories created")

# ── 3. Attributes ─────────────────────────────────────────────────────────────
# Primary: Flavor
attr_flavor = str(uuid.uuid4())
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'primary',1)", [attr_flavor, "Flavor", "flavor"])
# Secondary: Weight
attr_weight = str(uuid.uuid4())
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'secondary',2)", [attr_weight, "Weight", "weight"])
# Optional: Add-ons
attr_addon = str(uuid.uuid4())
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'optional',3)", [attr_addon, "Add-ons", "addons"])

# ── Attribute Values ─────────────────────────────────────────────────────────
flavors = ["Chocolate", "Vanilla", "Strawberry", "Saffron", "Cardamom"]
flavor_ids = {}
for f in flavors:
    fid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [fid, attr_flavor, f])
    flavor_ids[f] = fid

weights = ["250g", "500g", "1kg", "2kg"]
weight_ids = {}
for w in weights:
    wid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [wid, attr_weight, w])
    weight_ids[w] = wid

addons = ["Gift Wrapping", "Sugar-Free", "Extra Nuts"]
addon_ids = {}
for a in addons:
    aid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)", [aid, attr_addon, a])
    addon_ids[a] = aid
print("✓ Attributes and values created")

# ── 4. Variable Product: Talbeena Drink Mix ───────────────────────────────────
prod_id = str(uuid.uuid4())
db.execute(
    """INSERT INTO products (id, name, slug, sku, type, description, short_description,
       price, stock_quantity, stock_status, category_id, is_featured, is_active)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
    [prod_id, "Talbeena Drink Mix", "talbeena-drink-mix", "TLB-DM-001", "variable",
     "A nourishing barley-based drink mix available in multiple flavors. "
     "Rich in fiber and naturally sweetened. Perfect hot or cold.\n\n"
     "•- Key Ingredients :- Barley extract, natural flavors, stevia\n"
     "•- Shelf Life :- 12 months\n"
     "•- Preparation :- Mix 2 tbsp with warm water or milk",
     "Delicious barley drink mix in 5 flavors, 4 sizes.",
     299, 100, "in_stock", cat_drinks, 1, 1],
)

# Link attributes to product
db.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, attr_flavor])
db.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, attr_weight])
db.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, attr_addon])

# Link attribute values to product
for f in flavors:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, flavor_ids[f]])
for w in weights:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, weight_ids[w]])
for a in addons:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)", [str(uuid.uuid4()), prod_id, addon_ids[a]])

# Generate variations (calls our new generate_variations logic)
from routes.admin import generate_variations
generate_variations(prod_id)
print("✓ Variable product created with variations")

# ── 5. Simple Products ────────────────────────────────────────────────────────
simple_products = [
    ("Talbeena Barley Flour", "talbeena-barley-flour", "TLB-BF-001", "Pure stone-ground barley flour for baking.", 199, cat_snacks),
    ("Talbeena Energy Bites", "talbeena-energy-bites", "TLB-EB-001", "On-the-go barley energy bites with dates and nuts.", 349, cat_snacks),
    ("Talbeena Roasted Barley Tea", "talbeena-roasted-barley-tea", "TLB-RT-001", "Traditional roasted barley tea bags – 20 count.", 249, cat_drinks),
]
for name, slug, sku, desc, price, cat_id in simple_products:
    db.execute(
        """INSERT INTO products (id, name, slug, sku, type, description, price, stock_quantity, stock_status, category_id, is_active)
           VALUES (?,?,?,?,'simple',?,?,?,?,?,1)""",
        [str(uuid.uuid4()), name, slug, sku, desc, price, 50, "in_stock", cat_id],
    )
print("✓ Simple products created")

# ── 6. Store Settings ─────────────────────────────────────────────────────────
db.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES ('store_name', 'Talbeena')")
db.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES ('store_email', 'hello@talbeena.com')")
print("✓ Store settings configured")

print("\n🎉 Seed complete! Start the app with:  python app.py")
print("   Admin login: admin@talbeena.com / admin123")
