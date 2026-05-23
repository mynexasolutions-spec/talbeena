"""
seed.py — Populate the database with test data for Talbeena.
Run:    python seed.py
"""
import uuid
import bcrypt
import db

print("Seeding database...")

# ── Helper: create a media row and return its ID ──────────────────────────────
def create_media(filename):
    mid = str(uuid.uuid4())
    db.execute("INSERT INTO media (id, file_url) VALUES (?,?)",
               [mid, f"images/{filename}"])
    return mid

# ── 0. Clear existing data (for re-runs) ──────────────────────────────────────
for table in ["variation_images", "variation_attribute_values", "product_variations",
              "product_attribute_values", "product_attributes", "product_images",
              "order_items", "coupon_usages", "coupons", "orders",
              "user_addresses", "attribute_values", "attributes",
              "products", "categories", "brands", "media"]:
    try: db.execute(f"DELETE FROM {table}", [])
    except: pass
print("✓ Content data cleared (users preserved)")

# ── 1. Admin user (skip if exists) ────────────────────────────────────────────
admin = db.query_one("SELECT id FROM users WHERE email='admin@talbeena.com'")
if not admin:
    hashed = bcrypt.hashpw("admin123"[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    db.execute(
        "INSERT INTO users (id, first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?,?)",
        [str(uuid.uuid4()), "Admin", "User", "admin@talbeena.com", hashed, "admin"],
    )
    print("✓ Admin user created (admin@talbeena.com / admin123)")
else:
    print("ℹ️  Admin user already exists")

# ── 2. Media entries for sample images ────────────────────────────────────────
image_files = [
    "sample1.png", "sample2.jpg", "sample3.webp", "sample4.webp",
    "sample5.webp", "sample6.webp", "sample7.webp", "sample8.jpg",
    "sample9.webp", "sample10.jpg", "sample11.png",
]
media_ids = {f: create_media(f) for f in image_files}
print(f"✓ {len(media_ids)} media entries created")

# ── 3. Categories ─────────────────────────────────────────────────────────────
cat_barley = str(uuid.uuid4())
cat_drinks = str(uuid.uuid4())
cat_snacks = str(uuid.uuid4())
db.execute("INSERT INTO categories (id, name, slug, image_url, is_active, is_featured, display_order) VALUES (?,?,?,?,1,1,1)",
           [cat_barley, "Barley Products", "barley-products", "images/sample4.webp"])
db.execute("INSERT INTO categories (id, name, slug, parent_id, image_url, is_active, display_order) VALUES (?,?,?,?,?,1,2)",
           [cat_drinks, "Talbeena Drinks", "talbeena-drinks", cat_barley, "images/sample5.webp"])
db.execute("INSERT INTO categories (id, name, slug, parent_id, image_url, is_active, display_order) VALUES (?,?,?,?,?,1,3)",
           [cat_snacks, "Talbeena Snacks", "talbeena-snacks", cat_barley, "images/sample6.webp"])
print("✓ Categories created (with images)")

# ── 4. Attributes ─────────────────────────────────────────────────────────────
attr_flavor = str(uuid.uuid4())
attr_weight = str(uuid.uuid4())
attr_addon  = str(uuid.uuid4())
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'primary',1)",
           [attr_flavor, "Flavor", "flavor"])
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'secondary',2)",
           [attr_weight, "Weight", "weight"])
db.execute("INSERT INTO attributes (id, name, slug, variation_type, display_order) VALUES (?,?,?,'optional',3)",
           [attr_addon, "Add-ons", "addons"])

# ── Attribute Values (with swatch images for flavors) ─────────────────────────
flavor_swatches = ["sample2.jpg", "sample3.webp", "sample4.webp", "sample5.webp", "sample6.webp"]
flavors = ["Chocolate", "Vanilla", "Strawberry", "Saffron", "Cardamom"]
flavor_ids = {}
for i, f_name in enumerate(flavors):
    fid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value, image_url) VALUES (?,?,?,?)",
               [fid, attr_flavor, f_name, f"images/{flavor_swatches[i]}"])
    flavor_ids[f_name] = fid

weights = ["250g", "500g", "1kg", "2kg"]
weight_ids = {}
for w in weights:
    wid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)",
               [wid, attr_weight, w])
    weight_ids[w] = wid

