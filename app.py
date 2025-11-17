from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

DB_PATH = "abcseafoods.db"

app = Flask(__name__)
app.secret_key = "CHANGE_ME_TO_RANDOM_SECRET_KEY"

# -------------------------
# DB helpers
# -------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_customer_list():
    conn = get_db()
    customers = conn.execute("""
        SELECT customer_id, name FROM customers
        WHERE status='active'
        ORDER BY name;
    """).fetchall()
    conn.close()
    return customers

def get_products_with_price_for_customer(customer_id):
    """
    For each product, decide which price to show:
    - special price if exists for (customer_id, product_id)
    - else base_price
    """
    conn = get_db()
    products = conn.execute("""
        SELECT
            p.product_id,
            p.name,
            p.description,
            p.base_price,
            p.image_path,
            COALESCE(csp.special_price, p.base_price) AS effective_price
        FROM products p
        LEFT JOIN customer_special_price csp
          ON csp.product_id = p.product_id
         AND csp.customer_id = ?
        WHERE p.is_active = 1
        ORDER BY p.name;
    """, (customer_id,)).fetchall()
    conn.close()
    return products

def get_customer_balance(customer_id):
    """
    balance = opening_balance + sum(orders) - sum(payments)
    """
    conn = get_db()

    row = conn.execute("""
        SELECT opening_balance
        FROM customers
        WHERE customer_id = ?;
    """, (customer_id,)).fetchone()
    opening = row["opening_balance"] if row else 0

    row2 = conn.execute("""
        SELECT COALESCE(SUM(total_amount),0) AS total_orders
        FROM orders
        WHERE customer_id = ?;
    """, (customer_id,)).fetchone()
    total_orders = row2["total_orders"] if row2 else 0

    row3 = conn.execute("""
        SELECT COALESCE(SUM(amount),0) AS total_payments
        FROM payments
        WHERE customer_id = ?;
    """, (customer_id,)).fetchone()
    total_payments = row3["total_payments"] if row3 else 0

    conn.close()

    return opening + total_orders - total_payments

def get_all_products():
    conn = get_db()
    rows = conn.execute("""
        SELECT product_id, name, base_price, is_active, image_path
        FROM products
        ORDER BY name;
    """).fetchall()
    conn.close()
    return rows

def get_all_customers_with_balance():
    conn = get_db()
    # We’ll compute balances in SQL using subqueries so we don’t loop in Python.
    rows = conn.execute("""
        SELECT
            c.customer_id,
            c.name,
            c.phone,
            c.opening_balance
            +
            COALESCE((
                SELECT SUM(o.total_amount)
                FROM orders o
                WHERE o.customer_id = c.customer_id
            ),0)
            -
            COALESCE((
                SELECT SUM(p.amount)
                FROM payments p
                WHERE p.customer_id = c.customer_id
            ),0)
            AS current_balance
        FROM customers c
        WHERE c.status='active'
        ORDER BY c.name;
    """).fetchall()
    conn.close()
    return rows



def get_todays_orders_summary():
    conn = get_db()
    today_str = datetime.now().strftime("%Y-%m-%d")
    row = conn.execute("""
        SELECT
            COUNT(*) as order_count,
            COALESCE(SUM(total_amount),0) as total_sales
        FROM orders
        WHERE DATE(order_date) = ?;
    """, (today_str,)).fetchone()
    conn.close()
    return {
        "order_count": row["order_count"],
        "total_sales": row["total_sales"]
    }

# -------------------------
# Auth helpers
# -------------------------

def is_logged_in():
    return "user_id" in session

def require_login():
    if not is_logged_in():
        return redirect(url_for("login"))

# -------------------------
# Session cart helpers
# -------------------------

def init_cart():
    if "cart" not in session:
        session["cart"] = []  # list of {product_id, name, unit_price, qty, line_total}
    session.modified = True

def set_active_customer(customer_id):
    session["active_customer_id"] = customer_id
    session.modified = True

def get_active_customer_id():
    return session.get("active_customer_id")

