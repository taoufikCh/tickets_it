"""Envoi de tickets vers GLPI 10 (API REST historique « apirest.php »).

Sens unique : Tickets IT -> GLPI, ticket par ticket, à la demande du technicien.
Aucune dépendance : uniquement la bibliothèque standard (urllib).
"""
import json
import socket
import ssl
import threading
import urllib.error
import urllib.request

from .db import now
from .settings_store import get_settings

URGENCES = {1: "Très basse", 2: "Basse", 3: "Moyenne", 4: "Haute", 5: "Très haute"}
TYPES = {"1": "Incident", "2": "Demande"}
TIMEOUT = 10  # secondes

# Un seul envoi à la fois : évite le doublon en cas de double clic.
_send_lock = threading.Lock()


class GlpiError(Exception):
    """Erreur lisible par l'utilisateur (message en français)."""


# --- Réglages ----------------------------------------------------------------------
def api_url(cfg):
    """Adresse de l'API : accepte l'adresse de GLPI (http://serveur/glpi) ou celle de apirest.php."""
    u = cfg.get("glpi_url", "").strip().rstrip("/")
    return u if u.endswith("/apirest.php") else u + "/apirest.php"


def web_url(cfg):
    """Adresse de l'interface web de GLPI (sans apirest.php)."""
    u = api_url(cfg)
    return u[: -len("/apirest.php")]


def ticket_link(cfg, glpi_id):
    return f"{web_url(cfg)}/front/ticket.form.php?id={int(glpi_id)}"


def configured(cfg):
    return bool(cfg.get("glpi_url", "").strip() and cfg.get("glpi_app_token") and cfg.get("glpi_user_token"))


def glpi_enabled(cfg=None):
    cfg = cfg or get_settings()
    return cfg.get("glpi_enabled") == "1" and configured(cfg)


def default_urgences(prio_names):
    """Répartit les priorités de l'application sur les urgences GLPI 2 (basse) à 5 (très haute)."""
    n = len(prio_names)
    return {p: (3 if n == 1 else round(2 + i * 3 / (n - 1))) for i, p in enumerate(prio_names)}


def urgences(cfg):
    """Urgence GLPI de chaque priorité : réglage enregistré, sinon répartition automatique."""
    from .settings_store import derived
    names = derived().prio_names
    out = default_urgences(names)
    for k, v in json_dict(cfg.get("glpi_urgences")).items():
        if k in out and v in URGENCES:
            out[k] = v
    return out


def json_dict(raw):
    try:
        v = json.loads(raw)
        return v if isinstance(v, dict) else {}
    except (TypeError, ValueError):
        return {}


# --- Appels HTTP -------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Une redirection transformerait le POST en GET : on préfère signaler l'erreur."""

    def redirect_request(self, *a, **kw):
        return None


_ERREURS = {
    "ERROR_GLPI_LOGIN": "GLPI a refusé le jeton utilisateur (jeton incorrect, ou compte désactivé).",
    "ERROR_WRONG_APP_TOKEN_PARAMETER": "GLPI a refusé le jeton d'application (jeton incorrect).",
    "ERROR_APP_TOKEN_PARAMETERS_MISSING": "GLPI exige un jeton d'application : renseignez-le dans les paramètres.",
    "ERROR_RIGHT_MISSING": "Le compte GLPI utilisé n'a pas le droit de faire cette action (vérifiez son profil).",
    "ERROR_LOGIN_PARAMETERS_MISSING": "Jeton utilisateur manquant.",
}


def _http_message(code, body, location=""):
    if code in (301, 302, 303, 307, 308):
        return (f"GLPI redirige la demande vers « {location} ». Utilisez cette adresse dans le champ « Adresse de GLPI »"
                " (par exemple en https://) puis recommencez.")
    if code == 404:
        return "Adresse introuvable (404) : vérifiez l'adresse de GLPI et que l'API REST y est activée."
    err_code = err_msg = ""
    try:
        data = json.loads(body)
        if isinstance(data, list) and data:
            err_code, err_msg = str(data[0]), str(data[1]) if len(data) > 1 else ""
    except ValueError:
        pass
    if err_code in _ERREURS:
        return _ERREURS[err_code]
    if err_code:
        return f"GLPI a répondu « {err_code} » ({err_msg[:200]})."
    return f"GLPI a répondu une erreur HTTP {code}."


