"""Paramètres : sauvegardes automatiques."""
import os
import secrets
from flask import flash, redirect, request, url_for

from ...config import BACKUP_DIR
from ...routes.admin_settings.common import render_settings
from ...settings_store import derived, save_settings


# --- Sauvegardes -------------------------------------------------------------
def _check_writable(path):
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, f".test-{secrets.token_hex(4)}")
        with open(probe, "w") as fh:
            fh.write("ok")
        os.remove(probe)
        return None
    except OSError as e:
        return str(e.strerror or e)


def sec_sauvegardes():
    D = derived()
    if request.method == "POST":
        f, errors = request.form, []
        copy = f.get("backup_copy", "").strip()
        try:
            hour, days = int(f.get("backup_hour", "")), int(f.get("backup_days", ""))
            if not (0 <= hour <= 23 and 1 <= days <= 365):
                raise ValueError
        except ValueError:
            errors.append("Heure : entre 0 et 23 ; durée de conservation : entre 1 et 365 jours.")
            hour, days = D.backup_hour, D.backup_days
        if copy:
            if os.path.abspath(copy) == os.path.abspath(BACKUP_DIR):
                errors.append("Le 2e emplacement doit être différent du dossier principal.")
            else:
                err = _check_writable(copy)
                if err:
                    errors.append(f"Le dossier « {copy} » n'est pas accessible en écriture : {err}.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_settings("admin_settings/sauvegardes.html", "sauvegardes", auto=bool(f.get("backup_auto")), hour=f.get("backup_hour", ""),
                                   days=f.get("backup_days", ""), copy=copy, main=BACKUP_DIR), 400
        save_settings({"backup_auto": "1" if f.get("backup_auto") else "0", "backup_hour": str(hour),
                       "backup_days": str(days), "backup_copy": copy})
        flash("Réglages de sauvegarde enregistrés.", "ok")
        return redirect(url_for("settings_page", section="sauvegardes"))
    return render_settings("admin_settings/sauvegardes.html", "sauvegardes", auto=D.backup_auto, hour=D.backup_hour, days=D.backup_days,
                           copy=D.backup_copy, main=BACKUP_DIR)
