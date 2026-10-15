# 🏋️ Gewichtheben Tracker

Eine lokal laufende Vereinssoftware für **Gewichtheben-Wettkämpfe** mit **Python**, **Streamlit** und **SQLite**. Der Browser zeigt die Oberfläche; die Daten bleiben in einer lokalen Datenbank auf dem eigenen Rechner.

## Funktionen

- Athleten anlegen, Stammdaten ändern, deaktivieren oder mit allen gespeicherten Ergebnissen löschen
- Wettkämpfe anlegen/löschen und Ergebnisse manuell erfassen/ändern/löschen
- CSV-Import ganzer Wettkämpfe, mit automatischer Anlage unbekannter Athleten und Wettkämpfe
- Einlesen von Ergebnissen als Bestleistungen **oder** sechs Einzelversuchen (gültig `+`, ungültig `-`)
- Automatisches Ermitteln von Reißen, Stoßen und Zweikampf aus Einzelversuchen
- Interaktive Karriere-Diagramme, persönliche Wettkampfbestleistungen, Athletenvergleich
- CSV-Export, vollständiges SQLite-Backup; doppelt importierte Ergebnisse werden standardmäßig übersprungen

## Installation unter Windows

1. **Python ab Version 3.10** von [python.org](https://www.python.org/downloads/) installieren (beim Installieren **„Add Python to PATH“** auswählen).
2. Den ZIP-Ordner entpacken.
3. **`start_windows.bat` doppelklicken.** Beim ersten Start werden automatisch benötigte Python-Pakete installiert. Dazu ist einmalig eine Internetverbindung nötig.
4. Im Browser **http://localhost:8501** öffnen, falls er nicht automatisch erscheint.
5. Zum Beenden das Konsolenfenster schließen oder `Strg+C` drücken.

Falls Windows eine Ausführungswarnung anzeigt, kannst du statt der BAT-Datei folgende Befehle selbst im Terminal im entpackten Ordner ausführen:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
```

## Start auf macOS / Linux

```bash
./start_mac_linux.sh
```

Oder manuell mit `python3 -m venv .venv`, Pakete aus `requirements.txt` installieren, `python -m streamlit run app.py`.

## CSV-Format

Beispiele findest du in **`beispiele/wettkaempfe_beispiel.csv`** und **`beispiele/einzelversuche_beispiel.csv`**, die sich auch direkt in der Software herunterladen lassen.

**Einfache Variante** (Semikolon als Trennzeichen, Komma als Dezimalzeichen):

```csv
Athlet;Datum;Wettkampf;Ort;Körpergewicht;Reißen;Stoßen;Zweikampf
Mira Muster;10.02.2024;Frühjahrs-Cup;Augsburg;58,6;48;63;111
Leon Beispiel;10.02.2024;Frühjahrs-Cup;Augsburg;80,1;85;112;197
```

Pflichtspalten sind `Datum`, `Wettkampf`, eine Athletenangabe (`Athlet` oder `Vorname` und `Nachname` oder `athleten_id`) und mindestens eine Leistung (`Reißen`, `Stoßen`, `Zweikampf` oder Einzelversuche).

Unterstützte weitere Spalten: `Geschlecht`, `Gewichtsklasse`, `Platz`, `Bemerkung`, Einzelversuche `s1`, `s2`, `s3`, `c1`, `c2`, `c3` (alternativ z. B. `Reißen 1` oder `Stoßen 2`). Gültiger Versuch = **positives** Gewicht; ungültiger = **negatives** Gewicht; leeres Feld = nicht gestartet. Bei einem Fehlversuch zählt das negative Gewicht nicht zum Bestwert. Die Software kontrolliert, ob angegebene Bestwerte und Zweikampf zusammenpassen.

Akzeptiert werden UTF-8 und Windows-1252, Semikolon-, Komma- und Tab-getrennte Dateien, Datumsangaben `TT.MM.JJJJ` oder `JJJJ-MM-TT`, Dezimalpunkt oder -komma.

**Wichtig bei Namensgleichheit:** Falls zwei Athleten identische Vor- und Nachnamen besitzen, im CSV die Spalte `athleten_id` benutzen (die ID sieht man in der Athletenansicht). Beim Import einer CSV mit Vor- und Nachname wird das letzte Wort eines Vollnamens als Nachname interpretiert. Bei zusammengesetzten Nachnamen besser getrennte Spalten verwenden.

Beim Import wird eine Vorschau angezeigt. Ungültige Zeilen werden mit Fehlermeldung verworfen; gültige Zeilen können anschließend importiert werden. Alle gültigen Zeilen eines Imports werden **in einer Datenbanktransaktion** gespeichert. Existiert bereits ein Ergebnis derselben Person zum selben Wettkampf (Datum, Name, Ort), wird es standardmäßig übersprungen oder auf Wunsch aktualisiert.

## Wo werden Daten gespeichert?

In **`data/verein.sqlite3`**. Die Datei wird beim ersten Start automatisch angelegt. Du kannst regelmäßig unter **„Export & Sicherung“** ein vollständiges Datenbank-Backup herunterladen. Zum Wiederherstellen: Programm beenden, die Datei `data/verein.sqlite3` durch dein Backup ersetzen und neu starten. Sicherungen enthalten personenbezogene Daten; geschützt aufbewahren.

Wenn mehrere Installationen auf demselben Rechner verschiedene Vereine verwalten sollen, kann der Speicherort über die Umgebungsvariable `GEWICHTHEBEN_DB` geändert werden.

## Hinweise / Grenzen

- Software für **einen lokal genutzten Vereinsrechner**. Keine Anmeldung, kein Mehrbenutzer-Rechtemanagement, **nicht direkt ins öffentliche Internet stellen**.
- Es handelt sich um eine lokale Einzelplatzlösung; paralleles Lesen funktioniert, gleichzeitiges Erfassen mehrerer Personen ist nicht als vollwertiger Vereinsserver ausgelegt.
- Persönliche Bestleistungen sind **Wettkampf-Bestwerte aus den hinterlegten Daten**, keine Trainingsrekorde und keine alters- oder körpergewichtsbereinigten Punkte.
- Die Ergebnisse sind je Athlet/Wettkampf eindeutig. Bei einer Veranstaltung mit mehreren getrennten Starts müssten zwei unterschiedliche Wettkampfbezeichnungen verwendet werden.
- Bei der manuellen Korrektur eines bestehenden Ergebnisses werden Einzelversuche durch die korrigierten Bestwerte ersetzt.
- Beispiel-CSV enthält ausschließlich fiktive Personen und Wettkämpfe und wird **nicht automatisch** in deine Datenbank geladen.

## Tests ausführen (optional)

```bash
python -m unittest discover -s tests -v
```

Quellcode: `app.py` (Oberfläche), `database.py` (SQLite), `csv_import.py` (CSV), `domain.py` (Validierung).
