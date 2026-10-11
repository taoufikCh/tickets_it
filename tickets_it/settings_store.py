"""Paramètres enregistrés en base (cache, valeurs dérivées, listes dynamiques)."""
import json
import threading
import time
from datetime import date

from .config import BACKUP_HEURE, CANAUX_DEFAUT, BACKUP_JOURS, CATEGORIES_DEFAUT, EXT_AUTORISEES, EXT_CHOISISSABLES, HORAIRES, JOURS_OUVRES, MAX_FICHIERS, MAX_FICHIER_MO, PRIORITES_DEFAUT, SETTINGS_DEFAUTS, SETTINGS_TTL, SLA_DEFAUT
from .db import raw_db


class _Cache:
    lock = threading.Lock()
    t = 0.0
    cfg = None
    der = None


def get_settings(force=False):
    """Paramètres effectifs (valeurs par défaut + valeurs enregistrées), avec un petit cache mémoire."""
    c = _Cache
    if not force and c.cfg is not None and time.time() - c.t < SETTINGS_TTL:
        return dict(c.cfg)
    cfg = dict(SETTINGS_DEFAUTS)
    db = raw_db()
    try:
        for r in db.execute("SELECT key, value FROM meta WHERE key LIKE 'cfg.%'"):
            cfg[r["key"][4:]] = r["value"]
    finally:
        db.close()
    with c.lock:
        c.cfg, c.t, c.der = cfg, time.time(), None
    return dict(cfg)


