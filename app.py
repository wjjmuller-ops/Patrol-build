from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

APP_USERNAME = os.environ.get("APP_USERNAME", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "patrol123")

DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(".")
DB_PATH = DATA_DIR / "patrol_build.db"
UPLOAD_DIR = DATA_DIR / "uploads" if Path("/var/data").exists() else Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

DEFAULT_SECTIONS = [
    "Engine", "Cooling", "Fuel System", "Gearbox / Transfer", "Diffs / Axles",
    "Suspension", "Steering", "Brakes", "Electrical", "Interior", "Exterior",
    "Wheels & Tyres", "Accessories", "Recovery Gear", "Camping Setup", "To Research",
]

TASK_STATUSES = ["Planned", "Parts Ready", "In Progress", "Waiting", "Done"]
PART_STATUSES = ["Wishlist", "Ordered", "Received", "Installed"]
PRIORITIES = ["Low", "Medium", "High"]
COST_TYPES = ["Part", "Labour", "Tool", "Other"]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def task_progress_value(status):
    return {
        "Planned": 0,
        "Parts Ready": 25,
        "In Progress": 50,
        "Waiting": 75,
        "Done": 100,
    }.get(status, 0)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_photo(file):
    if not file or file.filename == "":
        return None
    if not allowed_file(file.filename):
        return None

    safe_name = secure_filename(file.filename)
    stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    filename = f"{stamp}_{safe_name}"
    file.save(UPLOAD_DIR / filename)
    return filename


