"""Tickets IT - application légère de gestion de tickets pour réseau interne."""
from .extensions import app
from .db import init_db
from .jobs import start_scheduler

# L'import de ces modules enregistre les routes, filtres et gestionnaires sur `app`.
from . import security, templating, errors  # noqa: F401
from .routes import public, auth, tickets, projects, calendar, backups, admin_settings  # noqa: F401

init_db()
start_scheduler()
