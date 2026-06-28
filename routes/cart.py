from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import db
from helpers import refresh_cart_prices, get_cached_store_settings
from queries import PRODUCTS_SELECT

bp = Blueprint("cart", __name__)


@bp.route("/cart")
def view_cart():
    cart_items = session.get("cart", {})
    cart_items, subtotal = refresh_cart_prices(cart_items)
    session["cart"] = cart_items

    # Use same shipping calculation as checkout page
    settings = get_cached_store_settings()
    if settings.get("free_shipping_all") == "true":
        shipping = 0
    elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
        shipping = 0
    else:
        shipping = float(settings.get("shipping_fee") or 99)

    return render_template(
        "cart.html",
        cart_items=cart_items,
        subtotal=subtotal,
        shipping=shipping,
        total=subtotal + shipping,
    )


@bp.route("/cart/add", methods=["POST"])
def cart_add():
    product_id       = str(request.form.get("product_id", "")).strip()
    variation_id     = str(request.form.get("variation_id", "")).strip()
    selected_options = str(request.form.get("selected_options", "")).strip()
    qty              = max(1, int(request.form.get("qty", 1)))

    if not product_id:
        flash("Invalid product.", "error")
        return redirect(request.referrer or url_for("public.shop"))

    try:
        product = db.query_one(f"{PRODUCTS_SELECT} WHERE p.id = ?", [product_id])
        if not product:
            flash("Product not found.", "error")
            return redirect(request.referrer or url_for("public.shop"))

        display_name = product["name"]
        price        = float(product.get("sale_price") or product.get("price") or 0)
        sku          = product.get("sku", "")
        img          = product.get("image_url", "")

        if variation_id:
            # Variable product — look up the specific variation
            var = db.query_one("SELECT * FROM product_variations WHERE id = ?", [variation_id])
            if var:
                price = float(var.get("sale_price") or var.get("price") or price)
                sku   = var.get("sku", sku) or sku
                opts  = db.query("""
                    SELECT av.value FROM attribute_values av
                    JOIN variation_attribute_values vav ON vav.attribute_value_id = av.id
                    WHERE vav.variation_id = ?
                """, [variation_id])
                if opts:
                    display_name += f" ({' / '.join(o['value'] for o in opts)})"
            item_key = variation_id
        else:
            item_key = product_id

        if selected_options:
            display_name += f" ({selected_options})"
            item_key = f"{product_id}|{selected_options}"

        cart = session.get("cart", {})
        if item_key in cart:
            cart[item_key]["qty"] += qty
        else:
            cart[item_key] = {
                "product_id": product_id,
                "variation_id": variation_id or None,
                "name": display_name,
                "price": price,
                "qty": qty,
                "image": img,
                "sku": sku,
            }
        session["cart"] = cart
        flash(f"'{display_name}' added to cart!", "success")
    except Exception as e:
        flash(f"Error adding to cart: {e}", "error")

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        count = sum(i["qty"] for i in session.get("cart", {}).values())
        return jsonify({"success": True, "cart_count": count})
    return redirect(request.referrer or url_for("public.shop"))


@bp.route("/cart/remove", methods=["POST"])
def cart_remove():
    cart = session.get("cart", {})
    item_key = str(request.form.get("product_id", "")).strip()
    if item_key in cart:
        cart.pop(item_key)
        session["cart"] = cart
        flash("Item removed from cart.", "info")
    elif item_key:
        fallback = [k for k in cart if k.strip() == item_key]
        if fallback:
            cart.pop(fallback[0])
            session["cart"] = cart
            flash("Item removed from cart.", "info")
        else:
            flash("Item not found in cart.", "error")
    else:
        flash("Item not found in cart.", "error")
    return redirect(url_for("cart.view_cart"))


@bp.route("/cart/update", methods=["POST"])
def cart_update():
    cart = session.get("cart", {})
    for key in list(cart.keys()):
        current_qty = int(cart[key].get("qty", 1) or 1)
        raw_qty = request.form.get(f"qty_{key}", current_qty)
        try:
            new_qty = int(raw_qty)
        except (TypeError, ValueError):
            new_qty = current_qty
        cart[key]["qty"] = max(1, new_qty)
    session["cart"] = cart
    
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"success": True})
        
    flash("Cart updated.", "success")
    return redirect(url_for("cart.view_cart"))


@bp.route("/cart/ajax_update", methods=["POST"])
def cart_ajax_update():
    """AJAX: update single item qty, return new subtotal/total."""
    cart = session.get("cart", {})
    item_key = request.form.get("key", "").strip()
    delta = request.form.get("delta", "0")
    try:
        delta = int(delta)
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid delta"}), 400

    if item_key in cart:
        new_qty = int(cart[item_key].get("qty", 1)) + delta
        new_qty = max(1, min(20, new_qty))
        cart[item_key]["qty"] = new_qty
        session["cart"] = cart

        from helpers import refresh_cart_prices
        _, subtotal = refresh_cart_prices(cart)

        # Calculate shipping based on settings
        settings = get_cached_store_settings()
        if settings.get("free_shipping_all") == "true":
            shipping = 0
        elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
            shipping = 0
        else:
            shipping = float(settings.get("shipping_fee") or 99)

        return jsonify({
            "success": True,
            "qty": new_qty,
            "item_total": cart[item_key]["price"] * new_qty,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
        })
    return jsonify({"error": "Item not found"}), 404


@bp.route("/cart/ajax_remove", methods=["POST"])
def cart_ajax_remove():
    """AJAX: remove item, return new subtotal/total."""
    cart = session.get("cart", {})
    item_key = request.form.get("key", "").strip()
    if item_key in cart:
        cart.pop(item_key)
        session["cart"] = cart
        from helpers import refresh_cart_prices
        _, subtotal = refresh_cart_prices(cart)

        # Calculate shipping based on settings
        settings = get_cached_store_settings()
        if settings.get("free_shipping_all") == "true":
            shipping = 0
        elif settings.get("free_shipping_enabled", "true") == "true" and subtotal >= float(settings.get("free_shipping_threshold") or 999):
            shipping = 0
        else:
            shipping = float(settings.get("shipping_fee") or 99)

        return jsonify({
            "success": True,
            "subtotal": subtotal,
            "shipping": shipping,
            "total": subtotal + shipping,
            "cart_empty": len(cart) == 0,
        })
    return jsonify({"error": "Item not found"}), 404
