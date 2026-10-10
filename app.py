"""
Techno Vender: a virtual vending machine.

Flask builds each page on the server. Every database query is plain SQL,
so you can read exactly what is sent to PostgreSQL.

Two settings come from Render's Environment tab, never from this file:
  DATABASE_URL  the Neon connection string (contains your database password)
  SECRET_KEY    any long random text (Render can generate one)
"""
import os
from decimal import Decimal, ROUND_HALF_UP

import psycopg
from psycopg.rows import dict_row
from flask import Flask, flash, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "only-for-testing-on-your-own-computer")

MEMBER_STATUSES = ["Active", "Paused", "Cancelled"]
PURCHASE_STATUSES = ["Completed", "Refunded", "Cancelled"]
METHOD_TYPES = ["Credit", "Debit", "Gift card", "Wallet"]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def db():
    """Open a connection to the database. Use it as `with db() as conn:`.
    Everything inside the `with` block is saved together when it ends."""
    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def work_out_total(unit_price, quantity, discount_percent):
    """total = unit price × quantity × (1 − discount ÷ 100), rounded to the cent."""
    total = Decimal(unit_price) * quantity * (1 - Decimal(discount_percent) / 100)
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def whole_number(text, default=0):
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def blank_to_none(text):
    text = (text or "").strip()
    return text or None


def database_said_no(error):
    """Turn a database rule violation into a sentence a person can act on."""
    rule = getattr(error.diag, "constraint_name", None) or ""
    messages = {
        "members_email_key": "Another member already uses that email.",
        "renewal_after_start":"The renewal date can't be before the start date.",
        "payment_methods_last_four_check": "Last four must be exactly 4 digits.",
        "payment_methods_expiry_year_check": "Expiry year must be 2024 or later.",
        "payment_methods_expiry_month_check": "Expiry month must be between 1 and 12.",
        "purchases_quantity_check": "Quantity must be between 1 and 10.",
        "products_stock_qty_check": "There isn't enough stock for that.",
    }
    detail = getattr(error.diag, "message_primary", None) or str(error)
    return messages.get(rule, f"The database rejected that: {detail}")


@app.template_filter("dollars")
def dollars(value):
    return f"${value:,.2f}"


# ---------------------------------------------------------------------
# The vending machine (home page)
# ---------------------------------------------------------------------
@app.route("/")
def machine():
    with db() as conn:
        products = conn.execute(
            "SELECT * FROM products WHERE is_active ORDER BY slot_code"
        ).fetchall()
        members = conn.execute("""
            SELECT m.member_id, m.first_name, m.last_name, p.plan_name, p.discount_percent
            FROM members m
            JOIN membership_plans p ON p.plan_id = m.plan_id
            WHERE m.status = 'Active'
            ORDER BY m.first_name, m.last_name
        """).fetchall()
        methods = conn.execute("""
            SELECT payment_method_id, member_id, method_type, nickname, card_brand, last_four, is_default
            FROM payment_methods
            ORDER BY is_default DESC, payment_method_id
        """).fetchall()

    chosen_slot = request.args.get("slot")
    chosen = next((p for p in products if p["slot_code"] == chosen_slot), None)
    return render_template("machine.html", products=products, members=members,
                           methods=methods, chosen=chosen)