addons = ["Gift Wrapping", "Sugar-Free", "Extra Nuts"]
addon_ids = {}
for a in addons:
    aid = str(uuid.uuid4())
    db.execute("INSERT INTO attribute_values (id, attribute_id, value) VALUES (?,?,?)",
               [aid, attr_addon, a])
    addon_ids[a] = aid
print("✓ Attributes and values created (flavors have swatch images)")

# ── 5. Variable Product: Talbeena Drink Mix ───────────────────────────────────
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

# Primary product image
db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,1,0)",
           [str(uuid.uuid4()), prod_id, media_ids["sample1.png"]])

# Gallery images
for fname in ["sample7.webp", "sample8.jpg", "sample9.webp"]:
    db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,0,1)",
               [str(uuid.uuid4()), prod_id, media_ids[fname]])

# Link attributes
for aid in [attr_flavor, attr_weight, attr_addon]:
    db.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)",
               [str(uuid.uuid4()), prod_id, aid])

# Link values
for f in flavors:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)",
               [str(uuid.uuid4()), prod_id, flavor_ids[f]])
for w in weights:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)",
               [str(uuid.uuid4()), prod_id, weight_ids[w]])
for a in addons:
    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)",
               [str(uuid.uuid4()), prod_id, addon_ids[a]])

# Generate variations
from routes.admin import generate_variations
generate_variations(prod_id)
print("✓ Variable product created with images & variations")

# ── Assign images to variations by flavor ──
variations = db.query("SELECT pv.id, av.value as flavor FROM product_variations pv "
                      "JOIN variation_attribute_values vav ON vav.variation_id = pv.id "
                      "JOIN attribute_values av ON av.id = vav.attribute_value_id "
                      "JOIN attributes a ON a.id = av.attribute_id "
                      "WHERE pv.product_id = ? AND a.variation_type = 'primary'",
                      [prod_id])

# Map each flavor to a set of gallery images
flavor_gallery = {
    "Chocolate":  ["sample7.webp", "sample8.jpg"],
    "Vanilla":    ["sample9.webp", "sample1.png"],
    "Strawberry": ["sample10.jpg", "sample11.png"],
    "Saffron":    ["sample2.jpg", "sample3.webp"],
    "Cardamom":   ["sample4.webp", "sample5.webp"],
}

vi_count = 0
for v in variations:
    flavor = v["flavor"]
    imgs = flavor_gallery.get(flavor, ["sample6.webp"])
    for idx, fname in enumerate(imgs):
        db.execute(
            "INSERT INTO variation_images (id, variation_id, media_id, is_primary, display_order) "
            "VALUES (?,?,?,?,?)",
            [str(uuid.uuid4()), v["id"], media_ids.get(fname, list(media_ids.values())[0]),
             1 if idx == 0 else 0, idx],
        )
        vi_count += 1

print(f"✓ Variable product created with images, variations & {vi_count} variation images")

# ── Set per-flavor descriptions ──
flavor_descriptions = {
    "Chocolate":  (
        "<h3>Chocolate Talbeena</h3>"
        "<p>Rich, velvety cocoa blended with pure barley for a comforting drink "
        "that satisfies your sweet cravings naturally.</p>"
        "<table class='desc-table'><tbody>"
        "<tr><td class='desc-key'>Flavor Profile</td><td class='desc-val'>Deep cocoa with malty undertones</td></tr>"
        "<tr><td class='desc-key'>Best Served</td><td class='desc-val'>Warm with a dash of milk</td></tr>"
        "</tbody></table>"
    ),
    "Vanilla": (
        "<h3>Vanilla Talbeena</h3>"
        "<p>Smooth, aromatic vanilla bean paired with wholesome barley — a classic "
        "flavor the whole family will love.</p>"
        "<table class='desc-table'><tbody>"
        "<tr><td class='desc-key'>Flavor Profile</td><td class='desc-val'>Creamy vanilla with subtle sweetness</td></tr>"
        "<tr><td class='desc-key'>Best Served</td><td class='desc-val'>Cold with ice or warm with honey</td></tr>"
        "</tbody></table>"
    ),
    "Strawberry": (
        "<h3>Strawberry Talbeena</h3>"
        "<p>Bright, fruity strawberry blended into nourishing barley — a refreshing "
        "twist on traditional talbeena.</p>"
        "<table class='desc-table'><tbody>"
        "<tr><td class='desc-key'>Flavor Profile</td><td class='desc-val'>Sweet berry with a hint of tartness</td></tr>"
        "<tr><td class='desc-key'>Best Served</td><td class='desc-val'>Chilled, garnished with fresh mint</td></tr>"
        "</tbody></table>"
    ),
    "Saffron": (
        "<h3>Saffron Talbeena</h3>"
        "<p>Luxurious Kashmiri saffron infused into pure barley — a golden, aromatic "
        "experience fit for special occasions.</p>"
        "<table class='desc-table'><tbody>"
        "<tr><td class='desc-key'>Flavor Profile</td><td class='desc-val'>Earthy saffron with floral notes</td></tr>"
        "<tr><td class='desc-key'>Best Served</td><td class='desc-val'>Warm, with crushed almonds on top</td></tr>"
        "</tbody></table>"
    ),
    "Cardamom": (
        "<h3>Cardamom Talbeena</h3>"
        "<p>Fragrant green cardamom pods ground with stone-milled barley — a soul-warming "
        "blend rooted in tradition.</p>"
        "<table class='desc-table'><tbody>"
        "<tr><td class='desc-key'>Flavor Profile</td><td class='desc-val'>Warm cardamom with a gentle spice kick</td></tr>"
        "<tr><td class='desc-key'>Best Served</td><td class='desc-val'>Hot, with a sprinkle of cinnamon</td></tr>"
        "</tbody></table>"
    ),
}

