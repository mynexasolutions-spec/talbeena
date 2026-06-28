"""
routes/public_api.py — FastAPI Public Routes (Homepage, Shop, Products)
Converts Flask routes/public.py to FastAPI
"""
from fastapi import APIRouter, Request, Query, HTTPException, Form
from fastapi.responses import RedirectResponse
import json
import db
from queries import (
    get_products, get_categories, get_brands,
    get_product_detail, get_related_products,
    get_homepage_products, get_featured_categories, get_blog_posts,
)

router = APIRouter()


@router.get("/", response_class=None)
async def index(request: Request):
    """Homepage"""
    try:
        data = get_homepage_products()
        featured_categories = get_featured_categories()
        blog_posts = get_blog_posts()
    except Exception as e:
        data = {"featured": [], "latest": [], "popular": [], "promo1": [], "promo2": []}
        featured_categories = []
        blog_posts = []

    return request.app.state.templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "featured": data.get("featured", []),
            "latest": data.get("latest", []),
            "popular": data.get("popular", []),
            "promo1": data.get("promo1", []),
            "promo2": data.get("promo2", []),
            "featured_categories": featured_categories,
            "blog_posts": blog_posts,
        }
    )


@router.get("/shop")
async def shop(
    request: Request,
    search: str = Query(""),
    category: list = Query([]),
    brand: list = Query([]),
    attr_value: list = Query([]),
    sort: str = Query("created_at_desc"),
    page: int = Query(1),
    on_sale: bool = Query(False),
    featured: bool = Query(False),
    min_price: str = Query(""),
    max_price: str = Query(""),
):
    """Shop page with filters"""
    page = max(1, page)

    try:
        min_price_val = float(min_price) if min_price else None
        max_price_val = float(max_price) if max_price else None
    except ValueError:
        min_price_val = max_price_val = None

    try:
        products, total, total_pages = get_products(
            search=search,
            categories=tuple(category),
            brands=tuple(brand),
            sort=sort,
            page=page,
            per_page=18,
            on_sale=on_sale,
            featured=featured,
            min_price=min_price_val,
            max_price=max_price_val,
            attribute_values=tuple(attr_value),
        )
        all_categories = get_categories()
        all_brands = get_brands()
        flavor_vals = db.query(
            "SELECT av.id, av.value, av.image_url FROM attribute_values av "
            "JOIN attributes a ON a.id = av.attribute_id "
            "WHERE a.variation_type = 'primary' ORDER BY av.value"
        )
    except Exception as e:
        products, total, total_pages = [], 0, 1
        all_categories = all_brands = []
        flavor_vals = []

    # Build category tree
    parent_cats = [c for c in all_categories if not c.get("parent_id")]
    children_map = {}
    for c in all_categories:
        pid = c.get("parent_id")
        if pid:
            children_map.setdefault(str(pid), []).append(c)

    return request.app.state.templates.TemplateResponse(
        "shop.html",
        {
            "request": request,
            "products": products,
            "total_count": total,
            "total_pages": total_pages,
            "current_page": page,
            "categories": all_categories,
            "brands": all_brands,
            "parent_cats": parent_cats,
            "children_map": children_map,
            "search": search,
            "current_categories": tuple(category),
            "current_brands": tuple(brand),
            "current_attrs": tuple(attr_value),
            "flavor_vals": flavor_vals,
            "current_sort": sort,
            "on_sale": on_sale,
            "min_price": min_price,
            "max_price": max_price,
        }
    )


@router.get("/product/{product_id}")
async def product_detail(request: Request, product_id: str, preselect: str = ""):
    """Product detail page"""
    try:
        product, images, variations, reviews, attributes = get_product_detail(product_id, preselect=preselect or None)
        if not product:
            raise HTTPException(status_code=404)

        # Build variation JSON for frontend
        var_data = _get_variation_data(product_id)
        variation_json = json.dumps(var_data) if var_data else "null"
        vars_json = json.dumps(var_data.get("variations", [])) if var_data else "[]"

        related = get_related_products(product.get("category_slug", ""), product_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Product not found: {e}")

    # Calculate review stats
    avg_rating = 0.0
    stars_count = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    stars_pct = {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}
    total_reviews = len(reviews) if reviews else 0

    if total_reviews > 0:
        total_stars = 0
        for r in reviews:
            rating = max(1, min(5, int(r.get("rating") or 5)))
            stars_count[rating] += 1
            total_stars += rating
        avg_rating = round(total_stars / total_reviews, 1)
        for rating in range(1, 6):
            stars_pct[rating] = int(round((stars_count[rating] / total_reviews) * 100))

    return request.app.state.templates.TemplateResponse(
        "product.html",
        {
            "request": request,
            "product": product,
            "images": images,
            "variations": variations,
            "reviews": reviews,
            "attributes": attributes,
            "related": related,
            "variation_json": variation_json,
            "vars_json": vars_json,
            "avg_rating": avg_rating,
            "stars_pct": stars_pct,
            "total_reviews": total_reviews,
            "stars_count": stars_count,
        }
    )


@router.get("/category/{slug}")
async def category_page(request: Request, slug: str):
    """Redirect to shop filtered by category"""
    return RedirectResponse(url=f"/shop?category={slug}", status_code=302)


@router.get("/brand/{slug}")
async def brand_page(request: Request, slug: str):
    """Redirect to shop filtered by brand"""
    return RedirectResponse(url=f"/shop?brand={slug}", status_code=302)


# Static pages
@router.get("/about")
async def about(request: Request):
    return request.app.state.templates.TemplateResponse("about.html", {"request": request})


@router.get("/clinical-studies")
async def clinical_studies(request: Request):
    return request.app.state.templates.TemplateResponse("clinical_studies.html", {"request": request})


@router.get("/privacy-policy")
async def privacy_policy(request: Request):
    return request.app.state.templates.TemplateResponse("policies/privacy_policy.html", {"request": request})


@router.get("/terms")
async def terms(request: Request):
    return request.app.state.templates.TemplateResponse("policies/terms.html", {"request": request})


@router.get("/refund-policy")
async def refund_policy(request: Request):
    return request.app.state.templates.TemplateResponse("policies/refund_policy.html", {"request": request})


@router.get("/shipping-policy")
async def shipping_policy(request: Request):
    return request.app.state.templates.TemplateResponse("policies/shipping_policy.html", {"request": request})


@router.get("/contact")
async def contact_get(request: Request):
    """Show contact form"""
    return request.app.state.templates.TemplateResponse("contact.html", {"request": request})


@router.post("/contact")
async def contact_post(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    message: str = Form(...),
):
    """Handle contact form submission"""
    if not all([name, email, phone, message]):
        return request.app.state.templates.TemplateResponse(
            "contact.html",
            {"request": request, "error": "All fields required"},
            status_code=400
        )

    try:
        # Save to database or send email
        db.execute(
            "INSERT INTO contact_submissions (name, email, phone, message) VALUES (?,?,?,?)",
            [name, email, phone, message]
        )

        return request.app.state.templates.TemplateResponse(
            "contact.html",
            {"request": request, "success": "Thank you! We'll get back to you soon."},
            status_code=200
        )
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            "contact.html",
            {"request": request, "error": f"Error: {e}"},
            status_code=500
        )


def _get_variation_data(product_id: str):
    """Get variation data for frontend (helper function)"""
    try:
        variations = db.query(
            "SELECT id, name, price, sale_price, stock_quantity FROM product_variations WHERE product_id=?",
            [product_id]
        )
        return {"variations": variations}
    except Exception:
        return None
