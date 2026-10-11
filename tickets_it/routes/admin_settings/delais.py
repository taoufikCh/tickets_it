"""Paramètres : délais, horaires, jours fériés."""
import json
from datetime import date, datetime
from flask import flash, redirect, request, url_for

from ...config import JOURS_NOMS, feries_tunisie
from ...db import fmt, parse_dt, raw_db
from ...routes.admin_settings.common import _indexed, render_settings
from ...settings_store import _hhmm, derived, save_settings
from ...sla import compute_due


# --- Délais et horaires ------------------------------------------------------
def recompute_open_due():
    """Recalcule l'échéance de tous les tickets ouverts avec les paramètres actuels."""
    db, n = raw_db(), 0
    try:
        for t in db.execute("SELECT id, created_at, priority, paused_secs, due_at FROM tickets "
                            "WHERE status IN ('Nouveau','En cours','En attente')").fetchall():
            nd = compute_due(t["created_at"], t["priority"], t["paused_secs"])
            if nd != t["due_at"]:
                db.execute("UPDATE tickets SET due_at=?, remind_state=NULL WHERE id=?", (nd, t["id"]))
                n += 1
        db.commit()
    finally:
        db.close()
    return n


def _to_hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sec_delais():
    D = derived()
    if request.method == "POST":
        f, errors = request.form, []
        start, end = _hhmm(f.get("work_start"), None), _hhmm(f.get("work_end"), None)
        if start is None or end is None or end <= start:
            errors.append("L'heure de fin doit être postérieure à l'heure de début.")
        days = [str(i) for i in range(7) if f.get(f"day_{i}")]
        if not days:
            errors.append("Sélectionnez au moins un jour ouvré.")
        prios = []
        for idx, p in enumerate(D.prios):
            raw = f.get(f"sla_{idx}", "").strip().replace(",", ".")
            try:
                v = float(raw)
                if not 0.25 <= v <= 999:
                    raise ValueError
            except ValueError:
                errors.append(f"Délai invalide pour « {p['name']} » (entre 0,25 et 999 heures).")
                v = p["sla"]
            prios.append({"name": p["name"], "sla": v})
        hols, seen = [], set()
        for i in _indexed(f, "hol_date"):
            raw, label = f.get(f"hol_date_{i}", "").strip(), f.get(f"hol_label_{i}", "").strip()[:60]
            if f.get(f"hol_del_{i}") or (not raw and not label):
                continue
            try:
                dt = date.fromisoformat(raw)
            except ValueError:
                errors.append(f"Date de jour férié invalide : « {raw or '(vide)'} ».")
                continue
            yearly = bool(f.get(f"hol_yearly_{i}"))
            key = (dt.strftime("%m-%d") if yearly else dt.isoformat(), yearly)
            if key not in seen:
                seen.add(key)
                hols.append({"date": dt.isoformat(), "label": label, "yearly": yearly})
        if f.get("action") == "tunisie":   # complète la liste sans enregistrer : on vérifie puis on enregistre
            added = 0
            for h in feries_tunisie(date.today().year):
                md = h["date"][5:]
                if (md, True) in seen or (h["date"], False) in seen or (not h["yearly"] and (md, True) in seen):
                    continue
                seen.add((md if h["yearly"] else h["date"], h["yearly"]))
                hols.append(h)
                added += 1
            flash(f"{added} jour(s) férié(s) de Tunisie ajouté(s) à la liste ci-dessous. "
                  "Cliquez sur « Enregistrer » pour les appliquer." if added else
                  "Les jours fériés de Tunisie sont déjà tous dans la liste.", "ok")
        hols.sort(key=lambda h: (h["date"][5:] if h["yearly"] else h["date"]))
        if not errors and f.get("action") != "tunisie":
            save_settings({"work_start": _to_hhmm(start), "work_end": _to_hhmm(end), "work_days": ",".join(days),
                           "holidays": json.dumps(hols, ensure_ascii=False),
                           "priorites": json.dumps(prios, ensure_ascii=False)})
            msg = "Délais et horaires enregistrés."
            if f.get("recalc"):
                msg += f" Échéances recalculées pour {recompute_open_due()} ticket(s) ouvert(s)."
            flash(msg, "ok")
            return redirect(url_for("settings_page", section="delais"))
        for e in dict.fromkeys(errors):
            flash(e, "error")
        rows = [{"i": i, "date": h["date"], "label": h["label"], "yearly": h["yearly"]} for i, h in enumerate(hols)]
        return render_settings("admin_settings/delais.html", "delais", start=f.get("work_start", ""), end=f.get("work_end", ""),
                               days={int(d) for d in days}, prios=prios, hols=rows, hol_next=len(rows) + 1, jours=JOURS_NOMS,
                               examples=[]), (400 if errors else 200)
    now_ = datetime.now()
    def _fr(dt):
        return f"{JOURS_NOMS[dt.weekday()][:3]}. {dt:%d/%m à %Hh%M}"
    examples = [{"name": p["name"], "sla": p["sla"], "due": _fr(parse_dt(compute_due(fmt(now_), p["name"])))} for p in D.prios]
    rows = [{"i": i, "date": h["date"], "label": h["label"], "yearly": h["yearly"]} for i, h in enumerate(D.holiday_rows)]
    return render_settings("admin_settings/delais.html", "delais", start=_to_hhmm(D.work_start), end=_to_hhmm(D.work_end), days=D.days,
                           prios=D.prios, hols=rows, hol_next=len(rows) + 1, jours=JOURS_NOMS, examples=examples)
