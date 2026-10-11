"""Espace technicien : projets et tâches."""
from datetime import date, timedelta
from flask import abort, flash, g, redirect, render_template, request, url_for

from ..config import PROJET_COLONNES, PROJET_FINIS, PROJET_RESTREINT, PROJET_STATUTS
from ..db import get_db, now
from ..extensions import app
from ..mail import projet_url, render_mail, send_mail
from ..routes.public import _progress
from ..security import can_edit_project, login_required
from ..services import add_pcomment, create_project, group_attachments, safe_next, save_files, serve_attachment, task_action, valid_date


# PROJETS : espace technicien
@app.route("/admin/projets")
@login_required()
def projects_board():
    db = get_db()
    q, owner = request.args.get("q", "").strip(), request.args.get("owner", "")
    sql = ["SELECT p.*, u.name AS owner, (SELECT COUNT(*) FROM tasks WHERE project_id=p.id) AS n_tasks, "
           "(SELECT COUNT(*) FROM tasks WHERE project_id=p.id AND done=1) AS n_done "
           "FROM projects p LEFT JOIN users u ON u.id=p.owner_id WHERE 1=1"]
    args = []
    if owner == "moi":
        sql.append("AND p.owner_id=?")
        args.append(g.user["id"])
    elif owner == "aucun":
        sql.append("AND p.owner_id IS NULL")
    if q:
        sql.append("AND (p.title LIKE ? OR p.description LIKE ? OR p.requester_name LIKE ? OR p.department LIKE ? OR CAST(p.id AS TEXT)=?)")
        args += [f"%{q}%"] * 4 + [q.lstrip("#")]
    sql.append("ORDER BY CASE WHEN p.due_date='' THEN 1 ELSE 0 END, p.due_date, p.created_at DESC")
    rows = db.execute(" ".join(sql), args).fetchall()
    cols = {c: [r for r in rows if r["status"] == c] for c in PROJET_COLONNES}
    cols["Terminé"] = sorted(cols["Terminé"], key=lambda r: r["closed_at"] or "", reverse=True)[:15]
    return render_template("projects.html", cols=cols, colonnes=PROJET_COLONNES, f=request.args,
                                  annules=[r for r in rows if r["status"] == "Annulé"][:20])


@app.route("/admin/projets/nouveau", methods=["GET", "POST"])
@login_required()
def project_new():
    db, f = get_db(), request.form
    techs = db.execute("SELECT id, name FROM users ORDER BY name").fetchall()
    if request.method == "POST":
        title = f.get("title", "").strip()
        if not title:
            flash("Le titre est obligatoire.", "error")
            return render_template("project_new.html", techs=techs, form=f), 400
        owner = int(f["owner"]) if f.get("owner", "").isdigit() else None
        pid, _token = create_project(db, title=title, description=f.get("description", "").strip(),
                                     requester_name=f.get("requester", "").strip() or "Service informatique",
                                     department=f.get("department", "").strip(), due_date=valid_date(f.get("due")),
                                     owner_id=owner, status="À faire", source="tech", created_by=g.user["id"])
        for line in f.get("steps", "").splitlines():
            if line.strip():
                db.execute("INSERT INTO tasks (project_id,title,assignee_id,created_by,created_at) VALUES (?,?,?,?,?)",
                           (pid, line.strip()[:200], owner, g.user["id"], now()))
        _saved, errors = save_files(db, pid, None, request.files.getlist("files"), kind="projet")
        db.commit()
        if errors:
            flash("Projet créé, mais : " + " ".join(errors), "error")
        return redirect(url_for("project_detail", pid=pid))
    return render_template("project_new.html", techs=techs, form={"owner": str(g.user["id"])})


