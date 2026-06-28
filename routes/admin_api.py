"""
routes/admin_api.py — FastAPI Admin Routes
Complete conversion from Flask routes/admin.py
CRUD operations for products, categories, orders, settings, etc.
"""
from fastapi import APIRouter, Request, Form, HTTPException, Query, File, UploadFile, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import uuid
import json
from datetime import datetime
import db
from helpers import handle_upload, get_unique_slug, slugify
from queries import get_products, get_categories, get_brands, PRODUCTS_SELECT, PRODUCTS_MINIMAL_SELECT
from dependencies import require_admin

router = APIRouter()


# ─── Admin Stats ───────────────────────────────────────────────────────────
def _get_admin_stats():
    """Get dashboard statistics."""
    try:
        total_products = db.query_one("SELECT COUNT(*) AS cnt FROM products WHERE is_active=1")
        total_orders = db.query_one("SELECT COUNT(*) AS cnt FROM orders")
        total_revenue = db.query_one("SELECT SUM(total_amount) AS total FROM orders WHERE payment_status='paid'")
        total_customers = db.query_one("SELECT COUNT(*) AS cnt FROM users WHERE role='customer'")
        pending_orders = db.query_one("SELECT COUNT(*) AS cnt FROM orders WHERE status='pending'")
        low_stock = db.query_one("SELECT COUNT(*) AS cnt FROM products WHERE stock_quantity < 10 AND is_active=1")

        return {
            "total_products": total_products.get("cnt", 0) if total_products else 0,
            "total_orders": total_orders.get("cnt", 0) if total_orders else 0,
            "total_revenue": float(total_revenue.get("total") or 0) if total_revenue else 0.0,
            "total_customers": total_customers.get("cnt", 0) if total_customers else 0,
            "pending_orders": pending_orders.get("cnt", 0) if pending_orders else 0,
            "low_stock": low_stock.get("cnt", 0) if low_stock else 0,
        }
    except Exception as e:
        return {
            "total_products": 0, "total_orders": 0, "total_revenue": 0.0,
            "total_customers": 0, "pending_orders": 0, "low_stock": 0,
        }


