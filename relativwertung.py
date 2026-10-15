"""BVDG-Relativabzug aus den bereits vorhandenen Vereins-CSV-Tabellen.

Es werden keine Werte interpoliert oder extrapoliert. Liegt das gemessene
Körpergewicht zwischen zwei Zeilen, gilt die nächste tabellierte Obergrenze.
Männer von 79,1 bis 95,5 kg haben spezielle Zehntelwerte.

Die Relativpunkte sind eine dynamisch berechnete Ansicht und keine DB-Spalte.
Damit ändern sich die Ansichten direkt beim Korrigieren von Versuchen oder
Stammdaten. Die Tabellen haben einen eingeschränkten Gewichtsbereich.
"""
from __future__ import annotations

from bisect import bisect_left
import csv
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path

TABLE_DIR = Path(__file__).resolve().parent / 'relativtabellen'


@lru_cache(maxsize=1)
def _tables() -> dict[str, tuple[list[Decimal], list[Decimal]]]:
    tables = {}
    for gender, file_name in (('m', 'Maenner.csv'), ('w', 'Frauen.csv')):
        with (TABLE_DIR / file_name).open('r', encoding='utf-8-sig', newline='') as fh:
            rows = list(csv.DictReader(fh))
        weights = [Decimal(row['bodyweight_kg']) for row in rows]
        deductions = [Decimal(row['deduction']) for row in rows]
        if (not rows or sorted(weights) != weights or len(set(weights)) != len(weights)
                or any(row['gender'].casefold() != gender for row in rows)):
            raise ValueError(f'Ungültige Relativtabelle: {file_name}')
        tables[gender] = weights, deductions
    return tables


def relativabzug(gender: str | None, bodyweight_kg: float | str | None) -> float | None:
    """Tabelle: genaue Zeile oder erste größere Zeile (Obergrenze).

    Für nicht abgedeckte Körpergewichte/Geschlechtsangaben wird None geliefert,
    damit nie ein frei geschätzter Abzug angezeigt wird.
    """
    gender = str(gender or '').casefold().strip()
    if gender not in ('m', 'w') or bodyweight_kg is None:
        return None
    try:
        weight = Decimal(str(bodyweight_kg))
    except (InvalidOperation, ValueError):
        return None
    if not weight.is_finite():
        return None
    weights, deductions = _tables()[gender]
    index = bisect_left(weights, weight)
    if index >= len(weights) or weight < weights[0]:
        return None
    return float(deductions[index])


def relativwerte(record: dict) -> dict:
    """Abzug, Disziplinpunkte und Gesamtpunkte für eine Wettkampfzeile.

    Eine positive Bestleistung zählt; eine fehlende/Null-Leistung nicht.
    Für nur eine dokumentierte Disziplin gilt nur ein Abzug (§57 SPO).
    Liegt ausschließlich ein Zweikampf vor, werden beide Abzüge berücksichtigt.
    """
    deduction = relativabzug(record.get('gender'), record.get('bodyweight_kg'))
    output = {'relative_deduction': deduction, 'relative_snatch': None,
              'relative_cj': None, 'relative_points': None}
    if deduction is None:
        return output

    def number(value):
        if value is None or str(value).strip() == '':
            return None
        try:
            number = Decimal(str(value))
            return number if number.is_finite() else None
        except (InvalidOperation, ValueError):
            return None

    best_s = number(record.get('snatch_best'))
    best_c = number(record.get('clean_jerk_best'))
    total = number(record.get('total_kg'))
    abzug = Decimal(str(deduction))
    if best_s is not None and best_s > 0:
        output['relative_snatch'] = float(best_s - abzug)
    if best_c is not None and best_c > 0:
        output['relative_cj'] = float(best_c - abzug)
    if output['relative_snatch'] is not None or output['relative_cj'] is not None:
        output['relative_points'] = round(sum(v for v in (output['relative_snatch'], output['relative_cj']) if v is not None), 1)
    elif total is not None and total > 0:
        output['relative_points'] = float(total - 2 * abzug)
    return output


def mit_relativwerten(results: list[dict]) -> list[dict]:
    return [{**r, **relativwerte(r)} for r in results]