def add_column_if_missing(conn, table, column, column_type):
    existing = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Planned',
            priority TEXT NOT NULL DEFAULT 'Medium',
            notes TEXT,
            photo TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            section TEXT NOT NULL,
            supplier TEXT,
            price REAL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Wishlist',
            notes TEXT,
            photo TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS costs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            amount REAL NOT NULL,
            cost_type TEXT NOT NULL DEFAULT 'Part',
            section TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            section TEXT NOT NULL,
            notes TEXT,
            photo TEXT,
            created_at TEXT NOT NULL
        )
    """)

    add_column_if_missing(conn, "tasks", "photo", "TEXT")
    add_column_if_missing(conn, "parts", "photo", "TEXT")
    add_column_if_missing(conn, "updates", "photo", "TEXT")

    for section in DEFAULT_SECTIONS:
        cur.execute("INSERT OR IGNORE INTO sections (name) VALUES (?)", (section,))

    conn.commit()
    conn.close()


def get_sections(conn):
    return conn.execute("SELECT * FROM sections ORDER BY name").fetchall()


def is_logged_in():
    return session.get("logged_in") is True


@app.before_request
def require_login():
    allowed = {"login", "static", "uploaded_file"}
    if request.endpoint in allowed:
        return
    if not is_logged_in():
        return redirect(url_for("login"))


@app.template_filter("status_class")
def status_class(status):
    return status.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == APP_USERNAME and request.form.get("password") == APP_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    conn = get_db()

    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    parts = conn.execute("SELECT * FROM parts ORDER BY id DESC LIMIT 5").fetchall()
    updates = conn.execute("SELECT * FROM updates ORDER BY id DESC LIMIT 5").fetchall()
    total_spend = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM costs").fetchone()["total"]

    total_tasks = len(tasks)
    open_tasks = len([t for t in tasks if t["status"] != "Done"])
    done_tasks = len([t for t in tasks if t["status"] == "Done"])

    overall_progress = round(sum(task_progress_value(t["status"]) for t in tasks) / total_tasks) if total_tasks else 0

    sections = get_sections(conn)
    section_progress = []
    spend_by_section = []
    spend_rows = conn.execute("""
        SELECT section, COALESCE(SUM(amount), 0) AS total
        FROM costs
        GROUP BY section
        ORDER BY total DESC
    """).fetchall()

    max_spend = max([row["total"] for row in spend_rows], default=0)

    for section in sections:
        section_tasks = [t for t in tasks if t["section"] == section["name"]]
        if section_tasks:
            progress = round(sum(task_progress_value(t["status"]) for t in section_tasks) / len(section_tasks))
            completed = len([t for t in section_tasks if t["status"] == "Done"])
            section_progress.append({
                "name": section["name"],
                "progress": progress,
                "total": len(section_tasks),
                "completed": completed,
            })

    for row in spend_rows:
        percent = round((row["total"] / max_spend) * 100) if max_spend else 0
        spend_by_section.append({"section": row["section"], "total": row["total"], "percent": percent})

    conn.close()

    return render_template(
        "dashboard.html",
        overall_progress=overall_progress,
        total_spend=total_spend,
        total_tasks=total_tasks,
        open_tasks=open_tasks,
        done_tasks=done_tasks,
        parts=parts,
        updates=updates,
        section_progress=section_progress,
        spend_by_section=spend_by_section
    )


@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    conn = get_db()

    if request.method == "POST":
        photo = save_photo(request.files.get("photo"))
        conn.execute(
            "INSERT INTO tasks (title, section, status, priority, notes, photo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["title"], request.form["section"], request.form["status"],
                request.form["priority"], request.form.get("notes", ""), photo,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("tasks"))

    query = request.args.get("q", "").strip()
    section_filter = request.args.get("section", "")
    status_filter = request.args.get("status", "")

    sql = "SELECT * FROM tasks WHERE 1=1"
    params = []

    if query:
        sql += " AND (title LIKE ? OR notes LIKE ?)"
        params += [f"%{query}%", f"%{query}%"]
    if section_filter:
        sql += " AND section = ?"
        params.append(section_filter)
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)

    sql += " ORDER BY id DESC"

    rows = conn.execute(sql, params).fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("tasks.html", tasks=rows, sections=sections, statuses=TASK_STATUSES, priorities=PRIORITIES,
                           task_progress_value=task_progress_value, filters={"q": query, "section": section_filter, "status": status_filter})


@app.route("/tasks/<int:item_id>/edit", methods=["GET", "POST"])
def edit_task(item_id):
    conn = get_db()

    if request.method == "POST":
        existing = conn.execute("SELECT * FROM tasks WHERE id=?", (item_id,)).fetchone()
        photo = save_photo(request.files.get("photo")) or existing["photo"]
        conn.execute(
            "UPDATE tasks SET title=?, section=?, status=?, priority=?, notes=?, photo=? WHERE id=?",
            (
                request.form["title"], request.form["section"], request.form["status"],
                request.form["priority"], request.form.get("notes", ""), photo, item_id,
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("tasks"))

    task = conn.execute("SELECT * FROM tasks WHERE id=?", (item_id,)).fetchone()
    sections = get_sections(conn)
    conn.close()
    return render_template("edit_task.html", task=task, sections=sections, statuses=TASK_STATUSES, priorities=PRIORITIES)


@app.route("/tasks/<int:item_id>/delete", methods=["POST"])
def delete_task(item_id):
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("tasks"))


@app.route("/parts", methods=["GET", "POST"])
def parts():
    conn = get_db()

    if request.method == "POST":
        price = request.form.get("price") or 0
        photo = save_photo(request.files.get("photo"))
        conn.execute(
            "INSERT INTO parts (name, section, supplier, price, status, notes, photo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"], request.form["section"], request.form.get("supplier", ""),
                float(price), request.form["status"], request.form.get("notes", ""), photo,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("parts"))

    query = request.args.get("q", "").strip()
    section_filter = request.args.get("section", "")
    status_filter = request.args.get("status", "")

    sql = "SELECT * FROM parts WHERE 1=1"
    params = []
    if query:
        sql += " AND (name LIKE ? OR supplier LIKE ? OR notes LIKE ?)"
        params += [f"%{query}%", f"%{query}%", f"%{query}%"]
    if section_filter:
        sql += " AND section = ?"
        params.append(section_filter)
    if status_filter:
        sql += " AND status = ?"
        params.append(status_filter)
    sql += " ORDER BY id DESC"

    rows = conn.execute(sql, params).fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("parts.html", parts=rows, sections=sections, statuses=PART_STATUSES,
                           filters={"q": query, "section": section_filter, "status": status_filter})


@app.route("/parts/<int:item_id>/edit", methods=["GET", "POST"])
def edit_part(item_id):
    conn = get_db()

    if request.method == "POST":
        existing = conn.execute("SELECT * FROM parts WHERE id=?", (item_id,)).fetchone()
        price = request.form.get("price") or 0
        photo = save_photo(request.files.get("photo")) or existing["photo"]
        conn.execute(
            "UPDATE parts SET name=?, section=?, supplier=?, price=?, status=?, notes=?, photo=? WHERE id=?",
            (
                request.form["name"], request.form["section"], request.form.get("supplier", ""),
                float(price), request.form["status"], request.form.get("notes", ""), photo, item_id,
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("parts"))

    part = conn.execute("SELECT * FROM parts WHERE id=?", (item_id,)).fetchone()
    sections = get_sections(conn)
    conn.close()
    return render_template("edit_part.html", part=part, sections=sections, statuses=PART_STATUSES)


@app.route("/parts/<int:item_id>/delete", methods=["POST"])
def delete_part(item_id):
    conn = get_db()
    conn.execute("DELETE FROM parts WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("parts"))


@app.route("/costs", methods=["GET", "POST"])
def costs():
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "INSERT INTO costs (title, amount, cost_type, section, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.form["title"], float(request.form["amount"]), request.form["cost_type"],
                request.form["section"], request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("costs"))

    section_filter = request.args.get("section", "")
    type_filter = request.args.get("cost_type", "")

    sql = "SELECT * FROM costs WHERE 1=1"
    params = []
    if section_filter:
        sql += " AND section = ?"
        params.append(section_filter)
    if type_filter:
        sql += " AND cost_type = ?"
        params.append(type_filter)
    sql += " ORDER BY id DESC"

    rows = conn.execute(sql, params).fetchall()
    total = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM costs").fetchone()["total"]
    sections = get_sections(conn)
    conn.close()
    return render_template("costs.html", costs=rows, total=total, sections=sections, cost_types=COST_TYPES,
                           filters={"section": section_filter, "cost_type": type_filter})


@app.route("/costs/<int:item_id>/edit", methods=["GET", "POST"])
def edit_cost(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "UPDATE costs SET title=?, amount=?, cost_type=?, section=?, notes=? WHERE id=?",
            (
                request.form["title"], float(request.form["amount"]), request.form["cost_type"],
                request.form["section"], request.form.get("notes", ""), item_id,
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("costs"))

    cost = conn.execute("SELECT * FROM costs WHERE id=?", (item_id,)).fetchone()
    sections = get_sections(conn)
    conn.close()
    return render_template("edit_cost.html", cost=cost, sections=sections, cost_types=COST_TYPES)


@app.route("/costs/<int:item_id>/delete", methods=["POST"])
def delete_cost(item_id):
    conn = get_db()
    conn.execute("DELETE FROM costs WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("costs"))


@app.route("/updates", methods=["GET", "POST"])
def updates():
    conn = get_db()

    if request.method == "POST":
        photo = save_photo(request.files.get("photo"))
        conn.execute(
            "INSERT INTO updates (title, section, notes, photo, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                request.form["title"], request.form["section"], request.form.get("notes", ""), photo,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("updates"))

    section_filter = request.args.get("section", "")
    sql = "SELECT * FROM updates WHERE 1=1"
    params = []
    if section_filter:
        sql += " AND section = ?"
        params.append(section_filter)
    sql += " ORDER BY id DESC"

    rows = conn.execute(sql, params).fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("updates.html", updates=rows, sections=sections, filters={"section": section_filter})


@app.route("/updates/<int:item_id>/edit", methods=["GET", "POST"])
def edit_update(item_id):
    conn = get_db()

    if request.method == "POST":
        existing = conn.execute("SELECT * FROM updates WHERE id=?", (item_id,)).fetchone()
        photo = save_photo(request.files.get("photo")) or existing["photo"]
        conn.execute(
            "UPDATE updates SET title=?, section=?, notes=?, photo=? WHERE id=?",
            (
                request.form["title"], request.form["section"], request.form.get("notes", ""),
                photo, item_id,
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("updates"))

    update = conn.execute("SELECT * FROM updates WHERE id=?", (item_id,)).fetchone()
    sections = get_sections(conn)
    conn.close()
    return render_template("edit_update.html", update=update, sections=sections)


@app.route("/updates/<int:item_id>/delete", methods=["POST"])
def delete_update(item_id):
    conn = get_db()
    conn.execute("DELETE FROM updates WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("updates"))



# Create or update database tables when the app starts, including on Render/Gunicorn.
init_db()

if __name__ == "__main__":
    app.run(debug=True)
