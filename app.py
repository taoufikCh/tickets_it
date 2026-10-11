"""
Tickets IT - application légère de gestion de tickets pour réseau interne.
Dépendance unique : Flask. Base de données : SQLite (fichier tickets.db).

Lancement :  python app.py   ->  http://<ip-du-serveur>:5000
Le code est organisé dans le paquet tickets_it/ (voir README.md).
"""
import os

from tickets_it import app

if __name__ == "__main__":
    # 0.0.0.0 = accessible depuis les autres postes du réseau interne
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False)
