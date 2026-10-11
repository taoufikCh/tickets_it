"""Espace technicien : tickets, statistiques, réponses types, tickets récurrents."""
import csv
import io
from datetime import datetime, timedelta
from flask import Response, abort, flash, g, jsonify, redirect, render_template, request, url_for

from .. import glpi
from ..config import FREQUENCES, HEURE_TACHES, JOURS_NOMS, OUVERTS_SQL, STATUTS
from ..db import fmt, get_db, now, parse_dt
from ..extensions import app
from ..jobs import backup_warning, next_run_after, run_recurring
from ..mail import projet_url, render_mail, send_mail, track_url
from ..security import delete_denied, login_required
from ..services import add_comment, add_pcomment, create_project, group_attachments, save_files, serve_attachment
from ..settings_store import CATEGORIES, CATEGORIES_ACTIVES, PRIORITES, derived, get_settings, prio_rank_sql
from ..sla import set_status


@app.route("/admin")
@login_required()
def admin():
    db = get_db()
    q, status = request.args.get("q", "").strip(), request.args.get("status", "ouverts")
    category, priority, assignee, sla_f = (request.args.get(k, "") for k in ("category", "priority", "assignee", "sla"))
    sql, args = ["SELECT t.*, u.name AS assignee FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id WHERE 1=1"], []
    if status == "ouverts":
        sql.append(f"AND t.status IN {OUVERTS_SQL}")
    elif status in STATUTS:
        sql.append("AND t.status=?")
        args.append(status)
    if category in CATEGORIES:
        sql.append("AND t.category=?")
        args.append(category)
    if priority in PRIORITES:
        sql.append("AND t.priority=?")
        args.append(priority)
    if assignee == "moi":
        sql.append("AND t.assignee_id=?")
        args.append(g.user["id"])
    elif assignee == "aucun":
        sql.append("AND t.assignee_id IS NULL")
    if sla_f == "retard":
        sql.append("AND t.status IN ('Nouveau','En cours') AND t.due_at < ?")
        args.append(now())
    if q:
        sql.append("AND (t.title LIKE ? OR t.requester_name LIKE ? OR t.description LIKE ? OR CAST(t.id AS TEXT)=?)")
        args += [f"%{q}%"] * 3 + [q.lstrip("#")]
    sql.append(f"ORDER BY {prio_rank_sql('t.priority')}, t.created_at DESC")
    tickets = db.execute(" ".join(sql), args).fetchall()

    def one(sql_, *a):
        return db.execute(sql_, a).fetchone()[0]
    stats = {
        "ouverts": one(f"SELECT COUNT(*) FROM tickets WHERE status IN {OUVERTS_SQL}"),
        "nouveaux": one("SELECT COUNT(*) FROM tickets WHERE status='Nouveau'"),
        "non_assignes": one(f"SELECT COUNT(*) FROM tickets WHERE assignee_id IS NULL AND status IN {OUVERTS_SQL}"),
        "urgents": one(f"SELECT COUNT(*) FROM tickets WHERE priority=? AND status IN {OUVERTS_SQL}", derived().prio_top),
        "en_retard": one("SELECT COUNT(*) FROM tickets WHERE status IN ('Nouveau','En cours') AND due_at < ?", now()),
        "resolus_7j": one("SELECT COUNT(*) FROM tickets WHERE closed_at >= datetime('now','localtime','-7 days')"),
    }
    warn = backup_warning() if g.user["role"] == "admin" else ""
    pending = one("SELECT COUNT(*) FROM projects WHERE status='Proposé'")
    return render_template("admin.html", tickets=tickets, stats=stats, categories=CATEGORIES, priorites=PRIORITES,
                                  statuts=STATUTS, f=request.args, status=status, warn=warn, pending=pending)


