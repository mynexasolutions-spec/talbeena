from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, Response, jsonify
import db
from helpers import resolve_image
from queries import (
    get_products, get_categories, get_brands,
    get_product_detail, get_related_products,
    get_homepage_products, get_featured_categories,
)

bp = Blueprint("public", __name__)


@bp.route("/")
def index():
    try:
        data = get_homepage_products()
        featured            = data["featured"]
        latest              = data["latest"]
        popular             = data["popular"]
        promo1              = data["promo1"]
        promo2              = data["promo2"]
        
        featured_categories = get_featured_categories()
    except Exception as e:
        featured = latest = popular = promo1 = promo2 = []
        featured_categories = []
        flash(f"Data loading error: {e}", "error")

    # Fetch latest blog posts for homepage
    try:
        blog_posts = db.query(
            "SELECT title, slug, excerpt, image_url, author, created_at "
            "FROM blog_posts WHERE published=1 ORDER BY created_at DESC LIMIT 3"
        )
    except Exception:
        blog_posts = []

    return render_template(
        "index.html",
        featured=featured, latest=latest, popular=popular,
        promo1=promo1, promo2=promo2,
        featured_categories=featured_categories,
        blog_posts=blog_posts,
    )


@bp.route("/shop")
def shop():
    search          = request.args.get("search", "").strip()
    selected_cats   = tuple(s for s in request.args.getlist("category") if s)
    selected_brands = tuple(s for s in request.args.getlist("brand")    if s)
    selected_attrs  = tuple(s for s in request.args.getlist("attr_value") if s)
    sort            = request.args.get("sort", "created_at_desc")
    page            = max(1, int(request.args.get("page", 1)))
    on_sale         = bool(request.args.get("on_sale", ""))
    featured        = bool(request.args.get("featured", ""))
    min_price       = request.args.get("min_price", "").strip()
    max_price       = request.args.get("max_price", "").strip()
    try:
        min_price_val = float(min_price) if min_price else None
        max_price_val = float(max_price) if max_price else None
    except ValueError:
        min_price_val = max_price_val = None
    try:
        products, total, total_pages = get_products(
            search=search, categories=selected_cats, brands=selected_brands,
            sort=sort, page=page, per_page=18, on_sale=on_sale,
            featured=featured, min_price=min_price_val, max_price=max_price_val,
            attribute_values=selected_attrs,
        )
        all_categories = get_categories()
        all_brands     = get_brands()
        # Fetch primary attribute values (e.g. Flavors) for sidebar filter
        flavor_vals = db.query(
            "SELECT av.id, av.value, av.image_url FROM attribute_values av "
            "JOIN attributes a ON a.id = av.attribute_id "
            "WHERE a.variation_type = 'primary' ORDER BY av.value"
        )
    except Exception as e:
        products, total, total_pages = [], 0, 1
        all_categories = all_brands = []
        flavor_vals = []
        flash(f"Database error: {e}", "error")

    # Build parent → children tree for the sidebar accordion
    parent_cats  = [c for c in all_categories if not c.get("parent_id")]
    children_map = {}
    for c in all_categories:
        pid = c.get("parent_id")
        if pid:
            children_map.setdefault(str(pid), []).append(c)

    return render_template(
        "shop.html",
        products=products, total_count=total, total_pages=total_pages,
        current_page=page,
        categories=all_categories, brands=all_brands,
        parent_cats=parent_cats, children_map=children_map,
        search=search,
        current_categories=selected_cats,
        current_brands=selected_brands,
        current_attrs=selected_attrs,
        flavor_vals=flavor_vals,
        current_sort=sort,
        on_sale=on_sale,
        min_price=min_price, max_price=max_price,
    )


@bp.route("/product/<product_id>")
def product_detail(product_id):
    try:
        product, images, variations, reviews, attributes = get_product_detail(product_id)
    except Exception as e:
        flash(f"Error loading product: {e}", "error")
        return redirect(url_for("public.shop"))
    if not product:
        abort(404)
    try:
        related = get_related_products(product.get("category_slug", ""), product_id)
    except Exception:
        related = []
    return render_template(
        "product.html",
        product=product, images=images, variations=variations,
        reviews=reviews, attributes=attributes, related=related,
    )


@bp.route("/category/<slug>")
def category_page(slug):
    return redirect(url_for("public.shop", category=slug))


@bp.route("/brand/<slug>")
def brand_page(slug):
    return redirect(url_for("public.shop", brand=slug))


@bp.route("/about")
def about():
    return render_template("about.html")


