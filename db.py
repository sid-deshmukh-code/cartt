"""
db.py - SQLite layer for the Smart Shopping Cart

Handles:
  - product catalog (barcode -> name, price, stock)
  - transaction log (for receipts / checkout history)
"""

import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "cart.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            barcode TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 100,
            weight_grams REAL NOT NULL DEFAULT 0
        )
    """)

    # Migration safety: if an older cart.db exists without this column, add it.
    cur.execute("PRAGMA table_info(products)")
    existing_cols = [c[1] for c in cur.fetchall()]
    if "weight_grams" not in existing_cols:
        cur.execute("ALTER TABLE products ADD COLUMN weight_grams REAL NOT NULL DEFAULT 0")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            items_json TEXT NOT NULL,
            total REAL NOT NULL,
            payment_method TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    conn.commit()

    # Simple, easy-to-type dummy barcodes for testing (001, 002, ...).
    # Swap these for your real product barcodes (typically 12-13 digit
    # EAN/UPC codes) once you're scanning actual items.
    # (barcode, name, price, stock, weight_grams)
    sample_products = [
        ("001", "Parle-G Biscuits 200g", 20.00, 50, 200),
        ("002", "Colgate Toothpaste 100g", 55.00, 40, 100),
        ("003", "Tata Salt 1kg", 25.00, 60, 1000),
        ("004", "Amul Butter 100g", 52.00, 30, 100),
        ("005", "Maggi Noodles 70g", 14.00, 100, 70),
        ("006", "Surf Excel 500g", 65.00, 25, 500),
        ("007", "Britannia Bread 400g", 40.00, 35, 400),
        ("008", "Dettol Soap 75g", 35.00, 45, 75),
        ("009", "Lay's Chips 90g", 20.00, 70, 90),
        ("010", "Coca-Cola 750ml", 40.00, 55, 780),  # ~780g incl. liquid+bottle
    ]

    # Seed with sample products only if the table is completely empty
    cur.execute("SELECT COUNT(*) FROM products")
    if cur.fetchone()[0] == 0:
        cur.executemany(
            "INSERT INTO products (barcode, name, price, stock, weight_grams) VALUES (?, ?, ?, ?, ?)",
            sample_products,
        )
        conn.commit()
    else:
        # Repair migration: an older cart.db may already have these dummy
        # barcodes from before weight_grams existed, left at the column's
        # default of 0. Backfill the correct weight for just those known
        # barcodes -- never touches any real products you've added yourself.
        for barcode, _name, _price, _stock, weight_grams in sample_products:
            cur.execute(
                "UPDATE products SET weight_grams = ? WHERE barcode = ? AND weight_grams = 0",
                (weight_grams, barcode),
            )
        conn.commit()

    conn.close()


def get_product_by_barcode(barcode):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def log_transaction(items, total, payment_method, status="SUCCESS"):
    """items: list of dicts [{barcode, name, price, qty}, ...]"""
    import json
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (timestamp, items_json, total, payment_method, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), json.dumps(items), total, payment_method, status),
    )
    conn.commit()
    conn.close()


def add_or_update_product(barcode, name, price, stock=100, weight_grams=0):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO products (barcode, name, price, stock, weight_grams) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(barcode) DO UPDATE SET name=excluded.name, price=excluded.price,
            stock=excluded.stock, weight_grams=excluded.weight_grams
    """, (barcode, name, price, stock, weight_grams))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")
