"""
Bigship Routes - Flask Blueprint for shipment management
"""

import os
import json
import uuid
from datetime import datetime
from flask import Blueprint, jsonify, request, render_template_string, session, abort
from dotenv import load_dotenv
import db
from .client import BigshipClient

load_dotenv()

bigship_bp = Blueprint("bigship", __name__, url_prefix="/shipping")

# Initialize Bigship client
_bigship_client = None


def get_bigship_client():
    """Get or create Bigship client"""
    global _bigship_client
    if _bigship_client is None:
        _bigship_client = BigshipClient(
            access_key=os.getenv("BIGSHIP_ACCESS_KEY"),
            email=os.getenv("BIGSHIP_EMAIL"),
            password=os.getenv("BIGSHIP_PASSWORD")
        )
    return _bigship_client


def get_bigship_settings():
    """Get all Bigship settings from database"""
    settings_rows = db.query("SELECT key, value FROM bigship_settings")
    settings = {row["key"]: row["value"] for row in settings_rows}
    return settings


def create_shipment_in_bigship(order):
    """
    Create a shipment in Bigship for an order

    Args:
        order: dict with order details from database

    Returns:
        dict with success status, bigship_order_id, and awb_number
    """
    try:
        # Get order items
        order_items = db.query(
            """SELECT oi.*, p.name as product_name
               FROM order_items oi
               LEFT JOIN products p ON p.id = oi.product_id
               WHERE oi.order_id = ?""",
            [order["id"]]
        )

        # Parse shipping address
        shipping_addr = {}
        try:
            shipping_addr = json.loads(order.get("shipping_address_json", "{}"))
        except:
            pass

        # Get settings
        settings = get_bigship_settings()

        # Prepare box dimensions
        box_length = float(settings.get("box_length", 20))
        box_width = float(settings.get("box_width", 15))
        box_height = float(settings.get("box_height", 10))
        default_weight = float(settings.get("default_weight", 1))

        # Calculate total weight
        total_weight = 0
        for item in order_items:
            total_weight += float(item.get("quantity", 1)) * default_weight

        # Prepare products list
        products = []
        for item in order_items:
            products.append({
                "productName": item.get("product_name", "Product"),
                "qty": str(item.get("quantity", 1)),
                "amount": str(item.get("unit_price", 0)),
                "totalAmount": item.get("total_price", 0),
                "collectableAmount": item.get("total_price", 0),
                "categoryId": "1"
            })

        # Determine payment mode (1 = Prepaid, 2 = COD)
        payment_mode = 2  # Default to COD
        if order.get("payment_method") == "razorpay":
            payment_mode = 1  # Prepaid

        # Prepare Bigship order payload
        bigship_order_data = {
            "segment_type": "domestic_b2c",
            "MasterOrderPickUpLocation": settings.get("pickup_location_id", 258),
            "MasterOrderReturnLocation": settings.get("return_location_id", 258),
            "MasterOrderDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "MasterOrderPaymentMode": payment_mode,
            "OrderInvoiceNo": order.get("order_number"),
            "MasterOrderInvoiceAmount": float(order.get("total_amount", 0)),
            "MasterOrderShippingName": order.get("customer_name", "Customer"),
            "MasterOrderShippingMobileNo": order.get("customer_phone", ""),
            "MasterOrderShippingAddress": shipping_addr.get("address_line1", ""),
            "MasterOrderShippingLandmark": shipping_addr.get("address_line2", ""),
            "MasterOrderShippingZipCode": shipping_addr.get("pincode", ""),
            "MasterOrderShippingCountry": shipping_addr.get("country", "India"),
            "MasterOrderShippingState": shipping_addr.get("state", "").upper(),
            "MasterOrderShippingCity": shipping_addr.get("city", "").upper(),
            "totalNumOfBoxes": 1,
            "boxes": [{
                "weight_unit": "kg",
                "dimension_unit": "cm",
                "noOfBoxes": 1,
                "dimensions": [{
                    "length": box_length,
                    "breadth": box_width,
                    "height": box_height,
                    "weight": total_weight
                }],
                "products": products
            }]
        }

        # Create order in Bigship
        client = get_bigship_client()
        result = client.create_order(bigship_order_data)

        if result.get("success"):
            bigship_order_id = result.get("order_id")
            shipment_id = str(uuid.uuid4())

            # Save to database as draft first
            db.execute(
                """INSERT INTO bigship_shipments
                   (id, order_id, bigship_order_id, status)
                   VALUES (?, ?, ?, ?)""",
                [shipment_id, order["id"], bigship_order_id, "draft"]
            )

            # Automatically get courier rates and book the shipment
            rates_result = client.get_courier_rates(bigship_order_id)

            if rates_result.get("success"):
                couriers = rates_result.get("couriers", [])

                if couriers:
                    # Select the best courier (cheapest rate)
                    best_courier = min(couriers, key=lambda c: float(c.get("rate", float('inf'))))
                    courier_id = best_courier.get("courier_id")

                    # Place the order with selected courier
                    place_result = client.place_order(bigship_order_id, courier_id)

                    if place_result.get("success"):
                        awb_number = place_result.get("awb_number")

                        # Update shipment with AWB and confirmed status
                        db.execute(
                            """UPDATE bigship_shipments
                               SET status = ?, awb_number = ?, updated_at = ?
                               WHERE id = ?""",
                            ["confirmed", awb_number, datetime.now().isoformat(), shipment_id]
                        )

                        return {
                            "success": True,
                            "bigship_order_id": bigship_order_id,
                            "shipment_id": shipment_id,
                            "awb_number": awb_number,
                            "status": "confirmed"
                        }
                    else:
                        # Booking failed, keep as draft
                        return {
                            "success": False,
                            "error": f"Failed to book shipment: {place_result.get('error')}",
                            "bigship_order_id": bigship_order_id,
                            "shipment_id": shipment_id
                        }
                else:
                    # No couriers available
                    return {
                        "success": False,
                        "error": "No courier options available for this shipment",
                        "bigship_order_id": bigship_order_id,
                        "shipment_id": shipment_id
                    }
            else:
                # Could not get courier rates, keep as draft
                return {
                    "success": False,
                    "error": f"Failed to get courier rates: {rates_result.get('error')}",
                    "bigship_order_id": bigship_order_id,
                    "shipment_id": shipment_id
                }
        else:
            return {"success": False, "error": result.get("error")}

    except Exception as e:
        return {"success": False, "error": str(e)}


