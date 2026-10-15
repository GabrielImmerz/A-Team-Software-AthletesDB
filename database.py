"""SQLite-Datenbank: Athleten, Wettkämpfe, Ergebnisse und Sicherungen."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import os
import sqlite3
import tempfile

from domain import ATTEMPTS, gender_code, normalized_name, parse_date, safe_name, text, validate_result

BASE = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('GEWICHTHEBEN_DB', str(BASE / 'data' / 'verein.sqlite3')))

SCHEMA = '''
CREATE TABLE IF NOT EXISTS athletes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name TEXT NOT NULL,
  last_name TEXT NOT NULL,
  gender TEXT NOT NULL DEFAULT '-',
  birth_year INTEGER,
  notes TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS competitions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL COLLATE NOCASE,
  event_date TEXT NOT NULL,
  location TEXT NOT NULL DEFAULT '' COLLATE NOCASE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(name, event_date, location)
);
CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  athlete_id INTEGER NOT NULL REFERENCES athletes(id) ON DELETE CASCADE,
  competition_id INTEGER NOT NULL REFERENCES competitions(id) ON DELETE CASCADE,
  bodyweight_kg REAL,
  weight_class TEXT NOT NULL DEFAULT '',
  s1 REAL, s2 REAL, s3 REAL,
  c1 REAL, c2 REAL, c3 REAL,
  snatch_best REAL,
  clean_jerk_best REAL,
  total_kg REAL,
  placing INTEGER,
  notes TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(athlete_id, competition_id)
);
CREATE INDEX IF NOT EXISTS idx_results_athlete ON results(athlete_id);
CREATE INDEX IF NOT EXISTS idx_results_competition ON results(competition_id);
CREATE INDEX IF NOT EXISTS idx_competitions_date ON competitions(event_date);
'''


@contextmanager
def connect(db_path: str | Path | None = None):
    path = Path(db_path) if db_path else DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=15000')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path=None):
    with connect(db_path) as c:
        c.executescript(SCHEMA)


def list_athletes(db_path=None):
    with connect(db_path) as c:
        return [dict(r) for r in c.execute('SELECT * FROM athletes ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE, id')]


def add_athlete(first_name, last_name, gender='-', birth_year=None, notes='', active=True, db_path=None):
    first, last = safe_name(first_name, 'Vorname'), safe_name(last_name, 'Nachname')
    year = validate_year(birth_year)
    with connect(db_path) as c:
        cur = c.execute('''INSERT INTO athletes(first_name,last_name,gender,birth_year,notes,active)
             VALUES(?,?,?,?,?,?)''', (first, last, gender_code(gender), year, text(notes)[:2000], int(active)))
        return cur.lastrowid


def validate_year(value):
    if value is None or text(value) == '':
        return None
    year = int(value)
    if year < 1900 or year > datetime.today().year:
        raise ValueError('Geburtsjahr liegt außerhalb des gültigen Bereichs.')
    return year


def edit_athlete(athlete_id, first_name, last_name, gender='-', birth_year=None, notes='', active=True, db_path=None):
    first, last = safe_name(first_name, 'Vorname'), safe_name(last_name, 'Nachname')
    with connect(db_path) as c:
        cur = c.execute('''UPDATE athletes SET first_name=?,last_name=?,gender=?,birth_year=?,notes=?,active=? WHERE id=?''',
              (first, last, gender_code(gender), validate_year(birth_year), text(notes)[:2000], int(active), athlete_id))
        if cur.rowcount == 0:
            raise ValueError('Athlet wurde nicht gefunden.')


def delete_athlete(athlete_id, db_path=None):
    with connect(db_path) as c:
        cur = c.execute('DELETE FROM athletes WHERE id=?', (athlete_id,))
        if cur.rowcount == 0:
            raise ValueError('Athlet wurde nicht gefunden.')


def create_competition(name, event_date, location='', db_path=None):
    name = safe_name(name, 'Wettkampf')
    date = parse_date(event_date)
    loc = text(location)[:200]
    with connect(db_path) as c:
        return _get_or_create_competition(c, name, date, loc)


def _get_or_create_competition(c, name, date, location):
    c.execute('INSERT OR IGNORE INTO competitions(name,event_date,location) VALUES (?,?,?)', (name, date, location))
    row = c.execute('SELECT id FROM competitions WHERE name=? COLLATE NOCASE AND event_date=? AND location=? COLLATE NOCASE',
                    (name, date, location)).fetchone()
    return row['id']


def list_competitions(db_path=None):
    with connect(db_path) as c:
        return [dict(r) for r in c.execute('''SELECT c.*, COUNT(r.id) AS starts
        FROM competitions c LEFT JOIN results r ON r.competition_id=c.id
        GROUP BY c.id ORDER BY c.event_date DESC, c.name''')]


def delete_competition(competition_id, db_path=None):
    with connect(db_path) as c:
        c.execute('DELETE FROM competitions WHERE id=?', (competition_id,))


_RESULT_FIELDS = ('bodyweight_kg','weight_class',*ATTEMPTS,'snatch_best','clean_jerk_best','total_kg','placing','notes')


def _write_result(c, athlete_id: int, competition_id: int, data: dict, overwrite=True):
    exists = c.execute('SELECT id FROM results WHERE athlete_id=? AND competition_id=?',
                       (athlete_id, competition_id)).fetchone()
    if exists and not overwrite:
        return 'übersprungen'
    values = validate_result(data)
    fields = ','.join(_RESULT_FIELDS)
    placeholders = ','.join('?' for _ in _RESULT_FIELDS)
    c.execute(f'''INSERT INTO results(athlete_id,competition_id,{fields}) VALUES(?,?,{placeholders})
        ON CONFLICT(athlete_id,competition_id) DO UPDATE SET
        {','.join(f'{f}=excluded.{f}' for f in _RESULT_FIELDS)}''',
        [athlete_id, competition_id, *(values[f] for f in _RESULT_FIELDS)])
    return 'aktualisiert' if exists else 'neu'


def save_result(athlete_id, competition_id, data, overwrite=True, db_path=None):
    with connect(db_path) as c:
        return _write_result(c, athlete_id, competition_id, data, overwrite)


def delete_result(result_id, db_path=None):
    with connect(db_path) as c:
        c.execute('DELETE FROM results WHERE id=?', (result_id,))


def list_results(db_path=None):
    with connect(db_path) as c:
        return [dict(r) for r in c.execute('''SELECT r.*, a.first_name, a.last_name, a.gender,
        c.name AS competition_name, c.event_date, c.location
        FROM results r JOIN athletes a ON a.id=r.athlete_id
        JOIN competitions c ON c.id=r.competition_id
        ORDER BY c.event_date, c.name, a.last_name, a.first_name, r.id''')]


def import_results(parsed_rows: list[dict], *, overwrite=False, db_path=None):
    """Transaktionaler Import: einmalige Namen müssen eindeutig einem Athleten entsprechen."""
    stats = {'neu': 0, 'aktualisiert': 0, 'übersprungen': 0, 'athleten_neu': 0, 'wettkaempfe_neu': 0}
    with connect(db_path) as c:
        # Fail-fast: validate every result before database changes.
        for row in parsed_rows:
            validate_result(row)
        for row in parsed_rows:
            aid = row.get('athlete_id')
            if aid is not None:
                athlete = c.execute('SELECT id FROM athletes WHERE id=?', (aid,)).fetchone()
                if not athlete:
                    raise ValueError(f'Athleten-ID {aid} existiert nicht.')
            else:
                all_matches = c.execute('SELECT id, first_name, last_name FROM athletes').fetchall()
                matches = [a for a in all_matches if normalized_name(a['first_name']) == normalized_name(row['first_name'])
                           and normalized_name(a['last_name']) == normalized_name(row['last_name'])]
                if len(matches) > 1:
                    raise ValueError(f'Mehrere Athleten heißen {row["first_name"]} {row["last_name"]}. Bitte Spalte athleten_id verwenden.')
                if matches:
                    aid = matches[0]['id']
                else:
                    cur = c.execute('INSERT INTO athletes(first_name,last_name,gender) VALUES(?,?,?)',
                                    (safe_name(row['first_name'], 'Vorname'), safe_name(row['last_name'], 'Nachname'),
                                     gender_code(row.get('gender'))))
                    aid = cur.lastrowid
                    stats['athleten_neu'] += 1
            name = safe_name(row['competition_name'], 'Wettkampf')
            event_date = parse_date(row['event_date'])
            loc = text(row.get('location'))[:200]
            old = c.execute('SELECT id FROM competitions WHERE name=? COLLATE NOCASE AND event_date=? AND location=? COLLATE NOCASE',
                            (name,event_date,loc)).fetchone()
            cid = _get_or_create_competition(c, name, event_date, loc)
            if not old:
                stats['wettkaempfe_neu'] += 1
            state = _write_result(c, aid, cid, row, overwrite=overwrite)
            stats[state] += 1
    return stats


def backup_bytes(db_path=None):
    """Konsistentes SQLite-Backup auch während die App geöffnet ist (WAL-fähig)."""
    with tempfile.TemporaryDirectory() as folder:
        target = Path(folder) / 'backup.sqlite3'
        with connect(db_path) as source:
            dest = sqlite3.connect(str(target))
            try:
                source.backup(dest)
            finally:
                dest.close()
        return target.read_bytes()