for flavor_name, desc_html in flavor_descriptions.items():
    if desc_html:
        # Batch-update all variations for this flavor
        db.execute(
            """UPDATE product_variations SET description = ?, short_description = ?
               WHERE id IN (
                   SELECT pv.id FROM product_variations pv
                   JOIN variation_attribute_values vav ON vav.variation_id = pv.id
                   JOIN attribute_values av ON av.id = vav.attribute_value_id
                   WHERE pv.product_id = ? AND av.value = ?
               )""",
            [desc_html, f"{flavor_name} Talbeena drink mix", prod_id, flavor_name],
        )

print(f"✓ Per-flavor descriptions set for {len(flavor_descriptions)} flavors")

# ── 6. Simple Products (with images) ──────────────────────────────────────────
simple_products = [
    ("Talbeena Barley Flour", "talbeena-barley-flour", "TLB-BF-001",
     "Pure stone-ground barley flour for baking. Perfect for breads, rotis, and traditional recipes.",
     199, cat_snacks, "sample10.jpg", ["sample11.png"]),
    ("Talbeena Energy Bites", "talbeena-energy-bites", "TLB-EB-001",
     "On-the-go barley energy bites with dates and nuts. A healthy snack for the whole family.",
     349, cat_snacks, "sample11.png", ["sample1.png"]),
    ("Talbeena Roasted Barley Tea", "talbeena-roasted-barley-tea", "TLB-RT-001",
     "Traditional roasted barley tea bags - 20 count. Caffeine-free, naturally nutty flavor.",
     249, cat_drinks, "sample9.webp", ["sample8.jpg"]),
]
for name, slug, sku, desc, price, cat_id, primary_img, gallery_imgs in simple_products:
    pid = str(uuid.uuid4())
    db.execute(
        """INSERT INTO products (id, name, slug, sku, type, description, price, stock_quantity, stock_status, category_id, is_active)
           VALUES (?,?,?,?,'simple',?,?,?,?,?,1)""",
        [pid, name, slug, sku, desc, price, 50, "in_stock", cat_id],
    )
    # Primary image
    db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,1,0)",
               [str(uuid.uuid4()), pid, media_ids[primary_img]])
    # Gallery
    for gimg in gallery_imgs:
        db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,0,1)",
                   [str(uuid.uuid4()), pid, media_ids[gimg]])
print("✓ Simple products created (with images)")

