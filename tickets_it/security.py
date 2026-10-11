"""Session, droits, CSRF, verrouillage de compte, politique de mot de passe."""
import re
import secrets
from datetime import datetime, timedelta
from flask import abort, g, redirect, request, session, url_for
from functools import wraps

from .config import LECTEUR_AUTORISE
from .db import fmt, get_db, now, parse_dt
from .extensions import app
from .settings_store import derived


# --- Sécurité : session, droits, CSRF ------------------------------------------
@app.before_request
def load_user_and_csrf():
    D = derived()
    app.config["MAX_CONTENT_LENGTH"] = D.max_request
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=D.session_hours or 24)
    g.user = None
    if session.get("uid"):
        g.user = get_db().execute("SELECT * FROM users WHERE id=?", (session["uid"],)).fetchone()
        if g.user is None:
            session.clear()
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    if request.method == "POST":
        if not secrets.compare_digest(request.form.get("csrf", ""), session["csrf"]):
            abort(400, "Jeton de sécurité invalide. Rechargez la page et recommencez.")
        if g.user is not None and g.user["role"] == "lecteur" and request.endpoint not in LECTEUR_AUTORISE:
            abort(403, "Votre compte est en lecture seule : cette modification n'est pas autorisée.")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return resp


app.jinja_env.globals["csrf_token"] = lambda: session.get("csrf", "")


def login_required(role=None):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if g.user is None:
                return redirect(url_for("login", next=request.path))
            if role == "admin" and g.user["role"] != "admin":
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco


def delete_denied():
    return derived().restrict_delete and g.user["role"] != "admin"


def login_locked(username):
    """Minutes restantes de verrouillage du compte (0 si non verrouillé)."""
    D = derived()
    if D.lock_attempts <= 0:
        return 0
    since = fmt(datetime.now() - timedelta(minutes=D.lock_minutes))
    rows = [r["ts"] for r in get_db().execute("SELECT ts FROM login_attempts WHERE username=? AND ts>=? ORDER BY ts", (username, since))]
    if len(rows) < D.lock_attempts:
        return 0
    left = (parse_dt(rows[len(rows) - D.lock_attempts]) + timedelta(minutes=D.lock_minutes) - datetime.now()).total_seconds()
    return int(left // 60) + (1 if left % 60 else 0) if left > 0 else 0


def record_failed_login(username):
    db = get_db()
    db.execute("INSERT INTO login_attempts (username, ip, ts) VALUES (?,?,?)", (username, request.remote_addr or "", now()))
    db.execute("DELETE FROM login_attempts WHERE ts < ?", (fmt(datetime.now() - timedelta(days=2)),))
    db.commit()


def clear_login_attempts(username):
    db = get_db()
    db.execute("DELETE FROM login_attempts WHERE username=?", (username,))
    db.commit()


def password_error(pw):
    D = derived()
    if len(pw) < D.pw_min:
        return f"Le mot de passe doit contenir au moins {D.pw_min} caractères."
    if D.pw_mix and not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "Le mot de passe doit contenir à la fois des lettres et des chiffres."
    return None


def can_edit_project(p):
    if not derived().restrict_edit:
        return True
    return g.user["role"] == "admin" or p["owner_id"] is None or p["owner_id"] == g.user["id"]


def can_delete_task(k):
    if not derived().restrict_delete:
        return True
    return g.user["role"] == "admin" or g.user["id"] in (k["created_by"], k["assignee_id"])


def admin_count(db):
    return db.execute("SELECT COUNT(*) FROM users WHERE role='admin'").fetchone()[0]
