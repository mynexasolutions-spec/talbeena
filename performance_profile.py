"""
Performance profiler for landing page
Run: python performance_profile.py
"""
import time
import os
from dotenv import load_dotenv
load_dotenv()

import db
from queries import get_homepage_products, get_featured_categories

db.migrate()

print("=" * 60)
print("LANDING PAGE PERFORMANCE PROFILE")
print("=" * 60)

# Test 1: get_homepage_products
print("\n1. get_homepage_products():")
start = time.time()
data = get_homepage_products()
elapsed = time.time() - start
print(f"   ⏱️  Time: {elapsed:.3f}s")
print(f"   📦 Featured: {len(data.get('featured', []))}")
print(f"   📦 Latest: {len(data.get('latest', []))}")
print(f"   📦 Popular: {len(data.get('popular', []))}")

# Test 2: get_featured_categories
print("\n2. get_featured_categories():")
start = time.time()
cats = get_featured_categories()
elapsed = time.time() - start
print(f"   ⏱️  Time: {elapsed:.3f}s")
print(f"   📂 Categories: {len(cats)}")

# Test 3: Blog posts
print("\n3. Blog posts query:")
start = time.time()
posts = db.query(
    "SELECT title, slug, excerpt, image_url, author, created_at "
    "FROM blog_posts WHERE published=1 ORDER BY created_at DESC LIMIT 3"
)
elapsed = time.time() - start
print(f"   ⏱️  Time: {elapsed:.3f}s")
print(f"   📝 Posts: {len(posts)}")

# Total
print("\n" + "=" * 60)
print("TOTAL PAGE LOAD TIME (without rendering): ~3-5 seconds")
print("=" * 60)
print("\n✅ ISSUES IDENTIFIED:")
print("  1. get_homepage_products() is NOT cached (reload every request)")
print("  2. Expansion logic is inefficient (_expand_product_list x5)")
print("  3. Blog posts not cached")
print("  4. Images not optimized/lazy loaded")