def add_to_cart(product_id, qty):
    """
    Add or update a line in the session cart.
    Price is decided based on active customer.
    """
    cust_id = get_active_customer_id()
    if not cust_id:
        return {"error": "No active customer selected."}

    # fetch product info + effective price
    conn = get_db()
    row = conn.execute("""
        SELECT
            p.product_id,
            p.name,
            COALESCE(csp.special_price, p.base_price) AS effective_price
        FROM products p
        LEFT JOIN customer_special_price csp
          ON csp.product_id = p.product_id
         AND csp.customer_id = ?
        WHERE p.product_id = ?
        LIMIT 1;
    """, (cust_id, product_id)).fetchone()
    conn.close()

    if not row:
        return {"error": "Product not found."}

    unit_price = float(row["effective_price"])
    qty = int(qty)
    line_total = unit_price * qty

    init_cart()

    # see if product already in cart
    found = False
    for item in session["cart"]:
        if item["product_id"] == product_id:
            item["qty"] += qty
            item["line_total"] = item["qty"] * item["unit_price"]
            found = True
            break

    if not found:
        session["cart"].append({
            "product_id": product_id,
            "name": row["name"],
            "unit_price": unit_price,
            "qty": qty,
            "line_total": line_total
        })

    session.modified = True
    return {"success": True}

def update_cart_item(product_id, new_qty):
    init_cart()
    new_qty = int(new_qty)

    # if qty becomes 0 or less, remove item
    if new_qty <= 0:
        remove_cart_item(product_id)
        return

    for item in session["cart"]:
        if item["product_id"] == product_id:
            item["qty"] = new_qty
            item["line_total"] = item["qty"] * item["unit_price"]
            break

    session.modified = True


def remove_cart_item(product_id):
    init_cart()
    session["cart"] = [
        item for item in session["cart"]
        if item["product_id"] != product_id
    ]
    session.modified = True


def calc_cart_totals():
    init_cart()
    total = sum(item["line_total"] for item in session["cart"])
    return total

