from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
import sqlite3
from pathlib import Path
from datetime import datetime
import hashlib
import hmac
import base64

from settings import (
    BANK_NAME,
    BANK_TAGLINE,
    PARENT_PIN,
    SECRET_KEY,
    DEFAULT_KIDS,
    STARTING_CHECKING,
    STARTING_SAVINGS,
    MONTHLY_RENT,
)

app = Flask(__name__)
app.secret_key = SECRET_KEY

DB_PATH = Path(__file__).with_name("family_bank.db")

DEFAULT_STORE_ITEMS = [
    {"name": "Snack", "price": 2.00, "icon": "🍪"},
    {"name": "Drink", "price": 1.50, "icon": "🥤"},
    {"name": "30 Min Game Time", "price": 5.00, "icon": "🎮"},
    {"name": "Movie Pick", "price": 4.00, "icon": "🎬"},
]

DEFAULT_TASKS = [
    # Regular household chores
    {"task_type": "chore", "title": "Take Out Trash", "description": "Take the household trash out and replace the bag.", "reward": 2.00, "icon": "🗑️"},
    {"task_type": "chore", "title": "Clean Room", "description": "Pick up the room, make the bed, and put things away.", "reward": 3.00, "icon": "🛏️"},
    {"task_type": "chore", "title": "Clean Bathroom", "description": "Clean the sink, counter, toilet area, and straighten the bathroom.", "reward": 4.00, "icon": "🧼"},
    {"task_type": "chore", "title": "Clean Living Room", "description": "Pick up, straighten the living room, and leave it neat.", "reward": 3.00, "icon": "🛋️"},
    {"task_type": "chore", "title": "Clean Kitchen", "description": "Straighten the kitchen, wipe surfaces, and clean up dishes.", "reward": 4.00, "icon": "🍽️"},

    # Bigger paid jobs
    {"task_type": "job", "title": "Wash Car", "description": "Wash and rinse the car and leave the outside clean.", "reward": 8.00, "icon": "🚗"},
    {"task_type": "job", "title": "Bathe Dog", "description": "Give the dog a bath and clean up the bath area afterward.", "reward": 6.00, "icon": "🐶"},
    {"task_type": "job", "title": "Gardening", "description": "Help with planting, watering, weeding, or garden cleanup.", "reward": 5.00, "icon": "🌱"},
    {"task_type": "job", "title": "Yard Work", "description": "Help clean, rake, trim, or tidy the yard.", "reward": 10.00, "icon": "🌿"},
]

# Parent Mode is a simple local-family lock, not bank-grade authentication.
# The configured PIN is converted to a PBKDF2 hash in memory at startup.
PIN_SALT = b"family-bank-parent-pin-v1"
PIN_HASH = hashlib.pbkdf2_hmac(
    "sha256", PARENT_PIN.encode("utf-8"), PIN_SALT, 200000
)

def verify_parent_pin(pin):
    candidate = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), PIN_SALT, 200000)
    return hmac.compare_digest(candidate, PIN_HASH)

