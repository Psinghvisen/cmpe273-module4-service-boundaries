"""
Inventory Service — owns item stock data.

Responsibility: answer "is this item available?" (a Query).
Data owned:     the in-memory STOCK table below. No other service reads or
                writes it directly; they must ask through this HTTP API.
"""
import logging
import os

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [inventory] %(message)s")
log = logging.getLogger(__name__)

# ---- Data owned by this service (sample, in-memory) ----
STOCK = {
    "laptop":   {"name": "Laptop",   "quantity": 5},
    "mouse":    {"name": "Mouse",    "quantity": 0},   # deliberately out of stock
    "keyboard": {"name": "Keyboard", "quantity": 12},
}


@app.get("/health")
def health():
    return jsonify(status="ok", service="inventory")


@app.get("/inventory/<item_id>")
def check_availability(item_id):
    """QUERY: read-only. Never changes STOCK."""
    request_id = request.headers.get("X-Request-ID", "-")
    try:
        wanted = int(request.args.get("quantity", 1))
    except ValueError:
        return jsonify(error="quantity must be an integer"), 400

    item = STOCK.get(item_id)
    if item is None:
        log.info("rid=%s item=%s -> not found", request_id, item_id)
        return jsonify(item_id=item_id, available=False, reason="UNKNOWN_ITEM"), 404

    available = item["quantity"] >= wanted
    log.info("rid=%s item=%s wanted=%d in_stock=%d -> available=%s",
             request_id, item_id, wanted, item["quantity"], available)
    return jsonify(
        item_id=item_id,
        requested_quantity=wanted,
        in_stock=item["quantity"],
        available=available,
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("INVENTORY_PORT", 5001)))
