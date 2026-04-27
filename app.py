
from flask import Flask, render_template
import sqlite3
from pathlib import Path

app = Flask(__name__)

DATA_DIR = Path("/var/data") if Path("/var/data").exists() else Path(".")
DB_PATH = DATA_DIR / "patrol_build.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT
        )
    """)

    conn.commit()
    conn.close()

@app.route("/")
def dashboard():
    conn = get_db()
    tasks = conn.execute("SELECT * FROM tasks").fetchall()
    conn.close()
    return f"App running. Tasks count: {len(tasks)}"

# IMPORTANT FIX FOR RENDER
init_db()

if __name__ == "__main__":
    app.run(debug=True)
