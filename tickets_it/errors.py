"""Pages d'erreur."""
from flask import render_template

from .extensions import app
from .settings_store import derived


# PAGES D'ERREUR
@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
@app.errorhandler(413)
def error_page(e):
    D = derived()
    msgs = {403: "Vous n'avez pas le droit d'accéder à cette page.", 404: "Cette page n'existe pas.",
            413: f"Envoi trop volumineux : {D.max_files} fichiers de {D.max_mo} Mo maximum."}
    custom, default = getattr(e, "description", ""), getattr(type(e), "description", "")
    msg = custom if custom and custom != default else msgs.get(e.code, custom)
    return render_template("error.html", code=e.code, msg=msg), e.code
