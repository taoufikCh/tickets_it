"""Connexion, déconnexion, comptes techniciens, mon compte."""
import secrets
import sqlite3
from flask import flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..config import ROLES
from ..db import get_db
from ..extensions import app
from ..mail import email_enabled
from ..security import admin_count, clear_login_attempts, login_locked, login_required, password_error, record_failed_login
from ..settings_store import derived


# CONNEXION
@app.route("/connexion", methods=["GET", "POST"], endpoint="login")
def login():
    if request.method == "POST":
        username, password = request.form.get("username", "").strip().lower(), request.form.get("password", "")
        wait = login_locked(username)
        if wait:
            flash(f"Trop de tentatives échouées. Réessayez dans {wait} minute{'s' if wait > 1 else ''}.", "error")
            return render_template("login.html"), 429
        u = get_db().execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if u and check_password_hash(u["password_hash"], password):
            clear_login_attempts(username)
            session.clear()
            session["uid"] = u["id"]
            session["csrf"] = secrets.token_hex(16)
            session.permanent = derived().session_hours > 0
            if password == "admin":
                session["default_pw"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("admin"))
        if derived().lock_attempts:
            record_failed_login(username)
            wait = login_locked(username)
            if wait:
                flash(f"Trop de tentatives échouées. Compte verrouillé pendant {wait} minute{'s' if wait > 1 else ''}.", "error")
                return render_template("login.html"), 429
        flash("Identifiant ou mot de passe incorrect.", "error")
    return render_template("login.html")


@app.route("/deconnexion", methods=["POST"], endpoint="logout")
def logout():
    session.clear()
    return redirect(url_for("nouveau"))


# COMPTES
@app.route("/admin/utilisateurs", methods=["GET", "POST"])
@login_required(role="admin")
def users():
    db = get_db()
    if request.method == "POST":
        f, action = request.form, request.form.get("action")
        uid = int(f["id"]) if f.get("id", "").isdigit() else None
        u = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone() if uid else None
        if action == "add":
            username, name, pw = f.get("username", "").strip().lower(), f.get("name", "").strip(), f.get("password", "")
            role = f.get("role") if f.get("role") in ROLES else "tech"
            if not (username and name):
                flash("Identifiant et nom sont obligatoires.", "error")
            elif password_error(pw):
                flash(password_error(pw), "error")
            else:
                try:
                    db.execute("INSERT INTO users (username,name,password_hash,role,email) VALUES (?,?,?,?,?)",
                               (username, name, generate_password_hash(pw), role, f.get("email", "").strip()))
                    db.commit()
                    flash("Compte ajouté.", "ok")
                except sqlite3.IntegrityError:
                    flash("Cet identifiant existe déjà.", "error")
        elif action == "update" and u:
            name = f.get("name", "").strip() or u["name"]
            role = f.get("role") if f.get("role") in ROLES else u["role"]
            pw = f.get("password", "")
            if u["role"] == "admin" and role != "admin" and (admin_count(db) <= 1 or u["id"] == g.user["id"]):
                flash("Vous ne pouvez pas retirer le rôle d'administrateur à ce compte (il en faut au moins un, et pas vous-même).", "error")
            elif pw and password_error(pw):
                flash(password_error(pw), "error")
            else:
                db.execute("UPDATE users SET name=?, email=?, role=? WHERE id=?", (name, f.get("email", "").strip(), role, u["id"]))
                if pw:
                    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(pw), u["id"]))
                db.commit()
                flash("Compte mis à jour.", "ok")
        elif action == "unlock" and u:
            clear_login_attempts(u["username"])
            flash(f"Compte « {u['username']} » déverrouillé.", "ok")
        elif action == "delete" and u and u["id"] != g.user["id"]:
            if u["role"] == "admin" and admin_count(db) <= 1:
                flash("Impossible de supprimer le dernier administrateur.", "error")
            else:
                db.execute("UPDATE tickets SET assignee_id=NULL WHERE assignee_id=?", (u["id"],))
                db.execute("UPDATE recurring SET assignee_id=NULL WHERE assignee_id=?", (u["id"],))
                db.execute("UPDATE projects SET owner_id=NULL WHERE owner_id=?", (u["id"],))
                db.execute("UPDATE tasks SET assignee_id=NULL WHERE assignee_id=?", (u["id"],))
                db.execute("DELETE FROM users WHERE id=?", (u["id"],))
                db.commit()
        return redirect(url_for("users"))
    rows = db.execute("SELECT * FROM users ORDER BY name").fetchall()
    D = derived()
    return render_template("users.html", users=rows, roles=ROLES, locked={r["username"]: login_locked(r["username"]) for r in rows},
                                  pw_rule=f"{D.pw_min} caractères min." + (", lettres et chiffres" if D.pw_mix else ""))


@app.route("/admin/compte", methods=["GET", "POST"], endpoint="account")
@login_required()
def account():
    db, f = get_db(), request.form
    if request.method == "POST":
        if f.get("action") == "profile":
            db.execute("UPDATE users SET email=?, notify=?, digest=? WHERE id=?",
                       (f.get("email", "").strip(), 1 if f.get("notify") else 0, 1 if f.get("digest") else 0, g.user["id"]))
            db.commit()
            flash("Préférences enregistrées.", "ok")
        elif not check_password_hash(g.user["password_hash"], f.get("old", "")):
            flash("Ancien mot de passe incorrect.", "error")
        elif f.get("new") != f.get("confirm"):
            flash("Les deux saisies du nouveau mot de passe ne sont pas identiques.", "error")
        elif password_error(f.get("new", "")):
            flash(password_error(f.get("new", "")), "error")
        else:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(f["new"]), g.user["id"]))
            db.commit()
            flash("Mot de passe modifié.", "ok")
            if f["new"] == "admin":
                session["default_pw"] = True
            else:
                session.pop("default_pw", None)
        return redirect(url_for("account"))
    return render_template("account.html", smtp=email_enabled())
