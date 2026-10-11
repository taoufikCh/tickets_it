"""Calcul des délais (SLA) en heures ouvrées et changement de statut des tickets."""
from datetime import datetime, timedelta

from .db import fmt, parse_dt
from .settings_store import SLA_HEURES, derived


# --- Calcul des délais (SLA) en heures ouvrées -------------------------------
def _at(d, minutes):
    return datetime(d.year, d.month, d.day) + timedelta(minutes=minutes)


def is_workday(d):
    D = derived()
    return d.weekday() in D.days and d.isoformat() not in D.holidays and d.strftime("%m-%d") not in D.holidays_yearly


def next_work_time(t):
    """Premier instant ouvré >= t."""
    D = derived()
    for _ in range(4000):
        d = t.date()
        if not is_workday(d):
            t = _at(d + timedelta(days=1), D.work_start)
            continue
        if t < _at(d, D.work_start):
            return _at(d, D.work_start)
        if t >= _at(d, D.work_end):
            t = _at(d + timedelta(days=1), D.work_start)
            continue
        return t
    return t


def add_work_hours(start, hours):
    D = derived()
    t = next_work_time(start)
    remaining = timedelta(hours=hours)
    for _ in range(4000):
        end = _at(t.date(), D.work_end)
        if remaining <= end - t:
            return t + remaining
        remaining -= end - t
        t = next_work_time(end)
    return t + remaining


def work_seconds_between(a, b):
    D = derived()
    if b <= a:
        return 0
    total, d = 0, a.date()
    while d <= b.date():
        if is_workday(d):
            s, e = max(a, _at(d, D.work_start)), min(b, _at(d, D.work_end))
            if e > s:
                total += (e - s).total_seconds()
        d += timedelta(days=1)
    return int(total)


def compute_due(created_at, priority, paused_secs=0):
    hours = SLA_HEURES.get(priority, 24) + (paused_secs or 0) / 3600
    return fmt(add_work_hours(parse_dt(created_at), hours))


def human_delta(td):
    minutes = int(abs(td.total_seconds()) // 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    hours = minutes // 60
    return f"{hours} h" if hours < 48 else f"{hours // 24} j"


def sla_state(t):
    """(classe CSS, libellé) de l'état du délai d'un ticket."""
    if not t["due_at"]:
        return ("", "")
    status = t["status"]
    if status in ("Résolu", "Clos"):
        ok = t["closed_at"] and t["closed_at"] <= t["due_at"]
        return ("ok", "Dans les délais") if ok else ("late", "Hors délai")
    if status == "En attente":
        return ("pause", "En pause")
    due, n = parse_dt(t["due_at"]), datetime.now()
    if n > due:
        return ("late", f"En retard de {human_delta(n - due)}")
    return ("soon" if due - n < timedelta(hours=4) else "ok", f"Avant le {due:%d/%m à %Hh%M}")


def set_status(db, t, new_status):
    """Change le statut en gérant clôture et mise en pause du délai. t = ligne du ticket."""
    old = t["status"]
    paused_at, paused_secs = t["paused_at"], t["paused_secs"] or 0
    n = datetime.now()
    if old == "En attente" and new_status != "En attente" and paused_at:
        paused_secs += work_seconds_between(parse_dt(paused_at), n)
        paused_at = None
    if new_status == "En attente" and old != "En attente":
        paused_at = fmt(n)
    closed_at = (t["closed_at"] or fmt(n)) if new_status in ("Résolu", "Clos") else None
    new_due = compute_due(t["created_at"], t["priority"], paused_secs)
    db.execute("UPDATE tickets SET status=?, closed_at=?, paused_at=?, paused_secs=?, due_at=?, updated_at=?, "
               "remind_state=CASE WHEN due_at=? THEN remind_state ELSE NULL END WHERE id=?",
               (new_status, closed_at, paused_at, paused_secs, new_due, fmt(n), new_due, t["id"]))
