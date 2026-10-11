"""Paramètres : pièces jointes."""
from flask import flash, redirect, request, url_for

from ...config import EXT_CATALOGUE, EXT_CHOISISSABLES
from ...routes.admin_settings.common import render_settings
from ...settings_store import derived, save_settings


# --- Pièces jointes ----------------------------------------------------------
def sec_fichiers():
    D = derived()
    if request.method == "POST":
        f, errors = request.form, []
        try:
            mo = int(f.get("max_mo", ""))
            nb = int(f.get("max_files", ""))
            if not (1 <= mo <= 200 and 1 <= nb <= 20):
                raise ValueError
        except ValueError:
            errors.append("Taille : entre 1 et 200 Mo ; nombre de fichiers : entre 1 et 20.")
            mo, nb = D.max_mo, D.max_files
        exts = [e for e in sorted(EXT_CHOISISSABLES) if f.get(f"ext_{e}")]
        if not exts:
            errors.append("Autorisez au moins un type de fichier.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_settings("admin_settings/fichiers.html", "fichiers", mo=f.get("max_mo", ""), nb=f.get("max_files", ""),
                                   exts=set(exts), catalogue=EXT_CATALOGUE), 400
        save_settings({"max_mo": str(mo), "max_files": str(nb), "extensions": ",".join(exts)})
        flash("Réglages des pièces jointes enregistrés.", "ok")
        return redirect(url_for("settings_page", section="fichiers"))
    return render_settings("admin_settings/fichiers.html", "fichiers", mo=D.max_mo, nb=D.max_files, exts=D.ext, catalogue=EXT_CATALOGUE)
