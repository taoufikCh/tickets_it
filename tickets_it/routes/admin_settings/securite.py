"""Paramètres : session, verrouillage, mots de passe."""
from flask import flash, redirect, request, url_for

from ...routes.admin_settings.common import render_settings
from ...settings_store import derived, save_settings


# --- Sécurité ----------------------------------------------------------------
def sec_securite():
    D = derived()
    if request.method == "POST":
        f, errors, vals = request.form, [], {}
        for key, lo, hi, label in (("session_hours", 0, 720, "Durée de session"), ("lock_attempts", 0, 50, "Nombre d'essais"),
                                   ("lock_minutes", 1, 1440, "Durée de verrouillage"), ("pw_min", 4, 64, "Longueur minimale")):
            try:
                v = int(f.get(key, ""))
                if not lo <= v <= hi:
                    raise ValueError
                vals[key] = str(v)
            except ValueError:
                errors.append(f"{label} : valeur entre {lo} et {hi} attendue.")
        if errors:
            for e in errors:
                flash(e, "error")
            return render_settings("admin_settings/securite.html", "securite", v={k: f.get(k, "") for k in
                                   ("session_hours", "lock_attempts", "lock_minutes", "pw_min")}, mix=bool(f.get("pw_mix"))), 400
        vals["pw_mix"] = "1" if f.get("pw_mix") else "0"
        save_settings(vals)
        flash("Réglages de sécurité enregistrés. Ils s'appliquent aux prochaines connexions et changements de mot de passe.", "ok")
        return redirect(url_for("settings_page", section="securite"))
    return render_settings("admin_settings/securite.html", "securite", v={"session_hours": D.session_hours, "lock_attempts": D.lock_attempts,
                           "lock_minutes": D.lock_minutes, "pw_min": D.pw_min}, mix=D.pw_mix)
