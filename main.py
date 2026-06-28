"""
main.py — FastAPI Application factory for Talbeena
Replaces Flask app.py
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import db
import queries
from helpers import register_jinja_filters

load_dotenv()

# Database
db.migrate()

# Rate limiting
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    yield
    # Shutdown
    try:
        db.close_pool()
    except Exception:
        pass


def create_app():
    app = FastAPI(
        title="Talbeena",
        description="E-commerce website",
        version="2.0.0",
        lifespan=lifespan
    )

    # Configuration
    app.state.secret_key = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    app.state.production = os.getenv("PRODUCTION", "False").lower() == "true"
    app.state.max_upload_size = 16 * 1024 * 1024  # 16MB

    # ─── Static Files ────────────────────────────────────────────────────────
    static_path = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path, check_dir=True), name="static")

    # ─── Templates ───────────────────────────────────────────────────────────
    templates_path = os.path.join(os.path.dirname(__file__), "templates")
    templates = Jinja2Templates(directory=templates_path)
    register_jinja_filters(templates.env)

    # Store templates in app state for easy access
    app.state.templates = templates

    # ─── Middleware ──────────────────────────────────────────────────────────
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[
            "htwo.store",
            "talbeenaa.com",
            "htwoindia.in",
            "localhost",
            "127.0.0.1",
            "*.aws.amazon.com",
        ]
    )

    # ─── Middleware: Session & CSRF ──────────────────────────────────────────
    from fastapi.middleware.sessions import SessionMiddleware

    app.add_middleware(
        SessionMiddleware,
        secret_key=app.state.secret_key,
        session_cookie="session",
        max_age=86400,  # 24 hours
        same_site="lax",
        https_only=app.state.production,
    )

    # ─── Rate Limiting ───────────────────────────────────────────────────────
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    # ─── Global Exception Handlers ───────────────────────────────────────────
    @app.exception_handler(404)
    async def not_found_handler(request: Request, exc):
        return templates.TemplateResponse("errors/404.html", {"request": request}, status_code=404)

    @app.exception_handler(500)
    async def server_error_handler(request: Request, exc):
        return templates.TemplateResponse("errors/500.html", {"request": request}, status_code=500)

    # ─── Middleware: Context (User, Cart Count) ──────────────────────────────
    @app.middleware("http")
    async def add_context(request: Request, call_next):
        # Add current user to request state
        user = request.session.get("user")
        request.state.user = user

        # Add cart count to request state
        cart = request.session.get("cart", {})
        cart_count = sum(item.get("qty", 0) for item in cart.values())
        request.state.cart_count = cart_count
        request.state.cart = cart

        # Add security headers
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Cache headers for static assets
        if request.url.path.startswith("/static/"):
            ext = request.url.path.rsplit(".", 1)[-1].lower()
            if ext in ("webp", "jpg", "jpeg", "png", "gif", "svg", "ico", "woff", "woff2", "js", "css"):
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        return response

    # ─── Routes ──────────────────────────────────────────────────────────────
    from routes.public_api import router as public_router
    from routes.auth_api import router as auth_router
    from routes.cart_api import router as cart_router
    from routes.checkout_api import router as checkout_router
    from routes.blog_api import router as blog_router
    from routes.admin_api import router as admin_router
    from bigship.routes_api import router as bigship_router

    app.include_router(public_router)
    app.include_router(auth_router, prefix="/auth", tags=["auth"])
    app.include_router(cart_router, prefix="/cart", tags=["cart"])
    app.include_router(checkout_router, prefix="/checkout", tags=["checkout"])
    app.include_router(blog_router, prefix="/blog", tags=["blog"])
    app.include_router(admin_router, prefix="/admin", tags=["admin"])
    app.include_router(bigship_router, prefix="/bigship", tags=["bigship"])

    # ─── Health Check ────────────────────────────────────────────────────────
    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    return app


async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Rate limit exceeded"}
    )


# Create the app instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 5001))
    debug = os.getenv("FLASK_ENV", "development") != "production"
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=debug)