def now_text():
    return datetime.now().isoformat(timespec="seconds")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS kids (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        nfc_uid TEXT UNIQUE,
        rent_amount REAL NOT NULL DEFAULT 10.00,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kid_id INTEGER NOT NULL,
        account_type TEXT NOT NULL CHECK(account_type IN ('checking','savings')),
        amount REAL NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL DEFAULT 'general',
        created_at TEXT NOT NULL,
        FOREIGN KEY (kid_id) REFERENCES kids(id)
    );

    CREATE TABLE IF NOT EXISTS store_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL CHECK(price >= 0),
        icon TEXT NOT NULL DEFAULT '⭐',
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );


    CREATE TABLE IF NOT EXISTS household_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL CHECK(task_type IN ('chore','job')),
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        reward REAL NOT NULL CHECK(reward >= 0),
        icon TEXT NOT NULL DEFAULT '✅',
        assigned_kid_id INTEGER,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (assigned_kid_id) REFERENCES kids(id)
    );

    CREATE TABLE IF NOT EXISTS task_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER NOT NULL,
        kid_id INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected')),
        submitted_at TEXT NOT NULL,
        reviewed_at TEXT,
        FOREIGN KEY (task_id) REFERENCES household_tasks(id),
        FOREIGN KEY (kid_id) REFERENCES kids(id)
    );
    """)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) AS c FROM kids").fetchone()["c"]
    if count == 0:
        for kid_config in DEFAULT_KIDS:
            name = kid_config["name"]
            cur = conn.execute(
                "INSERT INTO kids (name, rent_amount) VALUES (?, ?)",
                (name, MONTHLY_RENT)
            )
            kid_id = cur.lastrowid
            conn.execute(
                """INSERT INTO transactions
                (kid_id, account_type, amount, description, category, created_at)
                VALUES (?, 'checking', ?, ?, 'starting_balance', ?)""",
                (kid_id, STARTING_CHECKING, "Starting balance", now_text())
            )
        conn.commit()

    store_count = conn.execute("SELECT COUNT(*) AS c FROM store_items").fetchone()["c"]
    if store_count == 0:
        for item in DEFAULT_STORE_ITEMS:
            conn.execute(
                "INSERT INTO store_items (name, price, icon, active) VALUES (?, ?, ?, 1)",
                (item["name"], item["price"], item["icon"])
            )
        conn.commit()

    task_count = conn.execute("SELECT COUNT(*) AS c FROM household_tasks").fetchone()["c"]
    if task_count == 0:
        for task in DEFAULT_TASKS:
            conn.execute(
                """INSERT INTO household_tasks
                (task_type, title, description, reward, icon, assigned_kid_id, active)
                VALUES (?, ?, ?, ?, ?, NULL, 1)""",
                (
                    task["task_type"],
                    task["title"],
                    task["description"],
                    task["reward"],
                    task["icon"]
                )
            )
        conn.commit()

    conn.close()

def account_balance(conn, kid_id, account_type):
    row = conn.execute(
        """SELECT COALESCE(SUM(amount), 0) AS balance
           FROM transactions
           WHERE kid_id = ? AND account_type = ?""",
        (kid_id, account_type)
    ).fetchone()
    return round(row["balance"], 2)

def kid_theme(name):
    for kid_config in DEFAULT_KIDS:
        if kid_config["name"] == name:
            return {
                "animal": kid_config.get("animal", "dog"),
                "theme": kid_config.get("theme", "sun"),
                "message": kid_config.get("message", "Welcome!")
            }

    return {
        "animal": "dog",
        "theme": "sun",
        "message": "Welcome!"
    }

def kid_payload(conn, kid):
    checking = account_balance(conn, kid["id"], "checking")
    savings = account_balance(conn, kid["id"], "savings")
    theme = kid_theme(kid["name"])
    return {
        "id": kid["id"],
        "name": kid["name"],
        "nfc_uid": kid["nfc_uid"],
        "rent_amount": kid["rent_amount"],
        "checking": checking,
        "savings": savings,
        "total": round(checking + savings, 2),
        **theme,
    }

def parent_required():
    return session.get("parent_ok") is True


@app.context_processor
def inject_branding():
    return {
        "bank_name": BANK_NAME,
        "bank_tagline": BANK_TAGLINE,
    }

@app.route("/")
def dashboard():
    conn = get_db()
    rows = conn.execute("SELECT * FROM kids ORDER BY id").fetchall()
    kids = [kid_payload(conn, kid) for kid in rows]
    conn.close()
    return render_template("dashboard.html", kids=kids)

@app.route("/kid/<int:kid_id>")
def kid_page(kid_id):
    conn = get_db()
    kid_row = conn.execute("SELECT * FROM kids WHERE id = ?", (kid_id,)).fetchone()
    if not kid_row:
        conn.close()
        return "Account not found", 404

    kid = kid_payload(conn, kid_row)
    transactions = conn.execute(
        """SELECT * FROM transactions
           WHERE kid_id = ?
           ORDER BY id DESC
           LIMIT 12""",
        (kid_id,)
    ).fetchall()
    conn.close()
    return render_template("kid.html", kid=kid, transactions=transactions)

@app.route("/kid/<int:kid_id>/transfer", methods=["POST"])
def transfer(kid_id):
    source = request.form.get("from_account", "checking")
    destination = "savings" if source == "checking" else "checking"

    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        amount = 0

    if source not in ("checking", "savings") or amount <= 0:
        flash("Enter a valid transfer amount.", "error")
        return redirect(url_for("kid_page", kid_id=kid_id))

    conn = get_db()
    current = account_balance(conn, kid_id, source)
    if current < amount:
        conn.close()
        flash(f"Not enough money in {source}.", "error")
        return redirect(url_for("kid_page", kid_id=kid_id))

    stamp = now_text()
    conn.execute(
        """INSERT INTO transactions
        (kid_id, account_type, amount, description, category, created_at)
        VALUES (?, ?, ?, ?, 'transfer', ?)""",
        (kid_id, source, -amount, f"Moved to {destination}", stamp)
    )
    conn.execute(
        """INSERT INTO transactions
        (kid_id, account_type, amount, description, category, created_at)
        VALUES (?, ?, ?, ?, 'transfer', ?)""",
        (kid_id, destination, amount, f"Moved from {source}", stamp)
    )
    conn.commit()
    conn.close()

    flash(f"${amount:.2f} moved to {destination}.", "success")
    return redirect(url_for("kid_page", kid_id=kid_id))

@app.route("/store")
def store():
    conn = get_db()
    rows = conn.execute("SELECT * FROM kids ORDER BY id").fetchall()
    kids = [kid_payload(conn, kid) for kid in rows]
    items = conn.execute(
        "SELECT id, name, price, icon FROM store_items WHERE active = 1 ORDER BY id"
    ).fetchall()
    conn.close()
    return render_template("store.html", kids=kids, items=items)

@app.route("/store/checkout", methods=["POST"])
def store_checkout():
    try:
        kid_id = int(request.form.get("kid_id", "0"))
    except ValueError:
        kid_id = 0

    item_ids = []
    for raw_id in request.form.getlist("item_id"):
        try:
            item_ids.append(int(raw_id))
        except ValueError:
            pass

    if not kid_id or not item_ids:
        flash("Choose an account and at least one item.", "error")
        return redirect(url_for("store"))

    conn = get_db()

    placeholders = ",".join("?" for _ in item_ids)
    selected = conn.execute(
        f"SELECT id, name, price, icon FROM store_items WHERE active = 1 AND id IN ({placeholders})",
        item_ids
    ).fetchall()

    if not selected:
        conn.close()
        flash("Those store items are no longer available.", "error")
        return redirect(url_for("store"))

    total = round(sum(float(item["price"]) for item in selected), 2)

    kid = conn.execute("SELECT * FROM kids WHERE id = ?", (kid_id,)).fetchone()
    if not kid:
        conn.close()
        flash("Account not found.", "error")
        return redirect(url_for("store"))

    checking = account_balance(conn, kid_id, "checking")
    if checking < total:
        conn.close()
        flash(f"Declined — {kid['name']} does not have enough in checking.", "error")
        return redirect(url_for("store"))

    description = "Store: " + ", ".join(item["name"] for item in selected)
    conn.execute(
        """INSERT INTO transactions
        (kid_id, account_type, amount, description, category, created_at)
        VALUES (?, 'checking', ?, ?, 'purchase', ?)""",
        (kid_id, -total, description, now_text())
    )
    conn.commit()
    new_balance = account_balance(conn, kid_id, "checking")
    conn.close()

    flash(f"Approved ✓ {kid['name']} paid ${total:.2f}. New checking balance: ${new_balance:.2f}", "success")
    return redirect(url_for("store"))


@app.route("/jobs")
def jobs():
    conn = get_db()

    kid_rows = conn.execute("SELECT * FROM kids ORDER BY id").fetchall()
    kids = [kid_payload(conn, kid) for kid in kid_rows]

    selected_kid_id = request.args.get("kid_id", type=int)
    if not selected_kid_id and kids:
        selected_kid_id = kids[0]["id"]

    selected_kid = next((kid for kid in kids if kid["id"] == selected_kid_id), None)
    if not selected_kid and kids:
        selected_kid = kids[0]
        selected_kid_id = selected_kid["id"]

    chores = []
    paid_jobs = []
    history = []

    if selected_kid:
        rows = conn.execute(
            """SELECT t.*
               FROM household_tasks t
               WHERE t.active = 1
                 AND (t.assigned_kid_id IS NULL OR t.assigned_kid_id = ?)
                 AND NOT EXISTS (
                     SELECT 1
                     FROM task_submissions s
                     WHERE s.task_id = t.id AND s.status = 'pending'
                 )
               ORDER BY t.task_type, t.id""",
            (selected_kid_id,)
        ).fetchall()

        chores = [row for row in rows if row["task_type"] == "chore"]
        paid_jobs = [row for row in rows if row["task_type"] == "job"]

        history = conn.execute(
            """SELECT s.*, t.title, t.reward, t.icon, t.task_type
               FROM task_submissions s
               JOIN household_tasks t ON t.id = s.task_id
               WHERE s.kid_id = ?
               ORDER BY s.id DESC
               LIMIT 12""",
            (selected_kid_id,)
        ).fetchall()

    conn.close()

    return render_template(
        "jobs.html",
        kids=kids,
        selected_kid=selected_kid,
        chores=chores,
        paid_jobs=paid_jobs,
        history=history
    )


@app.route("/jobs/<int:task_id>/complete/<int:kid_id>", methods=["POST"])
def complete_task(task_id, kid_id):
    conn = get_db()

    kid = conn.execute("SELECT * FROM kids WHERE id = ?", (kid_id,)).fetchone()
    task = conn.execute("SELECT * FROM household_tasks WHERE id = ?", (task_id,)).fetchone()

    if not kid or not task or not task["active"]:
        conn.close()
        flash("That chore or job is not available anymore.", "error")
        return redirect(url_for("jobs", kid_id=kid_id))

    if task["assigned_kid_id"] is not None and task["assigned_kid_id"] != kid_id:
        conn.close()
        flash("That task is assigned to someone else.", "error")
        return redirect(url_for("jobs", kid_id=kid_id))

    pending = conn.execute(
        """SELECT id FROM task_submissions
           WHERE task_id = ? AND status = 'pending'
           LIMIT 1""",
        (task_id,)
    ).fetchone()

    if pending:
        conn.close()
        flash("That task is already waiting for parent approval.", "error")
        return redirect(url_for("jobs", kid_id=kid_id))

    conn.execute(
        """INSERT INTO task_submissions
        (task_id, kid_id, status, submitted_at)
        VALUES (?, ?, 'pending', ?)""",
        (task_id, kid_id, now_text())
    )
    conn.commit()
    conn.close()

    flash(f"Nice job, {kid['name']}! Sent to Parent Mode for approval.", "success")
    return redirect(url_for("jobs", kid_id=kid_id))


@app.route("/cards")
def cards():
    conn = get_db()
    rows = conn.execute("SELECT * FROM kids ORDER BY id").fetchall()
    kids = [kid_payload(conn, kid) for kid in rows]
    conn.close()
    return render_template("cards.html", kids=kids)

@app.route("/parent", methods=["GET", "POST"])
def parent():
    if request.method == "POST" and not parent_required():
        pin = request.form.get("pin", "")
        if verify_parent_pin(pin):
            session["parent_ok"] = True
            flash("Parent mode unlocked.", "success")
            return redirect(url_for("parent"))
        flash("That PIN is not correct.", "error")

    if not parent_required():
        return render_template("parent_login.html")

    conn = get_db()
    rows = conn.execute("SELECT * FROM kids ORDER BY id").fetchall()
    kids = [kid_payload(conn, kid) for kid in rows]
    store_items = conn.execute(
        "SELECT * FROM store_items ORDER BY active DESC, id"
    ).fetchall()

    tasks = conn.execute(
        """SELECT t.*, k.name AS assigned_name
           FROM household_tasks t
           LEFT JOIN kids k ON k.id = t.assigned_kid_id
           ORDER BY t.task_type, t.active DESC, t.id"""
    ).fetchall()

    pending_tasks = conn.execute(
        """SELECT s.id AS submission_id, s.submitted_at,
                  t.id AS task_id, t.title, t.description, t.reward, t.icon, t.task_type,
                  k.id AS kid_id, k.name AS kid_name
           FROM task_submissions s
           JOIN household_tasks t ON t.id = s.task_id
           JOIN kids k ON k.id = s.kid_id
           WHERE s.status = 'pending'
           ORDER BY s.id DESC"""
    ).fetchall()

    summary = {
        "family_total": round(sum(k["total"] for k in kids), 2),
        "checking_total": round(sum(k["checking"] for k in kids), 2),
        "savings_total": round(sum(k["savings"] for k in kids), 2),
        "cards_linked": sum(1 for k in kids if k["nfc_uid"]),
        "kids_count": len(kids),
        "active_store_items": sum(1 for item in store_items if item["active"]),
        "open_tasks": sum(1 for task in tasks if task["active"]),
        "pending_tasks": len(pending_tasks),
    }

    conn.close()
    return render_template(
        "parent.html",
        kids=kids,
        store_items=store_items,
        tasks=tasks,
        pending_tasks=pending_tasks,
        summary=summary
    )

@app.route("/parent/logout", methods=["POST"])
def parent_logout():
    session.pop("parent_ok", None)
    flash("Parent mode locked.", "success")
    return redirect(url_for("dashboard"))

@app.route("/parent/kid/<int:kid_id>/transaction", methods=["POST"])
def parent_transaction(kid_id):
    if not parent_required():
        return redirect(url_for("parent"))

    account_type = request.form.get("account_type", "checking")
    action = request.form.get("action", "deposit")
    description = request.form.get("description", "").strip() or "Parent adjustment"

    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        amount = 0

    if account_type not in ("checking", "savings") or amount <= 0:
        flash("Enter a valid amount.", "error")
        return redirect(url_for("parent"))

    conn = get_db()
    current = account_balance(conn, kid_id, account_type)

    if action == "charge":
        if current < amount:
            conn.close()
            flash(f"Declined — not enough in {account_type}.", "error")
            return redirect(url_for("parent"))
        signed = -amount
        category = "charge"
    else:
        signed = amount
        category = "deposit"

    conn.execute(
        """INSERT INTO transactions
        (kid_id, account_type, amount, description, category, created_at)
        VALUES (?, ?, ?, ?, ?, ?)""",
        (kid_id, account_type, signed, description, category, now_text())
    )
    conn.commit()
    conn.close()
    flash("Account updated.", "success")
    return redirect(url_for("parent"))

@app.route("/parent/kid/<int:kid_id>/rent", methods=["POST"])
def parent_rent(kid_id):
    if not parent_required():
        return redirect(url_for("parent"))

    conn = get_db()
    kid = conn.execute("SELECT * FROM kids WHERE id = ?", (kid_id,)).fetchone()
    if not kid:
        conn.close()
        flash("Account not found.", "error")
        return redirect(url_for("parent"))

    rent = float(kid["rent_amount"])
    checking = account_balance(conn, kid_id, "checking")
    if checking < rent:
        conn.close()
        flash(f"Rent declined for {kid['name']} — not enough in checking.", "error")
        return redirect(url_for("parent"))

    conn.execute(
        """INSERT INTO transactions
        (kid_id, account_type, amount, description, category, created_at)
        VALUES (?, 'checking', ?, 'Monthly rent', 'rent', ?)""",
        (kid_id, -rent, now_text())
    )
    conn.commit()
    conn.close()
    flash(f"${rent:.2f} rent charged to {kid['name']}.", "success")
    return redirect(url_for("parent"))

@app.route("/parent/kid/<int:kid_id>/card", methods=["POST"])
def parent_card(kid_id):
    if not parent_required():
        return redirect(url_for("parent"))

    uid = request.form.get("nfc_uid", "").strip().upper()
    if not uid:
        flash("Enter a card UID.", "error")
        return redirect(url_for("parent"))

    conn = get_db()
    try:
        conn.execute("UPDATE kids SET nfc_uid = ? WHERE id = ?", (uid, kid_id))
        conn.commit()
        flash("Card linked to the account.", "success")
    except sqlite3.IntegrityError:
        flash("That card is already linked to another account.", "error")
    finally:
        conn.close()
    return redirect(url_for("parent"))



@app.route("/parent/task/add", methods=["POST"])
def parent_task_add():
    if not parent_required():
        return redirect(url_for("parent"))

    task_type = request.form.get("task_type", "chore")
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "").strip() or "✅"

    try:
        reward = float(request.form.get("reward", "0"))
    except ValueError:
        reward = -1

    assigned_raw = request.form.get("assigned_kid_id", "").strip()
    assigned_kid_id = None
    if assigned_raw:
        try:
            assigned_kid_id = int(assigned_raw)
        except ValueError:
            assigned_kid_id = None

    if task_type not in ("chore", "job"):
        task_type = "chore"

    if not title or reward < 0:
        flash("Enter a task name and valid reward.", "error")
        return redirect(url_for("parent") + "#jobs-manager")

    conn = get_db()

    if assigned_kid_id is not None:
        kid = conn.execute("SELECT id FROM kids WHERE id = ?", (assigned_kid_id,)).fetchone()
        if not kid:
            conn.close()
            flash("That kid account was not found.", "error")
            return redirect(url_for("parent") + "#jobs-manager")

    conn.execute(
        """INSERT INTO household_tasks
        (task_type, title, description, reward, icon, assigned_kid_id, active)
        VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (
            task_type,
            title,
            description,
            round(reward, 2),
            icon[:12],
            assigned_kid_id
        )
    )
    conn.commit()
    conn.close()

    flash(f"{title} was added.", "success")
    return redirect(url_for("parent") + "#jobs-manager")


