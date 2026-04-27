from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from pathlib import Path
from datetime import datetime

app = Flask(__name__)
DB_PATH = Path("/var/data/patrol_build.db")

DEFAULT_SECTIONS = [
    "Engine",
    "Cooling",
    "Fuel System",
    "Gearbox / Transfer",
    "Diffs / Axles",
    "Suspension",
    "Steering",
    "Brakes",
    "Electrical",
    "Interior",
    "Exterior",
    "Wheels & Tyres",
    "Accessories",
    "Recovery Gear",
    "Camping Setup",
    "To Research",
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
    values = {
        "Planned": 0,
        "Parts Ready": 25,
        "In Progress": 50,
        "Waiting": 75,
        "Done": 100,
    }
    return values.get(status, 0)


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
            created_at TEXT NOT NULL
        )
    """)

    for section in DEFAULT_SECTIONS:
        cur.execute("INSERT OR IGNORE INTO sections (name) VALUES (?)", (section,))

    conn.commit()
    conn.close()


def get_sections(conn):
    return conn.execute("SELECT * FROM sections ORDER BY name").fetchall()


@app.template_filter("status_class")
def status_class(status):
    return status.lower().replace(" ", "-").replace("/", "-").replace("&", "and")


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

    if total_tasks:
        overall_progress = round(sum(task_progress_value(t["status"]) for t in tasks) / total_tasks)
    else:
        overall_progress = 0

    sections = get_sections(conn)
    section_progress = []

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
        section_progress=section_progress
    )


@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "INSERT INTO tasks (title, section, status, priority, notes, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                request.form["title"],
                request.form["section"],
                request.form["status"],
                request.form["priority"],
                request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("tasks"))

    rows = conn.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("tasks.html", tasks=rows, sections=sections, statuses=TASK_STATUSES, priorities=PRIORITIES, task_progress_value=task_progress_value)


@app.route("/tasks/<int:item_id>/edit", methods=["GET", "POST"])
def edit_task(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "UPDATE tasks SET title=?, section=?, status=?, priority=?, notes=? WHERE id=?",
            (
                request.form["title"],
                request.form["section"],
                request.form["status"],
                request.form["priority"],
                request.form.get("notes", ""),
                item_id,
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
        conn.execute(
            "INSERT INTO parts (name, section, supplier, price, status, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                request.form["name"],
                request.form["section"],
                request.form.get("supplier", ""),
                float(price),
                request.form["status"],
                request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("parts"))

    rows = conn.execute("SELECT * FROM parts ORDER BY id DESC").fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("parts.html", parts=rows, sections=sections, statuses=PART_STATUSES)


@app.route("/parts/<int:item_id>/edit", methods=["GET", "POST"])
def edit_part(item_id):
    conn = get_db()

    if request.method == "POST":
        price = request.form.get("price") or 0
        conn.execute(
            "UPDATE parts SET name=?, section=?, supplier=?, price=?, status=?, notes=? WHERE id=?",
            (
                request.form["name"],
                request.form["section"],
                request.form.get("supplier", ""),
                float(price),
                request.form["status"],
                request.form.get("notes", ""),
                item_id,
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
                request.form["title"],
                float(request.form["amount"]),
                request.form["cost_type"],
                request.form["section"],
                request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("costs"))

    rows = conn.execute("SELECT * FROM costs ORDER BY id DESC").fetchall()
    total = conn.execute("SELECT COALESCE(SUM(amount), 0) AS total FROM costs").fetchone()["total"]
    sections = get_sections(conn)
    conn.close()
    return render_template("costs.html", costs=rows, total=total, sections=sections, cost_types=COST_TYPES)


@app.route("/costs/<int:item_id>/edit", methods=["GET", "POST"])
def edit_cost(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "UPDATE costs SET title=?, amount=?, cost_type=?, section=?, notes=? WHERE id=?",
            (
                request.form["title"],
                float(request.form["amount"]),
                request.form["cost_type"],
                request.form["section"],
                request.form.get("notes", ""),
                item_id,
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
        conn.execute(
            "INSERT INTO updates (title, section, notes, created_at) VALUES (?, ?, ?, ?)",
            (
                request.form["title"],
                request.form["section"],
                request.form.get("notes", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            )
        )
        conn.commit()
        conn.close()
        return redirect(url_for("updates"))

    rows = conn.execute("SELECT * FROM updates ORDER BY id DESC").fetchall()
    sections = get_sections(conn)
    conn.close()
    return render_template("updates.html", updates=rows, sections=sections)


@app.route("/updates/<int:item_id>/edit", methods=["GET", "POST"])
def edit_update(item_id):
    conn = get_db()

    if request.method == "POST":
        conn.execute(
            "UPDATE updates SET title=?, section=?, notes=? WHERE id=?",
            (
                request.form["title"],
                request.form["section"],
                request.form.get("notes", ""),
                item_id,
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


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
