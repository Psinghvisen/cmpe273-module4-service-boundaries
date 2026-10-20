"""
Order Service — owns orders.

Responsibility: accept "create an order" (a Command), ask Inventory whether
                the item is available (a Query), store the order, then
                announce "OrderCreated" (an Event) to Notification.
Data owned:     the in-memory ORDERS table. Stock levels are NOT stored here;
                Order Service must ask Inventory Service for them.
"""
import logging
import os
import threading
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [order] %(message)s")
log = logging.getLogger(__name__)

INVENTORY_URL = os.getenv("INVENTORY_URL", "http://127.0.0.1:5001")
NOTIFICATION_URL = os.getenv("NOTIFICATION_URL", "http://127.0.0.1:5002")
TIMEOUT = (1.0, 2.0)  # (connect, read) seconds — never wait forever on a dependency

# ---- Data owned by this service ----
ORDERS = {}


@app.get("/health")
def health():
    return jsonify(status="ok", service="order")


def publish_order_created(order, request_id):
    """EVENT: fire-and-forget. A notification failure must not undo the order."""
    def _send():
        try:
            requests.post(
                f"{NOTIFICATION_URL}/events",
                json={"type": "OrderCreated", "data": order},
                headers={"X-Request-ID": request_id},
                timeout=TIMEOUT,
            )
            log.info("rid=%s published OrderCreated for %s", request_id, order["order_id"])
        except requests.RequestException as exc:
            log.warning("rid=%s could not publish OrderCreated (%s) — order still valid",
                        request_id, type(exc).__name__)
    threading.Thread(target=_send, daemon=True).start()


@app.post("/orders")
def create_order():
    """COMMAND: asks the system to change state (create a new order)."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    quantity = body.get("quantity", 1)
    customer = body.get("customer", "guest")

    if not item_id or not isinstance(quantity, int) or quantity < 1:
        return jsonify(error="item_id (string) and quantity (int >= 1) are required"), 400

    # ---- QUERY Inventory Service ----
    try:
        resp = requests.get(
            f"{INVENTORY_URL}/inventory/{item_id}",
            params={"quantity": quantity},
            headers={"X-Request-ID": request_id},
            timeout=TIMEOUT,
        )
    except requests.ConnectionError:
        log.error("rid=%s Inventory Service unreachable (connection refused)", request_id)
        return jsonify(
            error="INVENTORY_SERVICE_UNAVAILABLE",
            message="Cannot verify stock right now. Order was NOT created. Please retry later.",
            request_id=request_id,
        ), 503
    except requests.Timeout:
        log.error("rid=%s Inventory Service timed out", request_id)
        return jsonify(
            error="INVENTORY_SERVICE_TIMEOUT",
            message="Inventory check took too long. Order was NOT created.",
            request_id=request_id,
        ), 504

    if resp.status_code == 404:
        return jsonify(error="UNKNOWN_ITEM", item_id=item_id, request_id=request_id), 404
    if resp.status_code != 200:
        log.error("rid=%s Inventory returned %s", request_id, resp.status_code)
        return jsonify(error="INVENTORY_SERVICE_ERROR", request_id=request_id), 502

    stock = resp.json()
    if not stock.get("available"):
        log.info("rid=%s order rejected: %s out of stock", request_id, item_id)
        return jsonify(
            status="REJECTED",
            reason="ITEM_UNAVAILABLE",
            item_id=item_id,
            requested_quantity=quantity,
            in_stock=stock.get("in_stock"),
            request_id=request_id,
        ), 409

    # ---- Change our own state (we own ORDERS) ----
    order = {
        "order_id": "ord-" + uuid.uuid4().hex[:6],
        "item_id": item_id,
        "quantity": quantity,
        "customer": customer,
        "status": "CREATED",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    ORDERS[order["order_id"]] = order
    log.info("rid=%s order %s CREATED", request_id, order["order_id"])

    # ---- EVENT: tell whoever cares that it happened ----
    publish_order_created(order, request_id)

    return jsonify(order=order, request_id=request_id), 201


@app.get("/orders/<order_id>")
def get_order(order_id):
    order = ORDERS.get(order_id)
    if order is None:
        return jsonify(error="order not found"), 404
    return jsonify(order)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("ORDER_PORT", 5000)))
