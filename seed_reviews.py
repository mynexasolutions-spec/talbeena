"""
seed_reviews.py — Seed high-quality, realistic reviews by Indian users for all products.
Run: python seed_reviews.py
"""
import uuid
import datetime
import random
import bcrypt
import db

print("Seeding sample reviews from Indian users...")

# 1. Create or retrieve Indian customer accounts
indian_users = [
    {"first": "Rahul", "last": "Sharma", "email": "rahul.sharma@example.in"},
    {"first": "Priya", "last": "Patel", "email": "priya.patel@example.in"},
    {"first": "Amit", "last": "Singh", "email": "amit.singh@example.in"},
    {"first": "Anjali", "last": "Verma", "email": "anjali.verma@example.in"},
    {"first": "Vikram", "last": "Malhotra", "email": "vikram.m@example.in"},
    {"first": "Meera", "last": "Nair", "email": "meera.nair@example.in"},
    {"first": "Suresh", "last": "Iyer", "email": "suresh.iyer@example.in"},
    {"first": "Neha", "last": "Gupta", "email": "neha.g@example.in"}
]

user_ids = []
dummy_pass = bcrypt.hashpw("customer123"[:72].encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

for u in indian_users:
    existing = db.query_one("SELECT id FROM users WHERE email=?", [u["email"]])
    if existing:
        user_ids.append(existing["id"])
    else:
        uid = str(uuid.uuid4())
        db.execute(
            "INSERT INTO users (id, first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?,?)",
            [uid, u["first"], u["last"], u["email"], dummy_pass, "customer"]
        )
        user_ids.append(uid)

print(f"[OK] {len(user_ids)} Indian customer accounts prepared.")

# 2. Get all products
products = db.query("SELECT id, name FROM products")
if not products:
    print("[ERROR] No products found in the database. Please seed products first using python seed.py.")
    exit(1)

# 3. High-quality review pools
review_pool = [
    {
        "rating": 5,
        "title": "Absolutely Authentic & High Quality!",
        "body": "I have been using this Talbeena product every morning for the past month. It is incredibly easy to digest, very soothing for the stomach, and keeps me energetic all day. Tastes super authentic!"
    },
    {
        "rating": 5,
        "title": "Highly Recommended for Wellness",
        "body": "Excellent packaging and clean product. It reminds me of the traditional recipes my grandmother used to make. Really helps with digestion and keeping the gut healthy."
    },
    {
        "rating": 4,
        "title": "Very Smooth and Flavorful",
        "body": "The texture is fine and it blends beautifully with hot milk and a spoonful of honey. The family loves the aroma. Shipping was fast too, delivered within 3 days in Mumbai."
    },
    {
        "rating": 5,
        "title": "A Staple in My Morning Routine",
        "body": "I highly recommend this to anyone looking for a wholesome, natural breakfast. It feels light on the stomach yet keeps me full for hours. Perfect blend of health and taste."
    },
    {
        "rating": 5,
        "title": "Amazing Product - Great Taste!",
        "body": "Bought this on a friend's recommendation and I am completely satisfied. The taste is great, quality is premium, and it is a much better alternative to quick oats or cornflakes."
    },
    {
        "rating": 4,
        "title": "Excellent Quality, Soothing for Gut",
        "body": "Extremely soothing, especially if you have acidity issues. It acts as a great natural meal replacement. Very clean and fresh packaging."
    },
    {
        "rating": 5,
        "title": "Pure Barley Goodness",
        "body": "Very high quality. Truly organic taste and feels completely natural. I mix it with dry fruits and honey, and my kids love it too!"
    },
    {
        "rating": 3,
        "title": "Good Product, Needs Honey for Taste",
        "body": "Quality is very good and healthy. However, the taste is quite plain if had with water, so I highly suggest cooking it in milk with honey or dates. Good for health."
    }
]

# 4. Clear existing reviews to prevent duplicates on rerun
try:
    db.execute("DELETE FROM product_reviews", [])
    print("[OK] Existing reviews cleared.")
except Exception as e:
    pass

# 5. Seed reviews for each product
review_count = 0
for p in products:
    # Seed 3 to 5 random reviews per product
    num_reviews = random.randint(4, 6)
    selected_reviews = random.sample(review_pool, num_reviews)
    shuffled_users = random.sample(user_ids, num_reviews)
    
    for i, rev in enumerate(selected_reviews):
        review_id = str(uuid.uuid4())
        # Generate a realistic date in the past 30 days
        days_ago = random.randint(1, 30)
        review_date = datetime.datetime.now() - datetime.timedelta(days=days_ago)
        
        # Format date safely
        date_str = review_date.strftime("%Y-%m-%d %H:%M:%S")
        
        db.execute(
            "INSERT INTO product_reviews (id, product_id, user_id, rating, title, body, is_approved, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
            [review_id, p["id"], shuffled_users[i], rev["rating"], rev["title"], rev["body"], date_str]
        )
        review_count += 1

# 6. Flush get_product_detail cache to reflect instantly
try:
    from queries import get_product_detail
    get_product_detail.cache_clear()
    print("[OK] Storefront product details cache cleared successfully.")
except Exception as e:
    print(f"[INFO] Cache clear notice: {e}")

print(f"\n[SUCCESS] Successfully seeded {review_count} approved reviews by Indian users across {len(products)} products!")
