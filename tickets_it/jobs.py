"""Tâches de fond : tickets récurrents, sauvegardes, rappels, résumé quotidien."""
import os
import shutil
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

from .config import BACKUP_DIR, DB_PATH, FREQUENCES, HEURE_TACHES, JOURS_NOMS, SIG_DEFAUT, UPLOAD_DIR
from .db import fmt, get_meta, now, parse_dt, raw_db, set_meta
from .mail import email_enabled, link_for, render_mail, send_mail
from .services import create_ticket
from .settings_store import derived, get_settings
from .sla import _at, human_delta, is_workday


def freq_label(r):
    if r["freq"] == "semaine":
        return f"Chaque {JOURS_NOMS[r['weekday']]}"
    if r["freq"] == "mois":
        return f"Le {r['monthday']} de chaque mois"
    return FREQUENCES["jour_ouvre"]


def next_run_after(freq, weekday, monthday, after):
    for i in range(0, 800):
        d = after.date() + timedelta(days=i)
        dt = _at(d, HEURE_TACHES * 60)
        if dt <= after:
            continue
        if freq == "jour_ouvre" and is_workday(d):
            return dt
        if freq == "semaine" and d.weekday() == weekday:
            return dt
        if freq == "mois" and d.day == monthday:
            return dt
    return after + timedelta(days=1)