def save_settings(values):
    db = raw_db()
    try:
        for k, v in values.items():
            db.execute("INSERT INTO meta (key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       ("cfg." + k, v))
        db.commit()
    finally:
        db.close()
    with _Cache.lock:
        _Cache.cfg = None
        _Cache.der = None


def _json_list(raw, default):
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else default
    except (TypeError, ValueError):
        return default


def _hhmm(raw, default):
    try:
        h, m = str(raw).split(":")
        v = int(h) * 60 + int(m)
        return v if 0 <= v <= 1440 else default
    except ValueError:
        return default


class Derived:
    """Valeurs calculées à partir des paramètres (listes, horaires, jours fériés…)."""


def _build_derived(cfg):
    d = Derived()
    dflt = SETTINGS_DEFAUTS
    d.cats = [{"name": str(c.get("name", "")).strip(), "active": bool(c.get("active", True))}
              for c in _json_list(cfg["categories"], []) if isinstance(c, dict) and str(c.get("name", "")).strip()]
    if not d.cats:
        d.cats = [{"name": c, "active": True} for c in CATEGORIES_DEFAUT]
    d.cat_names = [c["name"] for c in d.cats]
    d.cat_active = [c["name"] for c in d.cats if c["active"]] or d.cat_names[:1]
    d.prios = []
    for p in _json_list(cfg["priorites"], []):
        if isinstance(p, dict) and str(p.get("name", "")).strip():
            try:
                sla = float(p.get("sla", 24))
            except (TypeError, ValueError):
                sla = 24.0
            d.prios.append({"name": str(p["name"]).strip(), "sla": sla})
    if not d.prios:
        d.prios = [{"name": p, "sla": float(SLA_DEFAUT[p])} for p in PRIORITES_DEFAUT]
    d.prio_names = [p["name"] for p in d.prios]
    d.sla = {p["name"]: p["sla"] for p in d.prios}
    d.prio_top = d.prio_names[-1]
    d.prio_second = d.prio_names[-2] if len(d.prio_names) >= 2 else None
    d.prio_default = "Normale" if "Normale" in d.prio_names else d.prio_names[min(1, len(d.prio_names) - 1)]
    d.services = [str(s) for s in _json_list(cfg["services"], []) if str(s).strip()]
    d.channels = [str(s) for s in _json_list(cfg["canaux"], CANAUX_DEFAUT) if str(s).strip()]
    d.bureaux = [str(s) for s in _json_list(cfg["bureaux"], []) if str(s).strip()]
    d.work_start = _hhmm(cfg["work_start"], HORAIRES[0] * 60)
    d.work_end = _hhmm(cfg["work_end"], HORAIRES[1] * 60)
    if d.work_end <= d.work_start:
        d.work_start, d.work_end = HORAIRES[0] * 60, HORAIRES[1] * 60
    d.days = {int(x) for x in str(cfg["work_days"]).split(",") if x.strip().isdigit() and 0 <= int(x) <= 6} or set(JOURS_OUVRES)
    d.holidays, d.holidays_yearly, d.holiday_rows = set(), set(), []
    for h in _json_list(cfg["holidays"], []):
        try:
            dt = date.fromisoformat(h["date"])
        except (KeyError, TypeError, ValueError):
            continue
        label, yearly = str(h.get("label", "")), bool(h.get("yearly"))
        d.holiday_rows.append({"date": dt.isoformat(), "label": label, "yearly": yearly})
        (d.holidays_yearly if yearly else d.holidays).add(dt.strftime("%m-%d") if yearly else dt.isoformat())
    def _int(key, default, lo, hi):
        try:
            v = int(float(cfg[key]))
        except (TypeError, ValueError):
            v = default
        return max(lo, min(hi, v))
    d.max_mo = _int("max_mo", MAX_FICHIER_MO, 1, 200)
    d.max_files = _int("max_files", MAX_FICHIERS, 1, 20)
    d.ext = {e for e in str(cfg["extensions"]).split(",") if e in EXT_CHOISISSABLES} or set(EXT_AUTORISEES)
    d.upload_accept = ",".join("." + e for e in sorted(d.ext))
    d.max_request = (d.max_files * d.max_mo + 5) * 1024 * 1024
    d.session_hours = _int("session_hours", 0, 0, 720)
    d.lock_attempts = _int("lock_attempts", 5, 0, 50)
    d.lock_minutes = _int("lock_minutes", 15, 1, 1440)
    d.pw_min = _int("pw_min", 6, 4, 64)
    d.pw_mix = cfg["pw_mix"] == "1"
    d.backup_auto = cfg["backup_auto"] == "1"
    d.backup_hour = _int("backup_hour", BACKUP_HEURE, 0, 23)
    d.backup_days = _int("backup_days", BACKUP_JOURS, 1, 365)
    d.backup_copy = str(cfg["backup_copy"]).strip()
    d.restrict_edit = cfg["restrict_edit"] == "1"
    d.restrict_delete = cfg["restrict_delete"] == "1"
    d.digest_on = cfg["digest_on"] == "1"
    d.digest_hour = _int("digest_hour", 8, 0, 23)
    try:
        d.remind_soon = max(0.0, min(72.0, float(cfg["remind_soon"])))
    except (TypeError, ValueError):
        d.remind_soon = 0.0
    d.remind_late = cfg["remind_late"] == "1"
    return d


def derived():
    get_settings()
    c = _Cache
    if c.der is None:
        with c.lock:
            if c.der is None:
                c.der = _build_derived(c.cfg or dict(SETTINGS_DEFAUTS))
    return c.der


class LazyList:
    """Liste dont le contenu suit les paramètres (les anciennes références restent valides)."""
    def __init__(self, fn):
        self._fn = fn

    def __iter__(self):
        return iter(self._fn())

    def __len__(self):
        return len(self._fn())

    def __getitem__(self, i):
        return self._fn()[i]

    def __contains__(self, x):
        return x in self._fn()

    def __repr__(self):
        return repr(self._fn())


class _SlaMap:
    def get(self, key, default=None):
        return derived().sla.get(key, default)

    def __getitem__(self, key):
        return derived().sla[key]

    def items(self):
        return derived().sla.items()


CATEGORIES = LazyList(lambda: derived().cat_names)


CATEGORIES_ACTIVES = LazyList(lambda: derived().cat_active)


PRIORITES = LazyList(lambda: derived().prio_names)


SLA_HEURES = _SlaMap()


def prio_cls(name):
    """Classe CSS d'une priorité d'après son rang (la plus haute en rouge, la plus basse en gris clair)."""
    names = derived().prio_names
    if name not in names or len(names) == 1:
        return "p-mid"
    idx, r = names.index(name), len(names) - 1 - names.index(name)
    if r == 0:
        return "p-top"
    if idx == 0:
        return "p-low"
    return "p-high" if r == 1 else "p-mid"


def prio_rank_sql(col):
    """Expression SQL qui classe les priorités de la plus urgente (0) à la moins urgente."""
    names = list(reversed(derived().prio_names))
    whens = " ".join("WHEN '%s' THEN %d" % (n.replace("'", "''"), i) for i, n in enumerate(names))
    return f"CASE {col} {whens} ELSE {len(names)} END"
