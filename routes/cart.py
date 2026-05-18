from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify
import db
from helpers import refresh_cart_prices
from queries import PRODUCTS_SELECT

bp = Blueprint("cart", __name__)


@bp.route("/cart")
def view_cart():
    cart_items = session.get("cart", {})
    cart_items, subtotal = refresh_cart_prices(cart_items)
    session["cart"] = cart_items
    shipping = 0 if subtotal >= 999 else 99
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
            # Traditional variation — look up the combo label from the DB
            var = db.query_one("SELECT * FROM product_variations WHERE id = ?", [variation_id])
            if var:
                sku  = var.get("sku", sku)
                opts = db.query("""
                    SELECT av.value FROM attribute_values av
                    JOIN variation_attribute_values vav ON vav.attribute_value_id = av.id
                    WHERE vav.variation_id = ?
                """, [variation_id])
                if opts:
                    display_name += f" ({' / '.join(o['value'] for o in opts)})"
            item_key = variation_id

        cart = session.get("cart", {})

        if selected_options:
            # Custom attribute selections (e.g. flavor, quantity, size)
            display_name += f" ({selected_options})"
            item_key = f"{product_id}|{selected_options}"
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
        else:
            item_key = product_id
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
    else:
        # Fallback for complex keys if they were somehow mutated
        removed = False
        for key in list(cart.keys()):
            if str(key).strip() == item_key:
                cart.pop(key)
                removed = True
                break
        if removed:
            session["cart"] = cart
            flash("Item removed from cart.", "info")
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
