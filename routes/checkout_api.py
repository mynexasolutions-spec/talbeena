"""
routes/checkout_api.py — FastAPI Checkout Routes
Handles checkout, payment processing, order creation
Full conversion from Flask routes/checkout.py
"""
from fastapi import APIRouter, Request, Form, HTTPException, status, Depends
from fastapi.responses import JSONResponse, RedirectResponse, TemplateResponse
import json
import uuid
import razorpay
import os
from datetime import datetime
import db
from helpers import refresh_cart_prices, get_cached_store_settings
from dependencies import require_user

router = APIRouter()


def _calc_shipping(subtotal, settings=None):
    """Calculate shipping cost based on settings."""
    if settings is None:
        settings = get_cached_store_settings()
    if settings.get("free_shipping_all") == "true":
        return 0.0
    fee = float(settings.get("shipping_fee") or 99)
    threshold = float(settings.get("free_shipping_threshold") or 999)
    if settings.get("free_shipping_enabled", "true") == "true" and subtotal >= threshold:
        return 0.0
    return fee


def _validate_coupon(code, user_id, subtotal):
    """Validate coupon and return (coupon_dict, discount_amount, error_message)."""
    code = (code or "").strip().upper()
    if not code:
        return None, 0.0, "Please enter a coupon code."

    coupon = db.query_one(
        "SELECT * FROM coupons WHERE UPPER(code) = ? AND is_active = 1", [code]
    )
    if not coupon:
        return None, 0.0, "Invalid or inactive coupon code."

    if coupon.get("expires_at") and coupon["expires_at"] < datetime.now():
        return None, 0.0, "This coupon has expired."

    min_order = float(coupon.get("min_order_amount") or 0)
    if subtotal < min_order:
        return None, 0.0, f"Minimum order amount of ₹{min_order:.0f} required for this coupon."

    if coupon.get("usage_limit"):
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM coupon_usages WHERE coupon_id = ?", [coupon["id"]]
        )
        if row and int(row.get("cnt", 0)) >= int(coupon["usage_limit"]):
            return None, 0.0, "This coupon has reached its usage limit."

    if user_id and coupon.get("usage_limit_per_user"):
        row = db.query_one(
            "SELECT COUNT(*) AS cnt FROM coupon_usages WHERE coupon_id = ? AND user_id = ?",
            [coupon["id"], user_id],
        )
        if row and int(row.get("cnt", 0)) >= int(coupon["usage_limit_per_user"]):
            return None, 0.0, "You have already used this coupon."

    value = float(coupon.get("value") or 0)
    if coupon["type"] == "percentage":
        discount = subtotal * (value / 100)
        if coupon.get("max_discount"):
            discount = min(discount, float(coupon["max_discount"]))
    else:
        discount = min(value, subtotal)

    return coupon, round(discount, 2), None


@router.get("")
async def checkout(request: Request, user: dict = Depends(require_user)):
    """Checkout page - GET"""
    cart = request.session.get("cart", {})
    if not cart:
        return RedirectResponse(url="/cart", status_code=302)

    cart, subtotal = refresh_cart_prices(cart)
    request.session["cart"] = cart

    settings = get_cached_store_settings()
    shipping = _calc_shipping(subtotal, settings)

    try:
        addresses = db.query(
            "SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
            [user["id"]],
        )
    except Exception:
        addresses = []

    return request.app.state.templates.TemplateResponse(
        "checkout.html",
        {
            "request": request,
            "cart": cart,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
            "addresses": addresses,
            "cod_enabled": settings.get("cod_enabled", "true") == "true",
            "online_enabled": settings.get("online_payment_enabled", "false") == "true",
            "free_shipping_threshold": float(settings.get("free_shipping_threshold") or 999),
            "free_shipping_enabled": settings.get("free_shipping_enabled", "true") == "true",
            "free_shipping_all": settings.get("free_shipping_all") == "true",
        }
    )