@app.route("/admin/projet/<int:pid>", methods=["GET", "POST"])
@login_required()
def project_detail(pid):
    db = get_db()
    p = db.execute("SELECT p.*, u.name AS owner, c.name AS creator FROM projects p LEFT JOIN users u ON u.id=p.owner_id "
                   "LEFT JOIN users c ON c.id=p.created_by WHERE p.id=?", (pid,)).fetchone()
    if p is None:
        abort(404)

    def tell(subject, text):  # email au demandeur (si adresse connue)
        send_mail(p["requester_email"], *render_mail("project_update", nom=p["requester_name"], numero=pid, titre=p["title"],
                                                     objet=subject, texte=text, lien=projet_url(p["token"])))

    can_edit = can_edit_project(p)
    if request.method == "POST":
        f, action = request.form, request.form.get("action")
        if not can_edit and (action in PROJET_RESTREINT or action == "toggle_task"):
            mine = False
            if action == "toggle_task" and f.get("id", "").isdigit():
                kk = db.execute("SELECT assignee_id FROM tasks WHERE id=? AND project_id=?", (int(f["id"]), pid)).fetchone()
                mine = bool(kk and kk["assignee_id"] == g.user["id"])
            if not mine:
                flash("Seul le responsable du projet ou un administrateur peut effectuer cette modification.", "error")
                return redirect(url_for("project_detail", pid=pid))
        if action == "update":
            status = f.get("status") if f.get("status") in PROJET_STATUTS else p["status"]
            owner = int(f["owner"]) if f.get("owner", "").isdigit() else None
            closed = (p["closed_at"] or now()) if status in PROJET_FINIS else None
            db.execute("UPDATE projects SET status=?, owner_id=?, due_date=?, closed_at=?, updated_at=? WHERE id=?",
                       (status, owner, valid_date(f.get("due")), closed, now(), pid))
            if status != p["status"]:
                add_pcomment(db, pid, g.user["name"], True, False, f"Statut : {p['status']} → {status}")
                tell(f"Statut : {status}", f"Votre projet « {p['title']} » est passé au statut « {status} ».")
            db.commit()
            flash("Projet mis à jour.", "ok")
        elif action == "edit":
            title = f.get("title", "").strip()
            if title:
                db.execute("UPDATE projects SET title=?, description=?, department=?, updated_at=? WHERE id=?",
                           (title, f.get("description", "").strip(), f.get("department", "").strip(), now(), pid))
                db.commit()
        elif action == "accept" and p["status"] == "Proposé":
            owner = int(f["owner"]) if f.get("owner", "").isdigit() else g.user["id"]
            due = valid_date(f.get("due")) or p["due_date"]
            name = db.execute("SELECT name FROM users WHERE id=?", (owner,)).fetchone()
            name = name["name"] if name else "un technicien"
            db.execute("UPDATE projects SET status='À faire', owner_id=?, due_date=?, updated_at=? WHERE id=?", (owner, due, now(), pid))
            msg = f"Demande acceptée. Responsable : {name}." + (f" Échéance prévue : {date.fromisoformat(due):%d/%m/%Y}." if due else "")
            add_pcomment(db, pid, g.user["name"], True, False, msg)
            db.commit()
            tell("Demande acceptée", f"Votre demande « {p['title']} » est acceptée. {msg}")
            flash("Demande acceptée : le projet est dans la colonne « À faire ».", "ok")
        elif action == "refuse" and p["status"] == "Proposé":
            reason = f.get("body", "").strip()
            if reason:
                db.execute("UPDATE projects SET status='Annulé', closed_at=?, updated_at=? WHERE id=?", (now(), now(), pid))
                add_pcomment(db, pid, g.user["name"], True, False, f"Demande refusée : {reason}")
                db.commit()
                tell("Demande refusée", f"Votre demande « {p['title']} » n'a pas pu être retenue.\n\nMotif : {reason}")
                flash("Demande refusée, le demandeur a été informé.", "ok")
            else:
                flash("Indiquez le motif du refus : il sera communiqué au demandeur.", "error")
        elif action == "comment":
            body, internal, files = f.get("body", "").strip(), bool(f.get("internal")), request.files.getlist("files")
            if body or any(x and x.filename for x in files):
                cid = add_pcomment(db, pid, g.user["name"], True, internal, body or "(pièce jointe)")
                _saved, errors = save_files(db, pid, cid, files, kind="projet")
                db.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
                db.commit()
                if errors:
                    flash(" ".join(errors), "error")
                if not internal and body:
                    tell("Nouveau message", f"{g.user['name']} a écrit à propos de votre projet « {p['title']} » :\n\n{body}")
        elif action == "add_task":
            title = f.get("title", "").strip()
            if title:
                db.execute("INSERT INTO tasks (project_id,title,assignee_id,due_date,created_by,created_at) VALUES (?,?,?,?,?,?)",
                           (pid, title[:200], int(f["assignee"]) if f.get("assignee", "").isdigit() else None,
                            valid_date(f.get("due")), g.user["id"], now()))
                db.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
                db.commit()
        elif action in ("toggle_task", "delete_task") and f.get("id", "").isdigit():
            if task_action(db, action, int(f["id"])):
                db.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), pid))
            db.commit()
        elif action == "link_ticket" and f.get("ticket", "").lstrip("#").isdigit():
            if db.execute("UPDATE tickets SET project_id=? WHERE id=?", (pid, int(f["ticket"].lstrip("#")))).rowcount:
                db.commit()
            else:
                flash("Ticket introuvable.", "error")
        elif action == "unlink_ticket" and f.get("id", "").isdigit():
            db.execute("UPDATE tickets SET project_id=NULL WHERE id=? AND project_id=?", (int(f["id"]), pid))
            db.commit()
        return redirect(url_for("project_detail", pid=pid))

    comments = db.execute("SELECT * FROM project_comments WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    atts = group_attachments(db.execute("SELECT * FROM project_attachments WHERE project_id=? ORDER BY id", (pid,)).fetchall())
    tasks = db.execute("SELECT k.*, u.name AS assignee FROM tasks k LEFT JOIN users u ON u.id=k.assignee_id "
                       "WHERE k.project_id=? ORDER BY k.done, k.id", (pid,)).fetchall()
    tickets = db.execute("SELECT id, title, status FROM tickets WHERE project_id=? ORDER BY id", (pid,)).fetchall()
    techs = db.execute("SELECT id, name FROM users ORDER BY name").fetchall()
    done, total = _progress(db, pid)
    return render_template("project.html", p=p, comments=comments, atts=atts, tasks=tasks, tickets=tickets, techs=techs,
                                  statuts=PROJET_STATUTS, done=done, total=total, link=projet_url(p["token"]), can_edit=can_edit)


@app.route("/admin/projet/fichier/<int:aid>")
@login_required()
def admin_projet_fichier(aid):
    a = get_db().execute("SELECT * FROM project_attachments WHERE id=?", (aid,)).fetchone()
    if a is None:
        abort(404)
    return serve_attachment(a)


# TÂCHES (personnelles ou rattachées à un projet)
@app.route("/admin/taches", methods=["GET", "POST"])
@login_required()
def tasks_page():
    db, f = get_db(), request.form
    if request.method == "POST":
        action = f.get("action")
        if action == "add":
            title = f.get("title", "").strip()
            if title:
                pid = int(f["project_id"]) if f.get("project_id", "").isdigit() else None
                if pid and not db.execute("SELECT 1 FROM projects WHERE id=?", (pid,)).fetchone():
                    pid = None
                db.execute("INSERT INTO tasks (project_id,title,notes,assignee_id,due_date,created_by,created_at) VALUES (?,?,?,?,?,?,?)",
                           (pid, title[:200], f.get("notes", "").strip(),
                            int(f["assignee"]) if f.get("assignee", "").isdigit() else None,
                            valid_date(f.get("due")), g.user["id"], now()))
                db.commit()
                flash("Tâche ajoutée.", "ok")
            else:
                flash("Le titre de la tâche est obligatoire.", "error")
        elif action in ("toggle_task", "delete_task") and f.get("id", "").isdigit():
            task_action(db, action, int(f["id"]))
            db.commit()
        return redirect(safe_next(url_for("tasks_page")))
    qui, fait = request.args.get("qui", "moi"), request.args.get("fait") == "1"
    sql = ["SELECT k.*, u.name AS assignee, p.title AS ptitle FROM tasks k LEFT JOIN users u ON u.id=k.assignee_id "
           "LEFT JOIN projects p ON p.id=k.project_id WHERE (k.project_id IS NULL OR p.status<>'Annulé')",
           "AND k.done=1" if fait else "AND k.done=0"]
    args = []
    if qui == "moi":
        sql.append("AND k.assignee_id=?")
        args.append(g.user["id"])
    elif qui == "aucun":
        sql.append("AND k.assignee_id IS NULL")
    sql.append("ORDER BY k.done_at DESC LIMIT 30" if fait else
               "ORDER BY CASE WHEN k.due_date='' THEN 1 ELSE 0 END, k.due_date, k.id")
    rows = db.execute(" ".join(sql), args).fetchall()
    today, soon = date.today().isoformat(), (date.today() + timedelta(days=7)).isoformat()
    sections = [("En retard", [r for r in rows if r["due_date"] and r["due_date"] < today]),
                ("Cette semaine", [r for r in rows if r["due_date"] and today <= r["due_date"] <= soon]),
                ("Plus tard", [r for r in rows if r["due_date"] and r["due_date"] > soon]),
                ("Sans date", [r for r in rows if not r["due_date"]])] if not fait else [("Terminées récemment", rows)]
    return render_template(
        "tasks.html", sections=sections, qui=qui, fait=fait, nxt=request.full_path.rstrip("?"),
        techs=db.execute("SELECT id, name FROM users ORDER BY name").fetchall(),
        projects=db.execute("SELECT id, title FROM projects WHERE status NOT IN ('Terminé','Annulé') ORDER BY title").fetchall(),
        total=len(rows))
