"""
bigship/routes_api.py — FastAPI Bigship Routes
Full conversion from bigship/routes.py
Handles shipment creation, tracking, label generation
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse, RedirectResponse
import os
import json
import uuid
from datetime import datetime
from dotenv import load_dotenv
import db
from .client import BigshipClient
from dependencies import require_admin

load_dotenv()

router = APIRouter()

# Global Bigship client instance
_bigship_client = None


def get_bigship_client():
    """Get or create Bigship client."""
    global _bigship_client
    if _bigship_client is None:
        _bigship_client = BigshipClient(
            access_key=os.getenv("BIGSHIP_ACCESS_KEY"),
            email=os.getenv("BIGSHIP_EMAIL"),
            password=os.getenv("BIGSHIP_PASSWORD")
        )
    return _bigship_client


def get_bigship_settings():
    """Get all Bigship settings from database."""
    try:
        settings_rows = db.query("SELECT key, value FROM bigship_settings")
        return {row["key"]: row["value"] for row in settings_rows}
    except Exception:
        return {}


def create_shipment_in_bigship(order):
    """
    Create a shipment in Bigship for an order.

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
        except Exception:
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
                "amount": str(float(item.get("unit_price", 0))),
                "totalAmount": str(float(item.get("total_price", 0))),
                "collectableAmount": str(float(item.get("total_price", 0))),
                "categoryId": "1"
            })

        # Determine payment mode (1 = Prepaid, 2 = COD)
        payment_mode = 2  # Default to COD
        if order.get("payment_method") == "razorpay":
            payment_mode = 1  # Prepaid

        # Prepare Bigship order payload
        bigship_order_data = {
            "segment_type": "domestic_b2c",
            "MasterOrderPickUpLocation": int(settings.get("pickup_location_id", 258)),
            "MasterOrderReturnLocation": int(settings.get("return_location_id", 258)),
            "MasterOrderDate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "MasterOrderPaymentMode": payment_mode,
            "OrderInvoiceNo": str(order.get("order_number", "")),
            "MasterOrderInvoiceAmount": float(order.get("total_amount", 0)),
            "MasterOrderShippingName": str(order.get("customer_name", "Customer")),
            "MasterOrderShippingMobileNo": str(order.get("customer_phone", "")),
            "MasterOrderShippingAddress": str(shipping_addr.get("address_line1", "")),
            "MasterOrderShippingLandmark": str(shipping_addr.get("address_line2", "")),
            "MasterOrderShippingZipCode": str(shipping_addr.get("pincode", "")),
            "MasterOrderShippingCountry": str(shipping_addr.get("country", "India")),
            "MasterOrderShippingState": str(shipping_addr.get("state", "")).upper(),
            "MasterOrderShippingCity": str(shipping_addr.get("city", "")).upper(),
            "totalNumOfBoxes": 1,
            "boxes": [{
                "weight_unit": "kg",
                "dimension_unit": "cm",
                "noOfBoxes": 1,
                "dimensions": [{
                    "length": float(box_length),
                    "breadth": float(box_width),
                    "height": float(box_height),
                    "weight": float(total_weight)
                }],
                "products": products
            }]
        }

        # Create order in Bigship
        client = get_bigship_client()
        print(f"[Bigship] Creating order for order_id={order['id']}")
        result = client.create_order(bigship_order_data)

        if result.get("success"):
            bigship_order_id = result.get("order_id")
            shipment_id = str(uuid.uuid4())
            print(f"[Bigship] Draft order created: bigship_order_id={bigship_order_id}")

            # Save to database as draft first
            db.execute(
                """INSERT INTO bigship_shipments
                   (id, order_id, bigship_order_id, status)
                   VALUES (?, ?, ?, ?)""",
                [shipment_id, order["id"], bigship_order_id, "draft"]
            )

            # Automatically get courier rates and book the shipment
            print(f"[Bigship] Fetching courier rates for bigship_order_id={bigship_order_id}")
            rates_result = client.get_courier_rates(bigship_order_id)

            if rates_result.get("success"):
                couriers = rates_result.get("couriers", [])
                print(f"[Bigship] Found {len(couriers)} courier options")

                if couriers:
                    # Select the best courier (cheapest rate)
                    best_courier = min(couriers, key=lambda c: float(c.get("rate", float('inf'))))
                    courier_id = best_courier.get("courier_id")
                    print(f"[Bigship] Selected courier: {courier_id} (rate: {best_courier.get('rate')})")

                    # Place the order with selected courier
                    place_result = client.place_order(bigship_order_id, courier_id)

                    if place_result.get("success"):
                        awb_number = place_result.get("awb_number")
                        print(f"[Bigship] Order booked successfully. AWB: {awb_number}")

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
                        error_msg = f"Failed to book shipment: {place_result.get('error')}"
                        print(f"[Bigship] {error_msg}")
                        return {
                            "success": False,
                            "error": error_msg,
                            "bigship_order_id": bigship_order_id,
                            "shipment_id": shipment_id
                        }
                else:
                    error_msg = "No courier options available for this shipment"
                    print(f"[Bigship] {error_msg}")
                    return {
                        "success": False,
                        "error": error_msg,
                        "bigship_order_id": bigship_order_id,
                        "shipment_id": shipment_id
                    }
            else:
                error_msg = f"Failed to get courier rates: {rates_result.get('error')}"
                print(f"[Bigship] {error_msg}")
                return {
                    "success": False,
                    "error": error_msg,
                    "bigship_order_id": bigship_order_id,
                    "shipment_id": shipment_id
                }
        else:
            error_msg = result.get("error")
            print(f"[Bigship] Failed to create draft order: {error_msg}")
            return {"success": False, "error": error_msg}

    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── Routes ────────────────────────────────────────────────────────────────

