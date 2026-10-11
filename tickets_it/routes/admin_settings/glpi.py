"""Paramètres : liaison avec GLPI 10 (envoi de tickets, à la demande)."""
import json

from flask import flash, redirect, request, url_for

from ... import glpi
from ...settings_store import derived, get_settings, save_settings
from .common import render_settings

GLPI_KEYS = ["glpi_enabled", "glpi_url", "glpi_app_token", "glpi_user_token", "glpi_verify", "glpi_type",
             "glpi_entity", "glpi_request_type", "glpi_categories", "glpi_urgences"]


def _form_to_cfg(f, saved):
    """Convertit le formulaire en configuration ; retourne (cfg, erreurs)."""
    cfg, errors = dict(saved), []
    cfg["glpi_enabled"] = "1" if f.get("glpi_enabled") else "0"
    cfg["glpi_url"] = f.get("glpi_url", "").strip().rstrip("/")
    for key, clear in (("glpi_app_token", "clear_app"), ("glpi_user_token", "clear_user")):
        if f.get(clear):
            cfg[key] = ""
        elif f.get(key, "").strip():
            cfg[key] = f[key].strip()
    cfg["glpi_verify"] = "1" if f.get("glpi_verify") else "0"
    cfg["glpi_type"] = f.get("glpi_type") if f.get("glpi_type") in glpi.TYPES else "1"
    for key, label in (("glpi_entity", "L'entité"), ("glpi_request_type", "La source de la demande")):
        v = f.get(key, "").strip()
        if v and not v.isdigit():
            errors.append(f"{label} GLPI doit être un numéro (ou rester vide).")
        else:
            cfg[key] = v
    cats, urg, i = {}, {}, 0
    while f"cat_name_{i}" in f or f"urg_name_{i}" in f:
        name, v = f.get(f"cat_name_{i}"), f.get(f"cat_{i}", "").strip()
        if name is not None and v:
            if v.isdigit() and int(v) > 0:
                cats[name] = int(v)
            else:
                errors.append(f"Catégorie GLPI de « {name} » : saisissez un numéro (voir la liste ci-dessous).")
        pname, u = f.get(f"urg_name_{i}"), f.get(f"urg_{i}", "")
        if pname is not None and u.isdigit() and int(u) in glpi.URGENCES:
            urg[pname] = int(u)
        i += 1
    cfg["glpi_categories"] = json.dumps(cats, ensure_ascii=False)
    cfg["glpi_urgences"] = json.dumps(urg, ensure_ascii=False)
    if cfg["glpi_url"] and not cfg["glpi_url"].startswith(("http://", "https://")):
        errors.append("L'adresse de GLPI doit commencer par http:// ou https://.")
    if cfg["glpi_enabled"] == "1":
        if not cfg["glpi_url"]:
            errors.append("Indiquez l'adresse de GLPI pour activer l'envoi.")
        if not cfg["glpi_app_token"] or not cfg["glpi_user_token"]:
            errors.append("Renseignez le jeton d'application et le jeton utilisateur de GLPI pour activer l'envoi.")
    return cfg, errors


def _render(cfg, found=None, status=200):
    D = derived()
    cats, urg = glpi.json_dict(cfg["glpi_categories"]), glpi.urgences(cfg)
    return render_settings("admin_settings/glpi.html", "glpi", cfg=cfg, types=glpi.TYPES, urgences=glpi.URGENCES,
                           cats=[{"i": i, "name": n, "value": cats.get(n, "")} for i, n in enumerate(D.cat_names)],
                           prios=[{"i": i, "name": n, "value": urg.get(n, 3)} for i, n in enumerate(D.prio_names)],
                           found=found or [], web=glpi.web_url(cfg) if cfg["glpi_url"].strip() else ""), status


def sec_glpi():
    saved = get_settings()
    if request.method == "POST":
        f = request.form
        cfg, errors = _form_to_cfg(f, saved)
        if f.get("action") == "test":
            if not cfg["glpi_url"].strip() or not cfg["glpi_app_token"] or not cfg["glpi_user_token"]:
                flash("Renseignez l'adresse de GLPI et les deux jetons avant de tester.", "error")
                return _render(cfg)
            try:
                info, found = glpi.test_connection(cfg)
                flash(info + " Pensez à enregistrer si les paramètres vous conviennent.", "ok")
                return _render(cfg, found)
            except glpi.GlpiError as e:
                flash("Échec du test : " + str(e), "error")
                return _render(cfg)
        if errors:
            for e in errors:
                flash(e, "error")
            return _render(cfg, status=400)
        save_settings({k: cfg[k] for k in GLPI_KEYS})
        flash("Paramètres GLPI enregistrés." + (" L'envoi vers GLPI est activé." if glpi.glpi_enabled() else " L'envoi vers GLPI est désactivé."), "ok")
        return redirect(url_for("settings_page", section="glpi"))
    return _render(saved)
