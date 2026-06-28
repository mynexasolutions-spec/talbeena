#!/usr/bin/env python3
"""
Manual Bigship booking utility - for testing and direct booking
Usage: python bigship_manual_booking.py <order_id>
"""

import os
import sys
from dotenv import load_dotenv
import db
from bigship.client import BigshipClient

load_dotenv()

def get_client():
    return BigshipClient(
        access_key=os.getenv("BIGSHIP_ACCESS_KEY"),
        email=os.getenv("BIGSHIP_EMAIL"),
        password=os.getenv("BIGSHIP_PASSWORD")
    )

def sync_locations():
    """Fetch and display locations from Bigship account"""
    print("\n=== Syncing Locations from Bigship ===\n")
    client = get_client()
    result = client.get_locations()

    if result.get("success"):
        locations = result.get("locations", [])
        print(f"\n✅ Found {len(locations)} locations:\n")
        for i, loc in enumerate(locations):
            print(f"  [{i}] ID: {loc.get('location_id')} | Name: {loc.get('name')}")

        if locations:
            first = locations[0]
            print(f"\n📍 Using first location as default:")
            print(f"   ID: {first.get('location_id')}")
            print(f"   Name: {first.get('name')}")

            # Update database settings
            db.execute(
                """INSERT INTO bigship_settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                ["pickup_location_id", str(first.get("location_id")), "NOW()"]
            )
            db.execute(
                """INSERT INTO bigship_settings (key, value, updated_at)
                   VALUES (?, ?, ?)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                ["return_location_id", str(first.get("location_id")), "NOW()"]
            )
            print("   ✅ Saved to database\n")
            return str(first.get("location_id"))
    else:
        print(f"❌ Error: {result.get('error')}\n")
    return None

def book_order_manually(order_id):
    """Manually book a specific order on Bigship"""
    print(f"\n=== Booking Order {order_id} ===\n")

    # Get the order and check if shipment exists
    order = db.query_one("SELECT * FROM orders WHERE id = ?", [order_id])
    if not order:
        print(f"❌ Order not found: {order_id}\n")
        return False

    shipment = db.query_one("SELECT * FROM bigship_shipments WHERE order_id = ?", [order_id])
    if shipment:
        print(f"⚠️  Shipment already exists for this order")
        print(f"   Status: {shipment.get('status')}")
        print(f"   Bigship Order ID: {shipment.get('bigship_order_id')}")

        if shipment.get('status') == 'confirmed':
            print(f"   AWB: {shipment.get('awb_number')}")
            print(f"   ✅ Order already booked!\n")
            return True
        else:
            print(f"   Will try to book with courier...\n")
    else:
        print(f"No existing shipment found. Creating new one...\n")

    # Import the function to create shipment
    from bigship.routes import create_shipment_in_bigship

    result = create_shipment_in_bigship(order)

    if result.get("success"):
        print(f"\n✅ SUCCESS! Order booked on Bigship")
        print(f"   Shipment ID: {result.get('shipment_id')}")
        print(f"   Bigship Order ID: {result.get('bigship_order_id')}")
        print(f"   AWB Number: {result.get('awb_number')}")
        print(f"   Status: {result.get('status')}\n")
        return True
    else:
        print(f"\n❌ Failed to book order: {result.get('error')}\n")
        return False

def show_latest_order():
    """Show the latest order from the website"""
    print("\n=== Latest Orders ===\n")
    latest_orders = db.query(
        """SELECT id, order_number, customer_name, total_amount,
                  status, created_at
           FROM orders
           ORDER BY created_at DESC
           LIMIT 5"""
    )

    if latest_orders:
        for order in latest_orders:
            print(f"  Order ID: {order['id']}")
            print(f"  Order Number: {order['order_number']}")
            print(f"  Customer: {order['customer_name']}")
            print(f"  Amount: ₹{order['total_amount']}")
            print(f"  Status: {order['status']}")
            print(f"  Created: {order['created_at']}\n")
        return latest_orders[0]['id']
    else:
        print("  No orders found\n")
    return None

if __name__ == "__main__":
    try:
        db.migrate()

        # Step 1: Sync locations
        sync_locations()

        # Step 2: Show latest orders
        latest_order_id = show_latest_order()

        # Step 3: Book order if provided or use latest
        if len(sys.argv) > 1:
            order_id = sys.argv[1]
            book_order_manually(order_id)
        elif latest_order_id:
            print(f"Auto-selecting latest order: {latest_order_id}\n")
            response = input("Do you want to book this order? (yes/no): ").strip().lower()
            if response in ['yes', 'y']:
                book_order_manually(latest_order_id)
            else:
                print("Cancelled.\n")

    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