# ─── Dashboard ──────────────────────────────────────────────────────────────
@router.get("")
async def admin_dashboard(request: Request, user: dict = Depends(require_admin)):
    """Admin dashboard with statistics."""
    stats = _get_admin_stats()

    try:
        recent_orders = db.query(
            """SELECT o.id, o.order_number, o.created_at, o.total_amount, o.status,
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
            "values": [float(r.get("amount", 0)) for r in chart_rows],
        }
    except Exception:
        chart_data = {"labels": [], "values": []}

    return request.app.state.templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "stats": stats,
            "recent_orders": recent_orders,
            "recent_products": recent_products,
            "chart_data": chart_data,
        }
    )


# ─── Products ───────────────────────────────────────────────────────────────
@router.get("/products")
async def admin_products(
    request: Request,
    user: dict = Depends(require_admin),
    search: str = Query(""),
    category: str = Query(""),
    brand: str = Query(""),
    page: int = Query(1),
):
    """List products for admin."""
    page = max(1, page)

    try:
        products, total, total_pages = get_products(
            search=search, category=category, brand=brand, page=page, per_page=20, skip_expand=True
        )
        categories = get_categories()
        brands = get_brands()
    except Exception as e:
        products, total, total_pages = [], 0, 1
        categories = brands = []

    return request.app.state.templates.TemplateResponse(
        "admin/products.html",
        {
            "request": request,
            "products": products,
            "total": total,
            "total_pages": total_pages,
            "page": page,
            "categories": categories,
            "brands": brands,
            "search": search,
            "selected_category": category,
            "selected_brand": brand,
        }
    )


@router.get("/products/new")
async def admin_product_new_get(request: Request, user: dict = Depends(require_admin)):
    """Show new product form."""
    try:
        categories = get_categories()
        brands = get_brands()
        all_attributes = db.query("SELECT * FROM attributes ORDER BY name ASC")
        for attr in all_attributes:
            attr["options"] = db.query(
                "SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr["id"]]
            )
    except Exception:
        categories = brands = all_attributes = []

    return request.app.state.templates.TemplateResponse(
        "admin/product_form.html",
        {
            "request": request,
            "categories": categories,
            "brands": brands,
            "attributes": all_attributes,
            "product": None,
        }
    )


@router.post("/products/new")
async def admin_product_new_post(
    request: Request,
    user: dict = Depends(require_admin),
    name: str = Form(...),
    sku: str = Form(default=""),
    description: str = Form(default=""),
    price: float = Form(...),
    sale_price: str = Form(default=""),
    stock_quantity: int = Form(default=0),
    category_id: str = Form(default=""),
    brand_id: str = Form(default=""),
    is_active: str = Form(default="1"),
    is_featured: str = Form(default="0"),
):
    """Create new product."""
    try:
        product_id = str(uuid.uuid4())
        sale_price_float = float(sale_price) if sale_price else None

        db.execute(
            """INSERT INTO products
               (id, name, sku, description, price, sale_price, stock_quantity,
                category_id, brand_id, is_active, is_featured)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                product_id, name, sku or "", description, price, sale_price_float,
                stock_quantity, category_id or None, brand_id or None,
                is_active == "1", is_featured == "1"
            ]
        )

        return RedirectResponse(url=f"/admin/products/{product_id}/edit", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating product: {e}")


@router.get("/products/{product_id}/edit")
async def admin_product_edit_get(request: Request, product_id: str, user: dict = Depends(require_admin)):
    """Show product edit form."""
    try:
        product = db.query_one("SELECT * FROM products WHERE id=?", [product_id])
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        categories = get_categories()
        brands = get_brands()
        all_attributes = db.query("SELECT * FROM attributes ORDER BY name ASC")
        for attr in all_attributes:
            attr["options"] = db.query(
                "SELECT * FROM attribute_values WHERE attribute_id = ? ORDER BY value ASC", [attr["id"]]
            )

        images = db.query("SELECT * FROM product_images WHERE product_id=? ORDER BY sort_order ASC", [product_id])
        variations = db.query("SELECT * FROM product_variations WHERE product_id=? ORDER BY created_at ASC", [product_id])

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return request.app.state.templates.TemplateResponse(
        "admin/product_form.html",
        {
            "request": request,
            "product": product,
            "categories": categories,
            "brands": brands,
            "attributes": all_attributes,
            "images": images,
            "variations": variations,
        }
    )


@router.post("/products/{product_id}/edit")
async def admin_product_edit_post(
    request: Request,
    product_id: str,
    user: dict = Depends(require_admin),
    name: str = Form(...),
    sku: str = Form(default=""),
    description: str = Form(default=""),
    price: float = Form(...),
    sale_price: str = Form(default=""),
    stock_quantity: int = Form(default=0),
    category_id: str = Form(default=""),
    brand_id: str = Form(default=""),
    is_active: str = Form(default="1"),
    is_featured: str = Form(default="0"),
):
    """Update product."""
    try:
        sale_price_float = float(sale_price) if sale_price else None

        db.execute(
            """UPDATE products SET
               name=?, sku=?, description=?, price=?, sale_price=?,
               stock_quantity=?, category_id=?, brand_id=?, is_active=?, is_featured=?
               WHERE id=?""",
            [
                name, sku or "", description, price, sale_price_float,
                stock_quantity, category_id or None, brand_id or None,
                is_active == "1", is_featured == "1", product_id
            ]
        )

        return RedirectResponse(url=f"/admin/products/{product_id}/edit", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating product: {e}")


@router.post("/products/{product_id}/delete")
async def admin_product_delete(request: Request, product_id: str, user: dict = Depends(require_admin)):
    """Delete product."""
    try:
        db.execute("DELETE FROM product_images WHERE product_id=?", [product_id])
        db.execute("DELETE FROM product_variations WHERE product_id=?", [product_id])
        db.execute("DELETE FROM products WHERE id=?", [product_id])
        return RedirectResponse(url="/admin/products", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting product: {e}")


# ─── Categories ────────────────────────────────────────────────────────────
@router.get("/categories")
async def admin_categories(request: Request, user: dict = Depends(require_admin)):
    """List categories."""
    try:
        categories = db.query("SELECT * FROM categories ORDER BY name ASC")
    except Exception:
        categories = []

    return request.app.state.templates.TemplateResponse(
        "admin/categories.html",
        {"request": request, "categories": categories}
    )


@router.get("/categories/new")
async def admin_category_new_get(request: Request, user: dict = Depends(require_admin)):
    """Show new category form."""
    try:
        parent_categories = db.query("SELECT * FROM categories WHERE parent_id IS NULL ORDER BY name ASC")
    except Exception:
        parent_categories = []

    return request.app.state.templates.TemplateResponse(
        "admin/category_form.html",
        {"request": request, "parent_categories": parent_categories, "category": None}
    )


@router.post("/categories/new")
async def admin_category_new_post(
    request: Request,
    user: dict = Depends(require_admin),
    name: str = Form(...),
    slug: str = Form(default=""),
    parent_id: str = Form(default=""),
    description: str = Form(default=""),
):
    """Create category."""
    try:
        slug = slug.strip() or slugify(name)
        slug = get_unique_slug("categories", slug)
        category_id = str(uuid.uuid4())

        db.execute(
            """INSERT INTO categories (id, name, slug, parent_id, description)
               VALUES (?, ?, ?, ?, ?)""",
            [category_id, name, slug, parent_id or None, description]
        )

        return RedirectResponse(url="/admin/categories", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating category: {e}")


@router.post("/categories/{cat_id}/delete")
async def admin_category_delete(request: Request, cat_id: str, user: dict = Depends(require_admin)):
    """Delete category."""
    try:
        db.execute("DELETE FROM categories WHERE id=?", [cat_id])
        return RedirectResponse(url="/admin/categories", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting category: {e}")


# ─── Orders ────────────────────────────────────────────────────────────────
@router.get("/orders")
async def admin_orders(request: Request, user: dict = Depends(require_admin), page: int = Query(1)):
    """List orders."""
    page = max(1, page)
    per_page = 20
    offset = (page - 1) * per_page

    try:
        orders = db.query(
            """SELECT o.*, (u.first_name || ' ' || u.last_name) AS customer_name, u.email
               FROM orders o LEFT JOIN users u ON u.id = o.user_id
               ORDER BY o.created_at DESC LIMIT ? OFFSET ?""",
            [per_page, offset]
        )
        total_result = db.query_one("SELECT COUNT(*) AS cnt FROM orders")
        total = total_result.get("cnt", 0) if total_result else 0
        total_pages = (total + per_page - 1) // per_page
    except Exception:
        orders, total, total_pages = [], 0, 1

    return request.app.state.templates.TemplateResponse(
        "admin/orders.html",
        {
            "request": request,
            "orders": orders,
            "page": page,
            "total": total,
            "total_pages": total_pages,
        }
    )


@router.get("/orders/{order_id}")
async def admin_order_detail(request: Request, order_id: str, user: dict = Depends(require_admin)):
    """View order details."""
    try:
        order = db.query_one("SELECT * FROM orders WHERE id=?", [order_id])
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = db.query("SELECT * FROM order_items WHERE order_id=?", [order_id])
        shipment = db.query_one("SELECT * FROM bigship_shipments WHERE order_id=?", [order_id])

        shipping_address = {}
        if order.get("shipping_address_json"):
            try:
                shipping_address = json.loads(order["shipping_address_json"])
            except Exception:
                pass

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return request.app.state.templates.TemplateResponse(
        "admin/order_detail.html",
        {
            "request": request,
            "order": order,
            "items": items,
            "shipment": shipment,
            "shipping_address": shipping_address,
        }
    )


@router.post("/orders/{order_id}/status")
async def admin_update_order_status(
    request: Request,
    order_id: str,
    user: dict = Depends(require_admin),
    status: str = Form(...),
):
    """Update order status."""
    try:
        db.execute("UPDATE orders SET status=? WHERE id=?", [status, order_id])
        return RedirectResponse(url=f"/admin/orders/{order_id}", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating order: {e}")


# ─── Settings ──────────────────────────────────────────────────────────────
@router.get("/settings")
async def admin_settings(request: Request, user: dict = Depends(require_admin)):
    """Show settings page."""
    try:
        settings = db.query("SELECT key, value FROM store_settings ORDER BY key ASC")
        settings_dict = {s["key"]: s["value"] for s in settings}
    except Exception:
        settings_dict = {}

    return request.app.state.templates.TemplateResponse(
        "admin/settings.html",
        {"request": request, "settings": settings_dict}
    )


@router.post("/settings")
async def admin_update_settings(request: Request, user: dict = Depends(require_admin)):
    """Update settings."""
    try:
        form_data = await request.form()

        for key, value in form_data.items():
            if key.startswith("setting_"):
                setting_key = key.replace("setting_", "")
                # Update or insert
                existing = db.query_one("SELECT id FROM store_settings WHERE key=?", [setting_key])
                if existing:
                    db.execute("UPDATE store_settings SET value=? WHERE key=?", [value, setting_key])
                else:
                    db.execute("INSERT INTO store_settings (key, value) VALUES (?, ?)", [setting_key, value])

        return RedirectResponse(url="/admin/settings", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating settings: {e}")


# ─── Brands ────────────────────────────────────────────────────────────────
@router.get("/brands")
async def admin_brands(request: Request, user: dict = Depends(require_admin)):
    """List brands."""
    try:
        brands = db.query("SELECT * FROM brands ORDER BY name ASC")
    except Exception:
        brands = []

    return request.app.state.templates.TemplateResponse(
        "admin/brands.html",
        {"request": request, "brands": brands}
    )


@router.post("/brands/new")
async def admin_brand_new(
    request: Request,
    user: dict = Depends(require_admin),
    name: str = Form(...),
    slug: str = Form(default=""),
):
    """Create brand."""
    try:
        brand_id = str(uuid.uuid4())
        slug = slug.strip() or slugify(name)
        slug = get_unique_slug("brands", slug)

        db.execute(
            "INSERT INTO brands (id, name, slug) VALUES (?, ?, ?)",
            [brand_id, name, slug]
        )

        return RedirectResponse(url="/admin/brands", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating brand: {e}")


@router.post("/brands/{brand_id}/delete")
async def admin_brand_delete(request: Request, brand_id: str, user: dict = Depends(require_admin)):
    """Delete brand."""
    try:
        db.execute("DELETE FROM brands WHERE id=?", [brand_id])
        return RedirectResponse(url="/admin/brands", status_code=302)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting brand: {e}")