def run_recurring(force_id=None):
    """Crée les tickets des tâches planifiées arrivées à échéance. Retourne le nombre créé."""
    db, n, created = raw_db(), datetime.now(), 0
    try:
        if force_id:
            rows = db.execute("SELECT * FROM recurring WHERE id=?", (force_id,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM recurring WHERE active=1 AND next_run<=?", (fmt(n),)).fetchall()
        for r in rows:
            if force_id:
                claimed = True
                db.execute("UPDATE recurring SET last_run=? WHERE id=?", (fmt(n), r["id"]))
            else:
                nxt = fmt(next_run_after(r["freq"], r["weekday"], r["monthday"], n))
                claimed = db.execute("UPDATE recurring SET next_run=?, last_run=? WHERE id=? AND next_run=?",
                                     (nxt, fmt(n), r["id"], r["next_run"])).rowcount == 1
            if claimed:
                create_ticket(db, title=r["title"], requester_name="Tâche planifiée",
                              department="Service informatique", category=r["category"], priority=r["priority"],
                              description=r["description"], assignee_id=r["assignee_id"], source="planifie")
                created += 1
        db.commit()
    finally:
        db.close()
    return created


# --- Sauvegarde automatique ----------------------------------------------------
def _sync_uploads(dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    if os.path.isdir(UPLOAD_DIR):
        for name in os.listdir(UPLOAD_DIR):
            target = os.path.join(dest_dir, name)
            if not os.path.exists(target):
                shutil.copy2(os.path.join(UPLOAD_DIR, name), target)


def _purge_old(db_dir):
    files = sorted((os.path.join(db_dir, f) for f in os.listdir(db_dir) if f.startswith("tickets-") and f.endswith(".db")),
                   key=os.path.getmtime, reverse=True)
    cutoff = time.time() - derived().backup_days * 86400
    for path in files[1:]:  # on garde toujours la plus récente
        if os.path.getmtime(path) < cutoff:
            os.remove(path)


def run_backup():
    """Sauvegarde la base (+ nouvelles pièces jointes) dans BACKUP_DIR et BACKUP_COPIE. Retourne (ok, message)."""
    try:
        name = f"tickets-{datetime.now():%Y%m%d-%H%M%S}.db"
        targets = [BACKUP_DIR] + ([derived().backup_copy] if derived().backup_copy else [])
        for base in targets:
            db_dir = os.path.join(base, "base")
            os.makedirs(db_dir, exist_ok=True)
            src, dst = sqlite3.connect(DB_PATH), sqlite3.connect(os.path.join(db_dir, name))
            with dst:
                src.backup(dst)
            dst.close()
            src.close()
            _sync_uploads(os.path.join(base, "fichiers"))
            _purge_old(db_dir)
        set_meta("last_backup_at", now())
        set_meta("last_backup_status", "ok")
        return True, f"Sauvegarde {name} effectuée."
    except Exception as e:
        set_meta("last_backup_status", f"Erreur : {e}")
        print("Erreur sauvegarde :", e)
        return False, f"Échec de la sauvegarde : {e}"


def backup_due():
    db_dir = os.path.join(BACKUP_DIR, "base")
    D = derived()
    if not D.backup_auto or datetime.now().hour < D.backup_hour:
        return False
    prefix = f"tickets-{datetime.now():%Y%m%d}"
    return not (os.path.isdir(db_dir) and any(f.startswith(prefix) for f in os.listdir(db_dir)))


def backup_warning():
    status, last = get_meta("last_backup_status"), get_meta("last_backup_at")
    if status is None:
        return ""
    if status != "ok":
        return f"La dernière sauvegarde automatique a échoué ({status})."
    if last and datetime.now() - parse_dt(last) > timedelta(days=2):
        return "Aucune sauvegarde réussie depuis plus de 2 jours."
    return ""


_scheduler_started = False


def _scheduler_loop():
    time.sleep(5)
    while True:
        try:
            run_recurring()
        except Exception as e:
            print("Erreur tâches planifiées :", e)
        try:
            if backup_due():
                run_backup()
        except Exception as e:
            print("Erreur sauvegarde :", e)
        for job in (run_reminders, run_digest):
            try:
                job()
            except Exception as e:
                print("Erreur notifications :", e)
        time.sleep(60)


def start_scheduler():
    global _scheduler_started
    if _scheduler_started or os.environ.get("TICKETS_NO_SCHEDULER"):
        return
    _scheduler_started = True
    threading.Thread(target=_scheduler_loop, daemon=True).start()


# --- Rappels d'échéance et résumé quotidien (tâches de fond) -----------------------
def _in_working_time(n):
    D = derived()
    return is_workday(n.date()) and D.work_start <= n.hour * 60 + n.minute < D.work_end


def run_reminders():
    """Envoie un rappel (une seule fois par échéance) pour les tickets proches de l'échéance ou en retard."""
    D = derived()
    if not (D.remind_late or D.remind_soon > 0) or not email_enabled():
        return 0
    n = datetime.now()
    if not _in_working_time(n):
        return 0
    db, sent = raw_db(), 0
    try:
        staff = [r["email"] for r in db.execute("SELECT email FROM users WHERE notify=1 AND email<>'' AND role<>'lecteur'")]
        rows = db.execute("SELECT t.*, u.email AS aemail, u.notify AS anotify FROM tickets t LEFT JOIN users u ON u.id=t.assignee_id "
                          "WHERE t.status IN ('Nouveau','En cours') AND t.due_at IS NOT NULL").fetchall()
        for t in rows:
            due, state, kind = parse_dt(t["due_at"]), t["remind_state"], None
            if D.remind_late and due < n < due + timedelta(days=2) and state != "late":
                kind = "late"
            elif D.remind_soon > 0 and state is None and n <= due <= n + timedelta(hours=D.remind_soon):
                kind = "soon"
            if not kind:
                continue
            claimed = db.execute("UPDATE tickets SET remind_state=? WHERE id=? AND COALESCE(remind_state,'')=?",
                                 (kind, t["id"], state or "")).rowcount == 1
            db.commit()
            if not claimed:
                continue
            to = [t["aemail"]] if (t["aemail"] and t["anotify"]) else staff
            subject, body = render_mail("reminder_" + kind, numero=t["id"], titre=t["title"], priorite=t["priority"],
                                        demandeur=t["requester_name"], echeance=f"{due:%d/%m/%Y à %H:%M}",
                                        lien=link_for(f"/admin/ticket/{t['id']}"))
            for addr in to:
                send_mail(addr, subject, body, kind="technicien")
            sent += 1
    finally:
        db.close()
    return sent


def build_digest(db, u):
    """(objet, texte) du résumé quotidien d'un utilisateur, ou None s'il n'y a rien à signaler."""
    n = datetime.now()
    today = n.date().isoformat()
    end_day = fmt(datetime(n.year, n.month, n.day, 23, 59, 59))
    uid, sections = u["id"], []

    def line(prefix, id_, title, path, extra=""):
        lk = link_for(path)
        title = " ".join(str(title).split())
        return f"  - {prefix}{id_} · {title}{extra}" + (f"\n    {lk}" if lk.startswith("http") else "")

    def add(title, items, total=None):
        if items:
            sections.append(f"{title} ({total or len(items)})\n" + "\n".join(items))
    OPEN = "t.status IN ('Nouveau','En cours')"
    late = db.execute(f"SELECT * FROM tickets t WHERE t.assignee_id=? AND {OPEN} AND t.due_at < ? ORDER BY t.due_at LIMIT 15", (uid, fmt(n))).fetchall()
    add("Vos tickets EN RETARD", [line("#", t["id"], t["title"], f"/admin/ticket/{t['id']}", f" · en retard de {human_delta(n - parse_dt(t['due_at']))}") for t in late])
    due_today = db.execute(f"SELECT * FROM tickets t WHERE t.assignee_id=? AND {OPEN} AND t.due_at >= ? AND t.due_at <= ? ORDER BY t.due_at LIMIT 15",
                           (uid, fmt(n), end_day)).fetchall()
    add("Vos tickets à échéance aujourd'hui", [line("#", t["id"], t["title"], f"/admin/ticket/{t['id']}", f" · avant {parse_dt(t['due_at']):%Hh%M}") for t in due_today])
    n_un = db.execute("SELECT COUNT(*) FROM tickets WHERE assignee_id IS NULL AND status='Nouveau'").fetchone()[0]
    un = db.execute("SELECT * FROM tickets WHERE assignee_id IS NULL AND status='Nouveau' ORDER BY created_at LIMIT 8").fetchall()
    add("Tickets sans technicien", [line("#", t["id"], t["title"], f"/admin/ticket/{t['id']}", f" · {t['priority']}") for t in un], n_un)
    tl = db.execute("SELECT k.*, p.title AS pt FROM tasks k LEFT JOIN projects p ON p.id=k.project_id WHERE k.done=0 AND k.assignee_id=? "
                    "AND k.due_date<>'' AND k.due_date < ? AND (k.project_id IS NULL OR p.status<>'Annulé') ORDER BY k.due_date LIMIT 15", (uid, today)).fetchall()
    add("Vos tâches en retard", [f"  - {k['title']}{' (' + k['pt'] + ')' if k['pt'] else ''} · échéance {date.fromisoformat(k['due_date']):%d/%m}" for k in tl])
    tt = db.execute("SELECT k.*, p.title AS pt FROM tasks k LEFT JOIN projects p ON p.id=k.project_id WHERE k.done=0 AND k.assignee_id=? "
                    "AND k.due_date=? AND (k.project_id IS NULL OR p.status<>'Annulé') LIMIT 15", (uid, today)).fetchall()
    add("Vos tâches du jour", [f"  - {k['title']}{' (' + k['pt'] + ')' if k['pt'] else ''}" for k in tt])
    pr = db.execute("SELECT * FROM projects WHERE status='Proposé' ORDER BY created_at LIMIT 8").fetchall()
    add("Demandes de projet à valider", [line("#", p["id"], p["title"], f"/admin/projet/{p['id']}", f" · {p['requester_name']}") for p in pr],
        db.execute("SELECT COUNT(*) FROM projects WHERE status='Proposé'").fetchone()[0])
    pl = db.execute("SELECT * FROM projects WHERE owner_id=? AND status NOT IN ('Terminé','Annulé','Proposé') AND due_date<>'' AND due_date < ? ORDER BY due_date LIMIT 10",
                    (uid, today)).fetchall()
    add("Vos projets en retard", [line("#", p["id"], p["title"], f"/admin/projet/{p['id']}", f" · échéance {date.fromisoformat(p['due_date']):%d/%m}") for p in pl])
    if not sections:
        return None
    team_late = db.execute(f"SELECT COUNT(*) FROM tickets t WHERE {OPEN} AND t.due_at < ?", (fmt(n),)).fetchone()[0]
    body = (f"Bonjour {u['name']},\n\nVoici votre résumé du {n:%d/%m/%Y} :\n\n" + "\n\n".join(sections) +
            (f"\n\nÀ l'échelle de l'équipe : {team_late} ticket(s) en retard." if team_late else "") +
            "\n\n" + (get_settings().get("mail_signature") or SIG_DEFAUT))
    return f"Résumé du jour - {n:%d/%m/%Y}", body


def run_digest():
    """Envoie le résumé quotidien (une fois par jour ouvré, à l'heure choisie) aux utilisateurs concernés."""
    D = derived()
    n = datetime.now()
    if not D.digest_on or not email_enabled() or n.hour < D.digest_hour or not is_workday(n.date()):
        return 0
    db, sent = raw_db(), 0
    try:
        cur = db.execute("INSERT INTO meta (key,value) VALUES ('digest_last',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value "
                         "WHERE meta.value<>excluded.value", (n.date().isoformat(),))
        db.commit()
        if cur.rowcount != 1:       # déjà envoyé aujourd'hui (ou envoi concurrent)
            return 0
        for u in db.execute("SELECT * FROM users WHERE digest=1 AND email<>''").fetchall():
            d = build_digest(db, u)
            if d:
                send_mail(u["email"], d[0], d[1], kind="technicien")
                sent += 1
    finally:
        db.close()
    return sent
