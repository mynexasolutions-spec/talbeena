"""
routes/blog_api.py — FastAPI Blog Routes
Full conversion from Flask routes/blog.py
"""
from fastapi import APIRouter, Request, Query, HTTPException
import db
from queries import PRODUCTS_MINIMAL_SELECT

router = APIRouter()


@router.get("")
async def blog_list(request: Request, page: int = Query(1)):
    """List blog posts with pagination."""
    page = max(1, page)
    per_page = 9
    offset = (page - 1) * per_page

    try:
        posts = db.query(
            "SELECT * FROM blog_posts WHERE published=1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [per_page, offset]
        )
        total_result = db.query_one("SELECT COUNT(*) AS cnt FROM blog_posts WHERE published=1")
        total = total_result.get("cnt", 0) if total_result else 0
    except Exception:
        posts, total = [], 0

    return request.app.state.templates.TemplateResponse(
        "blog_list.html",
        {
            "request": request,
            "posts": posts,
            "page": page,
            "total": total,
            "per_page": per_page,
        }
    )


@router.get("/{slug}")
async def blog_detail(request: Request, slug: str):
    """Blog post detail page."""
    try:
        post = db.query_one("SELECT * FROM blog_posts WHERE slug=? AND published=1", [slug])
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        sidebar_products = db.query(
            f"{PRODUCTS_MINIMAL_SELECT} WHERE p.is_active=1 ORDER BY p.created_at DESC LIMIT 3"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return request.app.state.templates.TemplateResponse(
        "blog_detail.html",
        {
            "request": request,
            "post": post,
            "sidebar_products": sidebar_products,
        }
    )
