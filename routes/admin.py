import csv
import io
import uuid
import itertools
import uuid
from functools import wraps
from flask import render_template, request, redirect, url_for, flash, abort, session
import db
from helpers import slugify, get_cached_store_settings, get_unique_slug, handle_upload
from queries import get_products, get_categories, get_brands, get_admin_stats, get_featured_categories, PRODUCTS_SELECT, get_product_detail


def _sanitize_sku_prefix(prefix, fallback):
    cleaned = "".join(ch for ch in (prefix or "").upper() if ch.isalnum() or ch in ("-", "_"))
    cleaned = cleaned.strip("-_")
    return cleaned or fallback


def generate_unique_product_sku(name=None):
    base = _sanitize_sku_prefix(slugify(name or ""), "PRD")
    for _ in range(8):
        candidate = f"{base}-{uuid.uuid4().hex[:8].upper()}"
        if not db.query_one("SELECT id FROM products WHERE sku = ?", [candidate]):
            return candidate
    return f"{base}-{uuid.uuid4().hex[:12].upper()}"


def generate_unique_variation_sku(base_sku=None, exclude_id=None):
    base = _sanitize_sku_prefix(base_sku, "VAR")
    for _ in range(8):
        candidate = f"{base}-{uuid.uuid4().hex[:6].upper()}"
        params = [candidate]
        sql = "SELECT id FROM product_variations WHERE sku = ?"
        if exclude_id:
            sql += " AND id <> ?"
            params.append(exclude_id)
        if not db.query_one(sql, params):
            return candidate
    return f"{base}-{uuid.uuid4().hex[:10].upper()}"


def generate_variations(product_id):
    """
    Generate real variation rows for the cartesian product of primary + secondary
    attribute values.  Optional attributes (gift wrap, sugar-free, etc.) are
    excluded because they don't change price/stock/SKU — they're just toggles on
    the product page.
    """
    # 1. Find primary + secondary attributes assigned to this product
    attr_rows = db.query("""
        SELECT pa.attribute_id, a.variation_type
        FROM product_attributes pa
        JOIN attributes a ON a.id = pa.attribute_id
        WHERE pa.product_id = ? AND a.variation_type IN ('primary', 'secondary')
        ORDER BY a.display_order
    """, [product_id])

    if not attr_rows:
        return  # nothing to generate

    # 2. Fetch values for each attribute (only admin-checked ones)
    value_groups = []
    for attr in attr_rows:
        vals = db.query("""
            SELECT av.id, av.value
            FROM product_attribute_values pav
            JOIN attribute_values av ON av.id = pav.attribute_value_id
            WHERE pav.product_id = ? AND av.attribute_id = ?
            ORDER BY av.value
        """, [product_id, attr["attribute_id"]])
        if vals:
            value_groups.append([(attr["attribute_id"], v["id"], v["value"]) for v in vals])

    if not value_groups:
        return

    # 3. Get base product data (use shared connection for speed)
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT price, sale_price, stock_quantity, sku, name FROM products WHERE id = %s", [product_id])
        row = cur.fetchone()
        if row:
            cols = [desc[0] for desc in cur.description]
            product = dict(zip(cols, row))
        else:
            product = None
    finally:
        conn.close()

    if not product:
        return

    base_price = float(product.get("sale_price") or product.get("price") or 0)
    base_stock = int(product.get("stock_quantity") or 0)
    base_sku   = product.get("sku") or "VAR"

    # 4. Delete existing variations and their attribute links (single connection)
    conn = db.get_conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM variation_images WHERE variation_id IN (SELECT id FROM product_variations WHERE product_id = %s)", [product_id])
        cur.execute("DELETE FROM variation_attribute_values WHERE variation_id IN (SELECT id FROM product_variations WHERE product_id = %s)", [product_id])
        cur.execute("DELETE FROM product_variations WHERE product_id = %s", [product_id])

        # 5. Batch-insert all variations + attribute-value links
        created = 0
        for combo in itertools.product(*value_groups):
            var_id  = str(uuid.uuid4())
            var_sku = generate_unique_variation_sku(base_sku)

            cur.execute(
                "INSERT INTO product_variations (id, product_id, sku, price, sale_price, stock_quantity) "
                "VALUES (%s,%s,%s,%s,%s,%s)",
                [var_id, product_id, var_sku, base_price, product.get("sale_price"), base_stock],
            )

            for attr_id, val_id, _ in combo:
                cur.execute(
                    "INSERT INTO variation_attribute_values (id, variation_id, attribute_value_id) "
                    "VALUES (%s,%s,%s)",
                    [str(uuid.uuid4()), var_id, val_id],
                )
            created += 1

        conn.commit()
    finally:
        conn.close()

    print(f"DEBUG: Generated {created} variations for product {product_id}")


def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = session.get("user")
        if not user:
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.url))
        if user.get("role") not in ("admin", "manager"):
            flash("You do not have permission to access this page.", "error")
            return redirect(url_for("public.index"))
        return f(*args, **kwargs)
    return decorated


