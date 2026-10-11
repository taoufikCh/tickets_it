"""Paramètres : droits et restrictions."""
from flask import flash, redirect, request, url_for

from ...routes.admin_settings.common import render_settings
from ...settings_store import derived, save_settings


# --- Droits ------------------------------------------------------------------
def sec_droits():
    D = derived()
    if request.method == "POST":
        f = request.form
        save_settings({"restrict_edit": "1" if f.get("restrict_edit") else "0",
                       "restrict_delete": "1" if f.get("restrict_delete") else "0"})
        flash("Droits enregistrés.", "ok")
        return redirect(url_for("settings_page", section="droits"))
    return render_settings("admin_settings/droits.html", "droits", re=D.restrict_edit, rd=D.restrict_delete)
