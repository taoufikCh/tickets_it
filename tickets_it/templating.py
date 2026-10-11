"""Filtres Jinja, variables communes à tous les gabarits."""
import unicodedata
from datetime import date
from flask import g, url_for

from .branding import darken, valid_brand
from .config import BRAND_DEFAUT, JOURS_NOMS, NOM_DEFAUT
from .db import get_db, parse_dt
from .extensions import app
from .jobs import freq_label
from .services import due_badge
from .settings_store import derived, get_settings, prio_cls
from .sla import sla_state


# --- Filtres et fonctions d'affichage ------------------------------------------
@app.template_filter("dt")
def fmt_dt(s):
    try:
        return parse_dt(s).strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return s or ""


@app.template_filter("slug")
def slug(s):
    s = unicodedata.normalize("NFD", (s or "").lower())
    return "".join(ch for ch in s if unicodedata.category(ch) != "Mn").replace(" ", "-")


@app.template_filter("fsize")
def fsize(n):
    return f"{round(n / 1024)} Ko" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} Mo".replace(".", ",")


@app.template_filter("hfmt")
def hfmt(h):
    if h is None:
        return "–"
    if h < 1:
        return f"{round(h * 60)} min"
    return f"{h:.1f} h".replace(".", ",") if h < 48 else f"{h / 24:.1f} j".replace(".", ",")


def work_text(D):
    fm = lambda m: f"{m // 60}h{m % 60:02d}"
    days = sorted(D.days)
    if len(days) > 1 and days == list(range(days[0], days[-1] + 1)):
        dtxt = f"du {JOURS_NOMS[days[0]]} au {JOURS_NOMS[days[-1]]}"
    else:
        dtxt = ", ".join(JOURS_NOMS[d] for d in days)
    return f"{fm(D.work_start)}–{fm(D.work_end)}, {dtxt}, hors jours fériés" if (D.holidays or D.holidays_yearly) else f"{fm(D.work_start)}–{fm(D.work_end)}, {dtxt}"


@app.context_processor
def common_context():
    D = derived()
    cfg = get_settings()
    brand = cfg["brand"] if valid_brand(cfg["brand"]) else BRAND_DEFAUT
    ctx = {"prio_cls": prio_cls, "prio_default": D.prio_default, "services": D.services, "bureaux": D.bureaux, "channels": D.channels,
           "sla_heures": D.sla, "work_txt": work_text(D), "app_name": cfg["app_name"] or NOM_DEFAUT, "brand": brand,
           "brand_dark": darken(brand), "welcome": cfg["welcome"], "max_mo": D.max_mo, "max_files": D.max_files,
           "upload_accept": D.upload_accept, "logo_url": url_for("logo", v=cfg["logo"]) if cfg["logo"] else ""}
    if g.get("user") is not None:
        db = get_db()
        ctx["nav"] = {
            "tickets": db.execute("SELECT COUNT(*) FROM tickets WHERE status='Nouveau'").fetchone()[0],
            "projets": db.execute("SELECT COUNT(*) FROM projects WHERE status='Proposé'").fetchone()[0],
            "taches": db.execute("SELECT COUNT(*) FROM tasks WHERE done=0 AND assignee_id=? AND due_date<>'' AND due_date<?",
                                 (g.user["id"], date.today().isoformat())).fetchone()[0]}
    return ctx


@app.template_filter("num")
def num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return str(int(f)) if f == int(f) else f"{f:g}".replace(".", ",")


app.jinja_env.globals.update(
    sla=sla_state, freq_label=freq_label, due_badge=due_badge)