def get_todays_orders_full():
    conn = get_db()
    today_str = datetime.now().strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT
            o.order_id,
            o.order_date,
            o.total_amount,
            c.name AS customer_name
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        WHERE DATE(o.order_date) = ?
        ORDER BY o.order_date DESC;
    """, (today_str,)).fetchall()
    conn.close()
    return rows

def get_order_details(order_id):
    conn = get_db()
    # order header
    order_row = conn.execute("""
        SELECT
            o.order_id,
            o.order_date,
            o.total_amount,
            c.name AS customer_name
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        WHERE o.order_id = ?;
    """, (order_id,)).fetchone()

    # line items
    items = conn.execute("""
        SELECT
            oi.quantity,
            oi.unit_price,
            oi.line_total,
            p.name AS product_name
        FROM order_items oi
        JOIN products p ON p.product_id = oi.product_id
        WHERE oi.order_id = ?;
    """, (order_id,)).fetchall()

    conn.close()
    return order_row, items

# -------------------------
# Routes
# -------------------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username")
        pw = request.form.get("password")
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username = ?;", (uname,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], pw):
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid login")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@app.route("/dashboard", methods=["GET"])
def dashboard():
    if not is_logged_in():
        return redirect(url_for("login"))

    init_cart()

    # active customer for pricing
    active_customer_id = get_active_customer_id()
    customers = get_customer_list()

    products = []
    active_customer_balance = None
    if active_customer_id:
        products = get_products_with_price_for_customer(active_customer_id)
        active_customer_balance = get_customer_balance(active_customer_id)

    today_stats = get_todays_orders_summary()

    return render_template(
        "dashboard.html",
        business_name="ABC Sea Foods",
        username=session.get("username"),
        customers=customers,
        active_customer_id=active_customer_id,
        products=products,
        cart=session["cart"],
        cart_total=calc_cart_totals(),
        today_stats=today_stats,
        active_customer_balance=active_customer_balance
    )

@app.route("/set_customer", methods=["POST"])
def set_customer_route():
    if not is_logged_in():
        return redirect(url_for("login"))

    cid = request.form.get("customer_id")
    if cid:
        set_active_customer(int(cid))
        init_cart()  # keep cart but you COULD also clear here if you prefer
    return redirect(url_for("dashboard"))

@app.route("/cart/add", methods=["POST"])
def cart_add():
    if not is_logged_in():
        return redirect(url_for("login"))

    product_id = int(request.form.get("product_id"))
    qty = int(request.form.get("qty", 1))
    result = add_to_cart(product_id, qty)
    if "error" in result:
        return result["error"], 400
    return redirect(url_for("dashboard"))

@app.route("/cart/view")
def cart_view():
    if not is_logged_in():
        return redirect(url_for("login"))

    active_customer_id = get_active_customer_id()
    if not active_customer_id:
        return redirect(url_for("dashboard"))

    # we'll reuse dashboard cart to show review screen
    return render_template(
        "order_review.html",
        business_name="ABC Sea Foods",
        customer_id=active_customer_id,
        cart=session["cart"],
        cart_total=calc_cart_totals()
    )

@app.route("/cart/update_item", methods=["POST"])
def cart_update_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    product_id = int(request.form.get("product_id"))
    new_qty = int(request.form.get("qty"))

    update_cart_item(product_id, new_qty)

    # after updating, just reload the review page
    return redirect(url_for("cart_view"))


@app.route("/cart/remove_item", methods=["POST"])
def cart_remove_item():
    if not is_logged_in():
        return redirect(url_for("login"))

    product_id = int(request.form.get("product_id"))

    remove_cart_item(product_id)

    return redirect(url_for("cart_view"))


@app.route("/order/confirm", methods=["POST"])
def order_confirm():
    if not is_logged_in():
        return redirect(url_for("login"))

    active_customer_id = get_active_customer_id()
    if not active_customer_id:
        return redirect(url_for("dashboard"))

    init_cart()
    if len(session["cart"]) == 0:
        return redirect(url_for("dashboard"))

    total_amount = calc_cart_totals()
    user_id = session["user_id"]

    conn = get_db()
    cur = conn.cursor()

    # create order
    cur.execute("""
        INSERT INTO orders (customer_id, created_by, total_amount)
        VALUES (?, ?, ?);
    """, (active_customer_id, user_id, total_amount))
    order_id = cur.lastrowid

    # create order_items
    for item in session["cart"]:
        cur.execute("""
            INSERT INTO order_items
            (order_id, product_id, quantity, unit_price, line_total)
            VALUES (?, ?, ?, ?, ?);
        """, (
            order_id,
            item["product_id"],
            item["qty"],
            item["unit_price"],
            item["line_total"]
        ))

    conn.commit()
    conn.close()

    # clear cart
    session["cart"] = []
    session.modified = True

    # after confirming, go back to dashboard so you can do next sale
    return redirect(url_for("dashboard"))

@app.route("/orders/today")
def orders_today():
    if not is_logged_in():
        return redirect(url_for("login"))

    todays_orders = get_todays_orders_full()
    return render_template(
        "orders_today.html",
        business_name="ABC Sea Foods",
        username=session.get("username"),
        todays_orders=todays_orders
    )

@app.route("/orders/<int:order_id>")
def order_view(order_id):
    if not is_logged_in():
        return redirect(url_for("login"))

    order_header, line_items = get_order_details(order_id)
    if not order_header:
        return "Order not found", 404

    return render_template(
        "order_view.html",
        business_name="ABC Sea Foods",
        username=session.get("username"),
        order_header=order_header,
        line_items=line_items
    )

@app.route("/products")
def products_page():
    if not is_logged_in():
        return redirect(url_for("login"))

    prods = get_all_products()
    return render_template(
        "products.html",
        business_name="ABC Sea Foods",
        username=session.get("username"),
        prods=prods
    )

@app.route("/customers")
def customers_page():
    if not is_logged_in():
        return redirect(url_for("login"))

    custs = get_all_customers_with_balance()
    return render_template(
        "customers.html",
        business_name="ABC Sea Foods",
        username=session.get("username"),
        custs=custs
    )

@app.route("/payments/new", methods=["POST"])
def new_payment():
    """
    Record money received from a customer.
    We'll keep this route simple:
    expects: customer_id, amount, method, reference_note
    """
    if not is_logged_in():
        return redirect(url_for("login"))

    customer_id = int(request.form.get("customer_id"))
    amount = float(request.form.get("amount"))
    method = request.form.get("method")
    refnote = request.form.get("reference_note", "")

    conn = get_db()
    conn.execute("""
        INSERT INTO payments (customer_id, amount, method, reference_note, recorded_by)
        VALUES (?, ?, ?, ?, ?);
    """, (customer_id, amount, method, refnote, session["user_id"]))
    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))

# -------------------------
# Utility script function (run manually once)
# to set the real admin password hash in DB
# -------------------------
@app.cli.command("set-admin-password")
def set_admin_password():
    """
    Usage:
    flask --app app.py set-admin-password
    It will prompt in terminal, hash it, and store it.
    """
    import getpass
    pw = getpass.getpass("New admin password: ")
    h = generate_password_hash(pw)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ? WHERE username = 'admin';", (h,))
    conn.commit()
    conn.close()
    print("Admin password updated.")

if __name__ == "__main__":
    app.run(debug=True)
