"""
routes/cart_api.py — FastAPI Cart Routes
Converts Flask routes/cart.py to FastAPI
"""
from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import JSONResponse, HTMLResponse
import db
from helpers import refresh_cart_prices, get_cached_store_settings

router = APIRouter()


@router.get("")
async def view_cart(request: Request):
    """View shopping cart"""
    cart_items = request.session.get("cart", {})
    cart_items, subtotal = refresh_cart_prices(cart_items)
    request.session["cart"] = cart_items

    # Calculate shipping based on settings
    settings = get_cached_store_settings()
    if settings.get("free_shipping_all") == "true":
        shipping = 0
    elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
        shipping = 0
    else:
        shipping = float(settings.get("shipping_fee") or 99)

    return request.app.state.templates.TemplateResponse(
        "cart.html",
        {
            "request": request,
            "cart_items": cart_items,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
        }
    )


@router.post("/add")
async def cart_add(
    request: Request,
    product_id: str = Form(...),
    variation_id: str = Form(default=""),
    selected_options: str = Form(default=""),
    qty: int = Form(default=1),
):
    """Add item to cart"""
    product_id = str(product_id).strip()
    qty = max(1, min(20, qty))

    if not product_id:
        raise HTTPException(status_code=400, detail="Invalid product")

    try:
        # Fetch product
        product = db.query_one(
            "SELECT id, name, sku, price, sale_price, stock_quantity FROM products WHERE id=?",
            [product_id]
        )
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        # Get price (sale or regular)
        price = float(product.get("sale_price") or product.get("price") or 0)

        # Create unique cart key
        cart_key = f"{product_id}_{variation_id}_{selected_options}" if variation_id else product_id

        # Add to cart
        cart = request.session.get("cart", {})
        if cart_key in cart:
            cart[cart_key]["qty"] += qty
        else:
            cart[cart_key] = {
                "product_id": product_id,
                "name": product.get("name", ""),
                "sku": product.get("sku", ""),
                "price": price,
                "qty": qty,
                "variation_id": variation_id or None,
                "selected_options": selected_options or None,
            }

        request.session["cart"] = cart

        return HTMLResponse(status_code=302, headers={"Location": "/cart"})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/ajax_update")
async def cart_ajax_update(
    request: Request,
    key: str = Form(...),
    delta: int = Form(...),
):
    """AJAX: Update cart item quantity"""
    cart = request.session.get("cart", {})
    key = str(key).strip()

    if key not in cart:
        return JSONResponse({"error": "Item not found"}, status_code=404)

    try:
        new_qty = int(cart[key].get("qty", 1)) + int(delta)
        new_qty = max(1, min(20, new_qty))
        cart[key]["qty"] = new_qty
        request.session["cart"] = cart

        _, subtotal = refresh_cart_prices(cart)

        # Calculate shipping
        settings = get_cached_store_settings()
        if settings.get("free_shipping_all") == "true":
            shipping = 0
        elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
            shipping = 0
        else:
            shipping = float(settings.get("shipping_fee") or 99)

        return JSONResponse({
            "success": True,
            "qty": new_qty,
            "item_total": cart[key].get("price", 0) * new_qty,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)


@router.post("/ajax_remove")
async def cart_ajax_remove(
    request: Request,
    key: str = Form(...),
):
    """AJAX: Remove item from cart"""
    cart = request.session.get("cart", {})
    key = str(key).strip()

    if key not in cart:
        return JSONResponse({"error": "Item not found"}, status_code=404)

    try:
        cart.pop(key)
        request.session["cart"] = cart

        _, subtotal = refresh_cart_prices(cart)

        # Calculate shipping
        settings = get_cached_store_settings()
        if settings.get("free_shipping_all") == "true":
            shipping = 0
        elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
            shipping = 0
        else:
            shipping = float(settings.get("shipping_fee") or 99)

        return JSONResponse({
            "success": True,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
            "cart_empty": len(cart) == 0,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=400)
