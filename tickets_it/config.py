"""Constantes et valeurs par défaut (modifiables ici ou par variables d'environnement)."""
import json
import os


# Racine du projet (dossier qui contient app.py) : tickets.db, fichiers/ et secret.key y restent.
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


DB_PATH = os.environ.get("TICKETS_DB", os.path.join(BASE_DIR, "tickets.db"))


UPLOAD_DIR = os.environ.get("TICKETS_UPLOADS", os.path.join(BASE_DIR, "fichiers"))


# CONFIGURATION (modifiable ici ou via variables d'environnement)
CATEGORIES_DEFAUT = ["Imprimante", "Réseau / Internet", "Installation logiciel (Office…)",
              "Compte / Mot de passe", "Matériel (PC, écran…)", "Messagerie", "Autre"]


CANAUX_DEFAUT = ["Téléphone", "Email", "Sur place / verbalement", "Courrier", "Autre"]
PRIORITES_DEFAUT = ["Basse", "Normale", "Haute", "Urgente"]


STATUTS = ["Nouveau", "En cours", "En attente", "Résolu", "Clos"]


STATUTS_OUVERTS = ["Nouveau", "En cours", "En attente"]


# Délais cibles (SLA) par priorité, en HEURES OUVRÉES.
SLA_DEFAUT = {"Urgente": 2, "Haute": 8, "Normale": 24, "Basse": 72}


HORAIRES = (8, 18)            # heures d'ouverture du service : de 8h à 18h


JOURS_OUVRES = (0, 1, 2, 3, 4)  # 0 = lundi ... 4 = vendredi


# Pièces jointes
EXT_AUTORISEES = {"png", "jpg", "jpeg", "gif", "webp", "bmp", "pdf", "txt", "log", "csv",
                  "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "zip", "eml", "msg"}


EXT_IMAGES = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
              "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp"}


MAX_FICHIER_MO = 10


MAX_FICHIERS = 5


# Tâches planifiées : heure de création des tickets récurrents
HEURE_TACHES = 8


# Sauvegarde automatique
BACKUP_DIR = os.environ.get("BACKUP_DIR", os.path.join(BASE_DIR, "sauvegardes"))


BACKUP_COPIE = os.environ.get("BACKUP_COPIE", "")   # 2e emplacement (autre disque / partage réseau)


BACKUP_HEURE = int(os.environ.get("BACKUP_HEURE", "2"))    # sauvegarde chaque nuit à partir de 2h


BACKUP_JOURS = int(os.environ.get("BACKUP_JOURS", "14"))   # durée de conservation


# Email (facultatif)
SMTP_HOST = os.environ.get("SMTP_HOST", "")          # ex: "smtp.entreprise.local"


SMTP_PORT = int(os.environ.get("SMTP_PORT", "25"))


SMTP_FROM = os.environ.get("SMTP_FROM", "support-it@entreprise.local")


APP_URL = os.environ.get("APP_URL", "")              # ex: "http://srv-tickets:5000"


REPONSES_PAR_DEFAUT = [
    ("Accusé de réception",
     "Bonjour {nom},\nnous avons bien reçu votre demande (ticket n°{numero}). Un technicien la traite dans les meilleurs délais.\n\n{technicien}"),
    ("Redémarrer l'appareil",
     "Bonjour {nom},\npouvez-vous redémarrer le poste (ou l'appareil concerné), puis nous dire si le problème persiste ?\n\n{technicien}"),
    ("Demande de précisions",
     "Bonjour {nom},\npour avancer, pouvez-vous nous indiquer : le message d'erreur exact (une capture d'écran aide beaucoup), depuis quand le problème existe, et s'il touche d'autres personnes ?\n\n{technicien}"),
    ("Intervention sur place",
     "Bonjour {nom},\nun technicien passera à votre bureau ({lieu}). Merci d'être présent(e) ou de nous indiquer un créneau qui vous convient.\n\n{technicien}"),
    ("Installation planifiée",
     "Bonjour {nom},\nl'installation demandée est planifiée. Merci d'enregistrer vos travaux en cours et de laisser le poste allumé en fin de journée.\n\n{technicien}"),
    ("En attente de votre retour",
     "Bonjour {nom},\nnous attendons votre retour pour poursuivre le traitement de ce ticket. Répondez simplement à ce message lorsque vous êtes disponible.\n\n{technicien}"),
    ("Problème résolu",
     "Bonjour {nom},\nle problème est résolu. S'il réapparaît, répondez simplement à ce message et nous rouvrirons le ticket.\n\nCordialement,\n{technicien}"),
]


