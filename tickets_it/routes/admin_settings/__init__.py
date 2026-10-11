"""Paramètres de l'application (administrateur) : un onglet par thème."""
from flask import abort

from ...extensions import app
from ...security import login_required
from .common import SETTINGS_TABS, SECTION_HANDLERS
from .email import sec_email
from .notifications import sec_notifications
from .glpi import sec_glpi
from .listes import sec_listes
from .delais import sec_delais
from .apparence import sec_apparence
from .fichiers import sec_fichiers
from .securite import sec_securite
from .sauvegardes import sec_sauvegardes
from .droits import sec_droits

SETTINGS_TABS[:] = [("email", "Email"),
                ("notifications", "Notifications"),
                ("glpi", "GLPI"),
                ("listes", "Listes"),
                ("delais", "Délais et horaires"),
                ("apparence", "Apparence"),
                ("fichiers", "Pièces jointes"),
                ("securite", "Sécurité"),
                ("sauvegardes", "Sauvegardes"),
                ("droits", "Droits")]
SECTION_HANDLERS.update(email=sec_email, notifications=sec_notifications, glpi=sec_glpi, listes=sec_listes, delais=sec_delais, apparence=sec_apparence, fichiers=sec_fichiers, securite=sec_securite, sauvegardes=sec_sauvegardes, droits=sec_droits)


@app.route("/admin/parametres", defaults={"section": "email"}, methods=["GET", "POST"])
@app.route("/admin/parametres/<section>", methods=["GET", "POST"])
@login_required(role="admin")
def settings_page(section):
    handler = SECTION_HANDLERS.get(section)
    if handler is None:
        abort(404)
    return handler()
