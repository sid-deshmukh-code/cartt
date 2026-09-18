"""
create_admin.py - One-time helper to create or update an admin dashboard
login. Run this after applying ../aws/schema.sql to your RDS instance.

Usage:
    python3 create_admin.py <username> <password>
"""

import os
import sys
from pathlib import Path

import pymysql
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 create_admin.py <username> <password>")
        sys.exit(1)

    username, password = sys.argv[1], sys.argv[2]

    conn = pymysql.connect(
        host=os.getenv("RDS_HOST"),
        port=int(os.getenv("RDS_PORT", "3306")),
        user=os.getenv("RDS_USER"),
        password=os.getenv("RDS_PASSWORD"),
        database=os.getenv("RDS_DB", "smart_cart"),
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)
                """,
                (username, generate_password_hash(password)),
            )
        conn.commit()
    finally:
        conn.close()

    print(f"Admin user '{username}' created/updated.")


if __name__ == "__main__":
    main()
