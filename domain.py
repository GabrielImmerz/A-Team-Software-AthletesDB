"""Validierung und Berechnung der Gewichtheber-Ergebnisse."""
from __future__ import annotations

from datetime import datetime
import math
import re
import unicodedata

ATTEMPTS = ('s1', 's2', 's3', 'c1', 'c2', 'c3')


def format_attempt(value: float | None, *, blank: str = '-') -> str:
    """Darstellung: 94 gültig, x94 ungültig, v Verzicht, - kein Start.

    Im bestehenden REAL-Datenbankfeld wird Verzicht als 0.0 gespeichert.
    NULL (None) bedeutet: kein Versuch/nicht angetreten. Es ist keine
    PostgreSQL-Tabellenänderung erforderlich.
    """
    if value is None:
        return blank
    number = float(value)
    if number == 0:
        return 'v'
    return ('x' if number < 0 else '') + f'{abs(number):g}'.replace('.', ',')


def parse_attempt(value: object, label: str) -> float | None:
    """Akzeptiert 94, x94, -94, v, - und leer.

    Numerische 0.0 aus der Datenbank repräsentiert bewusst 'v'.
    Der CSV-Text '0' ist dagegen kein Verzicht und wird als leer behandelt.
    """
    if isinstance(value, str):
        value = value.strip()
        if value.casefold() == 'v':
            return 0.0
        if value in ('', '-'):
            return None
        return parse_float(value, label, allow_negative=True, zero_as_none=True)
    if value is None:
        return None
    return parse_float(value, label, allow_negative=True, zero_as_none=False)


def text(value: object) -> str:
    return str(value).strip() if value is not None else ''


def normalized_name(value: str) -> str:
    return ' '.join(text(value).casefold().split())


def safe_name(value: object, label: str) -> str:
    result = ' '.join(text(value).split())
    if not result or len(result) > 100:
        raise ValueError(f'{label} muss zwischen 1 und 100 Zeichen lang sein.')
    return result


def parse_date(value: object) -> str:
    if hasattr(value, 'strftime'):
        return value.strftime('%Y-%m-%d')
    s = text(value)
    for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f'Ungültiges Datum: {s!r} (erlaubt: TT.MM.JJJJ oder JJJJ-MM-TT).')


def parse_float(value: object, label: str, *, allow_negative: bool = False, zero_as_none: bool = False, max_kg: float = 500) -> float | None:
    if value is None or text(value) == '':
        return None
    if isinstance(value, str):
        s = value.strip().replace(' ', '').replace('\u00a0', '')
        # 1.234,5 wird nicht gebraucht; Dezimalkomma und -punkt unterstützen.
        # Für Einzelversuche steht x94 (oder X94/×94) für einen ungültigen Versuch.
        if allow_negative and re.fullmatch(r'[xX×]\d+(?:[,.]\d+)?', s):
            s = '-' + s[1:]
        if not re.fullmatch(r'[+-]?\d+(?:[,.]\d+)?', s):
            raise ValueError(f'{label}: {value!r} ist keine gültige Zahl.')
        s = s.replace(',', '.')
        number = float(s)
    else:
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'{label}: ungültiger Zahlenwert.') from exc
    if not math.isfinite(number):
        raise ValueError(f'{label}: Zahl muss endlich sein.')
    if abs(number) > max_kg or (number < 0 and not allow_negative):
        raise ValueError(f'{label}: Gewicht außerhalb des erlaubten Bereichs.')
    if zero_as_none and number == 0:
        return None
    return round(number, 3)


def gender_code(value: object) -> str:
    s = text(value).casefold()
    options = {
        'm': 'm', 'mann': 'm', 'männlich': 'm', 'maennlich': 'm', 'male': 'm',
        'w': 'w', 'frau': 'w', 'weiblich': 'w', 'female': 'w', 'f': 'w',
        'd': 'd', 'divers': 'd', 'diverse': 'd', 'x': 'd',
        '': '-', '-': '-', 'offen': '-', 'keine angabe': '-', 'unbekannt': '-',
    }
    if s not in options:
        raise ValueError('Geschlecht muss m, w, d oder leer sein.')
    return options[s]


def validate_result(data: dict) -> dict:
    """Versuche: positiv gültig, negativ ungültig, 0 Verzicht, NULL kein Start."""
    values = {}
    for name in ATTEMPTS:
        values[name] = parse_attempt(data.get(name), name)
    values['bodyweight_kg'] = parse_float(data.get('bodyweight_kg'), 'Körpergewicht', zero_as_none=True)
    if values['bodyweight_kg'] is not None and not (20 <= values['bodyweight_kg'] <= 400):
        raise ValueError('Körpergewicht muss zwischen 20 und 400 kg liegen.')
    values['weight_class'] = text(data.get('weight_class'))[:40]
    values['placing'] = None
    if text(data.get('placing')):
        try:
            placing = int(text(data['placing']))
        except ValueError as exc:
            raise ValueError('Platzierung muss eine positive ganze Zahl sein.') from exc
        if placing < 1:
            raise ValueError('Platzierung muss mindestens 1 sein.')
        values['placing'] = placing
    values['notes'] = text(data.get('notes'))[:2000]

    for prefix, target in (('s', 'snatch_best'), ('c', 'clean_jerk_best')):
        attempts = [values[f'{prefix}{i}'] for i in range(1, 4)]
        known_attempts = [v for v in attempts if v is not None]
        valid = [v for v in known_attempts if v > 0]
        best_from_attempts = max(valid, default=None)
        provided_best = parse_float(data.get(target), target, zero_as_none=True)
        if known_attempts:
            if provided_best is not None and (
                best_from_attempts is None or abs(best_from_attempts - provided_best) > 0.011
            ):
                raise ValueError(f'{target}: Bestwert passt nicht zu den gültigen Einzelversuchen.')
            values[target] = best_from_attempts
        else:
            values[target] = provided_best

    snatch, cj = values['snatch_best'], values['clean_jerk_best']
    provided_total = parse_float(data.get('total_kg'), 'Zweikampf', max_kg=1000,
                                 zero_as_none=True)
    if snatch is not None and snatch > 0 and cj is not None and cj > 0:
        calculated_total = round(snatch + cj, 3)
        if provided_total is not None and abs(calculated_total - provided_total) > 0.011:
            raise ValueError('Zweikampf passt nicht zu Reißen + Stoßen.')
        values['total_kg'] = calculated_total
    else:
        # Bestehende historische CSV-Dateien mit ausschließlich einem
        # Zweikampfwert weiterhin akzeptieren. Sobald aber mindestens eine
        # Teildisziplin erfasst ist, darf kein Zweikampf vorgetäuscht werden.
        if provided_total is not None and (snatch is not None or cj is not None or
                                           any(values[a] is not None for a in ATTEMPTS)):
            raise ValueError('Zweikampf nur bei gültiger Leistung in Reißen UND Stoßen.')
        values['total_kg'] = provided_total if snatch is None and cj is None else None

    has_entry = (snatch is not None or cj is not None or values['total_kg'] is not None
                 or any(values[a] is not None for a in ATTEMPTS))
    if not has_entry:
        raise ValueError('Mindestens ein Versuch, Startstatus oder Ergebnis ist erforderlich.')
    return values


def csv_header_key(value: object) -> str:
    s = text(value).casefold().replace('ß', 'ss').replace('ø', 'o')
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]', '', s)
