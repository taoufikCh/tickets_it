"""Pages publiques : formulaire de demande et suivi par lien."""
from flask import abort, flash, g, redirect, render_template, request, url_for

from ..db import get_db, now
from ..extensions import app
from ..mail import notify_staff, notify_staff_project, projet_url, render_mail, send_mail, track_url
from ..services import add_comment, add_pcomment, create_project, create_ticket, group_attachments, save_files, serve_attachment, valid_date
from ..settings_store import CATEGORIES_ACTIVES, PRIORITES, derived
from ..sla import set_status


# PAGES PUBLIQUES (demandeurs)
def _title_from(desc, limit=100):
    """Titre court tiré de la description : première ligne non vide, coupée proprement."""
    first = next((l.strip() for l in desc.splitlines() if l.strip()), "")
    if len(first) <= limit:
        return first
    return first[:limit].rsplit(" ", 1)[0].rstrip(",;:- ") + "…"


@app.route("/", methods=["GET", "POST"])
def nouveau():
    if request.method == "POST":
        f = request.form
        kind = "projet" if f.get("kind") == "projet" else "ticket"
        name, desc = f.get("name", "").strip(), f.get("description", "").strip()
        title = _title_from(desc)   # plus de champ « résumé » : le titre vient du début de la description
        category, priority = f.get("category", ""), f.get("priority") or derived().prio_default
        email, department = f.get("email", "").strip(), f.get("department", "").strip()
        # Un technicien qui saisit la demande pour quelqu'un indique comment elle lui est parvenue.
        staff = g.user is not None and g.user["role"] != "lecteur"
        channel = f.get("channel", "") if staff else ""
        source, created_by = ("tech", g.user["id"]) if staff else ("web", None)
        if staff and channel not in derived().channels:
            flash("Indiquez la source de la demande (téléphone, email, sur place…).", "error")
            return render_template("nouveau.html", form=f, categories=CATEGORIES_ACTIVES, priorites=PRIORITES), 400
        if not (name and title and desc) or (kind == "ticket" and (category not in CATEGORIES_ACTIVES or priority not in PRIORITES)):
            flash("Merci de remplir tous les champs obligatoires.", "error")
            return render_template("nouveau.html", form=f, categories=CATEGORIES_ACTIVES, priorites=PRIORITES), 400
        db = get_db()
        if kind == "projet":
            pid, token = create_project(db, title=title, description=desc, requester_name=name, requester_email=email,
                                        department=department, wanted_date=valid_date(f.get("wanted")),
                                        source=source, created_by=created_by, channel=channel)
            _saved, errors = save_files(db, pid, None, request.files.getlist("files"), kind="projet")
            db.commit()
            if errors:
                flash("Demande enregistrée, mais : " + " ".join(errors), "error")
            send_mail(email, *render_mail("project_created", nom=name, numero=pid, titre=title, lien=projet_url(token)))
            notify_staff_project(db, pid, title, name, department)
            return redirect(url_for("projet_suivi", token=token, created=1))
        tid, token = create_ticket(db, title=title, requester_name=name, requester_email=email,
                                   department=department, location=f.get("location", "").strip(),
                                   category=category, priority=priority, description=desc,
                                   source=source, channel=channel, created_by=created_by)
        saved, errors = save_files(db, tid, None, request.files.getlist("files"))
        db.commit()
        if errors:
            flash("Ticket créé, mais : " + " ".join(errors), "error")
        send_mail(email, *render_mail("ticket_created", nom=name, numero=tid, titre=title, lien=track_url(token)))
        notify_staff(db, tid, title, priority, name, category)
        return redirect(url_for("suivi", token=token, created=1))
    return render_template("nouveau.html", form={}, categories=CATEGORIES_ACTIVES, priorites=PRIORITES)


def _ticket_by_token(db, token):
    t = db.execute("SELECT t.*, u.name AS assignee FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id "
                   "WHERE token=?", (token,)).fetchone()
    if t is None:
        abort(404)
    return t


