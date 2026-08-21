import math
import datetime as _dt
import uuid
import db
from helpers import ttl_cache

_EPOCH = _dt.datetime.min

# Pre-aggregated variation minimum prices joined once per query instead of a
# correlated subquery running per product row.
_VARIATION_PRICE_JOIN = """
    LEFT JOIN (
        SELECT product_id, MIN(price) AS var_min_price
        FROM product_variations
        WHERE price > 0
        GROUP BY product_id
    ) vp ON vp.product_id = p.id
"""

# Effective listing price: cheapest positive variation for variable products,
# otherwise the base product price.
_PRODUCTS_PRICE_EXPR = "COALESCE(CASE WHEN p.type = 'variable' THEN vp.var_min_price END, p.price)"

PRODUCTS_SELECT = f"""
    SELECT
        p.id, p.name, p.slug, p.sku, p.type, p.short_description, p.description,
        {_PRODUCTS_PRICE_EXPR} AS price,
        CASE WHEN p.type = 'variable' THEN NULL ELSE p.sale_price END AS sale_price,
        p.stock_quantity, p.stock_status,
        p.is_featured, p.is_active, p.created_at,
        c.name  AS category_name, c.slug AS category_slug,
        b.name  AS brand_name,    b.slug AS brand_slug,
        m.file_url AS image_url
    FROM products p
    {_VARIATION_PRICE_JOIN}
    LEFT JOIN categories c ON c.id = p.category_id
    LEFT JOIN brands b      ON b.id = p.brand_id
    LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_primary = 1
    LEFT JOIN media m ON m.id = pi.media_id
"""

PRODUCTS_MINIMAL_SELECT = f"""
    SELECT
        p.id, p.name, p.slug, p.sku, p.type,
        {_PRODUCTS_PRICE_EXPR} AS price,
        CASE WHEN p.type = 'variable' THEN NULL ELSE p.sale_price END AS sale_price,
        p.stock_status, p.is_featured, p.created_at,
        c.name AS category_name, c.slug AS category_slug,
        m.file_url AS image_url
    FROM products p
    {_VARIATION_PRICE_JOIN}
    LEFT JOIN categories c ON c.id = p.category_id
    LEFT JOIN product_images pi ON pi.product_id = p.id AND pi.is_primary = 1
    LEFT JOIN media m ON m.id = pi.media_id
"""


@ttl_cache(ttl_seconds=600)
def _get_variation_cards():
    """
    Returns a lookup: { product_id: [ expanded_row_dict, ... ] }
    where EVERY variation of a variable product becomes its own listing card.
    Each card has its own name, image, price, stock, SKU, and description.
    """
    variable_products = db.query("""
        SELECT DISTINCT p.id, p.name
        FROM products p
        WHERE p.is_active = 1 AND p.type = 'variable'
    """)
    if not variable_products:
        return {}

    product_ids = [str(p["id"]) for p in variable_products]
    if not product_ids:
        return {}

    ph = ",".join(["?"] * len(product_ids))

    # Fetch all variations with their attribute values in one query
    rows = db.query(f"""
        SELECT
            pv.product_id,
            pv.id AS var_id, pv.sku, pv.price, pv.sale_price,
            pv.stock_quantity, pv.stock_status,
            pv.name AS var_name, pv.description AS var_desc,
            pv.short_description AS var_short_desc,
            STRING_AGG(av.value, ', ' ORDER BY av.value) AS label,
            (SELECT m.file_url
             FROM variation_images vi
             JOIN media m ON m.id = vi.media_id
             WHERE vi.variation_id = pv.id AND vi.is_primary = 1
             LIMIT 1) AS var_image,
            (SELECT m.file_url
             FROM product_images pi2
             JOIN media m ON m.id = pi2.media_id
             WHERE pi2.product_id = pv.product_id AND pi2.is_primary = 1
             LIMIT 1) AS product_image
        FROM product_variations pv
        LEFT JOIN variation_attribute_values vav ON vav.variation_id = pv.id
        LEFT JOIN attribute_values av ON av.id = vav.attribute_value_id
        WHERE pv.product_id IN ({ph})
        GROUP BY pv.id
        ORDER BY pv.product_id, pv.price
    """, product_ids)

    result = {}
    product_names = {str(p["id"]): p["name"] for p in variable_products}

    for r in rows:
        pid = str(r["product_id"])
        if pid not in result:
            result[pid] = []

        label = r.get("label") or ""
        base_name = product_names.get(pid, "")

        var_price = r.get("sale_price") if r.get("sale_price") and float(r["sale_price"]) > 0 else r.get("price") if r.get("price") and float(r["price"]) > 0 else 0
        result[pid].append({
            "var_id":         r["var_id"],
            "sku":            r["sku"],
            "price":          float(var_price),
            "stock_quantity": int(r.get("stock_quantity") or 0),
            "stock_status":   r.get("stock_status", "in_stock"),
            "name_override":  r.get("var_name") or f"{base_name} – {label}" if label else base_name,
            "image_url":      r.get("var_image") or r.get("product_image") or "",
            "description":    r.get("var_desc") or "",
            "short_description": r.get("var_short_desc") or "",
            "label":          label,
            "_preselect_label": r.get("label", "")
        })

    return result


