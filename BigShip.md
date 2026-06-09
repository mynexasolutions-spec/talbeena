# Bigship Flask Integration

Complete Bigship Outbound API (v1.4) integration for Flask.

---

## Project Structure

```
your_project/
├── bigship/
│   ├── __init__.py      ← package exports
│   ├── client.py        ← BigshipClient (all API calls)
│   └── routes.py        ← Flask Blueprint (HTTP endpoints)
├── app.py               ← your Flask app
├── .env                 ← credentials (never commit this)
└── requirements.txt
```

---

## Setup

### 1. Copy the bigship/ folder into your Flask project

### 2. Install dependencies
```bash
pip install flask requests python-dotenv
```

### 3. Set your credentials
Create a `.env` file:
```
BIGSHIP_ACCESS_KEY=your_key_from_dashboard
BIGSHIP_EMAIL=your@email.com
BIGSHIP_PASSWORD=yourpassword
```

### 4. Register the blueprint in your Flask app
```python
from flask import Flask
from bigship import bigship_bp
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config["BIGSHIP_ACCESS_KEY"] = os.getenv("BIGSHIP_ACCESS_KEY")
app.config["BIGSHIP_EMAIL"]      = os.getenv("BIGSHIP_EMAIL")
app.config["BIGSHIP_PASSWORD"]   = os.getenv("BIGSHIP_PASSWORD")

app.register_blueprint(bigship_bp, url_prefix="/shipping")
```

---

## Order Flow

The Bigship API uses a 3-step flow to create and manifest a shipment:

```
Step 1: POST /shipping/create-order        → get order_id (draft)
Step 2: GET  /shipping/courier-rates/<id>  → pick a courier_id
Step 3: POST /shipping/place-order         → confirm with courier_id → get AWB
```

### Step 1 — Create Draft Order (Domestic B2C example)
```http
POST /shipping/create-order
Content-Type: application/json

{
  "segment_type": "domestic_b2c",
  "MasterOrderPickUpLocation": 258,
  "MasterOrderReturnLocation": 258,
  "MasterOrderDate": "2025-11-15 01:05:15",
  "MasterOrderPaymentMode": 1,
  "OrderInvoiceNo": "INV-001",
  "MasterOrderInvoiceAmount": 1000,
  "MasterOrderShippingName": "Rahul Sharma",
  "MasterOrderShippingMobileNo": 9876543210,
  "MasterOrderShippingAddress": "123 Main Street",
  "MasterOrderShippingLandmark": "Near Metro",
  "MasterOrderShippingZipCode": "110011",
  "MasterOrderShippingCountry": "India",
  "MasterOrderShippingState": "DELHI",
  "MasterOrderShippingCity": "DELHI",
  "totalNumOfBoxes": 1,
  "boxes": [{
    "weight_unit": "kg",
    "dimension_unit": "cm",
    "noOfBoxes": 1,
    "dimensions": [{"length": 20, "breadth": 15, "height": 10, "weight": 2}],
    "products": [{
      "productName": "T-Shirt",
      "qty": "1",
      "amount": "1000",
      "totalAmount": 1000,
      "collectableAmount": 1000,
      "categoryId": "1"
    }]
  }]
}
```
**Response:** `{ "success": true, "order_id": "311276742" }`

---

### Step 2 — Get Courier Options
```http
GET /shipping/courier-rates/311276742
```
**Response:** List of couriers with `courierId`, `courierName`, `total` charge, `tat` (days)

---

### Step 3 — Place Order (Hyperlocal)
```http
POST /shipping/place-order
Content-Type: application/json

{ "order_id": "311276742", "courier_id": 25 }
```

### Step 3 — Place Order (Domestic B2B/B2C)
```http
POST /shipping/place-order
Content-Type: multipart/form-data

order_id=311276742
courier_id=64
risk_type_id=2
invoice_file=<binary PDF>  (B2B only)
```
**Response:** `{ "success": true, "reference_number": 305585, "awb_number": 305585 }`

---

## Other Useful Calls

### Rate check without creating an order
```http
POST /shipping/rate-calculator
{ "segment_type": "domestic_b2c", "sourcePincode": 110001,
  "destPincode": 400001, "invoiceValue": 500,
  "paymentModeId": 1, "riskTypeId": 2,
  "boxes": [{"no_of_box": 1, "box_length": 20, "box_width": 15,
              "box_height": 10, "box_dead_weight": 2}] }
```

### Track an order
```http
GET /shipping/track/311276742
```

### Download shipping label
```http
GET /shipping/document/311276742/label
```
Returns a PDF URL you can redirect to or display.

### Cancel an order
```http
POST /shipping/cancel-order
{ "order_id": "311276742" }
```
Only works before Rider-Assigned status.

---

## Error Handling

All routes return consistent errors:
```json
{
  "success": false,
  "error": "Human-readable message",
  "status_code": 422,
  "validation_errors": { "field": ["Field is required"] }
}
```

Common status codes:
- `401` — token expired, re-login needed
- `422` — missing or invalid fields
- `429` — rate limit hit (100 req/min)
- `409` — conflict (e.g. order already placed)

---

## Notes

- **No sandbox** — all calls are live. Use small test orders carefully.
- **Token expiry** — the bearer token expires. For long-running apps, handle `401` by re-calling `login()`.
- **Rate limit** — 100 requests/minute per IP.
- **B2B invoice** — always required for B2B courier orders.
- **E-way bill** — required when invoice value ≥ ₹50,000 for B2B.
- **Domestic place-order** — must use `multipart/form-data`, not JSON.
