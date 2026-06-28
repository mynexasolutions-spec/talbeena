"""
routes/auth_api.py — FastAPI Authentication Routes
Converts Flask auth.py to FastAPI
Handles login, signup, Google OAuth, logout
"""
from fastapi import APIRouter, Request, HTTPException, status, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import bcrypt
import uuid
from typing import Optional
import db
from helpers import get_cached_store_settings
from dependencies import get_current_user
from authlib.integrations.starlette_client import OAuth
import os

router = APIRouter()

# Initialize OAuth
oauth = OAuth()

# Google OAuth Configuration
oauth.register(
    name='google',
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'email profile'}
)


@router.get("/login")
async def login_page(request: Request, next: Optional[str] = None):
    """Render login page."""
    return request.app.state.templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "next": next or "/"}
    )


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(default="/")
):
    """Handle user login."""
    email = email.strip().lower()

    if not email or not password:
        return request.app.state.templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Email and password required"},
            status_code=400
        )

    try:
        user = db.query_one("SELECT * FROM users WHERE email=?", [email])
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": f"Database error: {e}"},
            status_code=500
        )

    if not user or not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
        return request.app.state.templates.TemplateResponse(
            "auth/login.html",
            {"request": request, "error": "Invalid email or password"},
            status_code=401
        )

    # Create session
    request.session["user"] = {
        "id": user["id"],
        "email": user["email"],
        "first_name": user["first_name"],
        "last_name": user["last_name"],
        "role": user["role"],
    }

    return RedirectResponse(url=next_url, status_code=302)


@router.get("/signup")
async def signup_page(request: Request):
    """Render signup page."""
    return request.app.state.templates.TemplateResponse(
        "auth/signup.html",
        {"request": request}
    )


@router.post("/signup")
async def signup(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Handle user registration."""
    first_name = first_name.strip()
    last_name = last_name.strip()
    email = email.strip().lower()

    # Validation
    if not all([first_name, last_name, email, password, confirm_password]):
        return request.app.state.templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "All fields required"},
            status_code=400
        )

    if password != confirm_password:
        return request.app.state.templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "Passwords don't match"},
            status_code=400
        )

    if len(password) < 6:
        return request.app.state.templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": "Password must be at least 6 characters"},
            status_code=400
        )

    # Check if email exists
    try:
        existing = db.query_one("SELECT id FROM users WHERE email=?", [email])
        if existing:
            return request.app.state.templates.TemplateResponse(
                "auth/signup.html",
                {"request": request, "error": "Email already registered"},
                status_code=400
            )
    except Exception:
        pass

    # Hash password and create user
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())

    try:
        db.execute(
            "INSERT INTO users (id, first_name, last_name, email, password_hash, role) VALUES (?,?,?,?,?,?)",
            [user_id, first_name, last_name, email, password_hash, "customer"]
        )

        # Auto-login
        request.session["user"] = {
            "id": user_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "role": "customer",
        }

        return RedirectResponse(url="/", status_code=302)
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            "auth/signup.html",
            {"request": request, "error": f"Registration failed: {e}"},
            status_code=500
        )


@router.get("/google/authorize")
async def google_authorize(request: Request, next_url: Optional[str] = None):
    """Redirect to Google OAuth consent screen."""
    redirect_uri = str(request.url_for("google_callback"))
    if next_url:
        redirect_uri += f"?next={next_url}"

    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request, next_url: Optional[str] = None):
    """Handle Google OAuth callback."""
    try:
        token = await oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if not user_info:
            raise HTTPException(status_code=400, detail="Failed to get user info from Google")

        email = user_info.get("email", "").lower()
        first_name = user_info.get("given_name", "")
        last_name = user_info.get("family_name", "")

        # Find or create user
        try:
            user = db.query_one("SELECT * FROM users WHERE email=?", [email])
        except Exception:
            user = None

        if not user:
            # Create new user
            user_id = str(uuid.uuid4())
            try:
                db.execute(
                    "INSERT INTO users (id, first_name, last_name, email, role, password_hash) VALUES (?,?,?,?,?,?)",
                    [user_id, first_name, last_name, email, "customer", ""]
                )
                user = {"id": user_id, "email": email, "first_name": first_name, "last_name": last_name, "role": "customer"}
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to create user: {e}")

        # Create session
        request.session["user"] = {
            "id": user["id"],
            "email": user["email"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "role": user.get("role", "customer"),
        }

        return RedirectResponse(url=next_url or "/", status_code=302)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OAuth error: {e}")


@router.get("/logout")
async def logout(request: Request):
    """Logout user."""
    request.session.clear()
    return RedirectResponse(url="/", status_code=302)


@router.get("/account")
async def account(request: Request, user: dict = Depends(get_current_user)):
    """User account page (orders, addresses)."""
    if not user:
        return RedirectResponse(url=f"/auth/login?next=/auth/account", status_code=302)

    try:
        orders = db.query(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
            [user["id"]]
        )
        addresses = db.query(
            "SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
            [user["id"]]
        )
    except Exception:
        orders = []
        addresses = []

    return request.app.state.templates.TemplateResponse(
        "account.html",
        {"request": request, "user": user, "orders": orders, "addresses": addresses}
    )
