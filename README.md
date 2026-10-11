# Tickets IT

Application légère de gestion de tickets pour réseau interne (Flask + SQLite).

    pip install flask
    python app.py        # http://<ip-du-serveur>:5000

`app.py` ne contient plus que le lancement ; tout le code est dans le paquet `tickets_it/`.
`tickets.db`, `fichiers/`, `sauvegardes/` et `secret.key` restent à côté de `app.py` (aucune migration nécessaire).

## Organisation

| Fichier | Rôle |
|---|---|
| `config.py` | Constantes, valeurs par défaut, variables d'environnement |
| `extensions.py` | Création de l'application Flask, clé secrète |
| `db.py` | SQLite : schéma, connexions, migrations, table `meta` |
| `settings_store.py` | Paramètres enregistrés en base (cache, listes, horaires…) |
| `sla.py` | Délais en heures ouvrées, changement de statut |
| `security.py` | Session, CSRF, droits, verrouillage, mots de passe |
| `mail.py` | SMTP, textes d'emails, alertes |
| `services.py` | Création de tickets/projets/tâches, pièces jointes |
| `jobs.py` | Tâches de fond : récurrents, sauvegardes, rappels, résumé |
| `branding.py` / `templating.py` | Couleurs et logo / filtres et variables Jinja |
| `routes/public.py` | Formulaire de demande et pages de suivi |
| `routes/auth.py` | Connexion, comptes, « Mon compte » |
| `routes/tickets.py` | Tickets, statistiques, réponses types, récurrents |
| `routes/projects.py` | Projets et tâches |
| `routes/calendar.py` | Calendrier : échéances des tickets, tâches, projets, récurrents, jours fériés |
| `routes/backups.py` | Page des sauvegardes |
| `routes/admin_settings/` | Un fichier par onglet des paramètres |
| `templates/` | Gabarits HTML (un fichier par page) |

## Où modifier quoi

- Ajouter un onglet de paramètres : créer `routes/admin_settings/<nom>.py` (fonction `sec_<nom>`), un gabarit dans `templates/admin_settings/`, puis l'ajouter dans `routes/admin_settings/__init__.py`.
- Changer l'apparence d'une page : le fichier correspondant dans `templates/`.
- Ajouter un email automatique : `MAIL_TEMPLATES` dans `config.py`, puis `render_mail("<clé>", ...)`.

## Source de la demande, calendrier, jours fériés

- **Source** : quand un technicien connecté saisit une demande (menu « Nouvelle demande »), il choisit comment elle lui est parvenue (téléphone, email, sur place…). La liste se modifie dans Paramètres → Listes. Elle apparaît sur la fiche, dans l'export CSV (colonnes Source et Saisi par) ; les demandes du formulaire public restent « Formulaire en ligne ».
- **Calendrier** (`/admin/calendrier`) : vue mensuelle, « Mon planning » ou « Toute l'équipe », filtres par type.
- **Jours fériés de Tunisie** : Paramètres → Délais et horaires → bouton d'import. Dates fixes (chaque année) + fêtes religieuses connues (`FERIES_TUNISIE_MOBILES` dans `config.py`). Les fêtes religieuses sont à confirmer chaque année et à ajouter pour les années suivantes.

# Tickets IT – application légère pour réseau interne

Une seule dépendance (Flask), une base SQLite (`tickets.db`), aucun service externe, aucune ressource chargée depuis Internet.

## Démarrage

```bash
pip install -r requirements.txt
python app.py
```

Accès : `http://<ip-du-serveur>:5000`. Au premier lancement, un compte **admin / admin** est créé :
changez son mot de passe (clic sur votre nom en haut), puis ajoutez vos techniciens dans **Techniciens**.

Si vous aviez déjà une version précédente : remplacez simplement `app.py`, la base est mise à jour automatiquement.

## Ce que fait l'application

**Navigation** : un menu latéral à gauche (replié derrière un bouton « Menu » sur téléphone) avec des pastilles rouges pour les
tickets nouveaux, les demandes de projet à valider et vos tâches en retard. La section *Administration* n'apparaît que pour les administrateurs.

**Demandeurs (sans compte)** : un formulaire unique où l'on choisit la nature de la demande :
- *un problème ou un dépannage* → crée un **ticket** ;
- *un projet ou un nouveau besoin* (page sur le site web, cahier des charges…) → crée une **demande de projet**
  à valider par un technicien.

Dans les deux cas : captures d'écran / documents joints, puis lien de suivi privé pour voir l'avancement,
répondre et joindre d'autres fichiers.

**Techniciens** :
- **Alertes de nouveaux tickets et de demandes de projet** : fenêtre en bas à droite + bip + compteur dans l'onglet (rafraîchi toutes les 20 s,
  bouton « Son » en bas du menu pour le couper) et email aux techniciens qui ont renseigné leur adresse
  (menu *Techniciens*, ou en cliquant sur son nom en bas du menu).
- **Délais cibles (SLA)** : Urgente 2 h, Haute 8 h, Normale 24 h, Basse 72 h, en heures ouvrées (lun-ven, 8h-18h).
  Les tickets en retard sont signalés en rouge, filtrables. Le statut « En attente » met le délai en pause.
