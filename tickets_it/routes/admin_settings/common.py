"""Outils partagés par les onglets des paramètres."""
import re
from flask import render_template

SETTINGS_TABS = []
SECTION_HANDLERS = {}


def render_settings(tpl, section, **ctx):
    return render_template(tpl, tabs=SETTINGS_TABS, section=section, **ctx)


def _indexed(form, prefix):
    """Indices <i> des champs « <prefix>_<i> », dans l'ordre d'apparition dans le formulaire."""
    out = []
    for k in form.keys():
        m = re.match(r"^%s_(\d+)$" % re.escape(prefix), k)
        if m and int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def parse_lines(raw, maxlen=80, maxn=300):
    out, seen = [], set()
    for line in (raw or "").splitlines():
        v = line.strip()[:maxlen]
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:maxn]


def _count_use(db, col, value):
    n = db.execute(f"SELECT COUNT(*) FROM tickets WHERE {col}=?", (value,)).fetchone()[0]
    return n + db.execute(f"SELECT COUNT(*) FROM recurring WHERE {col}=?", (value,)).fetchone()[0]


def apply_renames(db, mapping, cols):
    """Renomme des valeurs dans plusieurs tables, en une seule passe (gère aussi les échanges A<->B)."""
    mapping = {a: b for a, b in mapping.items() if a != b}
    if not mapping:
        return
    for table, col in cols:
        case = " ".join("WHEN ? THEN ?" for _ in mapping)
        params = [x for a, b in mapping.items() for x in (a, b)] + list(mapping.keys())
        db.execute(f"UPDATE {table} SET {col}=CASE {col} {case} END WHERE {col} IN ({','.join('?' * len(mapping))})", params)


def parse_named_rows(f, prefix, col, db, errors, label, with_active=False, maxlen=60):
    rows, seen = [], set()
    for i in _indexed(f, f"{prefix}_name"):
        name, orig = f.get(f"{prefix}_name_{i}", "").strip(), f.get(f"{prefix}_orig_{i}", "").strip()
        if not name and not orig:
            continue
        used = _count_use(db, col, orig) if orig else 0
        row = {"i": i, "name": name or orig, "orig": orig, "used": used,
               "active": bool(f.get(f"{prefix}_active_{i}")) if with_active else True}
        if f.get(f"{prefix}_del_{i}"):
            if used:
                errors.append(f"« {orig} » est utilisée par {used} élément(s) : " +
                              ("désactivez-la plutôt que de la supprimer." if with_active else "impossible de la supprimer."))
            else:
                continue
        elif not name:
            errors.append(f"Un élément de la liste « {label} » n'a pas de nom.")
        if len(row["name"]) > maxlen:
            errors.append(f"« {row['name'][:20]}… » dépasse {maxlen} caractères.")
        if row["name"].lower() in seen:
            errors.append(f"Doublon dans « {label} » : « {row['name']} ».")
        seen.add(row["name"].lower())
        rows.append(row)
    return rows
