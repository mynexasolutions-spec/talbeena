"""
routes/blog.py — Blog routes for Talbeena.
"""
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
import db
from helpers import handle_upload, get_unique_slug, slugify
from queries import PRODUCTS_MINIMAL_SELECT

bp = Blueprint("blog", __name__, url_prefix="/blog")


@bp.route("")
def blog_list():
    page = request.args.get("page", 1, type=int)
    per_page = 9
    offset = (page - 1) * per_page
    try:
        posts = db.query(
            "SELECT * FROM blog_posts WHERE published=1 ORDER BY created_at DESC LIMIT ? OFFSET ?",
            [per_page, offset]
        )
        total = db.query_one("SELECT COUNT(*) AS cnt FROM blog_posts WHERE published=1")["cnt"]
    except Exception:
        posts, total = [], 0
    return render_template("blog_list.html", posts=posts, page=page, total=total, per_page=per_page)


@bp.route("/<slug>")
def blog_detail(slug):
    post = db.query_one("SELECT * FROM blog_posts WHERE slug=? AND published=1", [slug])
    if not post:
        abort(404)
    try:
        sidebar_products = db.query(f"{PRODUCTS_MINIMAL_SELECT} WHERE p.is_active=1 ORDER BY p.created_at DESC LIMIT 3")
    except Exception:
        sidebar_products = []
    return render_template("blog_detail.html", post=post, sidebar_products=sidebar_products)