DT_FMT = "%Y-%m-%d %H:%M:%S"


# --- Emails et notifications -------------------------------------------------
# --- Paramètres (stockés en base, modifiables depuis l'interface) ---------------
# Les constantes en haut du fichier et les variables d'environnement servent de valeurs initiales.
EXT_CATALOGUE = [
    ("Images", ["png", "jpg", "jpeg", "gif", "webp", "bmp"]),
    ("Documents", ["pdf", "txt", "log", "rtf", "doc", "docx", "odt"]),
    ("Tableurs et présentations", ["csv", "xls", "xlsx", "ods", "ppt", "pptx", "odp"]),
    ("Archives et emails", ["zip", "7z", "eml", "msg"]),
]


EXT_CHOISISSABLES = {e for _g, lst in EXT_CATALOGUE for e in lst}   # jamais d'exécutables, scripts, html, svg


# Jours fériés officiels de Tunisie.
# Dates fixes : se répètent chaque année. Fêtes religieuses : dates PRÉVISIONNELLES (calendrier lunaire),
# à confirmer chaque année à l'annonce officielle de la Présidence du gouvernement.
FERIES_TUNISIE_FIXES = [
    ("01-01", "Jour de l'an"), ("03-20", "Fête de l'Indépendance"), ("04-09", "Journée des Martyrs"),
    ("05-01", "Fête du Travail"), ("07-25", "Fête de la République"), ("08-13", "Fête de la Femme"),
    ("10-15", "Fête de l'Évacuation"), ("12-17", "Fête de la Révolution et de la Jeunesse"),
]
FERIES_TUNISIE_MOBILES = {
    2027: [("2027-03-09", "Aïd el-Fitr (jour 1)"), ("2027-03-10", "Aïd el-Fitr (jour 2)"), ("2027-03-11", "Aïd el-Fitr (jour 3)"),
           ("2027-05-16", "Aïd el-Idha (jour 1)"), ("2027-05-17", "Aïd el-Idha (jour 2)"),
           ("2027-06-06", "Ras el Am el Hijri (Nouvel an hégirien)"), ("2027-08-14", "Mouled (Naissance du Prophète)")],
}


def feries_tunisie(from_year=2026):
    """Liste de jours fériés (format des paramètres) : dates fixes + fêtes religieuses connues à partir de from_year."""
    rows = [{"date": f"{from_year}-{md}", "label": label, "yearly": True} for md, label in FERIES_TUNISIE_FIXES]
    for year, items in sorted(FERIES_TUNISIE_MOBILES.items()):
        if year >= from_year:
            rows += [{"date": d, "label": label, "yearly": False} for d, label in items]
    return rows


