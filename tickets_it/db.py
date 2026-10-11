"""Accès SQLite : schéma, connexions, migrations, dates, table meta."""
import os
import sqlite3
from datetime import datetime
from flask import g
from werkzeug.security import generate_password_hash

from .config import DB_PATH, DT_FMT, REPONSES_PAR_DEFAUT, UPLOAD_DIR
from .extensions import app


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'tech',
    email TEXT NOT NULL DEFAULT '',
    notify INTEGER NOT NULL DEFAULT 1,
    digest INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    requester_email TEXT,
    department TEXT,
    location TEXT,
    category TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Normale',
    description TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Nouveau',
    assignee_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    due_at TEXT,
    paused_at TEXT,
    paused_secs INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'web',
    project_id INTEGER,
    remind_state TEXT
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    author TEXT NOT NULL,
    is_staff INTEGER NOT NULL DEFAULT 0,
    internal INTEGER NOT NULL DEFAULT 0,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
    comment_id INTEGER REFERENCES comments(id),
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    priority TEXT NOT NULL DEFAULT 'Normale',
    freq TEXT NOT NULL,
    weekday INTEGER NOT NULL DEFAULT 0,
    monthday INTEGER NOT NULL DEFAULT 1,
    assignee_id INTEGER REFERENCES users(id),
    active INTEGER NOT NULL DEFAULT 1,
    next_run TEXT NOT NULL,
    last_run TEXT
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL DEFAULT '',
    department TEXT NOT NULL DEFAULT '',
    wanted_date TEXT NOT NULL DEFAULT '',
    due_date TEXT NOT NULL DEFAULT '',
    owner_id INTEGER REFERENCES users(id),
    status TEXT NOT NULL DEFAULT 'Proposé',
    source TEXT NOT NULL DEFAULT 'web',
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT
);
CREATE TABLE IF NOT EXISTS project_comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    author TEXT NOT NULL,
    is_staff INTEGER NOT NULL DEFAULT 0,
    internal INTEGER NOT NULL DEFAULT 0,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS project_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL REFERENCES projects(id),
    comment_id INTEGER REFERENCES project_comments(id),
    filename TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    size INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER REFERENCES projects(id),
    title TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    assignee_id INTEGER REFERENCES users(id),
    due_date TEXT NOT NULL DEFAULT '',
    done INTEGER NOT NULL DEFAULT 0,
    done_at TEXT,
    created_by INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    ip TEXT NOT NULL DEFAULT '',
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_login_user ON login_attempts(username);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_pcomments_project ON project_comments(project_id);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status);
CREATE INDEX IF NOT EXISTS idx_att_ticket ON attachments(ticket_id);
"""


# --- Base de données ---------------------------------------------------------
def raw_db():
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def get_db():
    if "db" not in g:
        g.db = raw_db()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_column(db, table, column, decl):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})")]
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db():
    from .sla import compute_due  # import différé (évite un import circulaire)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    db = raw_db()
    db.executescript(SCHEMA)
    # migrations (bases créées avec une version précédente)
    _ensure_column(db, "users", "email", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "users", "notify", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(db, "users", "digest", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(db, "tickets", "channel", "TEXT NOT NULL DEFAULT ''")
    _ensure_column(db, "tickets", "created_by", "INTEGER")
    for col, decl in (("glpi_id", "INTEGER"), ("glpi_sent_at", "TEXT"), ("glpi_error", "TEXT")):
        _ensure_column(db, "tickets", col, decl)
    _ensure_column(db, "projects", "channel", "TEXT NOT NULL DEFAULT ''")
    for col, decl in (("due_at", "TEXT"), ("paused_at", "TEXT"),
                      ("paused_secs", "INTEGER NOT NULL DEFAULT 0"), ("source", "TEXT NOT NULL DEFAULT 'web'"),
                      ("project_id", "INTEGER"), ("remind_state", "TEXT")):
        _ensure_column(db, "tickets", col, decl)
    for r in db.execute("SELECT id, created_at, priority FROM tickets WHERE due_at IS NULL").fetchall():
        db.execute("UPDATE tickets SET due_at=? WHERE id=?", (compute_due(r["created_at"], r["priority"], 0), r["id"]))
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute("INSERT INTO users (username, name, password_hash, role) VALUES (?,?,?,?)",
                   ("admin", "Administrateur", generate_password_hash("admin"), "admin"))
        print("\n>>> Compte créé : admin / admin  (changez le mot de passe dès la première connexion)\n")
    if db.execute("SELECT COUNT(*) FROM replies").fetchone()[0] == 0:
        db.executemany("INSERT INTO replies (title, body) VALUES (?,?)", REPONSES_PAR_DEFAUT)
    db.commit()
    db.close()


def now():
    return datetime.now().strftime(DT_FMT)


def parse_dt(s):
    return datetime.strptime(s, DT_FMT)


def fmt(dt):
    return dt.strftime(DT_FMT)


def get_meta(key, default=None):
    db = raw_db()
    try:
        r = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default
    finally:
        db.close()


def set_meta(key, value):
    db = raw_db()
    try:
        db.execute("INSERT INTO meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        db.commit()
    finally:
        db.close()
