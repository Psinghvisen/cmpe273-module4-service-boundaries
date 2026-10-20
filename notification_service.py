"""
Notification Service — reacts to events.

Responsibility: notify the user when something happened (here: OrderCreated).
Data owned:     the log of notifications it has sent (in-memory SENT list).
It never decides whether an order is valid; it only reacts to facts.
"""
import logging
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [notification] %(message)s")
log = logging.getLogger(__name__)

# ---- Data owned by this service ----
SENT = []


@app.get("/health")
def health():
    return jsonify(status="ok", service="notification")


@app.post("/events")
def receive_event():
    """EVENT consumer: 'OrderCreated' is a fact that already happened."""
    event = request.get_json(silent=True) or {}
    if event.get("type") != "OrderCreated":
        return jsonify(error="unsupported event type"), 400

    data = event.get("data", {})
    message = (f"Hi {data.get('customer', 'customer')}, your order "
               f"{data.get('order_id')} for {data.get('quantity')} x "
               f"{data.get('item_id')} is confirmed.")
    SENT.append({"at": datetime.now(timezone.utc).isoformat(), "message": message})
    log.info("rid=%s NOTIFY -> %s", request.headers.get("X-Request-ID", "-"), message)
    return jsonify(status="notified"), 202


@app.get("/notifications")
def list_notifications():
    return jsonify(SENT)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("NOTIFICATION_PORT", 5002)))