SETTINGS_DEFAUTS = {
    # email
    "email_enabled": "1" if SMTP_HOST else "0",
    "smtp_host": SMTP_HOST,
    "smtp_port": str(SMTP_PORT),
    "smtp_security": "none",          # none | starttls | ssl
    "smtp_user": "",
    "smtp_password": "",
    "smtp_from": SMTP_FROM,
    "smtp_verify": "1",               # vérifier le certificat du serveur
    "app_url": APP_URL,
    "mail_requesters": "1",           # confirmations et suivi envoyés aux demandeurs
    "mail_staff": "1",                # alertes envoyées aux techniciens
    # listes
    "categories": json.dumps([{"name": c, "active": True} for c in CATEGORIES_DEFAUT], ensure_ascii=False),
    "priorites": json.dumps([{"name": p, "sla": SLA_DEFAUT[p]} for p in PRIORITES_DEFAUT], ensure_ascii=False),
    "services": "[]",
    "bureaux": "[]",
    "canaux": json.dumps(CANAUX_DEFAUT, ensure_ascii=False),
    # délais et horaires
    "work_start": f"{HORAIRES[0]:02d}:00",
    "work_end": f"{HORAIRES[1]:02d}:00",
    "work_days": ",".join(str(d) for d in JOURS_OUVRES),
    "holidays": json.dumps(feries_tunisie(), ensure_ascii=False),
    # apparence
    "app_name": "Support informatique",
    "brand": "#0b5c7a",
    "welcome": "",
    "logo": "",
    # pièces jointes
    "max_mo": str(MAX_FICHIER_MO),
    "max_files": str(MAX_FICHIERS),
    "extensions": ",".join(sorted(EXT_AUTORISEES)),
    # sécurité
    "session_hours": "0",
    "lock_attempts": "5",
    "lock_minutes": "15",
    "pw_min": "6",
    "pw_mix": "0",
    # sauvegardes
    "backup_auto": "1",
    "backup_hour": str(BACKUP_HEURE),
    "backup_days": str(BACKUP_JOURS),
    "backup_copy": BACKUP_COPIE,
    # droits
    "restrict_edit": "0",
    "restrict_delete": "0",
    # notifications
    "mail_signature": "Service informatique",
    "digest_on": "0",
    "digest_hour": "8",
    "remind_soon": "0",
    "remind_late": "0",
    # GLPI (envoi de tickets vers GLPI 10, API REST)
    "glpi_enabled": "0",
    "glpi_url": "http://localhost/glpi",
    "glpi_app_token": "",
    "glpi_user_token": "",
    "glpi_verify": "1",               # vérifier le certificat HTTPS de GLPI
    "glpi_type": "1",                 # 1 = Incident, 2 = Demande
    "glpi_entity": "",                # vide = entité par défaut du compte GLPI
    "glpi_request_type": "",          # source de la demande GLPI (vide = défaut GLPI)
    "glpi_categories": "{}",          # {catégorie de l'application: id de catégorie GLPI}
    "glpi_urgences": "{}",            # {priorité de l'application: urgence GLPI 1-5}
}


SETTINGS_TTL = 5   # secondes : un réglage modifié par un autre processus est pris en compte au plus tard après ce délai


# --- Tâches planifiées (tickets récurrents) ------------------------------------
FREQUENCES = {"jour_ouvre": "Chaque jour ouvré", "semaine": "Chaque semaine", "mois": "Chaque mois"}


JOURS_NOMS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


# --- Projets et tâches ---------------------------------------------------------
PROJET_STATUTS = ["Proposé", "À faire", "En cours", "Bloqué", "Terminé", "Annulé"]


PROJET_COLONNES = ["Proposé", "À faire", "En cours", "Bloqué", "Terminé"]


PROJET_FINIS = ("Terminé", "Annulé")


PROJET_RESTREINT = {"update", "edit", "accept", "refuse", "link_ticket", "unlink_ticket", "add_task", "delete_task"}


# ESPACE TECHNICIEN : liste, ticket
OUVERTS_SQL = "('Nouveau','En cours','En attente')"


# PARAMÈTRES (administrateur) : un onglet par thème
SECURITES = {"none": "Aucune (port 25 en général)", "starttls": "STARTTLS (port 587 en général)",
             "ssl": "SSL/TLS (port 465 en général)"}


# --- Apparence ---------------------------------------------------------------
LOGO_MAX = 512 * 1024


BRAND_DEFAUT = "#0b5c7a"


NOM_DEFAUT = "Support informatique"


# --- Connexion : verrouillage, politique de mot de passe, droits -----------------
ROLES = {"admin": "Administrateur", "tech": "Technicien", "lecteur": "Lecteur (lecture seule)"}


LECTEUR_AUTORISE = {"logout", "account", "login", "nouveau", "suivi", "projet_suivi"}


