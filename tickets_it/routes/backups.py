"""Page des sauvegardes (administrateur)."""
import os
from datetime import datetime
from flask import abort, flash, redirect, render_template, request, send_file, url_for

from ..config import BACKUP_DIR, DT_FMT
from ..db import get_meta
from ..extensions import app
from ..jobs import run_backup
from ..security import login_required
from ..settings_store import derived


# SAUVEGARDES (administrateur)
def _list_backups():
    d = os.path.join(BACKUP_DIR, "base")
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d), reverse=True):
        if name.startswith("tickets-") and name.endswith(".db"):
            st = os.stat(os.path.join(d, name))
            out.append({"name": name, "size": st.st_size, "date": datetime.fromtimestamp(st.st_mtime).strftime(DT_FMT)})
    return out


@app.route("/admin/sauvegardes", methods=["GET", "POST"])
@login_required(role="admin")
def backups_page():
    if request.method == "POST":
        ok, msg = run_backup()
        flash(msg, "ok" if ok else "error")
        return redirect(url_for("backups_page"))
    return render_template(
        "backups.html", items=_list_backups(), last=get_meta("last_backup_at"), status=get_meta("last_backup_status"),
        heure=derived().backup_hour, jours=derived().backup_days, dossier=BACKUP_DIR, copie=derived().backup_copy)


@app.route("/admin/sauvegardes/<name>")
@login_required(role="admin")
def backup_download(name):
    if name not in {b["name"] for b in _list_backups()}:  # liste blanche : pas de chemin arbitraire
        abort(404)
    return send_file(os.path.join(BACKUP_DIR, "base", name), as_attachment=True, download_name=name)
