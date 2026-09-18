"""
generate_barcodes.py - Creates printable barcode images for the dummy
product codes in db.py (001, 002, ... 010), so you can print them out
and test the real scanner hardware end-to-end, not just type codes manually.

Usage:
    pip install python-barcode[images]
    python3 generate_barcodes.py

Output:
    barcodes/001.png, barcodes/002.png, ... (Code128 symbology)

Print these, stick them on anything, and scan away.
"""

import os
import barcode
from barcode.writer import ImageWriter

import db

OUT_DIR = os.path.join(os.path.dirname(__file__), "barcodes")


def generate_all():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db.get_connection()
    cur = conn.cursor()
    cur.execute("SELECT barcode, name FROM products")
    rows = cur.fetchall()
    conn.close()

    code128 = barcode.get_barcode_class("code128")

    for row in rows:
        code, name = row["barcode"], row["name"]
        writer = ImageWriter()
        writer.set_options({"write_text": True, "module_height": 12})
        bc = code128(code, writer=writer)
        filepath = os.path.join(OUT_DIR, code)
        bc.save(filepath)
        print(f"Generated {filepath}.png  ({name})")


if __name__ == "__main__":
    db.init_db()
    generate_all()
    print(f"\nDone. Barcode images are in: {OUT_DIR}")