# --- Textes des emails (personnalisables dans Paramètres → Notifications) -------
SIG_DEFAUT = "Service informatique"


MAIL_TEMPLATES = {
    "ticket_created": {
        "label": "Confirmation de création d'un ticket", "to": "demandeur",
        "subject": "[Ticket #{numero}] {titre}",
        "body": "Bonjour {nom},\n\nVotre demande a bien été enregistrée sous le numéro #{numero}.\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "lien"]},
    "ticket_status": {
        "label": "Changement de statut d'un ticket", "to": "demandeur",
        "subject": "[Ticket #{numero}] Statut : {statut}",
        "body": "Bonjour {nom},\n\nVotre ticket « {titre} » est passé au statut « {statut} ».\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "statut", "lien"]},
    "ticket_reply": {
        "label": "Réponse d'un technicien sur un ticket", "to": "demandeur",
        "subject": "[Ticket #{numero}] Nouvelle réponse",
        "body": "{technicien} a répondu à votre ticket « {titre} » :\n\n{message}\n\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "technicien", "message", "lien"]},
    "ticket_to_project": {
        "label": "Ticket transformé en projet", "to": "demandeur",
        "subject": "[Ticket #{numero}] Devenu le projet #{projet}",
        "body": "Bonjour {nom},\n\nVotre demande « {titre} » demande un travail plus long : elle est suivie désormais comme un projet.\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "projet", "lien"]},
    "project_created": {
        "label": "Confirmation d'une demande de projet", "to": "demandeur",
        "subject": "[Projet #{numero}] {titre}",
        "body": "Bonjour {nom},\n\nVotre demande de projet a bien été enregistrée sous le numéro #{numero}. Un technicien l'étudiera et vous répondra.\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "lien"]},
    "project_update": {
        "label": "Suivi d'un projet (statut, acceptation, refus, message)", "to": "demandeur",
        "subject": "[Projet #{numero}] {objet}",
        "body": "Bonjour {nom},\n\n{texte}\n\nSuivi : {lien}\n\n{signature}",
        "vars": ["nom", "numero", "titre", "objet", "texte", "lien"]},
    "staff_ticket": {
        "label": "Alerte : nouveau ticket", "to": "technicien",
        "subject": "[Nouveau ticket #{numero}] {urgence}{titre}",
        "body": "Nouveau ticket #{numero}\n\nSujet : {titre}\nDemandeur : {demandeur}\nCatégorie : {categorie}\nPriorité : {priorite}\n\nOuvrir le ticket : {lien}",
        "vars": ["numero", "titre", "demandeur", "categorie", "priorite", "urgence", "lien"]},
    "staff_project": {
        "label": "Alerte : nouvelle demande de projet", "to": "technicien",
        "subject": "[Demande de projet #{numero}] {titre}",
        "body": "Nouvelle demande de projet à valider\n\nSujet : {titre}\nDemandeur : {demandeur}{service}\n\nOuvrir : {lien}",
        "vars": ["numero", "titre", "demandeur", "service", "lien"]},
    "reminder_soon": {
        "label": "Rappel : échéance d'un ticket proche", "to": "technicien",
        "subject": "[Ticket #{numero}] Échéance proche : {titre}",
        "body": "Le ticket #{numero} « {titre} » arrive à échéance le {echeance}.\nPriorité : {priorite} · Demandeur : {demandeur}\n\nOuvrir le ticket : {lien}",
        "vars": ["numero", "titre", "priorite", "demandeur", "echeance", "lien"]},
    "reminder_late": {
        "label": "Rappel : ticket en retard", "to": "technicien",
        "subject": "[Ticket #{numero}] EN RETARD : {titre}",
        "body": "Le ticket #{numero} « {titre} » a dépassé son échéance ({echeance}).\nPriorité : {priorite} · Demandeur : {demandeur}\n\nOuvrir le ticket : {lien}",
        "vars": ["numero", "titre", "priorite", "demandeur", "echeance", "lien"]},
}