def _expand_product_list(products):
    """Expand every variation into a separate listing card."""
    var_map = _get_variation_cards()
    expanded = []
    for p in (products or []):
        pid = str(p["id"])
        if pid in var_map:
            has_valid = False
            for r in var_map[pid]:
                if r["price"] <= 0:
                    continue
                has_valid = True
                row = dict(p)
                row["id"]             = pid
                row["name"]           = r["name_override"]
                row["price"]          = r["price"]
                row["sale_price"]     = None
                row["stock_quantity"] = r["stock_quantity"]
                row["stock_status"]   = r["stock_status"]
                row["sku"]            = r["sku"]
                row["image_url"]      = r["image_url"] or p.get("image_url") or ""
                row["description"]    = r.get("description") or row.get("description") or ""
                row["short_description"] = r.get("short_description") or row.get("short_description") or ""
                row["_preselect_label"] = r.get("label", "")
                expanded.append(row)
            if not has_valid:
                expanded.append(p)
        else:
            expanded.append(p)
    return expanded


@ttl_cache(ttl_seconds=300)
def get_products(search=None, categories=(), brands=(),
                 sort="created_at_desc", page=1, per_page=16,
                 featured=False, limit=None, on_sale=False,
                 min_price=None, max_price=None,
                 # legacy single-value aliases kept for admin callers
                 category=None, brand=None, skip_expand=False,
                 attribute_values=()):
    # Normalise: merge legacy single values into the multi-select tuples
    cats_list = list(c for c in (list(categories or []) + ([category] if category else [])) if c)
    if len(cats_list) > 1:
        all_cats = get_categories()
        sel_cats = [c for c in all_cats if c["slug"] in cats_list]
        parent_ids = {c["parent_id"] for c in sel_cats if c.get("parent_id")}
        cats = tuple(c["slug"] for c in sel_cats if c["id"] not in parent_ids)
    else:
        cats = tuple(cats_list)
        
    brnds = tuple(b for b in (list(brands or []) + ([brand] if brand else [])) if b)

    conditions = ["p.is_active = 1"]
    params     = []

    if search:
        conditions.append("""(p.name LIKE ? OR p.sku LIKE ? OR p.description LIKE ?
            OR p.id IN (
                SELECT pv.product_id FROM product_variations pv
                JOIN variation_attribute_values vav ON vav.variation_id = pv.id
                JOIN attribute_values av ON av.id = vav.attribute_value_id
                WHERE av.value LIKE ?
            )
        )""")
        params += [f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"]
    if cats:
        ph = ",".join(["?"] * len(cats))
        # Include products from the selected category AND any of its child categories
        conditions.append(f"""p.category_id IN (
            SELECT id FROM categories
            WHERE slug IN ({ph})
               OR parent_id IN (SELECT id FROM categories WHERE slug IN ({ph}))
        )""")
        params += list(cats) + list(cats)
    if brnds:
        ph = ",".join(["?"] * len(brnds))
        conditions.append(f"b.slug IN ({ph})")
        params += list(brnds)
    if featured:
        conditions.append("p.is_featured = 1")
    if on_sale:
        conditions.append("p.sale_price IS NOT NULL AND p.sale_price > 0 AND p.sale_price < p.price")
    if attribute_values:
        ph = ",".join(["?"] * len(attribute_values))
        conditions.append(f"""p.id IN (
            SELECT pv.product_id FROM product_variations pv
            JOIN variation_attribute_values vav ON vav.variation_id = pv.id
            WHERE vav.attribute_value_id IN ({ph})
        )""")
        params += list(attribute_values)
    if min_price is not None:
        conditions.append("COALESCE(p.sale_price, p.price) >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("COALESCE(p.sale_price, p.price) <= ?")
        params.append(max_price)


    where     = "WHERE " + " AND ".join(conditions)
    order_map = {
        "created_at_desc": "p.created_at DESC",
        "created_at_asc":  "p.created_at ASC",
        # Sort on the aggregated listing price (min variation price for
        # variable products) so ordering matches what shoppers see.
        "price_asc":       "price ASC",
        "price_desc":      "price DESC",
        "name_asc":        "p.name ASC",
    }
    order            = f"{order_map.get(sort, 'p.created_at DESC')}"

    if limit:
        products = db.query(
            f"{PRODUCTS_MINIMAL_SELECT} {where} ORDER BY {order} LIMIT ?",
            params + [limit],
        )
        # Expand primary variations even for limited queries
        return _expand_product_list(products)

    # Total matching base products via a dedicated COUNT query — no need to
    # pull every row just to count them.
    total = int((db.query_one(
        f"SELECT COUNT(*) AS total FROM products p "
        f"LEFT JOIN brands b ON b.id = p.brand_id {where}",
        params,
    ) or {}).get("total") or 0)
    total_pages = max(1, math.ceil(total / per_page))
    offset      = (page - 1) * per_page

    # Fetch only one page worth of base products at the SQL level
    # (LIMIT/OFFSET), then expand variations just for that page.
    #
    # Behaviour nuance vs. the old fetch-everything approach: pages are now
    # built from base products, so a variable product expands into all of its
    # variation cards within a single page and a page may render more than
    # `per_page` cards when several variable products land on it. Previously
    # the expanded card list was sliced mid-product across page boundaries.
    # `total`/`total_pages` are computed from base product counts.
    page_products = db.query(
        f"{PRODUCTS_SELECT} {where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [per_page, offset],
    )

    if skip_expand:
        return page_products, total, total_pages

    products = _expand_product_list(page_products)
    return products, total, total_pages


@ttl_cache(ttl_seconds=300)
def get_homepage_products():
    """Single query for all homepage product sections; partitioned in Python. Cached for 5 minutes."""
    rows = db.query(
        f"{PRODUCTS_MINIMAL_SELECT} WHERE p.is_active = 1 ORDER BY p.is_featured DESC, p.created_at DESC LIMIT 100"
    )
    featured   = [r for r in rows if r.get("is_featured")][:10]
    if not featured:
        featured = rows[:10]
    latest     = sorted(rows, key=lambda r: r.get("created_at") or _EPOCH, reverse=True)[:10]
    popular    = sorted(rows, key=lambda r: (r.get("name") or "").lower())[:10]
    
    price_asc  = sorted(rows, key=lambda r: float(r.get("price") or 0))
    promo1     = rows[:2]
    promo2     = price_asc[:2]

    # Expand primary variations in all sections
    featured = _expand_product_list(featured)
    latest   = _expand_product_list(latest)
    popular  = _expand_product_list(popular)
    promo1   = _expand_product_list(promo1)
    promo2   = _expand_product_list(promo2)
    
    return {
        "featured": featured, "latest": latest, "popular": popular,
        "promo1": promo1, "promo2": promo2
    }


@ttl_cache(ttl_seconds=1800)
def get_featured_categories():
    return db.query("""
        SELECT name AS label, image_url AS img, slug
        FROM categories
        WHERE parent_id IS NULL
        GROUP BY name, image_url, slug
        ORDER BY name ASC
    """) or []


@ttl_cache(ttl_seconds=3600)
def get_blog_posts():
    """Get latest published blog posts. Cached for 1 hour."""
    return db.query(
        "SELECT title, slug, excerpt, image_url, author, created_at "
        "FROM blog_posts WHERE published=1 ORDER BY created_at DESC LIMIT 3"
    ) or []


@ttl_cache(ttl_seconds=600)
def get_product_detail(product_id, preselect=None):
    """Get product details. Cached for 10 minutes. Clears on product update."""
    product = db.query_one(f"{PRODUCTS_SELECT} WHERE p.id = ?", [product_id])
    if not product:
        return None, [], [], [], []

    images = db.query(
        """SELECT m.file_url AS image_url, pi.is_primary,
                  COALESCE(m.alt_text, '') AS alt_text
           FROM product_images pi
           JOIN media m ON m.id = pi.media_id
           WHERE pi.product_id = ?
           ORDER BY pi.is_primary DESC, pi.display_order""",
        [product_id],
    )

    variations = db.query(
        "SELECT * FROM product_variations WHERE product_id = ?", [product_id]
    )

    base_price = float(product.get("sale_price") or product.get("price") or 0)
    base_stock = int(product.get("stock_quantity") or 0)

    # ── Server-side pre-selection (before price overwriting) ──
    preselect_match = None
    if preselect and product.get("type") == "variable" and variations:
        preselect_parts = [p.strip() for p in preselect.split(",") if p.strip()]
        if preselect_parts:
            var_ids_tmp = [v["id"] for v in variations]
            ph_tmp = ",".join(["?"] * len(var_ids_tmp))
            vav_rows = db.query(
                f"SELECT vav.variation_id, av.value "
                f"FROM variation_attribute_values vav "
                f"JOIN attribute_values av ON av.id = vav.attribute_value_id "
                f"WHERE vav.variation_id IN ({ph_tmp})",
                var_ids_tmp,
            )
            var_val_map = {}
            for r in vav_rows:
                var_val_map.setdefault(str(r["variation_id"]), []).append(r["value"])
            for v in variations:
                vals = var_val_map.get(str(v["id"]), [])
                if all(p in vals for p in preselect_parts):
                    preselect_match = v
                    break

    # Batch-load all variation→attribute_value mappings in ONE query
    if variations:
        var_ids      = [v["id"] for v in variations]
        placeholders = ",".join(["?"] * len(var_ids))
        all_vav      = db.query(
            f"SELECT variation_id, attribute_value_id "
            f"FROM variation_attribute_values WHERE variation_id IN ({placeholders})",
            var_ids,
        )
        vav_map = {}
        for row in all_vav:
            vav_map.setdefault(str(row["variation_id"]), []).append(row["attribute_value_id"])
        for v in variations:
            # Only overwrite price/stock for non-matched variations
            if preselect_match and str(v["id"]) == str(preselect_match["id"]):
                pass  # keep the real DB values
            else:
                v["price"]          = base_price
                v["stock_quantity"] = base_stock
            v["attribute_value_ids"] = vav_map.get(str(v["id"]), [])
    else:
        for v in variations:
            v["price"]               = base_price
            v["stock_quantity"]      = base_stock
            v["attribute_value_ids"] = []

    if product.get("type") == "variable":
        product["price"] = base_price if base_price > 0 else float(product.get("price") or 0)

    # ── Apply preselect overrides (after price loading) ────────────────────
    if preselect_match:
        # Compose display name: use variation name or "Base – Label"
        var_label = ", ".join(preselect_parts)
        var_display_name = (preselect_match.get("name") or
                            f"{product['name']} – {var_label}") if var_label else product["name"]
        product["name"]             = var_display_name
        product["description"]      = preselect_match.get("description") or product.get("description", "")
        product["short_description"] = preselect_match.get("short_description") or product.get("short_description", "")
        product["price"]            = float(preselect_match.get("sale_price") or preselect_match.get("price") or product.get("price", 0))
        product["sale_price"]       = float(preselect_match["sale_price"]) if preselect_match.get("sale_price") else product.get("sale_price")
        product["sku"]              = preselect_match.get("sku") or product.get("sku", "")
        product["stock_quantity"]   = int(preselect_match.get("stock_quantity") or product.get("stock_quantity", 0))
        product["stock_status"]     = preselect_match.get("stock_status") or product.get("stock_status", "in_stock")

        # Load variation images (fall back to base images if none)
        var_images = db.query(
            """SELECT m.file_url AS image_url, vi.is_primary,
                      COALESCE(m.alt_text, '') AS alt_text
               FROM variation_images vi
               JOIN media m ON m.id = vi.media_id
               WHERE vi.variation_id = ?
               ORDER BY vi.is_primary DESC, vi.display_order""",
            [preselect_match["id"]],
        )
        if var_images:
            images = var_images
            product["image_url"] = var_images[0]["image_url"]
        # else: keep base images as fallback

    reviews = db.query(
        """SELECT r.*, (u.first_name || ' ' || u.last_name) AS reviewer_name
           FROM product_reviews r LEFT JOIN users u ON u.id = r.user_id
           WHERE r.product_id = ? AND r.is_approved = 1
           ORDER BY r.created_at DESC""",
        [product_id],
    )

    attributes = db.query("""
        SELECT a.id, a.name, a.slug
        FROM attributes a
        JOIN product_attributes pa ON pa.attribute_id = a.id
        WHERE pa.product_id = ?
        ORDER BY pa.display_order ASC
    """, [product_id])

    if not attributes:
        attributes = db.query("""
            SELECT DISTINCT a.id, a.name, a.slug
            FROM attributes a
            JOIN attribute_values av ON av.attribute_id = a.id
            JOIN variation_attribute_values vav ON vav.attribute_value_id = av.id
            JOIN product_variations pv ON pv.id = vav.variation_id
            WHERE pv.product_id = ?
        """, [product_id])

    # Batch-load attribute values with correct priority:
    # 1. Admin-selected values for this product (product_attribute_values)
    # 2. Values linked via generated variations (variation_attribute_values)
    # 3. All values for the attribute (last resort — should rarely be reached)
    if attributes:
        attr_ids     = [a["id"] for a in attributes]
        placeholders = ",".join(["?"] * len(attr_ids))

        # Priority 1: values the admin explicitly checked for this product
        pav_rows = db.query(
            f"""SELECT DISTINCT av.attribute_id, av.id, av.value
                FROM attribute_values av
                JOIN product_attribute_values pav ON pav.attribute_value_id = av.id
                WHERE av.attribute_id IN ({placeholders}) AND pav.product_id = ?
                ORDER BY av.value ASC""",
            attr_ids + [product_id],
        )
        pav_map = {}
        for row in pav_rows:
            pav_map.setdefault(str(row["attribute_id"]), []).append(
                {"id": str(row["id"]), "value": row["value"]}
            )

        # Priority 2: values linked through generated product variations
        var_rows = db.query(
            f"""SELECT DISTINCT av.attribute_id, av.id, av.value
                FROM attribute_values av
                JOIN variation_attribute_values vav ON vav.attribute_value_id = av.id
                JOIN product_variations pv ON pv.id = vav.variation_id
                WHERE av.attribute_id IN ({placeholders}) AND pv.product_id = ?
                ORDER BY av.value ASC""",
            attr_ids + [product_id],
        )
        var_map = {}
        for row in var_rows:
            var_map.setdefault(str(row["attribute_id"]), []).append(
                {"id": str(row["id"]), "value": row["value"]}
            )

        for attr in attributes:
            aid    = str(attr["id"])
            values = pav_map.get(aid) or var_map.get(aid)
            if not values:
                # Priority 3: load all values for this attribute (fallback)
                fallback = db.query(
                    "SELECT id, value FROM attribute_values "
                    "WHERE attribute_id = ? ORDER BY value ASC",
                    [attr["id"]],
                )
                values = [{"id": str(r["id"]), "value": r["value"]} for r in fallback]
            attr["values"] = values

    return product, images, variations, reviews, attributes


@ttl_cache(ttl_seconds=120)
@ttl_cache(ttl_seconds=600)
def get_related_products(category_slug, exclude_id, limit=4):
    """Get related products from same category. Cached for 10 minutes."""
    # First, try products from the same category
    results = db.query(
        f"{PRODUCTS_MINIMAL_SELECT} WHERE p.is_active = 1 AND c.slug = ? AND p.id != ? "
        f"ORDER BY p.created_at DESC LIMIT ?",
        [category_slug, exclude_id, limit],
    )
    if len(results) >= limit:
        return results
    # Fall back to other active products (excluding the current one)
    existing_ids = [r["id"] for r in results] + [exclude_id]
    needed = limit - len(results)
    fallback = db.query(
        f"{PRODUCTS_MINIMAL_SELECT} WHERE p.is_active = 1 AND p.id NOT IN ({','.join(['?']*len(existing_ids))}) "
        f"ORDER BY p.created_at DESC LIMIT ?",
        existing_ids + [needed],
    )
    return results + fallback


@ttl_cache(ttl_seconds=600)
def get_categories():
    return db.query("""
        SELECT c.id, c.name, c.slug, c.parent_id, cp.name AS parent_name, c.image_url AS img,
               (
                   SELECT COUNT(*)
                   FROM products p
                   WHERE p.is_active = 1
                     AND (
                         p.category_id = c.id
                         OR p.category_id IN (
                             SELECT id FROM categories WHERE parent_id = c.id
                         )
                     )
               ) AS product_count
        FROM categories c
        LEFT JOIN categories cp ON cp.id = c.parent_id
        ORDER BY c.name ASC
    """)


@ttl_cache(ttl_seconds=600)
def get_brands():
    return db.query("""
        SELECT b.id, b.name, b.slug, COUNT(p.id) AS product_count
        FROM brands b
        LEFT JOIN products p ON p.brand_id = b.id AND p.is_active = 1
        GROUP BY b.id, b.name, b.slug
        ORDER BY b.name
    """)


@ttl_cache(ttl_seconds=300)
def get_admin_stats():
    """All dashboard stats in a single round-trip."""
    row = db.query_one("""
        SELECT
            (SELECT COUNT(*)                  FROM products WHERE is_active = 1)                    AS total_products,
            (SELECT COUNT(*)                  FROM orders)                                              AS total_orders,
            (SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status != 'cancelled')            AS total_revenue,
            (SELECT COUNT(*)                  FROM users   WHERE role = 'customer')                    AS total_customers,
            (SELECT COUNT(*)                  FROM orders  WHERE status = 'pending')                   AS pending_orders,
            (SELECT COUNT(*)                  FROM products WHERE stock_quantity <= 5 AND is_active = 1) AS low_stock
    """) or {}
    return {
        "total_products":  row.get("total_products",  0),
        "total_orders":    row.get("total_orders",    0),
        "total_revenue":   float(row.get("total_revenue", 0)),
        "total_customers": row.get("total_customers", 0),
        "pending_orders":  row.get("pending_orders",  0),
        "low_stock":       row.get("low_stock",       0),
    }