@router.post("/create-shipment/{order_id}")
async def create_shipment(request: Request, order_id: str, user: dict = Depends(require_admin)):
    """Create a shipment in Bigship for an order."""
    try:
        order = db.query_one("SELECT * FROM orders WHERE id = ?", [order_id])
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")

        # Check if shipment already exists
        existing = db.query_one(
            "SELECT id FROM bigship_shipments WHERE order_id = ?", [order_id]
        )
        if existing:
            raise HTTPException(status_code=409, detail="Shipment already exists for this order")

        # Create shipment
        result = create_shipment_in_bigship(order)
        return JSONResponse(result, status_code=200 if result.get("success") else 400)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/courier-rates/{bigship_order_id}")
async def get_courier_rates(request: Request, bigship_order_id: str, user: dict = Depends(require_admin)):
    """Get available courier rates for a shipment."""
    try:
        client = get_bigship_client()
        result = client.get_courier_rates(bigship_order_id)
        return JSONResponse(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/place-order")
async def place_order(
    request: Request,
    user: dict = Depends(require_admin),
    bigship_order_id: str = None,
    courier_id: str = None,
):
    """Place an order with a selected courier."""
    try:
        data = await request.json()
        bigship_order_id = data.get("bigship_order_id")
        courier_id = data.get("courier_id")

        if not bigship_order_id or not courier_id:
            raise HTTPException(status_code=400, detail="Missing bigship_order_id or courier_id")

        client = get_bigship_client()
        result = client.place_order(bigship_order_id, courier_id)

        if result.get("success"):
            # Update shipment in database
            db.execute(
                """UPDATE bigship_shipments
                   SET status = ?, awb_number = ?, updated_at = ?
                   WHERE bigship_order_id = ?""",
                ["confirmed", result.get("awb_number"), datetime.now().isoformat(), bigship_order_id]
            )

        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/track/{shipment_id}")
async def track_shipment(request: Request, shipment_id: str):
    """Get tracking information for a shipment."""
    try:
        shipment = db.query_one("SELECT * FROM bigship_shipments WHERE id = ?", [shipment_id])
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

        client = get_bigship_client()
        result = client.get_shipment_status(shipment.get("bigship_order_id"))
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/label/{shipment_id}")
async def get_label(request: Request, shipment_id: str, user: dict = Depends(require_admin)):
    """Get shipping label for a shipment."""
    try:
        shipment = db.query_one("SELECT * FROM bigship_shipments WHERE id = ?", [shipment_id])
        if not shipment:
            raise HTTPException(status_code=404, detail="Shipment not found")

        awb_number = shipment.get("awb_number")
        if not awb_number:
            raise HTTPException(status_code=400, detail="AWB number not available")

        client = get_bigship_client()
        result = client.get_label(awb_number)
        return JSONResponse(result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync-locations")
async def sync_locations(request: Request, user: dict = Depends(require_admin)):
    """Sync pickup/return locations from Bigship account."""
    try:
        client = get_bigship_client()
        locations = client.get_locations()

        if locations:
            return JSONResponse({
                "success": True,
                "locations": locations,
                "message": f"Synced {len(locations)} locations"
            })
        else:
            raise HTTPException(status_code=400, detail="Failed to fetch locations from Bigship")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def bigship_webhook(request: Request):
    """Handle Bigship webhook notifications."""
    try:
        data = await request.json()

        # Update shipment status based on webhook
        bigship_order_id = data.get("order_id")
        status = data.get("status", "").lower()

        if bigship_order_id:
            db.execute(
                "UPDATE bigship_shipments SET status = ? WHERE bigship_order_id = ?",
                [status, bigship_order_id]
            )

        return JSONResponse({"success": True, "message": "Webhook processed"})
    except Exception as e:
        print(f"Error processing Bigship webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))