- **Réponses types** : liste déroulante dans chaque ticket, avec `{nom}`, `{technicien}`, `{numero}`, `{lieu}` remplacés automatiquement.
- **Statistiques** : tickets par mois, par catégorie / technicien / priorité, délai moyen, % résolus dans les délais,
  services les plus demandeurs, pannes récurrentes (même lieu + même catégorie).
- **Projets** (menu *Projets*) : tableau en colonnes *Proposé / À faire / En cours / Bloqué / Terminé*. Une demande
  d'un service arrive dans « Proposé » : le technicien l'**accepte** (responsable + échéance) ou la **refuse avec un motif**
  envoyé au demandeur. Un technicien peut aussi créer ses propres projets, avec une liste d'étapes (barre d'avancement
  automatique), des notes internes, des pièces jointes et des tickets liés. Pas de délai automatique : seulement
  l'échéance fixée, signalée quand elle approche ou est dépassée. Le demandeur voit le statut, l'avancement (pas le détail
  des étapes) et peut échanger avec le technicien.
- **Tâches** (menu *Tâches*) : to-do de chaque technicien, personnelles ou rattachées à un projet, avec échéance
  (En retard / Cette semaine / Plus tard / Sans date), vue « Mes tâches », « Toutes » ou « Non assignées ».
- **Du ticket au projet** : sur un ticket, « Transformer en projet » (le ticket est résolu et le demandeur prévenu)
  ou lien vers un projet existant.
- **Tickets récurrents** : tickets créés automatiquement à 8h (chaque jour ouvré, semaine ou mois).
- **Sauvegardes** (administrateur) : liste, téléchargement, sauvegarde manuelle.

## Configuration

**Dans l'application** (menu *Administration* à gauche, réservé aux administrateurs) :
- **Paramètres → Email (SMTP)** : activer ou désactiver l'envoi d'emails, serveur, port, sécurité (aucune / STARTTLS / SSL-TLS),
  identifiant et mot de passe, adresse d'expédition, vérification du certificat, adresse de l'application utilisée dans les liens,
  choix des emails envoyés (aux demandeurs, aux techniciens) et **bouton de test d'envoi** qui affiche la cause en cas d'échec.
  Les changements sont immédiats, sans redémarrage.
- **Paramètres → Listes et menus** : catégories, priorités, services et bureaux, une entrée par ligne.
  Une priorité peut porter un délai cible en heures ouvrées (« Urgente : 2 ») ; sans délai, le ticket n'a pas d'échéance SLA.
  La **dernière** priorité de la liste est la plus urgente (alerte rouge et compteur « urgents »).
  Services et bureaux vides = champ texte libre ; renseignés = menu déroulant dans le formulaire public
  (fiabilise les statistiques par service). Les listes vides reviennent aux valeurs par défaut ;
  les changements s'appliquent aux **nouveaux** tickets (les anciens conservent leurs valeurs).
- **Techniciens**, **Sauvegardes**, **Réponses types**, **Tickets récurrents**.

**Dans `tickets/config.py`** : statuts (figés, la logique en dépend), valeurs par défaut des listes, `SLA_HEURES`,
`HORAIRES`, `JOURS_OUVRES`, types et taille des pièces jointes, heure des tickets récurrents.

**Variables d'environnement** (toutes facultatives) :

| Variable | Rôle |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM`, `APP_URL` | Valeurs **initiales** de la configuration email, utilisées tant que rien n'est enregistré dans Paramètres. Ensuite, la page Paramètres prime. |
| `BACKUP_COPIE` | 2e emplacement de sauvegarde (autre disque, partage réseau monté) |
| `BACKUP_HEURE` (2), `BACKUP_JOURS` (14) | Heure de la sauvegarde nocturne et durée de conservation |
| `TICKETS_DB`, `TICKETS_UPLOADS`, `BACKUP_DIR` | Emplacements de la base, des pièces jointes et des sauvegardes |
| `PORT` | Port d'écoute (5000 par défaut) |

Note de sécurité : le mot de passe SMTP est enregistré en clair dans la base (et dans ses sauvegardes), car l'application
doit le présenter au serveur mail. Utilisez un compte dédié aux notifications, avec des droits limités à l'envoi.

## Sauvegarde et restauration

Chaque nuit (dès 2h), l'application copie la base dans `sauvegardes/base/` et les nouvelles pièces jointes dans
`sauvegardes/fichiers/` (et dans `BACKUP_COPIE` si défini). Un bandeau d'alerte apparaît pour l'administrateur si une
sauvegarde échoue ou n'a pas eu lieu depuis plus de 2 jours.

**Important** : le dossier `sauvegardes` est sur le même serveur que l'application. Configurez `BACKUP_COPIE`
vers un autre disque ou serveur pour être protégé d'une panne de ce serveur.

Restauration : arrêter l'application, copier la sauvegarde choisie en `tickets.db`, copier le dossier `fichiers`
de la sauvegarde si nécessaire, relancer.

## Mise en production

- `pip install waitress` puis `waitress-serve --port=5000 app:app` (service systemd sous Linux ; NSSM ou Planificateur
  de tâches sous Windows). Lancez **un seul processus** : les tâches planifiées et la sauvegarde tournent dans l'application.
- Pour le HTTPS, placez l'application derrière Nginx ou IIS avec un certificat interne.
- Les notifications du navigateur (hors fenêtre de la page) ne sont pas utilisées : l'alerte repose sur la fenêtre
  intégrée, le son et l'email, qui fonctionnent en HTTP simple.