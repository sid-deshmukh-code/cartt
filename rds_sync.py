"""
aws/rds_sync.py - Pushes local transactions to an AWS RDS (MySQL) database
in real time, right after each checkout.

Runs on the Raspberry Pi. Designed to never block or crash the checkout
flow: if the Pi has no internet right at that moment, the transaction is
written to a local queue file and retried automatically once connectivity
comes back (call retry_pending() periodically - main.py schedules this).

Setup:
    pip install pymysql python-dotenv
    cp aws/.env.example aws/.env
    # then fill in aws/.env with your RDS endpoint + a 'pi_writer' user
    # (see schema.sql for how to create that low-privilege user)
"""

import os
import json
import threading
from pathlib import Path
from datetime import datetime

import pymysql
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = int(os.getenv("RDS_PORT", "3306"))
RDS_DB = os.getenv("RDS_DB", "smart_cart")
RDS_USER = os.getenv("RDS_USER")
RDS_PASSWORD = os.getenv("RDS_PASSWORD")
RDS_SSL_CA = os.getenv("RDS_SSL_CA")  # path to AWS RDS CA bundle - optional, recommended

PENDING_QUEUE_FILE = Path(__file__).parent / "pending_sync.jsonl"


def _get_connection(timeout=5):
    if not RDS_HOST:
        raise RuntimeError("RDS_HOST not set - fill in aws/.env first")
    ssl_args = {"ca": RDS_SSL_CA} if RDS_SSL_CA else None
    return pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        database=RDS_DB,
        connect_timeout=timeout,
        ssl=ssl_args,
        cursorclass=pymysql.cursors.Cursor,
    )


def _insert_transaction(conn, record):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO transactions (transaction_time, items_json, total, payment_method, status) "
            "VALUES (%s, %s, %s, %s, %s)",
            (
                record["timestamp"],
                json.dumps(record["items"]),
                record["total"],
                record["payment_method"],
                record["status"],
            ),
        )
    conn.commit()


def push_transaction_async(items, total, payment_method, status="SUCCESS"):
    """Fire-and-forget: the network call runs on a background thread so a
    slow or unreachable RDS connection never freezes the checkout UI."""
    record = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "items": items,
        "total": total,
        "payment_method": payment_method,
        "status": status,
    }
    threading.Thread(target=_push_with_fallback, args=(record,), daemon=True).start()


def _push_with_fallback(record):
    try:
        conn = _get_connection()
        try:
            _insert_transaction(conn, record)
        finally:
            conn.close()
    except Exception:
        # No internet / RDS unreachable right now - queue locally and let
        # retry_pending() flush it once connectivity is back.
        _queue_for_retry(record)


def _queue_for_retry(record):
    with open(PENDING_QUEUE_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")


def retry_pending_async():
    """Fire-and-forget wrapper for retry_pending() - call this one from the
    Kivy Clock so the periodic connectivity check never taps the UI thread."""
    threading.Thread(target=retry_pending, daemon=True).start()


def retry_pending():
    """Flush any transactions that failed to sync earlier. Safe to call
    often - it's a no-op if the queue file is empty or RDS is unreachable."""
    if not PENDING_QUEUE_FILE.exists():
        return

    lines = [ln for ln in PENDING_QUEUE_FILE.read_text().splitlines() if ln.strip()]
    if not lines:
        PENDING_QUEUE_FILE.unlink(missing_ok=True)
        return

    try:
        conn = _get_connection()
    except Exception:
        return  # still offline - leave the queue file as-is, try again later

    still_pending = []
    try:
        for line in lines:
            record = json.loads(line)
            try:
                _insert_transaction(conn, record)
            except Exception:
                still_pending.append(line)
    finally:
        conn.close()

    if still_pending:
        PENDING_QUEUE_FILE.write_text("\n".join(still_pending) + "\n")
    else:
        PENDING_QUEUE_FILE.unlink(missing_ok=True)


def sync_products_from_sqlite():
    """One-way sync: push the full local SQLite product catalog up to RDS.
    Run manually whenever your local product list changes:

        python3 aws/rds_sync.py
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    import db as local_db

    conn_local = local_db.get_connection()
    products = conn_local.execute("SELECT * FROM products").fetchall()
    conn_local.close()

    conn = _get_connection(timeout=10)
    try:
        with conn.cursor() as cur:
            for p in products:
                cur.execute(
                    """
                    INSERT INTO products (barcode, name, price, stock, weight_grams)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        price = VALUES(price),
                        stock = VALUES(stock),
                        weight_grams = VALUES(weight_grams)
                    """,
                    (p["barcode"], p["name"], p["price"], p["stock"], p["weight_grams"]),
                )
        conn.commit()
    finally:
        conn.close()
    print(f"Synced {len(products)} products to RDS.")


if __name__ == "__main__":
    sync_products_from_sqlite()
