"""Création et manipulation de tickets, projets, tâches et pièces jointes."""
import os
import secrets
from datetime import date
from flask import abort, flash, request, send_file

from .config import EXT_IMAGES, UPLOAD_DIR
from .db import now
from .security import can_delete_task
from .settings_store import derived
from .sla import compute_due


# --- Création de tickets, commentaires, pièces jointes ---------------------------
def create_ticket(db, *, title, requester_name, category, priority, description,
                  requester_email="", department="", location="", assignee_id=None, source="web",
                  channel="", created_by=None):
    token, created = secrets.token_urlsafe(12), now()
    status = "En cours" if assignee_id else "Nouveau"
    cur = db.execute(
        """INSERT INTO tickets (token,title,requester_name,requester_email,department,location,category,
           priority,description,status,assignee_id,created_at,updated_at,due_at,source,channel,created_by)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (token, title, requester_name, requester_email, department, location, category, priority,
         description, status, assignee_id, created, created, compute_due(created, priority), source, channel, created_by))
    return cur.lastrowid, token


def add_comment(db, tid, author, is_staff, internal, body):
    return db.execute("INSERT INTO comments (ticket_id,author,is_staff,internal,body,created_at) VALUES (?,?,?,?,?,?)",
                      (tid, author, 1 if is_staff else 0, 1 if internal else 0, body, now())).lastrowid


def save_files(db, tid, cid, files, kind="ticket"):
    """Enregistre les fichiers envoyés. Retourne (nombre enregistré, liste d'erreurs)."""
    D = derived()
    files = [f for f in files if f and f.filename]
    saved, errors = 0, []
    if len(files) > D.max_files:
        errors.append(f"{D.max_files} fichiers maximum par envoi.")
        files = files[:D.max_files]
    for f in files:
        name = "".join(ch for ch in os.path.basename(f.filename.replace("\\", "/")) if ch.isprintable())[:120]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in D.ext:
            errors.append(f"« {name} » : type de fichier non accepté.")
            continue
        f.stream.seek(0, os.SEEK_END)
        size = f.stream.tell()
        f.stream.seek(0)
        if size == 0:
            continue
        if size > D.max_mo * 1024 * 1024:
            errors.append(f"« {name} » dépasse {D.max_mo} Mo.")
            continue
        stored = f"{secrets.token_hex(16)}.{ext}"
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        f.save(os.path.join(UPLOAD_DIR, stored))
        table, fk = ("project_attachments", "project_id") if kind == "projet" else ("attachments", "ticket_id")
        db.execute(f"INSERT INTO {table} ({fk},comment_id,filename,stored_name,size,created_at) VALUES (?,?,?,?,?,?)",
                   (tid, cid, name, stored, size, now()))
        saved += 1
    return saved, errors


def serve_attachment(a):
    path = os.path.join(UPLOAD_DIR, a["stored_name"])
    if not os.path.isfile(path):
        abort(404)
    ext = a["stored_name"].rsplit(".", 1)[-1].lower()
    inline = request.args.get("inline") == "1" and ext in EXT_IMAGES
    resp = send_file(path, mimetype=EXT_IMAGES[ext] if inline else "application/octet-stream",
                     as_attachment=not inline, download_name=a["filename"])
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resp


def group_attachments(rows, hidden_comment_ids=()):
    """Regroupe les pièces jointes par commentaire (clé 0 = description initiale)."""
    out = {}
    for a in rows:
        if a["comment_id"] in hidden_comment_ids:
            continue
        out.setdefault(a["comment_id"] or 0, []).append(a)
    return out


def valid_date(s):
    """Retourne la date au format AAAA-MM-JJ, ou '' si absente ou invalide."""
    try:
        return date.fromisoformat((s or "").strip()).isoformat()
    except ValueError:
        return ""


def due_badge(due, done=False):
    """(classe CSS, libellé) d'une échéance AAAA-MM-JJ (projets et tâches)."""
    if not due:
        return ("", "")
    try:
        d = date.fromisoformat(due)
    except ValueError:
        return ("", "")
    if done:
        return ("", f"Échéance : {d:%d/%m/%Y}")
    delta = (d - date.today()).days
    if delta < 0:
        return ("late", f"En retard de {-delta} j")
    if delta == 0:
        return ("soon", "Aujourd'hui")
    if delta <= 3:
        return ("soon", f"Dans {delta} j ({d:%d/%m})")
    return ("ok", f"Le {d:%d/%m/%Y}")


def safe_next(default):
    n = request.form.get("next", "")
    return n if n.startswith("/") and not n.startswith("//") else default


def create_project(db, *, title, description="", requester_name, requester_email="", department="",
                   wanted_date="", due_date="", owner_id=None, status="Proposé", source="web", created_by=None, channel=""):
    token, n = secrets.token_urlsafe(12), now()
    cur = db.execute(
        """INSERT INTO projects (token,title,description,requester_name,requester_email,department,wanted_date,
           due_date,owner_id,status,source,created_by,created_at,updated_at,channel) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (token, title, description, requester_name, requester_email, department, wanted_date, due_date,
         owner_id, status, source, created_by, n, n, channel))
    return cur.lastrowid, token


def add_pcomment(db, pid, author, is_staff, internal, body):
    return db.execute("INSERT INTO project_comments (project_id,author,is_staff,internal,body,created_at) VALUES (?,?,?,?,?,?)",
                      (pid, author, 1 if is_staff else 0, 1 if internal else 0, body, now())).lastrowid


def task_action(db, action, task_id):
    """Actions communes sur une tâche : cocher/décocher (toggle_task) ou supprimer (delete_task)."""
    if action == "toggle_task":
        db.execute("UPDATE tasks SET done=1-done, done_at=CASE WHEN done=0 THEN ? ELSE NULL END WHERE id=?", (now(), task_id))
    elif action == "delete_task":
        k = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if k is None:
            return True
        if not can_delete_task(k):
            flash("Cette tâche ne peut être supprimée que par son créateur, la personne assignée ou un administrateur.", "error")
            return False
        db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    return True