@bigship_bp.route("/create-shipment/<order_id>", methods=["POST"])
def create_shipment(order_id):
    """Create a shipment in Bigship for an order"""
    try:
        # Get order
        order = db.query_one("SELECT * FROM orders WHERE id = ?", [order_id])
        if not order:
            return jsonify({"success": False, "error": "Order not found"}), 404

        # Check if shipment already exists
        existing = db.query_one(
            "SELECT id FROM bigship_shipments WHERE order_id = ?",
            [order_id]
        )
        if existing:
            return jsonify({
                "success": False,
                "error": "Shipment already exists for this order"
            }), 409

        # Create shipment
        result = create_shipment_in_bigship(order)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bigship_bp.route("/courier-rates/<bigship_order_id>", methods=["GET"])
def get_courier_rates(bigship_order_id):
    """Get available courier options for a shipment"""
    try:
        client = get_bigship_client()
        result = client.get_courier_rates(bigship_order_id)
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bigship_bp.route("/place-order", methods=["POST"])
def place_order_endpoint():
    """Place (confirm) a shipment with selected courier"""
    try:
        data = request.get_json()
        bigship_order_id = data.get("bigship_order_id")
        courier_id = data.get("courier_id")
        risk_type_id = data.get("risk_type_id", 2)

        if not bigship_order_id or not courier_id:
            return jsonify({
                "success": False,
                "error": "bigship_order_id and courier_id required"
            }), 400

        client = get_bigship_client()
        result = client.place_order(bigship_order_id, courier_id, risk_type_id)

        if result.get("success"):
            # Update shipment in database
            db.execute(
                """UPDATE bigship_shipments
                   SET status = ?, awb_number = ?, reference_number = ?, courier_id = ?, updated_at = ?
                   WHERE bigship_order_id = ?""",
                ["confirmed", result.get("awb_number"), result.get("reference_number"), courier_id, datetime.now(), bigship_order_id]
            )

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bigship_bp.route("/track/<shipment_id>", methods=["GET"])
def track_shipment(shipment_id):
    """Get tracking details for a shipment"""
    try:
        shipment = db.query_one(
            "SELECT * FROM bigship_shipments WHERE id = ?",
            [shipment_id]
        )
        if not shipment:
            return jsonify({"success": False, "error": "Shipment not found"}), 404

        client = get_bigship_client()
        result = client.track_order(shipment["bigship_order_id"])

        if result.get("success"):
            # Update shipment status
            tracking = result.get("tracking", {})
            db.execute(
                """UPDATE bigship_shipments
                   SET status = ?, current_location = ?, last_update = ?, updated_at = ?
                   WHERE id = ?""",
                [tracking.get("status", "in_transit"), tracking.get("current_location"), datetime.now(), datetime.now(), shipment_id]
            )

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bigship_bp.route("/label/<shipment_id>", methods=["GET"])
def download_label(shipment_id):
    """Download shipping label for a shipment"""
    try:
        shipment = db.query_one(
            "SELECT * FROM bigship_shipments WHERE id = ?",
            [shipment_id]
        )
        if not shipment:
            return jsonify({"success": False, "error": "Shipment not found"}), 404

        client = get_bigship_client()
        result = client.get_label(shipment["bigship_order_id"])
        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@bigship_bp.route("/webhook", methods=["POST"])
def bigship_webhook():
    """Receive webhook updates from Bigship"""
    try:
        data = request.get_json()
        bigship_order_id = data.get("order_id")
        status = data.get("status")
        location = data.get("current_location")

        # Update shipment
        db.execute(
            """UPDATE bigship_shipments
               SET status = ?, current_location = ?, last_update = ?, updated_at = ?
               WHERE bigship_order_id = ?""",
            [status, location, datetime.now(), datetime.now(), bigship_order_id]
        )

        return jsonify({"success": True})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