@app.post("/vend")
def vend():
    product_id = whole_number(request.form.get("product_id"))
    member_id = whole_number(request.form.get("member_id"))
    method_id = whole_number(request.form.get("payment_method_id"))
    quantity = whole_number(request.form.get("quantity"), 1)
    back = redirect(url_for("machine", slot=request.form.get("slot_code")))

    if not 1 <= quantity <= 10:
        flash("Choose a quantity from 1 to 10.", "error")
        return back

    with db() as conn:
        member = conn.execute("""
            SELECT m.first_name, m.status, p.discount_percent
            FROM members m JOIN membership_plans p ON p.plan_id = m.plan_id
            WHERE m.member_id = %s
        """, (member_id,)).fetchone()
        method = conn.execute(
            "SELECT member_id FROM payment_methods WHERE payment_method_id = %s", (method_id,)
        ).fetchone()

        if member is None or member["status"] != "Active":
            flash("Choose an active member.", "error")
            return back
        if method is None or method["member_id"] != member_id:
            flash("Choose one of this member's own payment methods.", "error")
            return back

        # Take the items out of the machine. This only works if there is enough stock.
        product = conn.execute("""
            UPDATE products SET stock_qty = stock_qty - %s
            WHERE product_id = %s AND is_active AND stock_qty >= %s
            RETURNING product_name, slot_code, price
        """, (quantity, product_id, quantity)).fetchone()
        if product is None:
            flash("Not enough stock left in that slot.", "error")
            return back

        # Copy today's price and the member's discount into the receipt.
        total = work_out_total(product["price"], quantity, member["discount_percent"])
        conn.execute("""
            INSERT INTO purchases
                (member_id, product_id, payment_method_id, quantity, unit_price, discount_percent, total_amount)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (member_id, product_id, method_id, quantity, product["price"],
              member["discount_percent"], total))

    flash(f"Vended {quantity} × {product['product_name']} from {product['slot_code']} "
          f"for {member['first_name']}. Total {dollars(total)}.", "success")
    return redirect(url_for("purchases"))


# ---------------------------------------------------------------------
# Purchases: view, edit, delete (adding happens on the machine page)
# ---------------------------------------------------------------------
@app.route("/purchases")
def purchases():
    with db() as conn:
        rows = conn.execute("""
            SELECT pu.*, m.first_name, m.last_name, pr.product_name, pr.slot_code,
                   pm.nickname, pm.card_brand, pm.last_four
            FROM purchases pu
            JOIN members m  ON m.member_id = pu.member_id
            JOIN products pr ON pr.product_id = pu.product_id
            LEFT JOIN payment_methods pm ON pm.payment_method_id = pu.payment_method_id
            ORDER BY pu.purchased_at DESC
        """).fetchall()
    completed = [r for r in rows if r["status"] == "Completed"]
    revenue = sum((r["total_amount"] for r in completed), Decimal("0"))
    return render_template("purchases.html", rows=rows, completed=len(completed), revenue=revenue)


def get_purchase(conn, purchase_id):
    return conn.execute("""
        SELECT pu.*, m.first_name, m.last_name, pr.product_name, pr.slot_code
        FROM purchases pu
        JOIN members m  ON m.member_id = pu.member_id
        JOIN products pr ON pr.product_id = pu.product_id
        WHERE pu.purchase_id = %s
    """, (purchase_id,)).fetchone()


@app.route("/purchases/<int:purchase_id>/edit", methods=["GET", "POST"])
def edit_purchase(purchase_id):
    with db() as conn:
        purchase = get_purchase(conn, purchase_id)
        if purchase is None:
            flash("That purchase doesn't exist.", "error")
            return redirect(url_for("purchases"))
        methods = conn.execute(
            "SELECT * FROM payment_methods WHERE member_id = %s ORDER BY payment_method_id",
            (purchase["member_id"],),
        ).fetchall()

        if request.method == "POST":
            quantity = whole_number(request.form.get("quantity"))
            status = request.form.get("status")
            method_id = whole_number(request.form.get("payment_method_id")) or None
            own_ids = {m["payment_method_id"] for m in methods}

            if not 1 <= quantity <= 10:
                flash("Choose a quantity from 1 to 10.", "error")
            elif status not in PURCHASE_STATUSES:
                flash("Choose a status.", "error")
            elif method_id is not None and method_id not in own_ids:
                flash("Choose one of this member's own payment methods.", "error")
            else:
                # Only Completed purchases hold stock. Work out how much stock changes.
                held_before = purchase["quantity"] if purchase["status"] == "Completed" else 0
                held_after = quantity if status == "Completed" else 0
                change = held_after - held_before
                if change != 0:
                    ok = conn.execute("""
                        UPDATE products SET stock_qty = stock_qty - %s
                        WHERE product_id = %s AND stock_qty >= %s
                        RETURNING product_id
                    """, (change, purchase["product_id"], change)).fetchone()
                    if ok is None:
                        flash("Not enough stock in the machine for that quantity.", "error")
                        return render_template("purchase_form.html", p=purchase, methods=methods,
                                               statuses=PURCHASE_STATUSES)
                total = work_out_total(purchase["unit_price"], quantity, purchase["discount_percent"])
                conn.execute("""
                    UPDATE purchases
                    SET quantity = %s, status = %s, payment_method_id = %s, total_amount = %s
                    WHERE purchase_id = %s
                """, (quantity, status, method_id, total, purchase_id))
                flash(f"Purchase {purchase_id} saved. New total {dollars(total)}.", "success")
                return redirect(url_for("purchases"))

    return render_template("purchase_form.html", p=purchase, methods=methods,
                           statuses=PURCHASE_STATUSES)


@app.post("/purchases/<int:purchase_id>/delete")
def delete_purchase(purchase_id):
    with db() as conn:
        purchase = conn.execute(
            "DELETE FROM purchases WHERE purchase_id = %s RETURNING product_id, quantity, status",
            (purchase_id,),
        ).fetchone()
        # A deleted Completed purchase puts its items back in the machine.
        if purchase and purchase["status"] == "Completed":
            conn.execute("UPDATE products SET stock_qty = stock_qty + %s WHERE product_id = %s",
                         (purchase["quantity"], purchase["product_id"]))
    flash(f"Purchase {purchase_id} deleted.", "success")
    return redirect(url_for("purchases"))


# ---------------------------------------------------------------------
# Members (memberships): add, view, edit, delete
# ---------------------------------------------------------------------
@app.route("/members")
def members():
    with db() as conn:
        rows = conn.execute("""
            SELECT m.*, p.plan_name, p.discount_percent,
                   (SELECT COUNT(*) FROM purchases pu WHERE pu.member_id = m.member_id) AS purchase_count,
                   (SELECT COUNT(*) FROM payment_methods pm WHERE pm.member_id = m.member_id) AS method_count
            FROM members m
            JOIN membership_plans p ON p.plan_id = m.plan_id
            ORDER BY m.last_name, m.first_name
        """).fetchall()
        plans = conn.execute("SELECT * FROM membership_plans ORDER BY monthly_fee").fetchall()
    return render_template("members.html", rows=rows, plans=plans)


def member_from_form(form):
    return {
        "first_name": (form.get("first_name") or "").strip(),
        "last_name": (form.get("last_name") or "").strip(),
        "email": (form.get("email") or "").strip().lower(),
        "phone": blank_to_none(form.get("phone")),
        "plan_id": whole_number(form.get("plan_id")),
        "status": form.get("status"),
        "start_date": blank_to_none(form.get("start_date")),
        "renewal_date": blank_to_none(form.get("renewal_date")),
    }


@app.route("/members/new", methods=["GET", "POST"])
@app.route("/members/<int:member_id>/edit", methods=["GET", "POST"])
def member_form(member_id=None):
    with db() as conn:
        plans = conn.execute("SELECT * FROM membership_plans ORDER BY monthly_fee").fetchall()
        member = None
        if member_id is not None:
            member = conn.execute("SELECT * FROM members WHERE member_id = %s", (member_id,)).fetchone()
            if member is None:
                flash("That member doesn't exist.", "error")
                return redirect(url_for("members"))

    if request.method == "POST":
        m = member_from_form(request.form)
        missing = [label for key, label in [("first_name", "first name"), ("last_name", "last name"),
                                            ("email", "email"), ("start_date", "start date"),
                                            ("renewal_date", "renewal date")] if not m[key]]
        if missing:
            flash("Fill in: " + ", ".join(missing) + ".", "error")
            return render_template("member_form.html", m=m, member_id=member_id, plans=plans,
                                   statuses=MEMBER_STATUSES)
        try:
            with db() as conn:
                if member_id is None:
                    conn.execute("""
                        INSERT INTO members (first_name, last_name, email, phone, plan_id, status, start_date, renewal_date)
                        VALUES (%(first_name)s, %(last_name)s, %(email)s, %(phone)s, %(plan_id)s,
                                %(status)s, %(start_date)s, %(renewal_date)s)
                    """, m)
                    flash(f"{m['first_name']} {m['last_name']} added.", "success")
                else:
                    conn.execute("""
                        UPDATE members
                        SET first_name = %(first_name)s, last_name = %(last_name)s, email = %(email)s,
                            phone = %(phone)s, plan_id = %(plan_id)s, status = %(status)s,
                            start_date = %(start_date)s, renewal_date = %(renewal_date)s
                        WHERE member_id = %(member_id)s
                    """, {**m, "member_id": member_id})
                    flash(f"{m['first_name']} {m['last_name']} saved.", "success")
        except psycopg.errors.IntegrityError as error:
            flash(database_said_no(error), "error")
            return render_template("member_form.html", m=m, member_id=member_id, plans=plans,
                                   statuses=MEMBER_STATUSES)
        return redirect(url_for("members"))

    return render_template("member_form.html", m=member, member_id=member_id, plans=plans,
                           statuses=MEMBER_STATUSES)


@app.post("/members/<int:member_id>/delete")
def delete_member(member_id):
    try:
        with db() as conn:
            gone = conn.execute(
                "DELETE FROM members WHERE member_id = %s RETURNING first_name, last_name", (member_id,)
            ).fetchone()
        if gone:
            flash(f"{gone['first_name']} {gone['last_name']} and their payment methods were deleted.", "success")
    except psycopg.errors.ForeignKeyViolation:
        flash("This member has purchase history, so they can't be deleted. "
              "Edit them and set their status to Cancelled instead.", "error")
    return redirect(url_for("members"))


# ---------------------------------------------------------------------
# Payment methods: add, view, edit, delete
# ---------------------------------------------------------------------
@app.route("/payment-methods")
def payment_methods():
    only_member = whole_number(request.args.get("member")) or None
    with db() as conn:
        rows = conn.execute("""
            SELECT pm.*, m.first_name, m.last_name,
                   (SELECT COUNT(*) FROM purchases pu WHERE pu.payment_method_id = pm.payment_method_id) AS use_count
            FROM payment_methods pm
            JOIN members m ON m.member_id = pm.member_id
            WHERE %(member)s::int IS NULL OR pm.member_id = %(member)s::int
            ORDER BY m.last_name, m.first_name, pm.is_default DESC, pm.payment_method_id
        """, {"member": only_member}).fetchall()
        all_members = conn.execute(
            "SELECT member_id, first_name, last_name FROM members ORDER BY last_name, first_name"
        ).fetchall()
    return render_template("payment_methods.html", rows=rows, all_members=all_members,
                           only_member=only_member)


def method_from_form(form):
    return {
        "member_id": whole_number(form.get("member_id")),
        "method_type": form.get("method_type"),
        "nickname": blank_to_none(form.get("nickname")),
        "card_brand": (form.get("card_brand") or "").strip(),
        "last_four": (form.get("last_four") or "").strip(),
        "expiry_month": whole_number(form.get("expiry_month")),
        "expiry_year": whole_number(form.get("expiry_year")),
        "is_default": form.get("is_default") == "on",
    }


@app.route("/payment-methods/new", methods=["GET", "POST"])
@app.route("/payment-methods/<int:method_id>/edit", methods=["GET", "POST"])
def payment_method_form(method_id=None):
    with db() as conn:
        all_members = conn.execute(
            "SELECT member_id, first_name, last_name FROM members ORDER BY last_name, first_name"
        ).fetchall()
        method = None
        if method_id is not None:
            method = conn.execute(
                "SELECT * FROM payment_methods WHERE payment_method_id = %s", (method_id,)
            ).fetchone()
            if method is None:
                flash("That payment method doesn't exist.", "error")
                return redirect(url_for("payment_methods"))

    if request.method == "POST":
        pm = method_from_form(request.form)
        if not pm["card_brand"]:
            flash("Fill in the brand, for example Visa or Interac.", "error")
            return render_template("payment_method_form.html", pm=pm, method_id=method_id,
                                   all_members=all_members, types=METHOD_TYPES)
        try:
            with db() as conn:
                # Only one default per member: clear the old default first.
                if pm["is_default"]:
                    conn.execute("""
                        UPDATE payment_methods SET is_default = FALSE
                        WHERE member_id = %s AND payment_method_id IS DISTINCT FROM %s
                    """, (pm["member_id"], method_id))
                if method_id is None:
                    conn.execute("""
                        INSERT INTO payment_methods
                            (member_id, method_type, nickname, card_brand, last_four, expiry_month, expiry_year, is_default)
                        VALUES (%(member_id)s, %(method_type)s, %(nickname)s, %(card_brand)s, %(last_four)s,
                                %(expiry_month)s, %(expiry_year)s, %(is_default)s)
                    """, pm)
                    flash("Payment method added.", "success")
                else:
                    conn.execute("""
                        UPDATE payment_methods
                        SET member_id = %(member_id)s, method_type = %(method_type)s, nickname = %(nickname)s,
                            card_brand = %(card_brand)s, last_four = %(last_four)s,
                            expiry_month = %(expiry_month)s, expiry_year = %(expiry_year)s,
                            is_default = %(is_default)s
                        WHERE payment_method_id = %(method_id)s
                    """, {**pm, "method_id": method_id})
                    flash("Payment method saved.", "success")
        except psycopg.errors.IntegrityError as error:
            flash(database_said_no(error), "error")
            return render_template("payment_method_form.html", pm=pm, method_id=method_id,
                                   all_members=all_members, types=METHOD_TYPES)
        return redirect(url_for("payment_methods"))

    if method is None:  # new: pre-select the member when coming from a filtered list
        method = {"member_id": whole_number(request.args.get("member")), "method_type": "Credit"}
    return render_template("payment_method_form.html", pm=method, method_id=method_id,
                           all_members=all_members, types=METHOD_TYPES)


@app.post("/payment-methods/<int:method_id>/delete")
def delete_payment_method(method_id):
    with db() as conn:
        conn.execute("DELETE FROM payment_methods WHERE payment_method_id = %s", (method_id,))
    flash("Payment method deleted. Any purchases made with it are kept.", "success")
    return redirect(url_for("payment_methods"))


if __name__ == "__main__":
    app.run(debug=True)