@app.route("/admin/api/nouveaux")
def api_nouveaux():
    """Interrogé toutes les 20 s par les pages techniciens pour afficher les alertes (tickets et demandes de projet)."""
    if g.user is None:
        return jsonify(error="auth"), 401
    db = get_db()
    mx = db.execute("SELECT COALESCE(MAX(id),0) FROM tickets").fetchone()[0]
    mxp = db.execute("SELECT COALESCE(MAX(id),0) FROM projects").fetchone()[0]
    apres, apres_p = request.args.get("apres", type=int, default=-1), request.args.get("apres_p", type=int, default=-1)
    rows = projets = []
    if apres >= 0:
        rows = db.execute("SELECT id,title,priority,requester_name FROM tickets WHERE id>? AND source='web' ORDER BY id LIMIT 10",
                          (apres,)).fetchall()
    if apres_p >= 0:
        projets = db.execute("SELECT id,title,requester_name FROM projects WHERE id>? AND source='web' ORDER BY id LIMIT 10",
                             (apres_p,)).fetchall()
    D = derived()
    tickets = [dict(r, urgent=r["priority"] == D.prio_top, high=r["priority"] == D.prio_second) for r in rows]
    return jsonify(max=mx, tickets=tickets, max_p=mxp, projets=[dict(r) for r in projets])


@app.route("/admin/ticket/<int:tid>", methods=["GET", "POST"])
@login_required()
def admin_ticket(tid):
    db = get_db()
    t = db.execute("SELECT t.*, u.name AS assignee, c.name AS creator FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id "
                   "LEFT JOIN users c ON c.id=t.created_by WHERE t.id=?", (tid,)).fetchone()
    if t is None:
        abort(404)
    if request.method == "POST":
        f, action = request.form, request.form.get("action")
        if action == "update":
            status = f.get("status") if f.get("status") in STATUTS else t["status"]
            priority = f.get("priority") if f.get("priority") in PRIORITES else t["priority"]
            category = f.get("category") if f.get("category") in CATEGORIES else t["category"]
            assignee = int(f["assignee"]) if f.get("assignee", "").isdigit() else None
            if status == "Nouveau" and assignee:
                status = "En cours"
            db.execute("UPDATE tickets SET priority=?, category=?, assignee_id=? WHERE id=?", (priority, category, assignee, tid))
            t2 = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
            set_status(db, t2, status)  # recalcule aussi l'échéance (priorité modifiée)
            if status != t["status"]:
                add_comment(db, tid, g.user["name"], True, False, f"Statut : {t['status']} → {status}")
                send_mail(t["requester_email"], *render_mail("ticket_status", nom=t["requester_name"], numero=tid, titre=t["title"],
                                                             statut=status, lien=track_url(t["token"])))
            db.commit()
            flash("Ticket mis à jour.", "ok")
        elif action == "comment":
            body, internal = f.get("body", "").strip(), bool(f.get("internal"))
            files = request.files.getlist("files")
            if body or any(x and x.filename for x in files):
                cid = add_comment(db, tid, g.user["name"], True, internal, body or "(pièce jointe)")
                _saved, errors = save_files(db, tid, cid, files)
                db.execute("UPDATE tickets SET updated_at=? WHERE id=?", (now(), tid))
                db.commit()
                if errors:
                    flash(" ".join(errors), "error")
                if not internal:
                    send_mail(t["requester_email"], *render_mail("ticket_reply", nom=t["requester_name"], numero=tid, titre=t["title"],
                                                                 technicien=g.user["name"], message=body, lien=track_url(t["token"])))
        elif action == "link_project":
            pid = f.get("project_id", "")
            if pid.isdigit() and db.execute("SELECT 1 FROM projects WHERE id=?", (int(pid),)).fetchone():
                db.execute("UPDATE tickets SET project_id=? WHERE id=?", (int(pid), tid))
            elif not pid:
                db.execute("UPDATE tickets SET project_id=NULL WHERE id=?", (tid,))
            db.commit()
        elif action == "to_project":
            pid, ptoken = create_project(db, title=t["title"], description=t["description"], requester_name=t["requester_name"],
                                         requester_email=t["requester_email"] or "", department=t["department"] or "",
                                         owner_id=t["assignee_id"] or g.user["id"], status="À faire", source="ticket",
                                         created_by=g.user["id"])
            for a in db.execute("SELECT * FROM attachments WHERE ticket_id=? AND comment_id IS NULL", (tid,)).fetchall():
                db.execute("INSERT INTO project_attachments (project_id,comment_id,filename,stored_name,size,created_at) VALUES (?,?,?,?,?,?)",
                           (pid, None, a["filename"], a["stored_name"], a["size"], now()))
            add_pcomment(db, pid, g.user["name"], True, False, f"Projet créé à partir du ticket #{tid}.")
            db.execute("UPDATE tickets SET project_id=? WHERE id=?", (pid, tid))
            if t["status"] not in ("Résolu", "Clos"):
                set_status(db, db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone(), "Résolu")
            add_comment(db, tid, g.user["name"], True, False, f"Cette demande est devenue le projet #{pid}.")
            db.commit()
            send_mail(t["requester_email"], *render_mail("ticket_to_project", nom=t["requester_name"], numero=tid, titre=t["title"],
                                                         projet=pid, lien=projet_url(ptoken)))
            flash("Ticket transformé en projet.", "ok")
            return redirect(url_for("project_detail", pid=pid))
        elif action == "glpi_send":
            try:
                gid, already = glpi.send_ticket(db, tid, track_url(t["token"]))
                if already:
                    flash(f"Ce ticket a déjà été envoyé vers GLPI (ticket GLPI n° {gid}).", "ok")
                else:
                    add_comment(db, tid, g.user["name"], True, True, f"Ticket envoyé vers GLPI par {g.user['name']} (ticket GLPI n° {gid}).")
                    db.commit()
                    flash(f"Ticket envoyé vers GLPI : ticket GLPI n° {gid}.", "ok")
            except glpi.GlpiError as e:
                flash("Envoi vers GLPI impossible : " + str(e), "error")
        elif action == "take":
            db.execute("UPDATE tickets SET assignee_id=? WHERE id=?", (g.user["id"], tid))
            if t["status"] == "Nouveau":
                set_status(db, db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone(), "En cours")
            db.commit()
        return redirect(url_for("admin_ticket", tid=tid))
    comments = db.execute("SELECT * FROM comments WHERE ticket_id=? ORDER BY id", (tid,)).fetchall()
    atts = group_attachments(db.execute("SELECT * FROM attachments WHERE ticket_id=? ORDER BY id", (tid,)).fetchall())
    techs = db.execute("SELECT id, name FROM users ORDER BY name").fetchall()
    subst = {"{nom}": t["requester_name"], "{technicien}": g.user["name"], "{numero}": str(tid),
             "{lieu}": t["location"] or "votre bureau"}
    replies = {}
    for r in db.execute("SELECT * FROM replies ORDER BY title").fetchall():
        body = r["body"]
        for k, v in subst.items():
            body = body.replace(k, v)
        replies[r["id"]] = {"title": r["title"], "body": body}
    gcfg = get_settings()
    return render_template("ticket.html", t=t, comments=comments, glpi_on=glpi.glpi_enabled(gcfg),
                           glpi_link=glpi.ticket_link(gcfg, t["glpi_id"]) if t["glpi_id"] and gcfg["glpi_url"].strip() else "", atts=atts, techs=techs,
                                  categories=list(CATEGORIES_ACTIVES) + ([] if t["category"] in CATEGORIES_ACTIVES else [t["category"]]),
                                  priorites=PRIORITES, statuts=STATUTS, link=track_url(t["token"]), replies=replies,
                                  projects=db.execute("SELECT id, title FROM projects WHERE status NOT IN ('Terminé','Annulé') OR id=? ORDER BY id DESC",
                                                      (t["project_id"] or 0,)).fetchall(),
                                  proj=db.execute("SELECT id, title, status FROM projects WHERE id=?", (t["project_id"],)).fetchone() if t["project_id"] else None)


