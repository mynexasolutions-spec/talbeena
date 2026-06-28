"""
dependencies.py — FastAPI dependency injection
Handles authentication, user verification, etc.
"""
from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthCredentials
import db

security = HTTPBearer(auto_error=False)


async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from session."""
    user = request.session.get("user")
    return user


async def require_user(request: Request) -> dict:
    """Require authenticated user, redirect to login if not."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_admin(request: Request) -> dict:
    """Require admin user."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user


async def get_cart(request: Request) -> dict:
    """Get current cart from session."""
    return request.session.get("cart", {})


async def get_user_addresses(user_id: str):
    """Get all addresses for a user."""
    try:
        addresses = db.query(
            "SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
            [user_id],
        )
        return addresses
    except Exception:
        return []


async def get_user_by_id(user_id: str) -> Optional[dict]:
    """Get user by ID."""
    try:
        user = db.query_one("SELECT * FROM users WHERE id=?", [user_id])
        return user
    except Exception:
        return None


async def get_user_by_email(email: str) -> Optional[dict]:
    """Get user by email."""
    try:
        user = db.query_one("SELECT * FROM users WHERE email=?", [email.lower()])
        return user
    except Exception:
        return None
