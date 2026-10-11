"""Paramètres : nom, couleur, logo, message d'accueil."""
import os
import re
import secrets
from flask import abort, flash, redirect, request, send_file, url_for

from ...branding import _remove_logo_file, contrast_white, logo_ext, valid_brand
from ...config import BRAND_DEFAUT, LOGO_MAX, NOM_DEFAUT, UPLOAD_DIR
from ...extensions import app
from ...routes.admin_settings.common import render_settings
from ...settings_store import get_settings, save_settings


@app.route("/logo")
def logo():
    name = get_settings()["logo"]
    m = re.fullmatch(r"logo-[0-9a-f]{16}\.(png|jpg|gif|webp)", name or "")
    path = os.path.join(UPLOAD_DIR, name) if m else ""
    if not m or not os.path.isfile(path):
        abort(404)
    ext = "jpeg" if m.group(1) == "jpg" else m.group(1)
    resp = send_file(path, mimetype=f"image/{ext}", max_age=3600)
    resp.headers["Content-Security-Policy"] = "default-src 'none'; sandbox"
    return resp


def sec_apparence():
    cfg = get_settings()
    if request.method == "POST":
        f, errors = request.form, []
        name, brand, welcome = f.get("app_name", "").strip(), f.get("brand", "").strip().lower(), f.get("welcome", "").strip()
        if f.get("reset"):
            name, brand, welcome = NOM_DEFAUT, BRAND_DEFAUT, ""
        if not name or len(name) > 60:
            errors.append("Le nom de l'application est obligatoire (60 caractères maximum).")
        if not valid_brand(brand):
            errors.append("La couleur doit être au format #RRGGBB (ex. #0b5c7a).")
        elif contrast_white(brand) < 4.5:
            errors.append("Cette couleur est trop claire : le texte blanc des boutons et du menu ne serait pas assez lisible. Choisissez une teinte plus foncée.")
        if len(welcome) > 600:
            errors.append("Le message d'accueil est limité à 600 caractères.")
        new_logo, up = None, request.files.get("logo")
        if up and up.filename and not f.get("reset"):
            data = up.read(LOGO_MAX + 1)
            ext = logo_ext(data)
            if len(data) > LOGO_MAX:
                errors.append("Le logo dépasse 512 Ko.")
            elif not ext:
                errors.append("Format de logo non reconnu (PNG, JPEG, GIF ou WebP).")
            else:
                new_logo = (data, ext)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_settings("admin_settings/apparence.html", "apparence", cfg=dict(cfg, app_name=name, brand=brand, welcome=welcome)), 400
        logo_name = cfg["logo"]
        if f.get("reset") or f.get("remove_logo") or new_logo:
            _remove_logo_file(logo_name)
            logo_name = ""
        if new_logo:
            logo_name = f"logo-{secrets.token_hex(8)}.{new_logo[1]}"
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            with open(os.path.join(UPLOAD_DIR, logo_name), "wb") as fh:
                fh.write(new_logo[0])
        save_settings({"app_name": name, "brand": brand, "welcome": welcome, "logo": logo_name})
        flash("Apparence enregistrée.", "ok")
        return redirect(url_for("settings_page", section="apparence"))
    return render_settings("admin_settings/apparence.html", "apparence", cfg=cfg)