@bp.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name    = request.form.get("name", "").strip()
        email   = request.form.get("email", "").strip()
        message = request.form.get("message", "").strip()
        if not all([name, email, message]):
            flash("Please fill in all required fields.", "error")
        else:
            flash("Thank you for your message! We'll get back to you soon.", "success")
            return redirect(url_for("public.contact"))
    return render_template("contact.html")


@bp.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email", "").strip()
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or "application/json" in (request.headers.get("Accept") or "")
    if email:
        try:
            db.execute("INSERT INTO newsletter_subscribers (email) VALUES (?) ON CONFLICT (email) DO NOTHING", [email])
            message = "Thank you for subscribing to our newsletter!"
            if is_ajax:
                return jsonify({"success": True, "message": message})
            flash(message, "success")
        except Exception as e:
            message = "An error occurred while subscribing."
            if is_ajax:
                return jsonify({"success": False, "message": message}), 500
            flash(message, "error")
    else:
        message = "Please enter a valid email address."
        if is_ajax:
            return jsonify({"success": False, "message": message}), 400
        flash(message, "error")
    return redirect(request.referrer or url_for("public.index"))


@bp.route("/sitemap.xml")
def sitemap():
    base = request.host_url.rstrip("/")

    static_pages = [
        ("",         "1.0", "daily"),
        ("/shop",    "0.9", "daily"),
        ("/about",   "0.7", "monthly"),
        ("/contact", "0.7", "monthly"),
    ]

    try:
        products = db.query(
            "SELECT id, updated_at FROM products WHERE is_active = 1 ORDER BY updated_at DESC"
        )
    except Exception:
        products = []

    try:
        categories = db.query(
            "SELECT slug FROM categories WHERE is_active = 1"
        )
    except Exception:
        categories = []

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']

    for path, priority, freq in static_pages:
        lines.append(
            f"  <url><loc>{base}{path}</loc>"
            f"<changefreq>{freq}</changefreq>"
            f"<priority>{priority}</priority></url>"
        )

    for p in products:
        updated = p.get("updated_at")
        lastmod = f"<lastmod>{updated.strftime('%Y-%m-%d')}</lastmod>" if updated else ""
        lines.append(
            f"  <url><loc>{base}/product/{p['id']}</loc>"
            f"{lastmod}<changefreq>weekly</changefreq>"
            f"<priority>0.8</priority></url>"
        )

    for c in categories:
        lines.append(
            f"  <url><loc>{base}/shop?category={c['slug']}</loc>"
            f"<changefreq>weekly</changefreq>"
            f"<priority>0.7</priority></url>"
        )

    lines.append("</urlset>")
    return Response("\n".join(lines), mimetype="application/xml")


@bp.route("/robots.txt")
def robots():
    base = request.host_url.rstrip("/")
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /cart\n"
        "Disallow: /checkout\n"
        "Disallow: /account\n"
        "Disallow: /login\n"
        "Disallow: /register\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


# ── Variation API ──────────────────────────────────────────────────────────────

