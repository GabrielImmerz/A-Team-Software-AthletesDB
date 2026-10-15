import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import database as db
from csv_import import read_csv
from domain import validate_result


class TestTracker(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db_path = Path(self.folder.name) / 'subfolder' / 'test.sqlite3'
        db.init_db(self.db_path)

    def tearDown(self):
        self.folder.cleanup()

    def test_csv_import_and_idempotence(self):
        source = (Path(__file__).resolve().parents[1] / 'beispiele' / 'wettkaempfe_beispiel.csv').read_bytes()
        rows, errors, _ = read_csv(source)
        self.assertEqual(len(rows), 8)
        self.assertEqual(errors, [])
        report = db.import_results(rows, db_path=self.db_path)
        self.assertEqual(report['neu'], 8)
        self.assertEqual(report['athleten_neu'], 2)
        self.assertEqual(report['wettkaempfe_neu'], 4)
        self.assertEqual(len(db.list_athletes(self.db_path)), 2)
        self.assertEqual(len(db.list_results(self.db_path)), 8)
        report_again = db.import_results(rows, db_path=self.db_path)
        self.assertEqual(report_again['übersprungen'], 8)
        self.assertEqual(len(db.list_results(self.db_path)), 8)

    def test_attempts_and_negative_failed_lifts(self):
        source = (Path(__file__).resolve().parents[1] / 'beispiele' / 'einzelversuche_beispiel.csv').read_bytes()
        rows, errors, _ = read_csv(source)
        self.assertFalse(errors)
        self.assertEqual(rows[0]['snatch_best'], 53.0)
        self.assertEqual(rows[0]['clean_jerk_best'], 68.0)
        self.assertEqual(rows[0]['total_kg'], 121.0)
        db.import_results(rows, db_path=self.db_path)
        result = db.list_results(self.db_path)[0]
        self.assertEqual(result['s2'], -53.0)
        self.assertEqual(result['total_kg'], 121.0)

    def test_deleting_athlete_cascades_only_their_results(self):
        source = (Path(__file__).resolve().parents[1] / 'beispiele' / 'wettkaempfe_beispiel.csv').read_bytes()
        rows, _, _ = read_csv(source)
        db.import_results(rows, db_path=self.db_path)
        athletes = db.list_athletes(self.db_path)
        db.delete_athlete(athletes[0]['id'], self.db_path)
        self.assertEqual(len(db.list_athletes(self.db_path)), 1)
        self.assertEqual(len(db.list_results(self.db_path)), 4)
        self.assertEqual(len(db.list_competitions(self.db_path)), 4)

    def test_bad_total_rejected(self):
        with self.assertRaises(ValueError):
            validate_result({'snatch_best': '45', 'clean_jerk_best': '65', 'total_kg': '120'})

    def test_bad_rows_skipped_in_preview(self):
        content = ('Athlet;Datum;Wettkampf;Reißen;Stoßen\n'
                   'Anna Test;01.02.2026;Pokal;50;60\n'
                   'Bob Test;01.02.2026;Pokal;ups;70\n').encode('utf-8')
        rows, errors, _ = read_csv(content)
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn('Zeile 3',errors[0])

    def test_transactional_rollback_for_invalid_id(self):
        source = ('athleten_id;Datum;Wettkampf;Reißen;Stoßen\n'
                  '999;2026-01-01;Test;40;50\n').encode('utf-8')
        rows, errors, _ = read_csv(source)
        self.assertFalse(errors)
        with self.assertRaises(ValueError):
            db.import_results(rows,db_path=self.db_path)
        self.assertEqual(db.list_competitions(self.db_path),[])
        self.assertEqual(db.list_results(self.db_path),[])

    def test_ambiguous_names_rollback(self):
        db.add_athlete('Max','Muster',db_path=self.db_path)
        db.add_athlete('Max','Muster',db_path=self.db_path)
        content = 'Athlet;Datum;Wettkampf;Reißen\nMax Muster;01.01.2026;Test;50\n'.encode()
        rows, _, _ = read_csv(content)
        with self.assertRaisesRegex(ValueError,'Mehrere Athleten'):
            db.import_results(rows,db_path=self.db_path)
        self.assertFalse(db.list_competitions(self.db_path))

    def test_upsert_and_backup(self):
        a = db.add_athlete('Mira','Muster',db_path=self.db_path)
        comp = db.create_competition('Test','2026-10-14','Ulm',db_path=self.db_path)
        state = db.save_result(a,comp,{'snatch_best': 51,'clean_jerk_best':70},db_path=self.db_path)
        self.assertEqual(state,'neu')
        state = db.save_result(a,comp,{'snatch_best': 53,'clean_jerk_best':72},db_path=self.db_path)
        self.assertEqual(state,'aktualisiert')
        self.assertEqual(db.list_results(self.db_path)[0]['total_kg'],125)
        backup = db.backup_bytes(self.db_path)
        dest = Path(self.folder.name)/'restored.sqlite3'
        dest.write_bytes(backup)
        self.assertEqual(len(db.list_results(dest)),1)

    def test_cannot_insert_invalid_result(self):
        athlete = db.add_athlete('Anna','Test',db_path=self.db_path)
        comp = db.create_competition('Turnier','2026-01-20',db_path=self.db_path)
        with self.assertRaises(ValueError):
            db.save_result(athlete,comp,{'snatch_best':-20},db_path=self.db_path)
        self.assertEqual(db.list_results(self.db_path),[])


if __name__=='__main__':
    unittest.main()
