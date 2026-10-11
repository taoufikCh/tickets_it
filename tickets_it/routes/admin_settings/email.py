"""Paramètres : email (SMTP)."""
from flask import flash, g, redirect, request, url_for

from ...config import SECURITES
from ...mail import email_enabled, smtp_error_text, smtp_send
from ...routes.admin_settings.common import render_settings
from ...settings_store import get_settings, save_settings


# --- Email -------------------------------------------------------------------
def _email_form_to_cfg(f, saved):
    """Convertit le formulaire en configuration ; retourne (cfg, erreurs)."""
    cfg, errors = dict(saved), []
    cfg["email_enabled"] = "1" if f.get("email_enabled") else "0"
    cfg["smtp_host"] = f.get("smtp_host", "").strip()
    cfg["smtp_security"] = f.get("smtp_security") if f.get("smtp_security") in SECURITES else "none"
    cfg["smtp_user"] = f.get("smtp_user", "").strip()
    if f.get("clear_password"):
        cfg["smtp_password"] = ""
    elif f.get("smtp_password"):
        cfg["smtp_password"] = f["smtp_password"]
    cfg["smtp_from"] = f.get("smtp_from", "").strip()
    cfg["smtp_verify"] = "1" if f.get("smtp_verify") else "0"
    cfg["mail_requesters"] = "1" if f.get("mail_requesters") else "0"
    cfg["mail_staff"] = "1" if f.get("mail_staff") else "0"
    cfg["app_url"] = f.get("app_url", "").strip().rstrip("/")
    port = f.get("smtp_port", "").strip()
    if port.isdigit() and 1 <= int(port) <= 65535:
        cfg["smtp_port"] = port
    else:
        errors.append("Le port doit être un nombre entre 1 et 65535.")
    if cfg["email_enabled"] == "1" and not cfg["smtp_host"]:
        errors.append("Indiquez l'adresse du serveur SMTP pour activer l'envoi d'emails.")
    if cfg["email_enabled"] == "1" and "@" not in cfg["smtp_from"]:
        errors.append("L'adresse d'expédition doit être une adresse email valide (ex. support-it@entreprise.local).")
    if cfg["smtp_user"] and not cfg["smtp_password"]:
        errors.append("Un identifiant est renseigné mais aucun mot de passe n'est enregistré.")
    if cfg["app_url"] and not cfg["app_url"].startswith(("http://", "https://")):
        errors.append("L'adresse de l'application doit commencer par http:// ou https://.")
    return cfg, errors


def sec_email():
    saved = get_settings()
    if request.method == "POST":
        f = request.form
        cfg, errors = _email_form_to_cfg(f, saved)
        if f.get("action") == "test":
            to = f.get("test_to", "").strip()
            if "@" not in to:
                flash("Saisissez l'adresse email qui doit recevoir le message de test.", "error")
            elif not cfg["smtp_host"] or "@" not in cfg["smtp_from"] or not cfg["smtp_port"].isdigit():
                flash("Renseignez au moins le serveur, le port et l'adresse d'expédition avant de tester.", "error")
            else:
                try:
                    smtp_send(cfg, to, f"Test d'envoi - {cfg['app_name']}",
                              "Ce message confirme que la configuration email de l'application Tickets IT fonctionne.")
                    flash(f"Email de test envoyé à {to}. Pensez à enregistrer si les paramètres vous conviennent.", "ok")
                except Exception as e:
                    flash("Échec de l'envoi : " + smtp_error_text(e), "error")
            return render_settings("admin_settings/email.html", "email", cfg=cfg, securites=SECURITES, test_to=to)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_settings("admin_settings/email.html", "email", cfg=cfg, securites=SECURITES, test_to=""), 400
        save_settings({k: cfg[k] for k in EMAIL_KEYS})
        flash("Paramètres enregistrés." + (" L'envoi d'emails est activé." if email_enabled() else " L'envoi d'emails est désactivé."), "ok")
        return redirect(url_for("settings_page"))
    return render_settings("admin_settings/email.html", "email", cfg=saved, securites=SECURITES, test_to=g.user["email"] or "")


EMAIL_KEYS = ["email_enabled", "smtp_host", "smtp_port", "smtp_security", "smtp_user", "smtp_password", "smtp_from",
              "smtp_verify", "app_url", "mail_requesters", "mail_staff"]