@bp.route("/api/product/<product_id>/variation")
def api_product_variation(product_id):
    """
    Returns full variation data as JSON.  Two modes:

    1. No query params  →  Returns all attribute groups with their values
                             plus all variations for initial page render.

    2. ?selected=val1,val2  →  Returns the single matching variation's
                                price, stock, SKU, and images.
    """
    product = db.query_one(
        "SELECT id, name, price, sale_price, stock_quantity, stock_status, type, sku "
        "FROM products WHERE id = ? AND is_active = 1",
        [product_id],
    )
    if not product:
        return jsonify({"error": "Product not found"}), 404

    # ── Load attributes grouped by variation_type ──
    attrs = db.query("""
        SELECT a.id, a.name, a.slug, a.variation_type
        FROM product_attributes pa
        JOIN attributes a ON a.id = pa.attribute_id
        WHERE pa.product_id = ?
        ORDER BY a.display_order
    """, [product_id])

    if not attrs:
        # No attributes — return base product data
        return jsonify({
            "product": {
                "price":        float(product.get("sale_price") or product.get("price") or 0),
                "stock":        int(product.get("stock_quantity") or 0),
                "stock_status": product.get("stock_status"),
                "sku":          product.get("sku"),
            },
            "attributes": [],
            "variations": [],
        })

    # Load values for each attribute (admin-checked values first, then all)
    attr_ids = [a["id"] for a in attrs]
    ph = ",".join(["?"] * len(attr_ids))
    pav_rows = db.query(
        f"""SELECT av.attribute_id, av.id, av.value, av.image_url
            FROM product_attribute_values pav
            JOIN attribute_values av ON av.id = pav.attribute_value_id
            WHERE pav.product_id = ? AND av.attribute_id IN ({ph})
            ORDER BY av.value""",
        [product_id] + attr_ids,
    )
    # Fallback: all values for those attributes
    all_vals = db.query(
        f"SELECT attribute_id, id, value, image_url FROM attribute_values "
        f"WHERE attribute_id IN ({ph}) ORDER BY value",
        attr_ids,
    )

    # Build value maps — prefer admin-checked, fall back to all
    val_map = {}
    for row in pav_rows:
        val_map.setdefault(str(row["attribute_id"]), []).append(row)
    for row in all_vals:
        aid = str(row["attribute_id"])
        if aid not in val_map:
            val_map.setdefault(aid, []).append(row)

    # Build the grouped attributes response
    attr_groups = []
    for a in attrs:
        vals = val_map.get(str(a["id"]), [])
        attr_groups.append({
            "id":              a["id"],
            "name":            a["name"],
            "slug":            a["slug"],
            "variation_type":  a["variation_type"],
            "values": [{
                "id":        v["id"],
                "value":     v["value"],
                "image_url": resolve_image(v.get("image_url") or ""),
            } for v in vals],
        })

    # ── Load variations ──
    variations = db.query(
        "SELECT * FROM product_variations WHERE product_id = ?",
        [product_id],
    )
    # Batch-load variation→attribute_value mappings
    var_data = []
    if variations:
        var_ids = [v["id"] for v in variations]
        ph2 = ",".join(["?"] * len(var_ids))
        vav_rows = db.query(
            f"SELECT vav.variation_id, vav.attribute_value_id, av.value, av.attribute_id "
            f"FROM variation_attribute_values vav "
            f"JOIN attribute_values av ON av.id = vav.attribute_value_id "
            f"WHERE vav.variation_id IN ({ph2})",
            var_ids,
        )
        vav_map = {}
        for r in vav_rows:
            vav_map.setdefault(str(r["variation_id"]), []).append(r)

        # Batch-load variation images
        vi_rows = db.query(
            f"SELECT vi.variation_id, m.file_url, vi.is_primary "
            f"FROM variation_images vi "
            f"JOIN media m ON m.id = vi.media_id "
            f"WHERE vi.variation_id IN ({ph2}) "
            f"ORDER BY vi.is_primary DESC, vi.display_order",
            var_ids,
        )
        var_image_map = {}
        for r in vi_rows:
            var_image_map.setdefault(str(r["variation_id"]), []).append(
                resolve_image(r["file_url"] or "")
            )

        for v in variations:
            vid = str(v["id"])
            var_data.append({
                "id":             vid,
                "sku":            v.get("sku"),
                "price":          float(v.get("sale_price") or v.get("price") or 0),
                "stock_quantity": int(v.get("stock_quantity") or 0),
                "stock_status":   v.get("stock_status"),
                "images":         var_image_map.get(vid, []),
                "values": [{
                    "attribute_id": r["attribute_id"],
                    "value_id":     r["attribute_value_id"],
                    "value":        r["value"],
                } for r in vav_map.get(vid, [])],
                "name":             v.get("name") or "",
                "short_description": v.get("short_description") or "",
                "description":      v.get("description") or "",
            })

    # ── If ?selected= is provided, find the matching variation ──
    selected_raw = request.args.get("selected", "")
    if selected_raw:
        selected_ids = set(s.strip() for s in selected_raw.split(",") if s.strip())
        match = None
        for vd in var_data:
            v_val_ids = set(str(r["value_id"]) for r in vd["values"])
            if v_val_ids == selected_ids:
                match = vd
                break
        if match:
            return jsonify({
                "found": True,
                "price":          match["price"],
                "stock_quantity": match["stock_quantity"],
                "stock_status":   match["stock_status"],
                "sku":            match["sku"],
                "variation_id":   match["id"],
                "images":         match["images"],
                "name":           match.get("name", ""),
                "short_description": match.get("short_description", ""),
                "description":    match.get("description", ""),
            })
        else:
            return jsonify({"found": False, "message": "No matching variation"}), 404

    # Full data mode (no ?selected=)
    return jsonify({
        "product": {
            "price":        float(product.get("sale_price") or product.get("price") or 0),
            "stock":        int(product.get("stock_quantity") or 0),
            "stock_status": product.get("stock_status"),
            "sku":          product.get("sku"),
        },
        "attributes": attr_groups,
        "variations": var_data,
    })