@app.route("/suivi/<token>", methods=["GET", "POST"])
def suivi(token):
    db = get_db()
    t = _ticket_by_token(db, token)
    if request.method == "POST":
        body, files = request.form.get("body", "").strip(), request.files.getlist("files")
        if (body or any(x and x.filename for x in files)) and t["status"] != "Clos":
            cid = add_comment(db, t["id"], t["requester_name"], False, False, body or "(pièce jointe)")
            _saved, errors = save_files(db, t["id"], cid, files)
            if t["status"] in ("Résolu", "En attente"):  # une réponse rouvre / relance le ticket
                set_status(db, t, "En cours")
            else:
                db.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now(), t["id"]))
            db.commit()
            if errors:
                flash(" ".join(errors), "error")
        return redirect(url_for("suivi", token=token))
    comments = db.execute("SELECT * FROM comments WHERE ticket_id=? AND internal=0 ORDER BY id", (t["id"],)).fetchall()
    internal_ids = {r["id"] for r in db.execute("SELECT id FROM comments WHERE ticket_id=? AND internal=1", (t["id"],))}
    atts = group_attachments(db.execute("SELECT * FROM attachments WHERE ticket_id=? ORDER BY id", (t["id"],)).fetchall(),
                             internal_ids)
    return render_template("suivi.html", t=t, comments=comments, atts=atts, created=request.args.get("created"))


@app.route("/suivi/<token>/fichier/<int:aid>")
def suivi_fichier(token, aid):
    db = get_db()
    t = _ticket_by_token(db, token)
    a = db.execute("SELECT a.* FROM attachments a LEFT JOIN comments c ON c.id=a.comment_id "
                   "WHERE a.id=? AND a.ticket_id=? AND COALESCE(c.internal,0)=0", (aid, t["id"])).fetchone()
    if a is None:
        abort(404)
    return serve_attachment(a)


# PROJETS : pages publiques (demandeurs)
def _projet_by_token(db, token):
    p = db.execute("SELECT p.*, u.name AS owner FROM projects p LEFT JOIN users u ON u.id=p.owner_id WHERE token=?",
                   (token,)).fetchone()
    if p is None:
        abort(404)
    return p


def _progress(db, pid):
    r = db.execute("SELECT COUNT(*), COALESCE(SUM(done),0) FROM tasks WHERE project_id=?", (pid,)).fetchone()
    return r[1], r[0]  # (terminées, total)


@app.route("/projet/<token>", methods=["GET", "POST"])
def projet_suivi(token):
    db = get_db()
    p = _projet_by_token(db, token)
    if request.method == "POST":
        body, files = request.form.get("body", "").strip(), request.files.getlist("files")
        if (body or any(x and x.filename for x in files)) and p["status"] != "Annulé":
            cid = add_pcomment(db, p["id"], p["requester_name"], False, False, body or "(pièce jointe)")
            _saved, errors = save_files(db, p["id"], cid, files, kind="projet")
            if p["status"] == "Terminé":  # une réponse rouvre le projet
                db.execute("UPDATE projects SET status='En cours', closed_at=NULL, updated_at=? WHERE id=?", (now(), p["id"]))
            else:
                db.execute("UPDATE projects SET updated_at=? WHERE id=?", (now(), p["id"]))
            db.commit()
            if errors:
                flash(" ".join(errors), "error")
        return redirect(url_for("projet_suivi", token=token))
    comments = db.execute("SELECT * FROM project_comments WHERE project_id=? AND internal=0 ORDER BY id", (p["id"],)).fetchall()
    internal_ids = {r["id"] for r in db.execute("SELECT id FROM project_comments WHERE project_id=? AND internal=1", (p["id"],))}
    atts = group_attachments(db.execute("SELECT * FROM project_attachments WHERE project_id=? ORDER BY id", (p["id"],)).fetchall(),
                             internal_ids)
    done, total = _progress(db, p["id"])
    return render_template("projet_suivi.html", p=p, comments=comments, atts=atts, done=done, total=total,
                                  created=request.args.get("created"))


@app.route("/projet/<token>/fichier/<int:aid>")
def projet_suivi_fichier(token, aid):
    db = get_db()
    p = _projet_by_token(db, token)
    a = db.execute("SELECT a.* FROM project_attachments a LEFT JOIN project_comments c ON c.id=a.comment_id "
                   "WHERE a.id=? AND a.project_id=? AND COALESCE(c.internal,0)=0", (aid, p["id"])).fetchone()
    if a is None:
        abort(404)
    return serve_attachment(a)