@app.route("/admin/fichier/<int:aid>")
@login_required()
def admin_fichier(aid):
    a = get_db().execute("SELECT * FROM attachments WHERE id=?", (aid,)).fetchone()
    if a is None:
        abort(404)
    return serve_attachment(a)


@app.route("/admin/export.csv")
@login_required()
def export_csv():
    rows = get_db().execute("SELECT t.*, u.name AS assignee, c.name AS creator FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id "
                                "LEFT JOIN users c ON c.id=t.created_by ORDER BY t.id").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=";")
    w.writerow(["N°", "Créé le", "Statut", "Priorité", "Catégorie", "Titre", "Demandeur", "Service", "Lieu",
                "Technicien", "Échéance", "Clos le", "Délai respecté", "Source", "Saisi par"])
    for r in rows:
        done = r["closed_at"] and r["due_at"]
        vals = [r["id"], r["created_at"], r["status"], r["priority"], r["category"], r["title"], r["requester_name"],
                r["department"] or "", r["location"] or "", r["assignee"] or "", r["due_at"] or "", r["closed_at"] or "",
                ("oui" if r["closed_at"] <= r["due_at"] else "non") if done else "",
                r["channel"] or ("Ticket récurrent" if r["source"] == "planifie" else "Formulaire en ligne"), r["creator"] or ""]
        w.writerow([("'" + c) if isinstance(c, str) and c and c[0] in "=+-@" else c for c in vals])
    return Response("\ufeff" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=tickets.csv"})


# STATISTIQUES
@app.route("/admin/stats")
@login_required()
def stats_page():
    db = get_db()
    p = request.args.get("p", "90")
    days = int(p) if p in ("30", "90", "365") else 0
    W, args = ("WHERE created_at >= ?", [(datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")]) if days else ("WHERE 1=1", [])
    AVG = "AVG(CASE WHEN closed_at IS NOT NULL THEN (julianday(closed_at)-julianday(created_at))*24 END)"
    SLA_OK = "SUM(CASE WHEN closed_at IS NOT NULL AND due_at IS NOT NULL AND closed_at<=due_at THEN 1 ELSE 0 END)"
    CLOSED = "SUM(CASE WHEN closed_at IS NOT NULL THEN 1 ELSE 0 END)"
    OPEN = f"SUM(CASE WHEN status IN {OUVERTS_SQL} THEN 1 ELSE 0 END)"

    def rows(group_sql, extra=""):
        return db.execute(f"SELECT {group_sql} AS label, COUNT(*) AS n, {OPEN} AS open, {CLOSED} AS closed, "
                          f"{SLA_OK} AS sla_ok, {AVG} AS avg_h FROM tickets {W} {extra}", args).fetchall()

    total = rows("'Total'")[0]
    by_cat = rows("category", "GROUP BY category ORDER BY n DESC")
    by_prio = rows("priority", f"GROUP BY priority ORDER BY {prio_rank_sql('priority')}")
    by_dept = db.execute(f"SELECT department AS label, COUNT(*) AS n FROM tickets {W} AND department<>'' AND source<>'planifie' "
                         "GROUP BY lower(department) ORDER BY n DESC LIMIT 8", args).fetchall()
    by_tech = db.execute(f"SELECT COALESCE(u.name,'Non assigné') AS label, COUNT(*) AS n, "
                         f"SUM(CASE WHEN t.status IN {OUVERTS_SQL} THEN 1 ELSE 0 END) AS open, "
                         "SUM(CASE WHEN t.closed_at IS NOT NULL THEN 1 ELSE 0 END) AS closed, "
                         "AVG(CASE WHEN t.closed_at IS NOT NULL THEN (julianday(t.closed_at)-julianday(t.created_at))*24 END) AS avg_h "
                         f"FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id {W.replace('created_at', 't.created_at')} "
                         "GROUP BY u.id ORDER BY n DESC", args).fetchall()
    recurrent = db.execute(f"SELECT MIN(location) AS location, category, COUNT(*) AS n FROM tickets {W} AND location<>'' "
                           "AND source<>'planifie' GROUP BY lower(trim(location)), category HAVING n>=2 ORDER BY n DESC LIMIT 8", args).fetchall()
    created_m = {r[0]: r[1] for r in db.execute("SELECT strftime('%Y-%m', created_at), COUNT(*) FROM tickets GROUP BY 1")}
    closed_m = {r[0]: r[1] for r in db.execute("SELECT strftime('%Y-%m', closed_at), COUNT(*) FROM tickets WHERE closed_at IS NOT NULL GROUP BY 1")}
    months, y, m = [], datetime.now().year, datetime.now().month
    for _ in range(12):
        key = f"{y}-{m:02d}"
        months.append({"label": f"{m:02d}/{str(y)[2:]}", "created": created_m.get(key, 0), "closed": closed_m.get(key, 0)})
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    months.reverse()
    late = db.execute("SELECT COUNT(*) FROM tickets WHERE status IN ('Nouveau','En cours') AND due_at < ?", (now(),)).fetchone()[0]
    return render_template("stats.html", p=p, total=total, by_cat=by_cat, by_prio=by_prio, by_dept=by_dept,
                                  by_tech=by_tech, recurrent=recurrent, months=months, late=late,
                                  mx_month=max([1] + [x["created"] for x in months] + [x["closed"] for x in months]))


# RÉPONSES TYPES
@app.route("/admin/reponses", methods=["GET", "POST"])
@login_required()
def replies_page():
    db, f = get_db(), request.form
    if request.method == "POST":
        action, title, body = f.get("action"), f.get("title", "").strip(), f.get("body", "").strip()
        if action == "add" and title and body:
            db.execute("INSERT INTO replies (title, body) VALUES (?,?)", (title, body))
        elif action == "save" and f.get("id", "").isdigit() and title and body:
            db.execute("UPDATE replies SET title=?, body=? WHERE id=?", (title, body, int(f["id"])))
        elif action == "delete" and delete_denied():
            flash("La suppression est réservée aux administrateurs (Paramètres → Droits).", "error")
            return redirect(url_for("replies_page"))
        elif action == "delete" and f.get("id", "").isdigit():
            db.execute("DELETE FROM replies WHERE id=?", (int(f["id"]),))
        else:
            flash("Le titre et le texte sont obligatoires.", "error")
            return redirect(url_for("replies_page"))
        db.commit()
        flash("Réponses types mises à jour.", "ok")
        return redirect(url_for("replies_page"))
    return render_template("replies.html", replies=db.execute("SELECT * FROM replies ORDER BY title").fetchall())


# TÂCHES PLANIFIÉES
@app.route("/admin/planifiees", methods=["GET", "POST"])
@login_required()
def recurring_page():
    db, f = get_db(), request.form
    if request.method == "POST":
        action, rid = f.get("action"), f.get("id", "")
        if action == "add":
            title, desc = f.get("title", "").strip(), f.get("description", "").strip()
            freq = f.get("freq") if f.get("freq") in FREQUENCES else "semaine"
            category = f.get("category") if f.get("category") in CATEGORIES else CATEGORIES_ACTIVES[0]
            priority = f.get("priority") if f.get("priority") in PRIORITES else derived().prio_default
            weekday = int(f["weekday"]) if f.get("weekday", "").isdigit() and int(f["weekday"]) < 7 else 0
            monthday = int(f["monthday"]) if f.get("monthday", "").isdigit() and 1 <= int(f["monthday"]) <= 28 else 1
            assignee = int(f["assignee"]) if f.get("assignee", "").isdigit() else None
            if title and desc:
                nxt = fmt(next_run_after(freq, weekday, monthday, datetime.now()))
                db.execute("INSERT INTO recurring (title,description,category,priority,freq,weekday,monthday,assignee_id,next_run) "
                           "VALUES (?,?,?,?,?,?,?,?,?)", (title, desc, category, priority, freq, weekday, monthday, assignee, nxt))
                flash(f"Ticket récurrent créé. Prochain ticket : {parse_dt(nxt):%d/%m/%Y à %Hh%M}.", "ok")
            else:
                flash("Le titre et la description sont obligatoires.", "error")
        elif rid.isdigit():
            r = db.execute("SELECT * FROM recurring WHERE id=?", (int(rid),)).fetchone()
            if r and action == "toggle":
                nxt = fmt(next_run_after(r["freq"], r["weekday"], r["monthday"], datetime.now()))
                db.execute("UPDATE recurring SET active=?, next_run=? WHERE id=?", (0 if r["active"] else 1, nxt, r["id"]))
            elif r and action == "delete" and delete_denied():
                flash("La suppression est réservée aux administrateurs (Paramètres → Droits).", "error")
            elif r and action == "delete":
                db.execute("DELETE FROM recurring WHERE id=?", (r["id"],))
            elif r and action == "run":
                db.commit()
                run_recurring(force_id=r["id"])
                flash("Ticket créé.", "ok")
        db.commit()
        return redirect(url_for("recurring_page"))
    return render_template(
        "recurring.html", items=db.execute("SELECT r.*, u.name AS assignee FROM recurring r LEFT JOIN users u ON u.id=r.assignee_id ORDER BY r.title").fetchall(),
        techs=db.execute("SELECT id, name FROM users ORDER BY name").fetchall(), categories=CATEGORIES_ACTIVES, priorites=PRIORITES,
        frequences=FREQUENCES, jours=JOURS_NOMS, heure=HEURE_TACHES)
