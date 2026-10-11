"""Paramètres : catégories, priorités, services, bureaux, sources de demande."""
import json
from flask import flash, redirect, request, url_for

from ...db import raw_db
from ...routes.admin_settings.common import _count_use, apply_renames, parse_lines, parse_named_rows, render_settings
from ...settings_store import derived, save_settings


# --- Listes : catégories, priorités, services, bureaux -------------------------
def sec_listes():
    db, D = raw_db(), derived()
    try:
        if request.method == "POST":
            f, errors = request.form, []
            cats = parse_named_rows(f, "cat", "category", db, errors, "Catégories", with_active=True)
            pris = parse_named_rows(f, "pri", "priority", db, errors, "Priorités", maxlen=30)
            services = parse_lines(f.get("services", ""))
            bureaux = parse_lines(f.get("bureaux", ""))
            canaux = parse_lines(f.get("canaux", ""))
            if not canaux:
                errors.append("Il faut au moins une source de demande (téléphone, email…).")
            for kind_, col_, rows_, names_ in (("catégorie", "category", cats, D.cat_names), ("priorité", "priority", pris, D.prio_names)):
                kept = {r["orig"] for r in rows_}
                for n_ in names_:   # élément retiré du formulaire : même contrôle qu'une suppression
                    if n_ not in kept and _count_use(db, col_, n_):
                        errors.append(f"La {kind_} « {n_} » est utilisée : impossible de la supprimer.")
            if not cats or not any(r["active"] for r in cats):
                errors.append("Il faut au moins une catégorie active.")
            if not 1 <= len(pris) <= 8:
                errors.append("Il faut entre 1 et 8 priorités.")
            if not errors:
                renames_c = {r["orig"]: r["name"] for r in cats if r["orig"]}
                renames_p = {r["orig"]: r["name"] for r in pris if r["orig"]}
                apply_renames(db, renames_c, [("tickets", "category"), ("recurring", "category")])
                apply_renames(db, renames_p, [("tickets", "priority"), ("recurring", "priority")])
                db.commit()
                save_settings({
                    "categories": json.dumps([{"name": r["name"], "active": r["active"]} for r in cats], ensure_ascii=False),
                    "priorites": json.dumps([{"name": r["name"], "sla": D.sla.get(r["orig"], 24) if r["orig"] else 24}
                                             for r in pris], ensure_ascii=False),
                    "services": json.dumps(services, ensure_ascii=False),
                    "bureaux": json.dumps(bureaux, ensure_ascii=False),
                    "canaux": json.dumps(canaux, ensure_ascii=False)})
                flash("Listes enregistrées. Les tickets existants ont été mis à jour en cas de renommage.", "ok")
                return redirect(url_for("settings_page", section="listes"))
            for e in dict.fromkeys(errors):
                flash(e, "error")
            return render_settings("admin_settings/listes.html", "listes", cats=cats, pris=pris, services="\n".join(services),
                                   bureaux="\n".join(bureaux), canaux="\n".join(canaux), cat_next=max([r["i"] for r in cats] + [0]) + 1,
                                   pri_next=max([r["i"] for r in pris] + [0]) + 1), 400
        cats = [{"i": i, "name": c["name"], "orig": c["name"], "active": c["active"], "used": _count_use(db, "category", c["name"])}
                for i, c in enumerate(D.cats)]
        pris = [{"i": i, "name": p["name"], "orig": p["name"], "used": _count_use(db, "priority", p["name"])}
                for i, p in enumerate(D.prios)]
        return render_settings("admin_settings/listes.html", "listes", cats=cats, pris=pris, services="\n".join(D.services),
                               bureaux="\n".join(D.bureaux), canaux="\n".join(D.channels), cat_next=len(cats), pri_next=len(pris))
    finally:
        db.close()