# ── 8. Blog Posts ─────────────────────────────────────────────────────────────
blog_posts = [
    {
        "title": "The Blessed Grain: Barley in the Quran and Sunnah",
        "slug": "barley-in-quran-sunnah",
        "excerpt": "Discover the profound significance of barley (sha'ir) in Islamic tradition and its mention in the teachings of Prophet Muhammad ﷺ.",
        "content": "<h2>Barley: A Prophet's Choice</h2><p>Throughout the Seerah, barley appears as a recurring theme — from the simple meals of the Prophet's household to his specific recommendations for healing. The Prophet ﷺ said: <em>'Talbeena gives rest to the heart of the patient and relieves him from some of his grief.'</em> (Sahih Al-Bukhari)</p><p>Barley was a staple food in Madinah, forming the basis of many meals in the Prophet's ﷺ home. Its affordability and nutritional density made it accessible to all, embodying the Islamic principle of moderation and gratitude for simple blessings.</p><h2>Nutritional Wisdom</h2><p>Modern science has confirmed what our predecessors knew instinctively. Barley is rich in beta-glucan, a soluble fiber that supports heart health, stabilizes blood sugar, and promotes digestive wellness. It's a complete package of nourishment — body and soul.</p><p>By choosing talbeena, you're not just choosing a healthy breakfast; you're reviving a Sunnah that has blessed millions over fourteen centuries.</p>",
        "author": "Admin"
    },
    {
        "title": "5 Ways to Enjoy Talbeena Beyond Breakfast",
        "slug": "talbeena-beyond-breakfast",
        "excerpt": "Think talbeena is just for mornings? Think again! Here are five creative ways to enjoy barley goodness throughout the day.",
        "content": "<h2>1. Talbeena Smoothie Bowl</h2><p>Blend prepared talbeena with frozen banana, a handful of spinach, and a splash of almond milk. Top with granola, sliced almonds, and a drizzle of honey for a refreshing twist.</p><h2>2. Savoury Talbeena Porridge</h2><p>Skip the sweetener and add a pinch of salt, cumin, and turmeric. Top with a poached egg and fresh herbs for a warming savoury breakfast that keeps you full until lunch.</p><h2>3. Talbeena Energy Balls</h2><p>Mix cooled talbeena with dates, cocoa powder, and desiccated coconut. Roll into bite-sized balls and refrigerate for a wholesome on-the-go snack.</p><h2>4. Bedtime Talbeena Latte</h2><p>Whisk a spoonful of talbeena mix into warm milk with a pinch of cinnamon and cardamom. A comforting drink that soothes the mind and body before sleep.</p><h2>5. Talbeena Pancakes</h2><p>Add prepared talbeena to your favourite pancake batter for extra fluffiness and a nutritional boost. Serve with fresh fruit and yoghurt.</p><p>Which one will you try first?</p>",
        "author": "Admin"
    },
    {
        "title": "Understanding Beta-Glucan: The Heart-Friendly Fiber in Barley",
        "slug": "beta-glucan-barley-heart-health",
        "excerpt": "Learn about the powerful soluble fiber that makes barley a heart-health superfood, backed by modern nutritional science.",
        "content": "<h2>What is Beta-Glucan?</h2><p>Beta-glucan is a type of soluble fiber found abundantly in barley, oats, and certain mushrooms. But barley contains the highest concentration — making it one of the most potent sources available in nature.</p><h2>How It Works</h2><p>When consumed, beta-glucan forms a gel-like substance in your digestive tract. This gel: <ul><li>Binds to cholesterol-rich bile acids and helps excrete them</li><li>Slows down glucose absorption, preventing blood sugar spikes</li><li>Feeds beneficial gut bacteria, supporting digestive health</li><li>Promotes a feeling of fullness, aiding weight management</li></ul></p><h2>The Research</h2><p>The US Food and Drug Administration (FDA) has approved the claim that barley beta-glucan may reduce the risk of coronary heart disease. Studies show that consuming 3g of barley beta-glucan daily can lower LDL cholesterol by 5-10%.</p><p>One serving of Talbeena provides approximately 2g of beta-glucan — a significant step toward your daily heart-health goals.</p>",
        "author": "Admin"
    },
]

for bp in blog_posts:
    existing = db.query_one("SELECT id FROM blog_posts WHERE slug=?", [bp["slug"]])
    if not existing:
        db.execute(
            "INSERT INTO blog_posts (id, title, slug, excerpt, content, author, published) VALUES (?,?,?,?,?,?,1)",
            [str(uuid.uuid4()), bp["title"], bp["slug"], bp["excerpt"], bp["content"], bp["author"]]
        )
print("✓ Blog posts seeded")

# ── 9. Store Settings ─────────────────────────────────────────────────────────
db.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES ('store_name', 'Talbeena')")
db.execute("INSERT OR IGNORE INTO store_settings (key, value) VALUES ('store_email', 'hello@talbeena.com')")
print("✓ Store settings configured")

print("\n🎉 Seed complete! Start the app with:  python app.py")
print("   Admin login: admin@talbeena.com / admin123")
