# A-Team Athlete DB: dauerhafte Speicherung auf Streamlit Cloud

Die Anwendung unterstützt **SQLite lokal** und **PostgreSQL auf Streamlit Community Cloud**.
Sobald `DATABASE_URL` in den Streamlit-Secrets hinterlegt ist, verwendet die Anwendung PostgreSQL.
**Es ist keine Migration nötig**, wenn du mit einer leeren Datenbank starten möchtest.

## 1. Datenbank erstellen

1. Unter https://neon.tech/ ein Projekt anlegen (PostgreSQL). Für Vereinsdaten möglichst eine EU-Region wählen und vorher Datenschutz/Vertragsbedingungen prüfen.
2. Die **Connection string / Datenbank-URL** aus dem Neon-Dashboard kopieren. Beispiel (NUR PLATZHALTER):

   `postgresql://USER:PASSWORT@HOST/neondb?sslmode=require`

3. Es wird **kein** SQL-Skript per Hand benötigt. Die Tabellen werden beim ersten App-Start angelegt.

## 2. Streamlit Secrets einrichten

1. Unter https://share.streamlit.io/ die App `a-team-athlete-db` öffnen.
2. Menü der App -> **Settings** -> **Secrets** (je nach Oberfläche auch **Edit secrets**).
3. Diese zwei Einträge mit deinen echten Werten einfügen:

   ```toml
   DATABASE_URL = "postgresql://USER:PASSWORT@HOST/neondb?sslmode=require"
   APP_PASSWORD = "HIER-EIN-LANGES-EINZIGARTIGES-VEREINS-PASSWORT"
   ```

   `APP_PASSWORD` schützt diese erste Version mit einem **gemeinsamen Zugangspasswort**.
   Das ist kein echtes Benutzer-/Rechtesystem und sollte nur einem kleinen berechtigten Kreis mitgeteilt werden.

4. Speichern. Teile Datenbank-URL und Zugangspasswort **niemals im Chat oder über GitHub**.

## 3. Dateien auf GitHub ersetzen

Im Hauptverzeichnis deines Repositories diese Dateien ersetzen/ergänzen:

- `app.py` (ersetzen)
- `database.py` (ersetzen)
- `postgres_backend.py` (**neu**)
- `requirements.txt` (ersetzen, zusätzliche Bibliothek)
- `.gitignore` (ergänzen)
- `.streamlit/config.toml` (ändern; `address = "127.0.0.1"` entfernen)

Die übrigen Dateien bleiben unverändert. Streamlit installiert die Bibliotheken und startet die App nach dem Commit erneut.
Falls die Dateien im Repo direkt im Hauptverzeichnis liegen, **nicht** den ZIP-Überordner hochladen.

## 4. Kurztest

1. App öffnen: https://a-team-athlete-db.streamlit.app
2. Mit `APP_PASSWORD` anmelden.
3. Testathleten anlegen.
4. Seite neu laden und einen Neustart auslösen. Der Athlet sollte weiterhin vorhanden sein.
5. Beispiel-CSV importieren; Auswertungen und ZIP-Datenexport prüfen.

## Datensicherung und Datenschutz

- PostgreSQL-Daten bleiben bei einem Streamlit-Neustart bestehen, solange der Datenbankdienst und das Projekt vorhanden sind.
- Unter **Export & Sicherung** ist ein ZIP-/JSON-Export für eigene Aufbewahrung verfügbar. **Dies ist kein automatischer Restore.** Prüfe zusätzlich beim DB-Anbieter Möglichkeiten für Backups/Wiederherstellung.
- Die alte öffentliche Datei `data/verein.sqlite3` gehört nicht in GitHub. Prüfe, ob sie echte Personendaten enthält; entferne sie gegebenenfalls auch aus der Git-Historie.
- `.gitignore` verhindert **neue** Git-Aufnahmen, entfernt aber bereits versionierte Dateien nicht.
- Verwende für produktive Vereinsdaten eine nichtöffentliche Anwendung oder verlässliche Zugriffssteuerung. Das gemeinsame Passwort ist nur ein einfacher Anfangsschutz.
- Für personenbezogene Daten (insbesondere Minderjährige) muss der Verein Zugriffsrechte, Einwilligung/Rechtsgrundlage, Hosting und Auftragsverarbeitung passend prüfen.

## Technischer Hinweis

Die 9 vorhandenen SQLite-Tests bleiben unverändert und können mit
`python -m unittest discover -s tests -v` ausgeführt werden.
Die Verbindung zu Neon und die Cloud-Anmeldung müssen nach Eintragen der echten Zugangsdaten in der bereitgestellten App getestet werden.
