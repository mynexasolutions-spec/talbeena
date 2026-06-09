"""
Bigship Outbound API Client (v1.4)
Handles authentication and shipment creation/tracking
"""

import requests
import json
import os
from datetime import datetime


class BigshipClient:
    """Bigship API client for shipment management"""

    BASE_URL = "https://api.bigship.io"

    def __init__(self, access_key, email, password):
        self.access_key = access_key
        self.email = email
        self.password = password
        self.token = None
        self.token_expires = None

    def _login(self):
        """Authenticate and get bearer token"""
        url = f"{self.BASE_URL}/v1/auth/login"
        payload = {
            "accessKey": self.access_key,
            "email": self.email,
            "password": self.password
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            if data.get("success"):
                self.token = data.get("token")
                return True
            else:
                print(f"Login failed: {data.get('error', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"Login error: {e}")
            return False

    def _get_headers(self):
        """Get request headers with authentication"""
        if not self.token:
            self._login()

        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_order(self, order_data):
        """
        Create a draft order in Bigship

        Args:
            order_data: dict with order details

        Returns:
            dict with success status and order_id
        """
        url = f"{self.BASE_URL}/v1/outbound/create-order"
        headers = self._get_headers()

        try:
            resp = requests.post(url, json=order_data, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                print(f"[Bigship API] create_order success: order_id={result.get('order_id')}")
                return {"success": True, "order_id": result.get("order_id")}
            else:
                error = result.get("error", "Unknown error")
                print(f"[Bigship API] create_order failed: {error}")
                return {"success": False, "error": error}
        except Exception as e:
            print(f"[Bigship API] create_order exception: {e}")
            return {"success": False, "error": str(e)}

    def get_courier_rates(self, order_id):
        """
        Get available courier options for an order

        Args:
            order_id: Bigship order ID

        Returns:
            dict with success status and courier list
        """
        url = f"{self.BASE_URL}/v1/outbound/courier-rates/{order_id}"
        headers = self._get_headers()

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                couriers = result.get("couriers", [])
                print(f"[Bigship API] get_courier_rates success: {len(couriers)} couriers found")
                return {"success": True, "couriers": couriers}
            else:
                error = result.get("error", "Unknown error")
                print(f"[Bigship API] get_courier_rates failed: {error}")
                return {"success": False, "error": error}
        except Exception as e:
            print(f"[Bigship API] get_courier_rates exception: {e}")
            return {"success": False, "error": str(e)}

    def place_order(self, order_id, courier_id, risk_type_id=2, invoice_file=None):
        """
        Confirm and place an order with selected courier

        Args:
            order_id: Bigship order ID
            courier_id: Selected courier ID
            risk_type_id: Risk type (1=Low, 2=Medium, 3=High)
            invoice_file: Optional invoice file for B2B

        Returns:
            dict with success status, reference_number, and awb_number
        """
        url = f"{self.BASE_URL}/v1/outbound/place-order"
        headers = self._get_headers()
        headers.pop("Content-Type")  # Let requests set it for multipart

        data = {
            "order_id": order_id,
            "courier_id": courier_id,
            "risk_type_id": risk_type_id
        }

        files = {}
        if invoice_file:
            files["invoice_file"] = invoice_file

        try:
            if files:
                resp = requests.post(url, data=data, files=files, headers=headers, timeout=10)
            else:
                resp = requests.post(url, data=data, headers=headers, timeout=10)

            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                awb = result.get("awb_number")
                print(f"[Bigship API] place_order success: awb_number={awb}")
                return {
                    "success": True,
                    "reference_number": result.get("reference_number"),
                    "awb_number": awb
                }
            else:
                error = result.get("error", "Unknown error")
                print(f"[Bigship API] place_order failed: {error}")
                return {"success": False, "error": error}
        except Exception as e:
            print(f"[Bigship API] place_order exception: {e}")
            return {"success": False, "error": str(e)}

    def track_order(self, order_id):
        """
        Get tracking details for an order

        Args:
            order_id: Bigship order ID

        Returns:
            dict with tracking information
        """
        url = f"{self.BASE_URL}/v1/outbound/track/{order_id}"
        headers = self._get_headers()

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                return {"success": True, "tracking": result.get("tracking", {})}
            else:
                return {"success": False, "error": result.get("error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_label(self, order_id):
        """
        Download shipping label PDF

        Args:
            order_id: Bigship order ID

        Returns:
            dict with success status and label URL
        """
        url = f"{self.BASE_URL}/v1/outbound/document/{order_id}/label"
        headers = self._get_headers()

        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                return {"success": True, "label_url": result.get("label_url")}
            else:
                return {"success": False, "error": result.get("error")}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_order(self, order_id):
        """
        Cancel a Bigship order (only before rider assignment)

        Args:
            order_id: Bigship order ID

        Returns:
            dict with success status
        """
        url = f"{self.BASE_URL}/v1/outbound/cancel-order"
        headers = self._get_headers()
        payload = {"order_id": order_id}

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            result = resp.json()

            return {"success": result.get("success"), "error": result.get("error")}
        except Exception as e:
            return {"success": False, "error": str(e)}
