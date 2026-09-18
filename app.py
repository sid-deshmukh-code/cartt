"""
admin_webapp/app.py - Admin dashboard for the Smart Shopping Cart.

Reads directly from the same AWS RDS (MySQL) database the Raspberry Pi
carts sync their transactions and products to. Deploy this on an EC2
instance (see ../AWS_DEPLOYMENT.md for the full walkthrough).

Run (dev, on your laptop):
    pip install -r requirements.txt
    cp .env.example .env         # fill in RDS + Flask secret
    python3 create_admin.py admin yourpassword   # one-time: create a login
    python3 app.py                # http://localhost:8000

Run (production, on EC2):
    gunicorn -w 2 -b 0.0.0.0:8000 app:app
"""

import os
import json
from datetime import date
from functools import wraps
from pathlib import Path

import pymysql
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-only-change-this")

RDS_HOST = os.getenv("RDS_HOST")
RDS_PORT = int(os.getenv("RDS_PORT", "3306"))
RDS_DB = os.getenv("RDS_DB", "smart_cart")
RDS_USER = os.getenv("RDS_USER")
RDS_PASSWORD = os.getenv("RDS_PASSWORD")

app.jinja_env.filters["fromjson"] = lambda s: json.loads(s) if s else []


def get_db():
    return pymysql.connect(
        host=RDS_HOST,
        port=RDS_PORT,
        user=RDS_USER,
        password=RDS_PASSWORD,
        database=RDS_DB,
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=8,
    )


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_user"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        conn = get_db()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM admin_users WHERE username = %s", (username,))
                user = cur.fetchone()
        finally:
            conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["admin_user"] = username
            return redirect(url_for("dashboard"))
        flash("Invalid username or password")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS revenue "
                "FROM transactions WHERE DATE(transaction_time) = %s",
                (date.today(),),
            )
            today = cur.fetchone()

            cur.execute("SELECT COUNT(*) AS c, COALESCE(SUM(total), 0) AS revenue FROM transactions")
            all_time = cur.fetchone()

            cur.execute("SELECT COUNT(*) AS c FROM products WHERE stock <= 10")
            low_stock = cur.fetchone()

            cur.execute("SELECT * FROM transactions ORDER BY transaction_time DESC LIMIT 8")
            recent = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "dashboard.html", today=today, all_time=all_time, low_stock=low_stock, recent=recent
    )


@app.route("/transactions")
@login_required
def transactions():
    page = max(int(request.args.get("page", 1)), 1)
    per_page = 20

    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM transactions")
            total_count = cur.fetchone()["c"]

            cur.execute(
                "SELECT * FROM transactions ORDER BY transaction_time DESC LIMIT %s OFFSET %s",
                (per_page, (page - 1) * per_page),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    total_pages = max((total_count + per_page - 1) // per_page, 1)
    return render_template("transactions.html", rows=rows, page=page, total_pages=total_pages)


@app.route("/products")
@login_required
def products():
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products ORDER BY name")
            rows = cur.fetchall()
    finally:
        conn.close()

    return render_template("products.html", rows=rows)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