@app.route("/parent/task/<int:task_id>/edit", methods=["POST"])
def parent_task_edit(task_id):
    if not parent_required():
        return redirect(url_for("parent"))

    task_type = request.form.get("task_type", "chore")
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    icon = request.form.get("icon", "").strip() or "✅"

    try:
        reward = float(request.form.get("reward", "0"))
    except ValueError:
        reward = -1

    assigned_raw = request.form.get("assigned_kid_id", "").strip()
    assigned_kid_id = None
    if assigned_raw:
        try:
            assigned_kid_id = int(assigned_raw)
        except ValueError:
            assigned_kid_id = None

    if task_type not in ("chore", "job"):
        task_type = "chore"

    if not title or reward < 0:
        flash("Enter a valid task name and reward.", "error")
        return redirect(url_for("parent") + "#jobs-manager")

    conn = get_db()
    conn.execute(
        """UPDATE household_tasks
           SET task_type = ?, title = ?, description = ?, reward = ?,
               icon = ?, assigned_kid_id = ?
           WHERE id = ?""",
        (
            task_type,
            title,
            description,
            round(reward, 2),
            icon[:12],
            assigned_kid_id,
            task_id
        )
    )
    conn.commit()
    conn.close()

    flash("Task updated.", "success")
    return redirect(url_for("parent") + "#jobs-manager")


