# A-Team Athlete DB — UI-Update 1.8

Dieses Update basiert auf `app.py` aus Version 1.7 und enthält **nur Änderungen an der Oberfläche**:

1. **Athleten:** zuerst „Profil & Verwaltung“, danach „Neuen Athleten anlegen“.
2. **Wettkämpfe:** zuerst „Ergebnisse verwalten“, dann „Wettkämpfe verwalten“, zuletzt „Ergebnis erfassen“.
3. **Athletenauswahl** im Profil: alphabetisch nach Nachname (bei Gleichstand nach Vorname), angezeigt ohne `#ID`. Die Zuordnung erfolgt weiterhin über die unveränderte ID.

## Installieren

1. ZIP entpacken.
2. `app.py` im Hauptverzeichnis des GitHub-Repositories `GabrielImmerz/A-Team-Software-AthletesDB` durch die neue Datei ersetzen.
3. Änderung committen. Streamlit Community Cloud übernimmt den neuen Code automatisch.

**Keine Änderungen an Neon, Secrets oder anderen Python-Dateien erforderlich.**

Hinweis: Zwei Athleten mit identischem Vor- und Nachnamen sehen in der Liste gleich aus. Sie bleiben über ihre IDs eindeutig zugeordnet; die Namen sind dann jedoch in der Auswahl nicht unterscheidbar.