def _call(cfg, method, path, body=None, session=None):
    url = api_url(cfg) + "/" + path
    headers = {"App-Token": cfg["glpi_app_token"], "Accept": "application/json"}
    if session:
        headers["Session-Token"] = session
    else:
        headers["Authorization"] = "user_token " + cfg["glpi_user_token"]
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    ctx = None
    if url.startswith("https://"):
        ctx = ssl.create_default_context()
        if cfg.get("glpi_verify") != "1":
            ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    try:
        with opener.open(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raise GlpiError(_http_message(e.code, e.read().decode("utf-8", "replace"), e.headers.get("Location", ""))) from None
    except (socket.timeout, TimeoutError):
        raise GlpiError("GLPI ne répond pas (délai de %d s dépassé)." % TIMEOUT) from None
    except urllib.error.URLError as e:
        reason = e.reason
        if isinstance(reason, (socket.timeout, TimeoutError)):
            raise GlpiError("GLPI ne répond pas (délai de %d s dépassé)." % TIMEOUT) from None
        if isinstance(reason, ssl.SSLError):
            raise GlpiError("Certificat HTTPS de GLPI refusé : décochez « Vérifier le certificat » s'il est auto-signé.") from None
        raise GlpiError(f"GLPI est injoignable à l'adresse {web_url(cfg)} ({reason}). Vérifiez qu'il est démarré.") from None
    except (OSError, ValueError) as e:
        raise GlpiError(f"Échec de la connexion à GLPI ({e}).") from None
    try:
        return json.loads(raw) if raw.strip() else {}
    except ValueError:
        raise GlpiError("Réponse inattendue de GLPI : l'adresse pointe-t-elle bien vers GLPI ?") from None


class _Session:
    """Session GLPI ouverte puis toujours fermée (initSession / killSession)."""

    def __init__(self, cfg):
        self.cfg, self.token = cfg, None

    def __enter__(self):
        r = _call(self.cfg, "GET", "initSession")
        self.token = r.get("session_token") if isinstance(r, dict) else None
        if not self.token:
            raise GlpiError("GLPI n'a pas ouvert de session : vérifiez l'adresse et les jetons.")
        return self

    def __exit__(self, *exc):
        try:
            _call(self.cfg, "GET", "killSession", session=self.token)
        except GlpiError:
            pass
        return False

    def call(self, method, path, body=None):
        return _call(self.cfg, method, path, body, session=self.token)


# --- Fonctions utilisées par l'application -----------------------------------------
def test_connection(cfg):
    """Ouvre une session. Retourne (description de la connexion, catégories GLPI [(id, nom)])."""
    with _Session(cfg) as s:
        info, cats = "Connexion à GLPI réussie.", []
        try:
            sess = s.call("GET", "getFullSession").get("session", {})
            who, ent = sess.get("glpiname"), sess.get("glpiactive_entity_name")
            if who:
                info = f"Connexion à GLPI réussie (compte « {who} »" + (f", entité « {ent} »)." if ent else ").")
        except (GlpiError, AttributeError):
            pass
        try:
            rows = s.call("GET", "ITILCategory?range=0-299&only_id=false")
            cats = [(int(c["id"]), str(c.get("completename") or c.get("name") or "")) for c in rows
                    if isinstance(c, dict) and str(c.get("id", "")).isdigit()]
        except (GlpiError, TypeError):
            pass
    return info, cats


def _content(t, cfg_app_link):
    lines = [t["description"].strip(), "", "---", f"Envoyé depuis Tickets IT (ticket n° {t['id']})",
             f"Demandeur : {t['requester_name']}" + (f" <{t['requester_email']}>" if t["requester_email"] else "")]
    if t["department"]:
        lines.append(f"Service : {t['department']}")
    if t["location"]:
        lines.append(f"Lieu : {t['location']}")
    lines.append(f"Catégorie : {t['category']} · Priorité : {t['priority']}")
    if t["channel"]:
        lines.append(f"Source de la demande : {t['channel']}")
    if cfg_app_link:
        lines.append(f"Suivi dans Tickets IT : {cfg_app_link}")
    return "\n".join(lines)


def build_input(t, cfg, urgences, app_link=""):
    """Corps JSON du ticket GLPI."""
    urg = urgences.get(t["priority"])
    urg = urg if urg in URGENCES else default_urgences([t["priority"]])[t["priority"]]
    inp = {"name": t["title"][:255], "content": _content(t, app_link), "type": int(cfg["glpi_type"]) if cfg["glpi_type"] in TYPES else 1,
           "urgency": urg, "impact": urg}
    cat = json_dict(cfg.get("glpi_categories")).get(t["category"])
    if str(cat or "").isdigit() and int(cat) > 0:
        inp["itilcategories_id"] = int(cat)
    if str(cfg.get("glpi_entity", "")).isdigit():
        inp["entities_id"] = int(cfg["glpi_entity"])
    if str(cfg.get("glpi_request_type", "")).isdigit() and int(cfg["glpi_request_type"]) > 0:
        inp["requesttypes_id"] = int(cfg["glpi_request_type"])
    return {"input": inp}


def send_ticket(db, tid, app_link=""):
    """Crée le ticket dans GLPI et mémorise son numéro. Retourne (numéro GLPI, déjà_envoyé).

    Lève GlpiError ; l'erreur est alors mémorisée sur le ticket pour être affichée.
    """
    cfg = get_settings()
    if not glpi_enabled(cfg):
        raise GlpiError("L'envoi vers GLPI n'est pas activé (Paramètres → GLPI).")
    with _send_lock:
        t = db.execute("SELECT * FROM tickets WHERE id=?", (tid,)).fetchone()
        if t is None:
            raise GlpiError("Ticket introuvable.")
        if t["glpi_id"]:
            return t["glpi_id"], True
        try:
            with _Session(cfg) as s:
                r = s.call("POST", "Ticket", build_input(t, cfg, urgences(cfg), app_link))
            gid = r.get("id") if isinstance(r, dict) else None
            if not isinstance(gid, int):
                raise GlpiError("GLPI n'a pas confirmé la création du ticket (réponse inattendue).")
        except GlpiError as e:
            db.execute("UPDATE tickets SET glpi_error=? WHERE id=?", (str(e)[:500], tid))
            db.commit()
            raise
        db.execute("UPDATE tickets SET glpi_id=?, glpi_sent_at=?, glpi_error=NULL WHERE id=?", (gid, now(), tid))
        db.commit()
        return gid, False