@app.route("/parent/task/<int:task_id>/toggle", methods=["POST"])
def parent_task_toggle(task_id):
    if not parent_required():
        return redirect(url_for("parent"))

    conn = get_db()
    task = conn.execute(
        "SELECT title, active FROM household_tasks WHERE id = ?",
        (task_id,)
    ).fetchone()

    if not task:
        conn.close()
        flash("Task not found.", "error")
        return redirect(url_for("parent") + "#jobs-manager")

    new_active = 0 if task["active"] else 1

    if new_active:
        pending = conn.execute(
            """SELECT id FROM task_submissions
               WHERE task_id = ? AND status = 'pending'
               LIMIT 1""",
            (task_id,)
        ).fetchone()
        if pending:
            conn.close()
            flash("Review the pending request before reopening this task.", "error")
            return redirect(url_for("parent") + "#jobs-manager")

    conn.execute(
        "UPDATE household_tasks SET active = ? WHERE id = ?",
        (new_active, task_id)
    )
    conn.commit()
    conn.close()

    flash(f"{task['title']} is now {'open' if new_active else 'closed'}.", "success")
    return redirect(url_for("parent") + "#jobs-manager")


@app.route("/parent/task/submission/<int:submission_id>/<action>", methods=["POST"])
def parent_task_review(submission_id, action):
    if not parent_required():
        return redirect(url_for("parent"))

    if action not in ("approve", "reject"):
        flash("Invalid review action.", "error")
        return redirect(url_for("parent") + "#jobs-manager")

    conn = get_db()
    row = conn.execute(
        """SELECT s.*, t.title, t.reward, t.task_type, k.name AS kid_name
           FROM task_submissions s
           JOIN household_tasks t ON t.id = s.task_id
           JOIN kids k ON k.id = s.kid_id
           WHERE s.id = ?""",
        (submission_id,)
    ).fetchone()

    if not row or row["status"] != "pending":
        conn.close()
        flash("That request was already reviewed.", "error")
        return redirect(url_for("parent") + "#jobs-manager")

    stamp = now_text()

    if action == "approve":
        reward = round(float(row["reward"]), 2)

        conn.execute(
            """INSERT INTO transactions
            (kid_id, account_type, amount, description, category, created_at)
            VALUES (?, 'checking', ?, ?, ?, ?)""",
            (
                row["kid_id"],
                reward,
                f"{'Job' if row['task_type'] == 'job' else 'Chore'}: {row['title']}",
                row["task_type"],
                stamp
            )
        )

        conn.execute(
            """UPDATE task_submissions
               SET status = 'approved', reviewed_at = ?
               WHERE id = ?""",
            (stamp, submission_id)
        )

        # Close it after payment. Parent can reopen it for the next time.
        conn.execute(
            "UPDATE household_tasks SET active = 0 WHERE id = ?",
            (row["task_id"],)
        )

        conn.commit()
        conn.close()

        flash(
            f"Approved ✓ {row['kid_name']} earned ${reward:.2f} for {row['title']}.",
            "success"
        )
    else:
        conn.execute(
            """UPDATE task_submissions
               SET status = 'rejected', reviewed_at = ?
               WHERE id = ?""",
            (stamp, submission_id)
        )
        conn.commit()
        conn.close()

        flash(
            f"{row['title']} was sent back to {row['kid_name']} to try again.",
            "success"
        )

    return redirect(url_for("parent") + "#jobs-manager")