def register(app):

    # ── Dashboard ──────────────────────────────────────────────────────────────

    @app.route("/admin/")
    @app.route("/admin")
    @require_admin
    def admin_dashboard():
        _empty_stats = {
            "total_products": 0, "total_orders": 0, "total_revenue": 0.0,
            "total_customers": 0, "pending_orders": 0, "low_stock": 0,
        }
        try:
            stats = get_admin_stats()
        except Exception as e:
            stats = _empty_stats
            flash(f"Stats error: {e}", "error")
        # Ensure all keys exist even if get_admin_stats returns a partial dict
        for k, v in _empty_stats.items():
            stats.setdefault(k, v)

        try:
            recent_orders = db.query(
                """SELECT o.id, o.created_at, o.total_amount, o.status,
                          (u.first_name || ' ' || u.last_name) AS customer_name, u.email AS customer_email
                   FROM orders o LEFT JOIN users u ON u.id = o.user_id
                   ORDER BY o.created_at DESC LIMIT 10"""
            )
        except Exception:
            recent_orders = []

        try:
            recent_products = db.query(
                f"{PRODUCTS_SELECT} WHERE p.is_active=1 ORDER BY p.created_at DESC LIMIT 8"
            )
        except Exception:
            recent_products = []

        try:
            chart_rows = db.query("""
                SELECT TO_CHAR(created_at, 'DD Mon') AS day,
                       SUM(total_amount) AS amount
                FROM orders
                WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
                  AND status != 'cancelled'
                GROUP BY TO_CHAR(created_at, 'YYYY-MM-DD')
                ORDER BY TO_CHAR(created_at, 'YYYY-MM-DD')
            """)
            chart_data = {
                "labels": [r["day"] for r in chart_rows],
                "values": [float(r["amount"]) for r in chart_rows],
            }
        except Exception:
            chart_data = {"labels": [], "values": []}
        return render_template(
            "admin/dashboard.html",
            stats=stats, recent_orders=recent_orders,
            recent_products=recent_products, chart_data=chart_data,
        )

    # ── Products ───────────────────────────────────────────────────────────────

    @app.route("/admin/products")
    @require_admin
    def admin_products():
        search   = request.args.get("search", "").strip()
        category = request.args.get("category", "").strip()
        brand    = request.args.get("brand", "").strip()
        page     = max(1, int(request.args.get("page", 1)))
        try:
            products, total, total_pages = get_products(
                search=search, category=category, brand=brand, page=page, per_page=20, skip_expand=True
            )
            if products:
                print(f"DEBUG: First product '{products[0]['name']}' price: {products[0]['price']}")
            categories = get_categories()
            brands     = get_brands()
        except Exception as e:
            products, total, total_pages = [], 0, 1
            categories = brands = []
            flash(f"Error: {e}", "error")
        return render_template(
            "admin/products.html",
            products=products, total=total, total_pages=total_pages, page=page,
            categories=categories, brands=brands,
            search=search, selected_category=category, selected_brand=brand,
        )

    @app.route("/admin/products/new", methods=["GET", "POST"])
    @require_admin
    def admin_product_new():
        categories     = get_categories()
        brands         = get_brands()
        all_attributes = db.query("SELECT * FROM attributes ORDER BY name ASC")
        for attr in all_attributes:
            attr["options"] = db.query(
                "SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr["id"]]
            )
        
        if request.method == "POST":
            f = request.form
            name = (f.get("name") or "").strip()
            if not name:
                flash("Product name is required.", "error")
                return render_template("admin/product_form.html", product=None, categories=categories,
                                       brands=brands, all_attributes=all_attributes, action="new")
            try:
                import time as _t
                t0 = _t.time()

                stock_qty = int(f.get("stock_quantity") or 0)
                stock_status = f.get("stock_status", "in_stock")
                name = f.get("name")
                slug = get_unique_slug("products", f.get("slug") or slugify(name))
                sku_input = f.get("sku", "").strip()
                sku = sku_input or generate_unique_product_sku(name)

                print(f"DEBUG [{_t.time()-t0:.2f}s]: Creating product '{name}'...")
                product_id = db.execute_returning(
                    """INSERT INTO products
                       (id, name, slug, sku, type, description, short_description,
                        price, sale_price, stock_quantity, stock_status,
                        category_id, brand_id, is_featured, is_active)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) RETURNING id""",
                    [
                        str(uuid.uuid4()), name, slug, sku,
                        f.get("type", "simple"), f.get("description"), f.get("short_description"),
                        float(f.get("price") or 0), float(f.get("sale_price") or 0) or None,
                        stock_qty, stock_status,
                        f.get("category_id") or None, f.get("brand_id") or None,
                        1 if f.get("is_featured") == "on" else 0, 1 if f.get("is_active", "on") == "on" else 0,
                    ]
                )["id"]
                print(f"DEBUG [{_t.time()-t0:.2f}s]: Product row inserted.")

                # Handle Primary Image
                primary_file = request.files.get("primary_image")
                if primary_file and primary_file.filename:
                    print(f"DEBUG [{_t.time()-t0:.2f}s]: Uploading primary image to Cloudinary...")
                    url = handle_upload(primary_file)
                    mid = str(uuid.uuid4())
                    db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, url])
                    db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,1,0)", [str(uuid.uuid4()), product_id, mid])
                    print(f"DEBUG [{_t.time()-t0:.2f}s]: Primary image done.")

                # Handle Gallery Images
                gallery_files = request.files.getlist("gallery_images")
                if gallery_files and any(g.filename for g in gallery_files):
                    print(f"DEBUG [{_t.time()-t0:.2f}s]: Uploading {len(gallery_files)} gallery images...")
                    for i, gfile in enumerate(gallery_files):
                        if gfile and gfile.filename:
                            url = handle_upload(gfile)
                            mid = str(uuid.uuid4())
                            db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, url])
                            db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,0,?)", [str(uuid.uuid4()), product_id, mid, i+1])
                    print(f"DEBUG [{_t.time()-t0:.2f}s]: Gallery images done.")

                # Batch-insert attribute associations (1 query instead of N)
                print(f"DEBUG [{_t.time()-t0:.2f}s]: Saving attributes...")
                attr_ids = request.form.getlist("attribute_ids")
                if attr_ids:
                    values_sql = ",".join(["(?,?,?)"] * len(attr_ids))
                    params = []
                    for attr_id in attr_ids:
                        params.extend([str(uuid.uuid4()), product_id, attr_id])
                    db.execute(
                        f"INSERT INTO product_attributes (id, product_id, attribute_id) VALUES {values_sql}",
                        params
                    )

                val_ids = request.form.getlist("attribute_value_ids")
                if val_ids:
                    values_sql = ",".join(["(?,?,?)"] * len(val_ids))
                    params = []
                    for val_id in val_ids:
                        params.extend([str(uuid.uuid4()), product_id, val_id])
                    db.execute(
                        f"INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES {values_sql}",
                        params
                    )
                print(f"DEBUG [{_t.time()-t0:.2f}s]: {len(attr_ids)} attrs + {len(val_ids)} values saved in batch.")

                if f.get("type") == "variable":
                    print(f"DEBUG [{_t.time()-t0:.2f}s]: Creating placeholder variation...")
                    generate_variations(product_id)

                print(f"DEBUG [{_t.time()-t0:.2f}s]: Product creation complete.")
                get_products.cache_clear()
                flash("Product created successfully.", "success")
                return redirect(url_for("admin_products"))
            except Exception as e:
                flash(f"Error creating product: {e}", "error")

        return render_template("admin/product_form.html", product=None, categories=categories, brands=brands, all_attributes=all_attributes, action="new")

    @app.route("/admin/products/<product_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_product_edit(product_id):
        product = db.query_one("SELECT * FROM products WHERE id=?", [product_id])
        if not product: abort(404)
        
        categories = get_categories()
        brands = get_brands()
        all_attributes = db.query("SELECT * FROM attributes ORDER BY name ASC")
        for attr in all_attributes:
            attr["options"] = db.query("SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr["id"]])
        
        if request.method == "POST":
            f = request.form
            try:
                name = f.get("name")
                slug = get_unique_slug("products", f.get("slug") or slugify(name), exclude_id=product_id)
                sku_input = (f.get("sku") or "").strip()
                updated_sku = sku_input or product.get("sku") or generate_unique_product_sku(name)
                db.execute(
                    """UPDATE products SET name=?, slug=?, sku=?, type=?, description=?,
                       short_description=?, price=?, sale_price=?, stock_quantity=?, stock_status=?,
                       category_id=?, brand_id=?, is_featured=?, is_active=? WHERE id=?""",
                    [
                        name, slug, updated_sku, f.get("type"), f.get("description"),
                        f.get("short_description"), float(f.get("price") or 0), float(f.get("sale_price") or 0) or None,
                        int(f.get("stock_quantity") or 0), f.get("stock_status"),
                        f.get("category_id") or None, f.get("brand_id") or None,
                        1 if f.get("is_featured") == "on" else 0, 1 if f.get("is_active") == "on" else 0, product_id
                    ]
                )

                # Handle Primary Image
                primary_file = request.files.get("primary_image")
                if primary_file and primary_file.filename:
                    url = handle_upload(primary_file)
                    mid = str(uuid.uuid4())
                    db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, url])
                    db.execute("DELETE FROM product_images WHERE product_id=? AND is_primary=1", [product_id])
                    db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary, display_order) VALUES (?,?,?,1,0)", [str(uuid.uuid4()), product_id, mid])

                # Handle New Gallery Images
                gallery_files = request.files.getlist("gallery_images")
                for gfile in gallery_files:
                    if gfile and gfile.filename:
                        url = handle_upload(gfile)
                        mid = str(uuid.uuid4())
                        db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, url])
                        db.execute("INSERT INTO product_images (id, product_id, media_id, is_primary) VALUES (?,?,?,0)", [str(uuid.uuid4()), product_id, mid])

                # Handle Deletions
                for key in request.form:
                    if key.startswith("delete_image_"):
                        img_id = key.replace("delete_image_", "")
                        db.execute("DELETE FROM product_images WHERE id=?", [img_id])

                db.execute("DELETE FROM product_attributes WHERE product_id=?", [product_id])
                for aid in request.form.getlist("attribute_ids"):
                    db.execute("INSERT INTO product_attributes (id, product_id, attribute_id) VALUES (?,?,?)", [str(uuid.uuid4()), product_id, aid])
                
                db.execute("DELETE FROM product_attribute_values WHERE product_id=?", [product_id])
                for vid in request.form.getlist("attribute_value_ids"):
                    db.execute("INSERT INTO product_attribute_values (id, product_id, attribute_value_id) VALUES (?,?,?)", [str(uuid.uuid4()), product_id, vid])

                # Clean up variations if type changed
                old_type = product.get("type")
                new_type = f.get("type")
                if old_type == "variable" and new_type != "variable":
                    db.execute("DELETE FROM variation_images WHERE variation_id IN (SELECT id FROM product_variations WHERE product_id = ?)", [product_id])
                    db.execute("DELETE FROM variation_attribute_values WHERE variation_id IN (SELECT id FROM product_variations WHERE product_id = ?)", [product_id])
                    db.execute("DELETE FROM product_variations WHERE product_id = ?", [product_id])
                elif new_type == "variable" and old_type != "variable":
                    generate_variations(product_id)

                get_products.cache_clear()
                flash("Product updated successfully.", "success")
                return redirect(url_for("admin_products"))
            except Exception as e:
                flash(f"Error: {e}", "error")

        # Fetch images for display
        product_images = db.query("""
            SELECT pi.id, pi.is_primary, m.file_url as image_url 
            FROM product_images pi 
            JOIN media m ON m.id = pi.media_id 
            WHERE pi.product_id=? ORDER BY pi.is_primary DESC, pi.display_order ASC
        """, [product_id])
        
        product_attribute_ids = [r["attribute_id"] for r in db.query("SELECT attribute_id FROM product_attributes WHERE product_id=?", [product_id])]
        product_value_ids = [r["attribute_value_id"] for r in db.query("SELECT attribute_value_id FROM product_attribute_values WHERE product_id=?", [product_id])]
        
        return render_template(
            "admin/product_form.html",
            product=product, product_images=product_images,
            categories=categories, brands=brands, all_attributes=all_attributes,
            product_attribute_ids=product_attribute_ids, product_value_ids=product_value_ids,
            action="edit"
        )

    @app.route("/admin/products/<product_id>/delete", methods=["POST"])
    @require_admin
    def admin_product_delete(product_id):
        try:
            db.execute("UPDATE products SET is_active=0 WHERE id=?", [product_id])
            get_products.cache_clear()
            flash("Product deleted (deactivated).", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_products"))

    # ── Categories ─────────────────────────────────────────────────────────────

    @app.route("/admin/categories")
    @require_admin
    def admin_categories():
        try:
            categories = get_categories()
        except Exception as e:
            categories = []
            flash(f"Error: {e}", "error")
        return render_template("admin/categories.html", categories=categories)

    @app.route("/admin/categories/new", methods=["GET", "POST"])
    @require_admin
    def admin_category_new():
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Category name is required.", "error")
                return render_template("admin/category_form.html", category=None, categories=get_categories())
            slug       = request.form.get("slug") or slugify(name)
            parent_id  = request.form.get("parent_id") or None
            is_featured = 1 if request.form.get("is_featured") == "on" else 0
            
            # Handle Upload
            image_url = handle_upload(request.files.get("image_file")) or request.form.get("image_url") or None
            
            try:
                db.execute(
                    "INSERT INTO categories (id, name, slug, parent_id, image_url, is_featured) VALUES (?,?,?,?,?,?)",
                    [str(uuid.uuid4()), name, slug, parent_id, image_url, is_featured]
                )
                get_categories.cache_clear()
                get_featured_categories.cache_clear()
                flash("Category created", "success")
                return redirect(url_for("admin_categories"))
            except Exception as e:
                flash(f"Error: {e}", "error")
        return render_template("admin/category_form.html", category=None, categories=get_categories())

    @app.route("/admin/categories/<cat_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_category_edit(cat_id):
        category = db.query_one("SELECT * FROM categories WHERE id = ?", [cat_id])
        if not category:
            abort(404)
        if request.method == "POST":
            # Handle Upload
            image_url = handle_upload(request.files.get("image_file")) or handle_upload(request.files.get("image_file")) or category["image_url"]
            
            try:
                db.execute(
                    "UPDATE categories SET name=?, slug=?, parent_id=?, image_url=?, is_featured=? WHERE id=?",
                    [request.form.get("name"), request.form.get("slug"),
                     request.form.get("parent_id") or None, image_url,
                     1 if request.form.get("is_featured") == "on" else 0, cat_id]
                )
                get_categories.cache_clear()
                get_featured_categories.cache_clear()
                flash("Category updated", "success")
                return redirect(url_for("admin_categories"))
            except Exception as e:
                flash(f"Error: {e}", "error")
        return render_template("admin/category_form.html", category=category, categories=get_categories())

    @app.route("/admin/categories/<cat_id>/delete", methods=["POST"])
    @require_admin
    def admin_category_delete(cat_id):
        try:
            # Manually decouple products and subcategories before deletion
            db.execute("UPDATE products SET category_id = NULL WHERE category_id = ?", [cat_id])
            db.execute("UPDATE categories SET parent_id = NULL WHERE parent_id = ?", [cat_id])
            
            db.execute("DELETE FROM categories WHERE id=?", [cat_id])
            get_categories.cache_clear()
            get_featured_categories.cache_clear()
            flash("Category deleted.", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_categories"))

    # ── Brands ─────────────────────────────────────────────────────────────────

    @app.route("/admin/brands")
    @require_admin
    def admin_brands():
        try:
            brands = db.query(
                """
                SELECT b.*, COUNT(p.id) AS product_count
                FROM brands b
                LEFT JOIN products p ON p.brand_id = b.id
                GROUP BY b.id
                ORDER BY b.name ASC
                """
            )
        except Exception as e:
            brands = []
            flash(f"Error: {e}", "error")
        return render_template("admin/brands.html", brands=brands)

    @app.route("/admin/brands/new", methods=["GET", "POST"])
    @require_admin
    def admin_brand_new():
        if request.method == "POST":
            name = (request.form.get("name") or "").strip()
            if not name:
                flash("Brand name is required.", "error")
                return render_template("admin/brand_form.html", brand=None)
            slug = request.form.get("slug") or slugify(name)
            image_url = handle_upload(request.files.get("image_file")) or None
            try:
                db.execute(
                    "INSERT INTO brands (id, name, slug, image_url) VALUES (?,?,?,?)",
                    [str(uuid.uuid4()), name, slug, image_url]
                )
                get_brands.cache_clear()
                flash("Brand created.", "success")
                return redirect(url_for("admin_brands"))
            except Exception as e:
                flash(f"Error: {e}", "error")
        return render_template("admin/brand_form.html", brand=None)

    @app.route("/admin/brands/<brand_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_brand_edit(brand_id):
        brand = db.query_one("SELECT * FROM brands WHERE id = ?", [brand_id])
        if not brand: abort(404)
        if request.method == "POST":
            name = request.form.get("name")
            slug = request.form.get("slug") or slugify(name)
            image_url = handle_upload(request.files.get("image_file")) or brand["image_url"]
            try:
                db.execute(
                    "UPDATE brands SET name=?, slug=?, image_url=? WHERE id=?",
                    [name, slug, image_url, brand_id]
                )
                get_brands.cache_clear()
                flash("Brand updated.", "success")
                return redirect(url_for("admin_brands"))
            except Exception as e:
                flash(f"Error: {e}", "error")
        return render_template("admin/brand_form.html", brand=brand)

    @app.route("/admin/brands/<brand_id>/delete", methods=["POST"])
    @require_admin
    def admin_brand_delete(brand_id):
        try:
            # Manually decouple products before deletion
            db.execute("UPDATE products SET brand_id = NULL WHERE brand_id = ?", [brand_id])
            
            db.execute("DELETE FROM brands WHERE id=?", [brand_id])
            get_brands.cache_clear()
            flash("Brand deleted.", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_brands"))

    # ── Orders ─────────────────────────────────────────────────────────────────

    @app.route("/admin/orders")
    @require_admin
    def admin_orders():
        import math
        page     = max(1, int(request.args.get("page", 1)))
        per_page = 20
        offset   = (page - 1) * per_page
        try:
            orders = db.query(
                """SELECT o.id, o.created_at, o.total_amount, o.status,
                          (u.first_name || ' ' || u.last_name) AS customer_name,
                          u.email AS customer_email, COUNT(oi.id) AS item_count
                   FROM orders o
                   LEFT JOIN users u  ON u.id = o.user_id
                   LEFT JOIN order_items oi ON oi.order_id = o.id
                   GROUP BY o.id, o.created_at, o.total_amount, o.status, u.first_name, u.last_name, u.email
                   ORDER BY o.created_at DESC LIMIT ? OFFSET ?""",
                [per_page, offset]
            )
            total       = (db.query_one("SELECT COUNT(*) AS cnt FROM orders") or {}).get("cnt", 0)
            total_pages = max(1, math.ceil(total / per_page))
        except Exception as e:
            orders, total, total_pages = [], 0, 1
            flash(f"Error: {e}", "error")
        return render_template(
            "admin/orders.html", orders=orders, total=total, total_pages=total_pages, page=page
        )

    @app.route("/admin/orders/<order_id>")
    @require_admin
    def admin_order_detail(order_id):
        try:
            order = db.query_one(
                """SELECT o.*, (u.first_name || ' ' || u.last_name) AS customer_name, u.email AS customer_email
                   FROM orders o LEFT JOIN users u ON u.id = o.user_id WHERE o.id=?""",
                [order_id]
            )
            if not order:
                abort(404)
            items = db.query(
                "SELECT oi.*, p.name AS product_name, p.sku FROM order_items oi "
                "LEFT JOIN products p ON p.id = oi.product_id WHERE oi.order_id=?",
                [order_id]
            )
        except Exception as e:
            flash(f"Error: {e}", "error")
            return redirect(url_for("admin_orders"))
        return render_template("admin/order_detail.html", order=order, items=items)

    @app.route("/admin/orders/<order_id>/status", methods=["POST"])
    @require_admin
    def admin_order_status(order_id):
        status = request.form.get("status")
        valid  = ("pending", "processing", "shipped", "delivered", "cancelled", "refunded")
        if status not in valid:
            flash("Invalid status.", "error")
            return redirect(url_for("admin_order_detail", order_id=order_id))
        try:
            db.execute("UPDATE orders SET status=? WHERE id=?", [status, order_id])
            flash(f"Order status updated to '{status}'.", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_order_detail", order_id=order_id))

    # ── Customers ──────────────────────────────────────────────────────────────

    @app.route("/admin/customers")
    @require_admin
    def admin_customers():
        try:
            customers = db.query("SELECT * FROM users WHERE role='customer' ORDER BY created_at DESC")
        except Exception as e:
            customers = []
            flash(f"Error: {e}", "error")
        return render_template("admin/customers.html", customers=customers)

    @app.route("/admin/subscribers")
    @require_admin
    def admin_subscribers():
        try:
            subscribers = db.query("SELECT * FROM newsletter_subscribers ORDER BY subscribed_at DESC")
        except Exception as e:
            subscribers = []
            flash(f"Error loading subscribers: {e}", "error")
        return render_template("admin/subscribers.html", subscribers=subscribers)

    # ── Attributes ─────────────────────────────────────────────────────────────

    @app.route("/admin/attributes")
    @require_admin
    def admin_attributes():
        try:
            attributes = db.query("""
                SELECT a.*, (SELECT COUNT(*) FROM attribute_values v WHERE v.attribute_id = a.id) as value_count
                FROM attributes a ORDER BY a.name ASC
            """)
        except Exception as e:
            attributes = []
            flash(f"Error: {e}", "error")
        return render_template("admin/attributes.html", attributes=attributes)

    @app.route("/admin/attributes/new", methods=["GET", "POST"])
    @require_admin
    def admin_attribute_new():
        if request.method == "POST":
            name       = request.form.get("name")
            slug       = request.form.get("slug") or slugify(name)
            var_type   = request.form.get("variation_type", "secondary")
            is_featured = 1 if request.form.get("is_featured") == "on" else 0
            image_url = handle_upload(request.files.get("image_file")) or None
            
            if not name:
                flash("Name is required", "error")
            else:
                try:
                    db.execute(
                        "INSERT INTO attributes (id, name, slug, variation_type, image_url, is_featured) VALUES (?,?,?,?,?,?)",
                        [str(uuid.uuid4()), name, slug, var_type, image_url, is_featured]
                    )
                    flash("Attribute created", "success")
                    return redirect(url_for("admin_attributes"))
                except Exception as e:
                    flash(f"Error: {e}", "error")
        return render_template("admin/attribute_form.html", attribute=None)

    @app.route("/admin/attributes/<attr_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_attribute_edit(attr_id):
        attribute = db.query_one("SELECT * FROM attributes WHERE id = ?", [attr_id])
        if not attribute:
            abort(404)
        if request.method == "POST":
            var_type  = request.form.get("variation_type", "secondary")
            image_url = handle_upload(request.files.get("image_file")) or attribute["image_url"]
            try:
                db.execute(
                    "UPDATE attributes SET name=?, slug=?, variation_type=?, image_url=?, is_featured=? WHERE id=?",
                    [request.form.get("name"), request.form.get("slug"),
                     var_type, image_url,
                     1 if request.form.get("is_featured") == "on" else 0, attr_id]
                )
                flash("Attribute updated", "success")
                return redirect(url_for("admin_attributes"))
            except Exception as e:
                flash(f"Error: {e}", "error")
        return render_template("admin/attribute_form.html", attribute=attribute)

    @app.route("/admin/attributes/<attr_id>/delete", methods=["POST"])
    @require_admin
    def admin_attribute_delete(attr_id):
        try:
            db.execute("DELETE FROM attributes WHERE id = ?", [attr_id])
            flash("Attribute deleted", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_attributes"))

    @app.route("/admin/attributes/<attr_id>/values", methods=["GET", "POST"])
    @require_admin
    def admin_attribute_values(attr_id):
        attribute = db.query_one("SELECT * FROM attributes WHERE id = ?", [attr_id])
        if not attribute:
            flash("Attribute not found", "error")
            return redirect(url_for("admin_attributes"))
        if request.method == "POST":
            value     = request.form.get("value")
            image_url = handle_upload(request.files.get("image_file")) or None
            if value:
                try:
                    db.execute(
                        "INSERT INTO attribute_values (id, attribute_id, value, image_url) VALUES (?,?,?,?)",
                        [str(uuid.uuid4()), attr_id, value, image_url]
                    )
                    
                    flash("Value added", "success")
                except Exception as e:
                    flash(f"Error: {e}", "error")
        values = db.query(
            "SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr_id]
        )
        return render_template("admin/attribute_values.html", attribute=attribute, values=values)

    @app.route("/admin/attributes/<attr_id>/values/bulk_update", methods=["POST"])
    @require_admin
    def admin_attribute_values_bulk_update(attr_id):
        f = request.form
        try:
            values = db.query("SELECT id FROM attribute_values WHERE attribute_id = ?", [attr_id])
            for v in values:
                v_id = v["id"]
                new_value = (f.get(f"value_{v_id}") or "").strip()
                if new_value:
                    db.execute("UPDATE attribute_values SET value=? WHERE id=?", [new_value, v_id])
            
            flash("Attribute values updated.", "success")
        except Exception as e:
            flash(f"Error updating values: {e}", "error")
        return redirect(url_for("admin_attribute_values", attr_id=attr_id))

    @app.route("/admin/attributes/values/<val_id>/delete", methods=["POST"])
    @require_admin
    def admin_attribute_value_delete(val_id):
        attr_id = request.form.get("attribute_id")
        try:
            # Cascade: remove all product & variation references first
            db.execute("DELETE FROM product_attribute_values WHERE attribute_value_id = ?", [val_id])
            db.execute("DELETE FROM variation_attribute_values WHERE attribute_value_id = ?", [val_id])
            db.execute("DELETE FROM attribute_values WHERE id = ?", [val_id])
            
            get_products.cache_clear()
            flash("Value deleted", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_attribute_values", attr_id=attr_id))

    @app.route("/admin/attributes/values/<val_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_attribute_value_edit(val_id):
        value = db.query_one("SELECT * FROM attribute_values WHERE id = ?", [val_id])
        if not value:
            abort(404)
        
        attribute = db.query_one("SELECT * FROM attributes WHERE id = ?", [value["attribute_id"]])
        
        if request.method == "POST":
            new_value = request.form.get("value")
            image_url = handle_upload(request.files.get("image_file")) or value.get("image_url")
            
            try:
                db.execute(
                    "UPDATE attribute_values SET value=?, image_url=? WHERE id=?",
                    [new_value, image_url, val_id]
                )
                
                flash("Value updated", "success")
                return redirect(url_for("admin_attribute_values", attr_id=value["attribute_id"]))
            except Exception as e:
                flash(f"Error: {e}", "error")
                
        return render_template("admin/attribute_value_form.html", attribute=attribute, value=value)

    # ── Variations ─────────────────────────────────────────────────────────────

    @app.route("/admin/products/<product_id>/variations")
    @require_admin
    def admin_product_variations(product_id):
        product = db.query_one("SELECT id, name, type FROM products WHERE id = ?", [product_id])
        if not product:
            abort(404)
        variations = db.query("""
            SELECT v.*,
                   (SELECT string_agg(av.value, ' / ')
                    FROM variation_attribute_values vav
                    JOIN attribute_values av ON av.id = vav.attribute_value_id
                    WHERE vav.variation_id = v.id) as option_names
            FROM product_variations v WHERE v.product_id = ? ORDER BY v.sku ASC
        """, [product_id])
        linked_attributes = db.query("""
            SELECT a.id, a.name FROM attributes a
            JOIN product_attributes pa ON pa.attribute_id = a.id
            WHERE pa.product_id = ? ORDER BY pa.display_order ASC
        """, [product_id])
        for attr in linked_attributes:
            attr["options"] = db.query("""
                SELECT av.* FROM attribute_values av
                JOIN product_attribute_values pav ON pav.attribute_value_id = av.id
                WHERE av.attribute_id = ? AND pav.product_id = ? ORDER BY av.value ASC
            """, [attr["id"], product_id])
            if not attr["options"]:
                attr["options"] = db.query(
                    "SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr["id"]]
                )
        # Fetch existing variation images
        var_ids = [v["id"] for v in variations]
        variation_images = {}
        if var_ids:
            ph = ",".join(["?"] * len(var_ids))
            rows = db.query(f"""
                SELECT vi.variation_id, vi.is_primary, m.file_url
                FROM variation_images vi
                JOIN media m ON m.id = vi.media_id
                WHERE vi.variation_id IN ({ph})
                ORDER BY vi.is_primary DESC, vi.display_order
            """, var_ids)
            for r in rows:
                vid = str(r["variation_id"])
                variation_images.setdefault(vid, []).append(r)
        return render_template(
            "admin/variations.html", product=product, variations=variations,
            attributes=linked_attributes, variation_images=variation_images,
        )

    @app.route("/admin/products/<product_id>/variations/new", methods=["POST"])
    @require_admin
    def admin_variation_new(product_id):
        f = request.form
        try:
            product = db.query_one("SELECT price, sale_price, stock_quantity, sku FROM products WHERE id = ?", [product_id]) or {}
            variation_sku = (f.get("sku") or "").strip() or generate_unique_variation_sku(
                (product or {}).get("sku")
            )
            var_id = str(uuid.uuid4())
            db.execute(
                "INSERT INTO product_variations (id, product_id, sku, price, sale_price, stock_quantity) "
                "VALUES (?,?,?,?,?,?)",
                [var_id, product_id, variation_sku,
                 float(product.get("sale_price") or product.get("price") or 0), None,
                 int(product.get("stock_quantity") or 0)]
            )
            for key, val_id in f.items():
                if key.startswith("attr_") and val_id:
                    db.execute(
                        "INSERT INTO variation_attribute_values (id, variation_id, attribute_value_id) VALUES (?,?,?)",
                        [str(uuid.uuid4()), var_id, val_id]
                    )
            flash("Variation created", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_product_variations", product_id=product_id))

    @app.route("/admin/variations/<var_id>/delete", methods=["POST"])
    @require_admin
    def admin_variation_delete(var_id):
        product_id = request.form.get("product_id")
        try:
            db.execute("DELETE FROM variation_images WHERE variation_id = ?", [var_id])
            db.execute("DELETE FROM variation_attribute_values WHERE variation_id = ?", [var_id])
            db.execute("DELETE FROM order_items WHERE variation_id = ?", [var_id])
            db.execute("DELETE FROM product_variations WHERE id = ?", [var_id])
            get_products.cache_clear()
            flash("Variation deleted", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_product_variations", product_id=product_id))

    @app.route("/admin/products/<product_id>/variations/bulk_update", methods=["POST"])
    @require_admin
    def admin_variations_bulk_update(product_id):
        try:
            rows = db.query("SELECT id, sku FROM product_variations WHERE product_id = ?", [product_id])
            var_ids = [r["id"] for r in rows]

            for vid in var_ids:
                sku     = (request.form.get(f"sku_{vid}") or "").strip()
                price   = request.form.get(f"price_{vid}", "").strip()
                stock   = request.form.get(f"stock_{vid}", "").strip()
                var_name = (request.form.get(f"name_{vid}") or "").strip()
                short_desc = (request.form.get(f"short_desc_{vid}") or "").strip()
                desc    = (request.form.get(f"description_{vid}") or "").strip()

                try:
                    p = float(price) if price else 0
                except (ValueError, TypeError):
                    p = 0
                try:
                    s = int(stock) if stock else 0
                except (ValueError, TypeError):
                    s = 0

                db.execute(
                    """UPDATE product_variations
                       SET sku=?, price=?, stock_quantity=?, stock_status=?,
                           name=?, short_description=?, description=?
                       WHERE id=?""",
                    [
                        sku or f"VAR-{vid[:8].upper()}",
                        p, s,
                        "out_of_stock" if (s <= 0) else "in_stock",
                        var_name, short_desc, desc, vid,
                    ],
                )

                # Handle variation image uploads (multiple files)
                img_files = request.files.getlist(f"image_{vid}")
                img_files = [f for f in img_files if f and f.filename]
                if img_files:
                    # Mark existing images as non-primary
                    db.execute("UPDATE variation_images SET is_primary=0 WHERE variation_id=?", [vid])
                    for idx, img_file in enumerate(img_files):
                        url = handle_upload(img_file, folder="talbeena-variations")
                        if url:
                            mid = str(uuid.uuid4())
                            db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, url])
                            db.execute(
                                "INSERT INTO variation_images (id, variation_id, media_id, is_primary, display_order) "
                                "VALUES (?,?,?,?,?)",
                                [str(uuid.uuid4()), vid, mid, 1 if idx == 0 else 0, idx],
                            )

            get_products.cache_clear()
            flash("All variations updated successfully.", "success")
        except Exception as e:
            flash(f"Error during bulk update: {e}", "error")
        return redirect(url_for("admin_product_variations", product_id=product_id))

    # ── Reviews ────────────────────────────────────────────────────────────────

    @app.route("/admin/reviews")
    @require_admin
    def admin_reviews():
        try:
            reviews = db.query("""
                SELECT r.*, p.name AS product_name, p.id AS product_id,
                       (u.first_name || ' ' || u.last_name) AS reviewer_name
                FROM product_reviews r 
                LEFT JOIN products p ON p.id = r.product_id
                LEFT JOIN users u ON u.id = r.user_id
                ORDER BY r.created_at DESC
            """)
        except Exception as e:
            reviews = []
            flash(f"Error loading reviews: {e}", "error")
        return render_template("admin/reviews.html", reviews=reviews)

    @app.route("/admin/reviews/<review_id>/approve", methods=["POST"])
    @require_admin
    def admin_review_approve(review_id):
        action = request.form.get("action", "approve")
        try:
            approved = action == "approve"
            db.execute("UPDATE product_reviews SET is_approved=? WHERE id=?", [approved, review_id])
            get_product_detail.cache_clear()
            flash("Review " + ("approved." if approved else "rejected."), "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_reviews"))

    @app.route("/admin/reviews/<review_id>/delete", methods=["POST"])
    @require_admin
    def admin_review_delete(review_id):
        try:
            db.execute("DELETE FROM product_reviews WHERE id=?", [review_id])
            get_product_detail.cache_clear()
            flash("Review deleted.", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_reviews"))

    # ── Settings ───────────────────────────────────────────────────────────────

    @app.route("/admin/settings", methods=["GET", "POST"])
    @require_admin
    def admin_settings():
        if request.method == "POST":
            toggle_keys  = ["cod_enabled", "online_payment_enabled", "free_shipping_enabled", "free_shipping_all"]
            text_keys    = ["razorpay_key_id", "razorpay_key_secret"]
            numeric_keys = ["shipping_fee", "free_shipping_threshold"]
            try:
                for key in toggle_keys:
                    value = "true" if request.form.get(key) == "on" else "false"
                    db.execute(
                        "INSERT INTO store_settings (key, value) VALUES (?,?) "
                        "ON CONFLICT (key) DO UPDATE SET value=?, updated_at=CURRENT_TIMESTAMP",
                        [key, value, value]
                    )
                for key in text_keys:
                    value = request.form.get(key, "").strip()
                    db.execute(
                        "INSERT INTO store_settings (key, value) VALUES (?,?) "
                        "ON CONFLICT (key) DO UPDATE SET value=?, updated_at=CURRENT_TIMESTAMP",
                        [key, value, value]
                    )
                for key in numeric_keys:
                    raw = request.form.get(key, "").strip()
                    try:
                        value = str(max(0, float(raw))) if raw else ("99" if key == "shipping_fee" else "999")
                    except ValueError:
                        value = "99" if key == "shipping_fee" else "999"
                    db.execute(
                        "INSERT INTO store_settings (key, value) VALUES (?,?) "
                        "ON CONFLICT (key) DO UPDATE SET value=?, updated_at=CURRENT_TIMESTAMP",
                        [key, value, value]
                    )
                get_cached_store_settings.cache_clear()
                flash("Settings saved successfully.", "success")
            except Exception as e:
                flash(f"Error saving settings: {e}", "error")
            return redirect(url_for("admin_settings"))
        return render_template("admin/settings.html", settings=get_cached_store_settings())

    # ── Coupons ────────────────────────────────────────────────────────────────
    @app.route("/admin/coupons")
    @require_admin
    def admin_coupons():
        try:
            coupons = db.query("""
                SELECT c.*, (SELECT COUNT(*) FROM coupon_usages WHERE coupon_id::text = c.id::text) as used_count
                FROM coupons c 
                ORDER BY c.created_at DESC
            """)
        except Exception:
            coupons = []
        return render_template("admin/coupons.html", coupons=coupons)

    @app.route("/admin/coupons/new", methods=["GET", "POST"])
    @require_admin
    def admin_coupon_new():
        if request.method == "POST":
            f = request.form
            code = (f.get("code") or "").strip().upper()
            ctype = (f.get("type") or "").strip()

            # Validation
            if not code:
                flash("Coupon code is required.", "error")
                return render_template("admin/coupon_form.html", coupon=None)
            if ctype not in ("percentage", "fixed"):
                flash("Coupon type must be 'percentage' or 'fixed'.", "error")
                return render_template("admin/coupon_form.html", coupon=None)
            if db.query_one("SELECT id FROM coupons WHERE code = ?", [code]):
                flash(f"Coupon code '{code}' already exists.", "error")
                return render_template("admin/coupon_form.html", coupon=None)

            try:
                db.execute(
                    """INSERT INTO coupons 
                       (id, code, type, value, min_order_amount, usage_limit, 
                        usage_limit_per_user, max_discount, expires_at, is_active)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    [
                        str(uuid.uuid4()), code, ctype,
                        float(f.get("value") or 0), float(f.get("min_order_amount") or 0),
                        int(f.get("usage_limit")) if f.get("usage_limit") else None,
                        int(f.get("usage_limit_per_user") or 1),
                        float(f.get("max_discount")) if f.get("max_discount") else None,
                        f.get("expires_at") or None,
                        1 if f.get("is_active") == "on" else 0
                    ]
                )
                flash("Coupon created successfully.", "success")
                return redirect(url_for("admin_coupons"))
            except Exception as e:
                flash(f"Error creating coupon: {e}", "error")
        return render_template("admin/coupon_form.html", coupon=None)

    @app.route("/admin/coupons/<coupon_id>/delete", methods=["POST"])
    @require_admin
    def admin_coupon_delete(coupon_id):
        try:
            db.execute("DELETE FROM coupons WHERE id=?", [coupon_id])
            flash("Coupon deleted successfully.", "success")
        except Exception as e:
            flash(f"Error deleting coupon: {e}", "error")
        return redirect(url_for("admin_coupons"))

    # ── CSV Import ─────────────────────────────────────────────────────────────

    @app.route("/admin/import", methods=["GET", "POST"])
    @require_admin
    def admin_import():
        results = None
        if request.method == "POST":
            csv_file = request.files.get("csv_file")
            if not csv_file or csv_file.filename == "":
                flash("Please select a CSV file.", "error")
                return render_template("admin/import.html", results=None)
            try:
                content  = csv_file.read().decode("utf-8-sig")
                reader   = csv.DictReader(io.StringIO(content))
                imported = skipped = 0
                errors   = []
                for i, row in enumerate(reader, 1):
                    try:
                        name  = (row.get("post_title") or row.get("name") or "").strip()
                        sku   = (row.get("sku") or "").strip() or generate_unique_product_sku(name)
                        desc  = (row.get("description") or row.get("post_content") or "").strip()
                        short = (row.get("short_description") or row.get("post_excerpt") or "").strip()
                        img   = (row.get("images") or row.get("image") or "").strip().split("|")[0].strip()
                        slug  = (row.get("post_name") or row.get("slug") or name.lower().replace(" ", "-")).strip()

                        if not name:
                            skipped += 1
                            continue
                        if db.query_one("SELECT id FROM products WHERE sku=? OR slug=?", [sku, slug]):
                            skipped += 1
                            continue

                        # Safely parse numeric fields
                        try:
                            price = float(row.get("regular_price") or row.get("price") or 0)
                        except (ValueError, TypeError):
                            price = 0
                        try:
                            sale = float(row.get("sale_price") or 0) or None
                        except (ValueError, TypeError):
                            sale = None
                        try:
                            stock = int(row.get("stock") or row.get("stock_quantity") or 0)
                        except (ValueError, TypeError):
                            stock = 0
                        result = db.execute_returning(
                            """INSERT INTO products (id, name, slug, sku, price, sale_price,
                               stock_quantity, stock_status, description, short_description, is_active)
                               VALUES (?,?,?,?,?,?,?,?,?,?,1) RETURNING id""",
                            [str(uuid.uuid4()), name, slug, sku, price, sale, stock,
                             "in_stock" if stock > 0 else "out_of_stock", desc, short]
                        )
                        if result and img:
                            mid = str(uuid.uuid4())
                            db.execute("INSERT INTO media (id, file_url) VALUES (?,?)", [mid, img])
                            db.execute(
                                "INSERT INTO product_images (id, product_id, media_id, is_primary) VALUES (?,?,?,1)",
                                [str(uuid.uuid4()), result["id"], mid]
                            )
                        imported += 1
                    except Exception as row_err:
                        errors.append(f"Row {i}: {row_err}")
                get_products.cache_clear()
                results = {"imported": imported, "skipped": skipped, "errors": errors}
                flash(f"Import complete: {imported} imported, {skipped} skipped.", "success")
            except Exception as e:
                flash(f"CSV parse error: {e}", "error")
        return render_template("admin/import.html", results=results)

    # ── Blog ───────────────────────────────────────────────────────────────────

    @app.route("/admin/blog")
    @require_admin
    def admin_blog():
        posts = db.query("SELECT * FROM blog_posts ORDER BY created_at DESC")
        return render_template("admin/blog_list.html", posts=posts)

    @app.route("/admin/blog/new", methods=["GET", "POST"])
    @require_admin
    def admin_blog_new():
        if request.method == "POST":
            f = request.form
            title = (f.get("title") or "").strip()
            if not title:
                flash("Title is required.", "error")
                return render_template("admin/blog_form.html", post=None)
            slug = get_unique_slug("blog_posts", f.get("slug") or slugify(title))
            image_url = handle_upload(request.files.get("image_file")) or f.get("image_url") or ""
            try:
                db.execute(
                    "INSERT INTO blog_posts (id, title, slug, excerpt, content, image_url, author, published) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    [str(uuid.uuid4()), title, slug, f.get("excerpt", ""), f.get("content", ""),
                     image_url, f.get("author", "Admin") or "Admin",
                     1 if f.get("published") == "on" else 0]
                )
                flash("Blog post created.", "success")
                return redirect(url_for("admin_blog"))
            except Exception as e:
                flash(f"Error creating post: {e}", "error")
        return render_template("admin/blog_form.html", post=None)

    @app.route("/admin/blog/<post_id>/edit", methods=["GET", "POST"])
    @require_admin
    def admin_blog_edit(post_id):
        post = db.query_one("SELECT * FROM blog_posts WHERE id=?", [post_id])
        if not post:
            abort(404)
        if request.method == "POST":
            f = request.form
            title = (f.get("title") or "").strip()
            if not title:
                flash("Title is required.", "error")
                return render_template("admin/blog_form.html", post=post)
            slug = get_unique_slug("blog_posts", f.get("slug") or slugify(title), exclude_id=post_id)
            image_url = handle_upload(request.files.get("image_file")) or f.get("image_url") or post.get("image_url", "")
            try:
                db.execute(
                    "UPDATE blog_posts SET title=?, slug=?, excerpt=?, content=?, image_url=?, author=?, published=? WHERE id=?",
                    [title, slug, f.get("excerpt", ""), f.get("content", ""),
                     image_url, f.get("author", "Admin") or "Admin",
                     1 if f.get("published") == "on" else 0, post_id]
                )
                flash("Blog post updated.", "success")
                return redirect(url_for("admin_blog"))
            except Exception as e:
                flash(f"Error updating post: {e}", "error")
        return render_template("admin/blog_form.html", post=post)

    @app.route("/admin/blog/<post_id>/delete", methods=["POST"])
    @require_admin
    def admin_blog_delete(post_id):
        try:
            db.execute("DELETE FROM blog_posts WHERE id=?", [post_id])
            flash("Blog post deleted.", "success")
        except Exception as e:
            flash(f"Error: {e}", "error")
        return redirect(url_for("admin_blog"))

    # ── Shipments ──────────────────────────────────────────────────────────

    @app.route("/admin/shipments")
    def admin_shipments():
        """Admin shipment management dashboard"""
        if "user" not in session or session["user"].get("role") != "admin":
            abort(403)

        page = request.args.get("page", 1, type=int)
        per_page = 20
        offset = (page - 1) * per_page

        # Get total count
        total_row = db.query_one("SELECT COUNT(*) as cnt FROM bigship_shipments")
        total = total_row["cnt"] if total_row else 0

        # Get shipments with order details
        shipments = db.query(
            """SELECT s.*, o.order_number, o.customer_name, o.customer_email, o.customer_phone, o.total_amount
               FROM bigship_shipments s
               LEFT JOIN orders o ON o.id = s.order_id
               ORDER BY s.updated_at DESC
               LIMIT ? OFFSET ?""",
            [per_page, offset]
        )

        total_pages = (total + per_page - 1) // per_page

        return render_template(
            "admin/shipments.html",
            shipments=shipments,
            page=page,
            total_pages=total_pages,
            total=total
        )

    @app.route("/admin/bigship-settings", methods=["GET", "POST"])
    def admin_bigship_settings():
        """Manage Bigship settings (box dimensions, addresses, etc)"""
        if "user" not in session or session["user"].get("role") != "admin":
            abort(403)

        if request.method == "POST":
            try:
                # Update settings
                settings = {
                    "pickup_address": request.form.get("pickup_address", ""),
                    "return_address": request.form.get("return_address", ""),
                    "pickup_contact_name": request.form.get("pickup_contact_name", ""),
                    "pickup_phone": request.form.get("pickup_phone", ""),
                    "box_length": request.form.get("box_length", "20"),
                    "box_width": request.form.get("box_width", "15"),
                    "box_height": request.form.get("box_height", "10"),
                    "default_weight": request.form.get("default_weight", "1"),
                }

                for key, value in settings.items():
                    db.execute(
                        "INSERT INTO bigship_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                        [key, value, value]
                    )

                flash("Bigship settings updated successfully.", "success")
            except Exception as e:
                flash(f"Error updating settings: {e}", "error")

        # Get current settings
        settings_rows = db.query("SELECT key, value FROM bigship_settings")
        settings = {row["key"]: row["value"] for row in settings_rows}

        return render_template("admin/bigship_settings.html", settings=settings)
