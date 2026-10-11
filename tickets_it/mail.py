"""Envoi d'emails, textes personnalisables, liens de suivi, alertes aux techniciens."""
import smtplib
import socket
import ssl
import threading
from email.message import EmailMessage
from flask import has_request_context, request, url_for

from .config import MAIL_TEMPLATES, SIG_DEFAUT
from .settings_store import derived, get_settings


def email_enabled():
    cfg = get_settings()
    return cfg["email_enabled"] == "1" and bool(cfg["smtp_host"])


def smtp_send(cfg, to, subject, body):
    """Envoie un email avec la configuration donnée. Lève une exception en cas d'échec."""
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["smtp_from"], to, subject
    msg.set_content(body)
    port = int(cfg["smtp_port"] or 25)
    ctx = ssl.create_default_context()
    if cfg["smtp_verify"] != "1":
        ctx.check_hostname, ctx.verify_mode = False, ssl.CERT_NONE
    if cfg["smtp_security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["smtp_host"], port, timeout=10, context=ctx)
    else:
        server = smtplib.SMTP(cfg["smtp_host"], port, timeout=10)
    with server:
        if cfg["smtp_security"] == "starttls":
            server.starttls(context=ctx)
        if cfg["smtp_user"]:
            server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.send_message(msg)


def smtp_error_text(e):
    if isinstance(e, smtplib.SMTPAuthenticationError):
        return "Identifiant ou mot de passe refusé par le serveur."
    if isinstance(e, smtplib.SMTPNotSupportedError):
        return f"Fonction non supportée par le serveur ({e}). Vérifiez le mode de sécurité choisi."
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return "Adresse du destinataire refusée par le serveur."
    if isinstance(e, smtplib.SMTPSenderRefused):
        return "Adresse d'expédition refusée par le serveur (vérifiez le champ « Adresse d'expédition »)."
    if isinstance(e, ssl.SSLError):
        return ("Erreur de sécurité TLS/SSL : mode de sécurité incorrect pour ce port, ou certificat non reconnu "
                "(vous pouvez décocher « Vérifier le certificat » pour un serveur interne).")
    if isinstance(e, (TimeoutError, socket.timeout)):
        return "Délai dépassé : le serveur ne répond pas (vérifiez l'adresse, le port et le pare-feu)."
    if isinstance(e, ConnectionRefusedError):
        return "Connexion refusée : vérifiez l'adresse du serveur et le port."
    if isinstance(e, socket.gaierror):
        return "Nom de serveur introuvable : vérifiez l'adresse du serveur."
    if isinstance(e, smtplib.SMTPServerDisconnected):
        return "Le serveur a coupé la connexion (mode de sécurité incorrect pour ce port ?)."
    return f"{type(e).__name__} : {e}"


def send_mail(to, subject, body, kind="demandeur"):
    """Envoi en arrière-plan. kind = 'demandeur' ou 'technicien' (chaque type peut être désactivé dans Paramètres)."""
    cfg = get_settings()
    if cfg["email_enabled"] != "1" or not cfg["smtp_host"] or not to:
        return
    if (kind == "technicien" and cfg["mail_staff"] != "1") or (kind == "demandeur" and cfg["mail_requesters"] != "1"):
        return

    def _send():
        try:
            smtp_send(cfg, to, subject, body)
        except Exception as e:  # ne jamais bloquer l'appli pour un email
            print("Erreur email :", smtp_error_text(e))
    threading.Thread(target=_send, daemon=True).start()


def base_url():
    url = get_settings()["app_url"].strip().rstrip("/")
    if url:
        return url
    return request.host_url.rstrip("/") if has_request_context() else ""


def track_url(token):
    return f"{base_url()}{url_for('suivi', token=token)}"


def notify_staff(db, tid, title, priority, who, category):
    """Email d'alerte à tous les techniciens qui ont une adresse et l'alerte activée."""
    if not email_enabled():
        return
    link = f"{base_url()}{url_for('admin_ticket', tid=tid)}"
    D = derived()
    urgent = f"{priority.upper()} · " if priority == D.prio_top else (f"{priority} · " if priority == D.prio_second else "")
    subject, body = render_mail("staff_ticket", numero=tid, titre=title, demandeur=who, categorie=category,
                                priorite=priority, urgence=urgent, lien=link)
    for u in db.execute("SELECT email FROM users WHERE notify=1 AND email<>'' AND role<>'lecteur'").fetchall():
        send_mail(u["email"], subject, body, kind="technicien")


def projet_url(token):
    return f"{base_url()}{url_for('projet_suivi', token=token)}"


def notify_staff_project(db, pid, title, who, department):
    if not email_enabled():
        return
    link = f"{base_url()}{url_for('project_detail', pid=pid)}"
    subject, body = render_mail("staff_project", numero=pid, titre=title, demandeur=who,
                                service=f" ({department})" if department else "", lien=link)
    for u in db.execute("SELECT email FROM users WHERE notify=1 AND email<>'' AND role<>'lecteur'").fetchall():
        send_mail(u["email"], subject, body, kind="technicien")


def render_mail(key, **v):
    """(objet, texte) d'un email : texte personnalisé s'il existe, sinon texte par défaut."""
    t, cfg = MAIL_TEMPLATES[key], get_settings()
    subject = cfg.get(f"tpl.{key}.subject") or t["subject"]
    body = cfg.get(f"tpl.{key}.body") or t["body"]
    v.setdefault("signature", cfg.get("mail_signature") or SIG_DEFAUT)

    def fill(text):
        for k, val in v.items():
            text = text.replace("{" + k + "}", str(val))
        return text
    return " ".join(fill(subject).split()), fill(body)


def link_for(path):
    """Lien absolu hors requête (tâches de fond) : nécessite l'adresse de l'application dans Paramètres → Email."""
    base = get_settings()["app_url"].strip().rstrip("/")
    return f"{base}{path}" if base else path