@app.route("/parent/store/add", methods=["POST"])
def parent_store_add():
    if not parent_required():
        return redirect(url_for("parent"))

    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip() or "⭐"
    try:
        price = float(request.form.get("price", "0"))
    except ValueError:
        price = -1

    if not name:
        flash("Give the store item a name.", "error")
        return redirect(url_for("parent") + "#store-manager")
    if price < 0:
        flash("Enter a valid price.", "error")
        return redirect(url_for("parent") + "#store-manager")

    conn = get_db()
    conn.execute(
        "INSERT INTO store_items (name, price, icon, active) VALUES (?, ?, ?, 1)",
        (name, round(price, 2), icon[:12])
    )
    conn.commit()
    conn.close()
    flash(f"{name} was added to the House Store.", "success")
    return redirect(url_for("parent") + "#store-manager")


@app.route("/parent/store/<int:item_id>/edit", methods=["POST"])
def parent_store_edit(item_id):
    if not parent_required():
        return redirect(url_for("parent"))

    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip() or "⭐"
    try:
        price = float(request.form.get("price", "0"))
    except ValueError:
        price = -1

    if not name or price < 0:
        flash("Enter a valid item name and price.", "error")
        return redirect(url_for("parent") + "#store-manager")

    conn = get_db()
    conn.execute(
        "UPDATE store_items SET name = ?, price = ?, icon = ? WHERE id = ?",
        (name, round(price, 2), icon[:12], item_id)
    )
    conn.commit()
    conn.close()
    flash("Store item updated.", "success")
    return redirect(url_for("parent") + "#store-manager")