@router.post("")
async def checkout_post(
    request: Request,
    user: dict = Depends(require_user),
    payment_method: str = Form(...),
    coupon_code: str = Form(default=""),
    addr_first_name: str = Form(default=""),
    addr_last_name: str = Form(default=""),
    addr_phone: str = Form(default=""),
    addr_line1: str = Form(default=""),
    addr_line2: str = Form(default=""),
    addr_city: str = Form(default=""),
    addr_state: str = Form(default=""),
    addr_pincode: str = Form(default=""),
    addr_country: str = Form(default="India"),
    notes: str = Form(default=""),
    save_address: str = Form(default=""),
    saved_address_id: str = Form(default=""),
    razorpay_payment_id: str = Form(default=""),
    razorpay_order_id: str = Form(default=""),
    razorpay_signature: str = Form(default=""),
):
    """Process checkout - POST"""
    uid = user["id"]
    cart = request.session.get("cart", {})
    if not cart:
        return RedirectResponse(url="/cart", status_code=302)

    cart, subtotal = refresh_cart_prices(cart)
    settings = get_cached_store_settings()
    shipping = _calc_shipping(subtotal, settings)

    # Validate payment method
    ALLOWED_PAYMENT_METHODS = ["cod", "razorpay"]
    if payment_method not in ALLOWED_PAYMENT_METHODS:
        raise HTTPException(status_code=400, detail="Invalid payment method")

    razorpay_key_id = settings.get("razorpay_key_id", "").strip()
    razorpay_key_secret = settings.get("razorpay_key_secret", "").strip()
    razorpay_ready = settings.get("online_payment_enabled", "false") == "true" and bool(razorpay_key_id) and bool(razorpay_key_secret)

    cod_enabled = settings.get("cod_enabled", "true") == "true"

    if payment_method == "cod" and not cod_enabled:
        raise HTTPException(status_code=400, detail="Cash on Delivery is not available")
    if payment_method == "razorpay" and not razorpay_ready:
        raise HTTPException(status_code=400, detail="Online payment is not available")

    # Get addresses
    try:
        addresses = db.query(
            "SELECT * FROM user_addresses WHERE user_id=? ORDER BY is_default DESC, created_at DESC",
            [uid],
        )
    except Exception:
        addresses = []

    # Load saved address if selected
    shipping_addr = None
    if saved_address_id:
        try:
            shipping_addr = db.query_one(
                "SELECT first_name, last_name, phone, address_line1, address_line2, city, state, pincode, country FROM user_addresses WHERE id=? AND user_id=?",
                [saved_address_id, uid],
            )
            if shipping_addr:
                addr_first_name = shipping_addr.get("first_name", "").strip()
                addr_last_name = shipping_addr.get("last_name", "").strip()
                addr_phone = shipping_addr.get("phone", "").strip()
                addr_line1 = shipping_addr.get("address_line1", "").strip()
                addr_line2 = shipping_addr.get("address_line2", "").strip()
                addr_city = shipping_addr.get("city", "").strip()
                addr_state = shipping_addr.get("state", "").strip()
                addr_pincode = shipping_addr.get("pincode", "").strip()
                addr_country = shipping_addr.get("country", "India").strip()
        except Exception:
            pass

    # Validate required address fields
    if not addr_line1 or not addr_city or not addr_pincode or not addr_phone:
        return request.app.state.templates.TemplateResponse(
            "checkout.html",
            {
                "request": request,
                "cart": cart,
                "subtotal": subtotal,
                "shipping": shipping,
                "total": subtotal + shipping,
                "addresses": addresses,
                "error": "Please fill in all required address fields",
            },
            status_code=400
        )

    # Validate coupon
    coupon = None
    discount_amount = 0.0
    if coupon_code:
        coupon, discount_amount, coupon_error = _validate_coupon(coupon_code, uid, subtotal)
        if coupon_error:
            return request.app.state.templates.TemplateResponse(
                "checkout.html",
                {
                    "request": request,
                    "cart": cart,
                    "subtotal": subtotal,
                    "shipping": shipping,
                    "total": subtotal + shipping,
                    "addresses": addresses,
                    "error": f"Coupon: {coupon_error}",
                },
                status_code=400
            )

    total = max(0.0, subtotal + shipping - discount_amount)

    # Verify Razorpay payment if applicable
    payment_status = "pending"
    if payment_method == "razorpay":
        if not razorpay_payment_id or not razorpay_order_id or not razorpay_signature:
            raise HTTPException(status_code=400, detail="Payment information incomplete")

        try:
            client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
            client.utility.verify_payment_signature({
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": razorpay_payment_id,
                "razorpay_signature": razorpay_signature,
            })
            payment_status = "paid"
        except razorpay.errors.SignatureVerificationError:
            raise HTTPException(status_code=400, detail="Payment signature verification failed")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Payment verification failed: {e}")

    # Create order
    shipping_addr = shipping_addr or {
        "first_name": addr_first_name,
        "last_name": addr_last_name,
        "phone": addr_phone,
        "address_line1": addr_line1,
        "address_line2": addr_line2,
        "city": addr_city,
        "state": addr_state,
        "pincode": addr_pincode,
        "country": addr_country,
    }

    customer_name = f"{addr_first_name} {addr_last_name}".strip()
    customer_email = user.get("email", "")

    try:
        order_id = str(uuid.uuid4())
        order_number = f"ORD-{uuid.uuid4().hex[:12].upper()}"

        db.execute(
            """INSERT INTO orders
               (id, order_number, user_id, subtotal, shipping_amount, total_amount, status,
                payment_method, payment_status, shipping_address_json, customer_name,
                customer_email, customer_phone, notes, coupon_code, discount_amount)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                order_id, order_number, uid, subtotal, shipping, total, "pending",
                payment_method, payment_status, json.dumps(shipping_addr),
                customer_name, customer_email, addr_phone, notes,
                coupon_code or "", discount_amount,
            ],
        )

        # Add order items and update stock
        for item_key, item in cart.items():
            unit_price = float(item.get("price", 0))
            qty = int(item.get("qty", 1))
            pid = item.get("product_id")
            vid = item.get("variation_id")

            db.execute(
                "UPDATE products SET stock_quantity = stock_quantity - ? WHERE id = ?",
                [qty, pid],
            )

            p_row = db.query_one("SELECT stock_quantity FROM products WHERE id = ?", [pid])
            if p_row and p_row.get("stock_quantity", 0) <= 0:
                db.execute(
                    "UPDATE products SET stock_quantity = 0, stock_status = 'out_of_stock' WHERE id = ?",
                    [pid],
                )

            db.execute(
                """INSERT INTO order_items
                   (id, order_id, product_id, variation_id, quantity,
                    unit_price, total_price, product_name_snapshot)
                   VALUES (?,?,?,?,?,?,?,?)""",
                [
                    str(uuid.uuid4()), order_id, pid, vid or None, qty,
                    unit_price, unit_price * qty, item.get("name", ""),
                ],
            )

        # Record coupon usage
        if coupon:
            db.execute(
                "INSERT INTO coupon_usages (id, coupon_id, user_id, order_id) VALUES (?,?,?,?)",
                [str(uuid.uuid4()), coupon["id"], uid, order_id],
            )

        # Save address if requested
        if save_address == "on":
            try:
                is_default = 1 if len(addresses) == 0 else 0
                if is_default:
                    db.execute("UPDATE user_addresses SET is_default=0 WHERE user_id=?", [uid])

                db.execute(
                    """INSERT INTO user_addresses
                       (id, user_id, label, first_name, last_name, phone,
                        address_line1, address_line2, city, state, pincode, country, is_default)
                       VALUES (?,?,'Home',?,?,?,?,?,?,?,?,?,?)""",
                    [
                        str(uuid.uuid4()), uid, addr_first_name, addr_last_name, addr_phone,
                        addr_line1, addr_line2, addr_city, addr_state, addr_pincode,
                        addr_country, is_default,
                    ],
                )
            except Exception:
                pass

        # Create Bigship shipment
        try:
            from bigship.routes import create_shipment_in_bigship
            order = db.query_one("SELECT * FROM orders WHERE id=?", [order_id])
            shipment_result = create_shipment_in_bigship(order)
            if not shipment_result.get("success"):
                print(f"Warning: Failed to create Bigship shipment: {shipment_result.get('error')}")
        except Exception as e:
            print(f"Warning: Error creating Bigship shipment: {e}")

        # Clear cart and redirect
        request.session.pop("cart", None)
        return RedirectResponse(url=f"/checkout/order/{order_id}/success", status_code=302)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error placing order: {e}")


@router.post("/razorpay/create_order")
async def create_razorpay_order(request: Request, user: dict = Depends(require_user)):
    """Create Razorpay order for payment."""
    data = await request.json()
    coupon_code = data.get("coupon_code", "").strip().upper()

    cart = request.session.get("cart", {})
    if not cart:
        raise HTTPException(status_code=400, detail="Cart is empty")

    cart, subtotal = refresh_cart_prices(cart)
    settings = get_cached_store_settings()
    shipping = _calc_shipping(subtotal, settings)

    # Apply coupon if provided
    discount_amount = 0.0
    if coupon_code:
        coupon, discount_amount, error = _validate_coupon(coupon_code, user["id"], subtotal)
        if error:
            return JSONResponse({"error": error}, status_code=400)

    amount = int((subtotal + shipping - discount_amount) * 100)  # Razorpay expects paise

    try:
        razorpay_key_id = settings.get("razorpay_key_id", "").strip()
        razorpay_key_secret = settings.get("razorpay_key_secret", "").strip()

        client = razorpay.Client(auth=(razorpay_key_id, razorpay_key_secret))
        order = client.order.create({
            "amount": amount,
            "currency": "INR",
            "receipt": f"order_{user['id'][:8]}",
            "notes": {"customer_email": user.get("email", "")}
        })

        return JSONResponse({
            "success": True,
            "order_id": order["id"],
            "amount": amount,
            "key": razorpay_key_id,
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create order: {e}")


@router.post("/apply_coupon")
async def apply_coupon(request: Request, user: dict = Depends(require_user)):
    """Validate and apply coupon - AJAX endpoint."""
    data = await request.json()
    coupon_code = data.get("coupon_code", "").strip().upper()
    subtotal = float(data.get("subtotal", 0))

    if not coupon_code:
        return JSONResponse({"valid": False, "error": "Please enter a coupon code"})

    coupon, discount_amount, error = _validate_coupon(coupon_code, user["id"], subtotal)

    if error:
        return JSONResponse({"valid": False, "error": error})

    settings = get_cached_store_settings()
    shipping = _calc_shipping(subtotal, settings)
    new_total = round(subtotal + shipping - discount_amount, 2)

    return JSONResponse({
        "valid": True,
        "discount_amount": discount_amount,
        "new_total": new_total,
        "message": f"Coupon applied! Discount: ₹{discount_amount:.0f}",
    })


@router.get("/order/{order_id}/success")
async def order_success(request: Request, order_id: str, user: dict = Depends(require_user)):
    """Order success page."""
    try:
        order = db.query_one("SELECT * FROM orders WHERE id=? AND user_id=?", [order_id, user["id"]])
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = db.query("SELECT * FROM order_items WHERE order_id=?", [order_id])

        shipping_address = {}
        if order.get("shipping_address_json"):
            try:
                shipping_address = json.loads(order["shipping_address_json"])
            except Exception:
                pass

        return request.app.state.templates.TemplateResponse(
            "order_success.html",
            {
                "request": request,
                "order": order,
                "items": items,
                "shipping_address": shipping_address,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/order/{order_id}")
async def order_detail(request: Request, order_id: str, user: dict = Depends(require_user)):
    """Order detail page."""
    try:
        order = db.query_one("SELECT * FROM orders WHERE id=? AND user_id=?", [order_id, user["id"]])
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        items = db.query("SELECT * FROM order_items WHERE order_id=?", [order_id])
        shipment = db.query_one("SELECT * FROM bigship_shipments WHERE order_id=?", [order_id])

        return request.app.state.templates.TemplateResponse(
            "order_detail.html",
            {
                "request": request,
                "order": order,
                "items": items,
                "shipment": shipment,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
