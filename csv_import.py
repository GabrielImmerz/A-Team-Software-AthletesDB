"""CSV-Import mit deutschen/englischen Spalten, verschiedenen Trennzeichen und Datumsformaten."""
from __future__ import annotations

import csv
from io import StringIO

from domain import ATTEMPTS, csv_header_key, gender_code, parse_date, safe_name, text, validate_result

ALIASES = {
    'athlete_id': ['athleten_id', 'athlete_id', 'athletid', 'athleteid'],
    'first_name': ['vorname', 'firstname', 'first_name'],
    'last_name': ['nachname', 'lastname', 'last_name'],
    'full_name': ['athlet', 'athletin', 'name', 'athlete', 'athletenname', 'sportler'],
    'gender': ['geschlecht', 'gender', 'sex'],
    'competition_name': ['wettkampf', 'competition', 'meet', 'veranstaltung', 'wettkampfname'],
    'event_date': ['datum', 'date', 'wettkampfdatum', 'eventdate'],
    'location': ['ort', 'location', 'veranstaltungsort'],
    'bodyweight_kg': ['koerpergewicht', 'körpergewicht', 'bodyweight', 'bodyweightkg', 'kgkoerpergewicht', 'kg'],
    'weight_class': ['gewichtsklasse', 'weightclass', 'klasse'],
    'snatch_best': ['reissen', 'reißen', 'snatch', 'bestreissen', 'bestesreissen', 'snatchbest'],
    'clean_jerk_best': ['stossen', 'stoßen', 'stoss', 'stoß', 'cleanjerk', 'cleanandjerk', 'cj', 'beststossen'],
    'total_kg': ['zweikampf', 'total', 'gesamt', 'gesamtleistung', 'total_kg', 'totalpunkt'],
    'placing': ['platz', 'platzierung', 'placing', 'rank'],
    'notes': ['notiz', 'notizen', 'notes', 'bemerkung', 'kommentar'],
}
for name in ATTEMPTS:
    kind = 'reissen' if name[0] == 's' else 'stossen'
    english = 'snatch' if name[0] == 's' else 'cleanjerk'
    num = name[1]
    ALIASES[name] = [name, f'{kind}{num}', f'{kind}versuch{num}', f'{english}{num}', f'{english}attempt{num}']

LOOKUP = {}
for canonical, aliases in ALIASES.items():
    for alias in aliases:
        key = csv_header_key(alias)
        if key in LOOKUP and LOOKUP[key] != canonical:
            raise RuntimeError(f'Ambige CSV-Spaltenzuordnung: {alias}')
        LOOKUP[key] = canonical


def _decoded(raw: bytes) -> str:
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('Datei ist nicht als UTF-8 oder Windows-1252 lesbar.')


def read_csv(raw: bytes) -> tuple[list[dict], list[str], dict]:
    """Liefert geprüfte Zeilen, Fehler und Metadaten (ohne DB-Veränderungen)."""
    if not raw:
        raise ValueError('Die CSV-Datei ist leer.')
    if len(raw) > 10 * 1024 * 1024:
        raise ValueError('CSV-Datei ist größer als 10 MB.')
    content = _decoded(raw).lstrip('\ufeff')
    try:
        dialect = csv.Sniffer().sniff(content[:8192], delimiters=';,\t')
        delim = dialect.delimiter
    except csv.Error:
        delim = ';' if content.splitlines()[0].count(';') else ','
    reader = csv.DictReader(StringIO(content), delimiter=delim)
    if not reader.fieldnames:
        raise ValueError('Die CSV-Datei hat keine Kopfzeile.')
    headers = {}
    for original in reader.fieldnames:
        key = LOOKUP.get(csv_header_key(original))
        if key:
            if key in headers:
                raise ValueError(f'Spalte {key} kommt mehrfach vor.')
            headers[key] = original
    for required in ('competition_name', 'event_date'):
        if required not in headers:
            raise ValueError(f'Pflichtspalte fehlt: {required} (Wettkampf/Datum).')
    if 'athlete_id' not in headers and 'full_name' not in headers and not {'first_name','last_name'}.issubset(headers):
        raise ValueError('Benötigt: Athlet, Vorname + Nachname oder athleten_id.')
    if not any(k in headers for k in ('snatch_best','clean_jerk_best','total_kg', *ATTEMPTS)):
        raise ValueError('Leistungsspalten fehlen: z. B. Reißen, Stoßen oder Zweikampf.')

    parsed, errors = [], []
    for line_no, orig in enumerate(reader, start=2):
        if None in orig:
            errors.append(f'Zeile {line_no}: Zu viele Spalten. Trennzeichen überprüfen.')
            continue
        if not any(text(v) for v in orig.values()):
            continue
        row = {key: text(orig.get(column)) for key, column in headers.items()}
        try:
            aid = row.get('athlete_id', '')
            if aid:
                try:
                    row['athlete_id'] = int(aid)
                except ValueError as exc:
                    raise ValueError('athleten_id muss eine ganze Zahl sein.') from exc
                if row['athlete_id'] <= 0:
                    raise ValueError('athleten_id muss positiv sein.')
            else:
                row['athlete_id'] = None
            if row.get('full_name') and (not row.get('first_name') or not row.get('last_name')):
                parts = row['full_name'].split()
                if len(parts) < 2:
                    raise ValueError('Athlet muss Vorname und Nachname enthalten.')
                row['first_name'] = ' '.join(parts[:-1])
                row['last_name'] = parts[-1]
            if row['athlete_id'] is None:
                row['first_name'] = safe_name(row.get('first_name'), 'Vorname')
                row['last_name'] = safe_name(row.get('last_name'), 'Nachname')
            row['competition_name'] = safe_name(row.get('competition_name'), 'Wettkampf')
            row['event_date'] = parse_date(row.get('event_date'))
            row['gender'] = gender_code(row.get('gender'))
            cleaned = validate_result(row)
            parsed.append({**row, **cleaned, 'location': row.get('location','')})
        except ValueError as exc:
            errors.append(f'Zeile {line_no}: {exc}')
    return parsed, errors, {'delimiter': delim, 'columns': list(headers), 'count': len(parsed) + len(errors)}