@app.route("/parent/store/<int:item_id>/toggle", methods=["POST"])
def parent_store_toggle(item_id):
    if not parent_required():
        return redirect(url_for("parent"))

    conn = get_db()
    item = conn.execute("SELECT name, active FROM store_items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        conn.close()
        flash("Store item not found.", "error")
        return redirect(url_for("parent") + "#store-manager")

    new_active = 0 if item["active"] else 1
    conn.execute("UPDATE store_items SET active = ? WHERE id = ?", (new_active, item_id))
    conn.commit()
    conn.close()
    flash(f"{item['name']} is now {'visible' if new_active else 'hidden'} in the store.", "success")
    return redirect(url_for("parent") + "#store-manager")


@app.route("/parent/store/<int:item_id>/delete", methods=["POST"])
def parent_store_delete(item_id):
    if not parent_required():
        return redirect(url_for("parent"))

    conn = get_db()
    item = conn.execute("SELECT name FROM store_items WHERE id = ?", (item_id,)).fetchone()
    if item:
        conn.execute("DELETE FROM store_items WHERE id = ?", (item_id,))
        conn.commit()
        flash(f"{item['name']} was removed from the store.", "success")
    else:
        flash("Store item not found.", "error")
    conn.close()
    return redirect(url_for("parent") + "#store-manager")


@app.route("/tap")
def tap_lookup():
    uid = request.args.get("uid", "").strip().upper()
    if not uid:
        return jsonify({"ok": False, "error": "Missing uid"}), 400

    conn = get_db()
    row = conn.execute("SELECT * FROM kids WHERE nfc_uid = ?", (uid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"ok": False, "error": "Card not registered"}), 404

    kid = kid_payload(conn, row)
    conn.close()
    return jsonify({"ok": True, **kid})

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
