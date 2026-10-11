"""Calendrier : planning des tickets (échéances), tâches, projets et tickets récurrents."""
import calendar
from datetime import date, datetime, timedelta
from flask import g, render_template, request

from ..config import HEURE_TACHES, JOURS_NOMS
from ..db import fmt, get_db
from ..extensions import app
from ..jobs import next_run_after
from ..security import login_required
from ..settings_store import derived

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
TYPES = [("t", "Tickets (échéances)"), ("k", "Tâches"), ("p", "Projets"), ("r", "Tickets récurrents")]
ORDRE = {"ticket": 0, "projet": 1, "tache": 2, "recurrent": 3}


def _parse_month(raw):
    try:
        y, m = (int(x) for x in raw.split("-"))
        date(y, m, 1)
        return y, m
    except (AttributeError, ValueError):
        t = date.today()
        return t.year, t.month


def _shift(y, m, delta):
    m += delta
    while m < 1:
        m, y = m + 12, y - 1
    while m > 12:
        m, y = m - 12, y + 1
    return f"{y}-{m:02d}"


def collect_events(db, start, end, show, qui, uid):
    """Événements du planning entre deux dates incluses : {date ISO: [événement, …]}."""
    ev = {}
    lo, hi = start.isoformat(), end.isoformat()
    n = datetime.now()

    def add(day, **e):
        ev.setdefault(day, []).append(e)

    if "t" in show:
        sql = ("SELECT t.id, t.title, t.priority, t.status, t.due_at, u.name AS who FROM tickets t "
               "LEFT JOIN users u ON u.id=t.assignee_id WHERE t.status IN ('Nouveau','En cours','En attente') "
               "AND t.due_at >= ? AND t.due_at <= ?")
        args = [lo + " 00:00:00", hi + " 23:59:59"]
        if qui == "moi":
            sql += " AND t.assignee_id=?"
            args.append(uid)
        for t in db.execute(sql + " ORDER BY t.due_at", args):
            late = t["due_at"] < fmt(n) and t["status"] != "En attente"
            add(t["due_at"][:10], kind="ticket", label=f"#{t['id']} {t['title']}", time=t["due_at"][11:16],
                sub=f"Échéance du ticket · {t['priority']} · {t['status']}" + (f" · {t['who']}" if t["who"] else ""),
                url=f"/admin/ticket/{t['id']}", late=late, done=False)
    if "k" in show:
        sql = ("SELECT k.id, k.title, k.due_date, k.done, k.project_id, p.title AS pt, u.name AS who FROM tasks k "
               "LEFT JOIN projects p ON p.id=k.project_id LEFT JOIN users u ON u.id=k.assignee_id "
               "WHERE k.due_date >= ? AND k.due_date <= ? AND (k.project_id IS NULL OR p.status<>'Annulé')")
        args = [lo, hi]
        if qui == "moi":
            sql += " AND k.assignee_id=?"
            args.append(uid)
        for k in db.execute(sql + " ORDER BY k.done, k.id", args):
            add(k["due_date"], kind="tache", label=k["title"], time="",
                sub="Tâche" + (f" · projet « {k['pt']} »" if k["pt"] else " personnelle") + (f" · {k['who']}" if k["who"] else ""),
                url=(f"/admin/projet/{k['project_id']}" if k["project_id"] else "/admin/taches"),
                late=(not k["done"] and k["due_date"] < date.today().isoformat()), done=bool(k["done"]))
    if "p" in show:
        sql = ("SELECT p.id, p.title, p.due_date, p.status, u.name AS who FROM projects p "
               "LEFT JOIN users u ON u.id=p.owner_id WHERE p.due_date >= ? AND p.due_date <= ? AND p.status<>'Annulé'")
        args = [lo, hi]
        if qui == "moi":
            sql += " AND p.owner_id=?"
            args.append(uid)
        for p in db.execute(sql + " ORDER BY p.id", args):
            done = p["status"] == "Terminé"
            add(p["due_date"], kind="projet", label=f"Projet #{p['id']} {p['title']}", time="",
                sub=f"Échéance du projet · {p['status']}" + (f" · {p['who']}" if p["who"] else ""),
                url=f"/admin/projet/{p['id']}", late=(not done and p["due_date"] < date.today().isoformat()), done=done)
    if "r" in show:
        sql = ("SELECT r.*, u.name AS who FROM recurring r LEFT JOIN users u ON u.id=r.assignee_id WHERE r.active=1")
        args = []
        if qui == "moi":
            sql += " AND r.assignee_id=?"
            args.append(uid)
        for r in db.execute(sql, args):
            after = max(n, datetime(start.year, start.month, start.day)) - timedelta(seconds=1)
            for _ in range(70):
                nxt = next_run_after(r["freq"], r["weekday"], r["monthday"], after)
                if nxt.date() > end:
                    break
                add(nxt.date().isoformat(), kind="recurrent", label=r["title"], time=f"{HEURE_TACHES:02d}:00",
                    sub="Création automatique d'un ticket récurrent" + (f" · {r['who']}" if r["who"] else ""),
                    url="/admin/planifiees", late=False, done=False)
                after = nxt
    for day in ev:
        ev[day].sort(key=lambda e: (ORDRE[e["kind"]], e["done"], e["time"], e["label"]))
    return ev


@app.route("/admin/calendrier")
@login_required()
def calendar_page():
    D, db = derived(), get_db()
    y, m = _parse_month(request.args.get("m", ""))
    qui = request.args.get("qui", "moi")
    qui = qui if qui in ("moi", "tous") else "moi"
    show = {c for c in request.args.getlist("t") if c in dict(TYPES)} if request.args.get("f") else {c for c, _ in TYPES}
    weeks = calendar.Calendar(0).monthdatescalendar(y, m)
    start, end = weeks[0][0], weeks[-1][-1]
    ev = collect_events(db, start, end, show, qui, g.user["id"])
    # jours fériés et fermetures
    feries = {}
    for h in D.holiday_rows:
        d0 = date.fromisoformat(h["date"])
        for d in (weeks[0][0] + timedelta(days=i) for i in range((end - start).days + 1)):
            if (h["yearly"] and (d.month, d.day) == (d0.month, d0.day)) or (not h["yearly"] and d == d0):
                feries[d.isoformat()] = h["label"] or "Jour férié"
    today = date.today()
    sel = request.args.get("jour", "")
    try:
        sel = date.fromisoformat(sel).isoformat()
    except ValueError:
        sel = today.isoformat() if start <= today <= end else ""
    keep = {"qui": qui, "f": 1, "t": sorted(show)}
    return render_template("calendar.html", weeks=weeks, ev=ev, feries=feries, workdays=D.days, y=y, m=m,
                           titre=f"{MOIS[m - 1].capitalize()} {y}", mois=f"{y}-{m:02d}", prev=_shift(y, m, -1),
                           next=_shift(y, m, 1), today=today, sel=sel, sel_ev=ev.get(sel, []), qui=qui, show=show,
                           types=TYPES, keep=keep, jours=JOURS_NOMS,
                           sel_date=date.fromisoformat(sel) if sel else None, total=sum(len(v) for v in ev.values()))
