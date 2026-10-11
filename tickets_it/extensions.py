"""Création de l'application Flask et de sa clé secrète."""
import os
import secrets
from flask import Flask

from .config import BASE_DIR, MAX_FICHIERS, MAX_FICHIER_MO


app = Flask(__name__)


app.config["MAX_CONTENT_LENGTH"] = (MAX_FICHIERS * MAX_FICHIER_MO + 5) * 1024 * 1024


def _secret_key():
    path = os.path.join(BASE_DIR, "secret.key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


app.secret_key = os.environ.get("SECRET_KEY") or _secret_key()
