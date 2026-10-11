"""Paramètres : notifications, rappels, textes des emails."""
import re
from flask import flash, g, redirect, request, url_for

from ...config import MAIL_TEMPLATES
from ...db import get_db
from ...jobs import build_digest
from ...mail import email_enabled, smtp_error_text, smtp_send
from ...routes.admin_settings.common import render_settings
from ...settings_store import derived, get_settings, save_settings


# --- Paramètres → Notifications ------------------------------------------------
def sec_notifications():
    D, cfg = derived(), get_settings()
    if request.method == "POST":
        f, errors, vals = request.form, [], {}
        if f.get("action") == "test_digest":
            if not g.user["email"]:
                flash("Renseignez d'abord votre adresse email dans « Mon compte ».", "error")
            elif not email_enabled():
                flash("L'envoi d'emails est désactivé (onglet Email).", "error")
            else:
                d = build_digest(get_db(), g.user)
                if d is None:
                    flash("Rien à signaler aujourd'hui : un résumé n'est envoyé que s'il y a du contenu.", "ok")
                else:
                    try:
                        smtp_send(cfg, g.user["email"], d[0], d[1])
                        flash(f"Résumé de test envoyé à {g.user['email']}.", "ok")
                    except Exception as e:
                        flash("Échec de l'envoi : " + smtp_error_text(e), "error")
            return redirect(url_for("settings_page", section="notifications"))
        sig = f.get("mail_signature", "").strip()
        if not sig or len(sig) > 200:
            errors.append("La signature est obligatoire (200 caractères maximum).")
        vals["mail_signature"] = sig
        try:
            hour = int(f.get("digest_hour", ""))
            soon = float(f.get("remind_soon", "0").replace(",", ".") or 0)
            if not (0 <= hour <= 23 and 0 <= soon <= 72):
                raise ValueError
        except ValueError:
            errors.append("Heure du résumé : entre 0 et 23 ; rappel avant échéance : entre 0 et 72 heures.")
            hour, soon = D.digest_hour, D.remind_soon
        vals.update(digest_on="1" if f.get("digest_on") else "0", digest_hour=str(hour), remind_soon=f"{soon:g}",
                    remind_late="1" if f.get("remind_late") else "0")
        shown = []
        for key, t in MAIL_TEMPLATES.items():
            subj, body = f.get(f"tpl_{key}_subject", "").strip(), f.get(f"tpl_{key}_body", "").strip()
            if f.get(f"tpl_{key}_reset"):
                subj, body = t["subject"], t["body"]
            ok = True
            if not subj or not body or len(subj) > 200 or len(body) > 5000:
                errors.append(f"« {t['label']} » : objet et texte obligatoires (objet 200 car., texte 5000 car. maximum).")
                ok = False
            unknown = {x for x in re.findall(r"\{(\w+)\}", subj + body)} - set(t["vars"]) - {"signature"}
            if unknown:
                errors.append(f"« {t['label']} » : variable(s) inconnue(s) " + ", ".join("{" + x + "}" for x in sorted(unknown)) + ".")
                ok = False
            shown.append((key, {**t, "subject": subj, "body": body, "custom": subj != t["subject"] or body != t["body"]}))
            vals[f"tpl.{key}.subject"] = "" if subj == t["subject"] else subj
            vals[f"tpl.{key}.body"] = "" if body == t["body"] else body
        if errors:
            for e in dict.fromkeys(errors):
                flash(e, "error")
            return render_settings("admin_settings/notifications.html", "notifications", v=dict(cfg, **{k: vals[k] for k in vals if not k.startswith("tpl.")}),
                                   templates=shown, email_on=email_enabled(), has_url=bool(cfg["app_url"].strip())), 400
        save_settings(vals)
        msg = "Notifications enregistrées."
        if (vals["digest_on"] == "1" or vals["remind_late"] == "1" or soon > 0) and not cfg["app_url"].strip():
            msg += " Pensez à renseigner l'adresse de l'application (onglet Email) : sans elle, les liens des emails automatiques ne seront pas cliquables."
        flash(msg, "ok")
        return redirect(url_for("settings_page", section="notifications"))
    shown = []
    for key, t in MAIL_TEMPLATES.items():
        subj, body = cfg.get(f"tpl.{key}.subject") or t["subject"], cfg.get(f"tpl.{key}.body") or t["body"]
        shown.append((key, {**t, "subject": subj, "body": body, "custom": subj != t["subject"] or body != t["body"]}))
    return render_settings("admin_settings/notifications.html", "notifications", v=cfg, templates=shown, email_on=email_enabled(),
                           has_url=bool(cfg["app_url"].strip()))
