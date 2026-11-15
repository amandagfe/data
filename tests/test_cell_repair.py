import argparse
import hashlib
import importlib.util
import pathlib
import sqlite3
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "weather_pipeline.py"
SPEC = importlib.util.spec_from_file_location("weather_pipeline_repair", SCRIPT)
WEATHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WEATHER)


def build_ledger(run_dir: pathlib.Path, cache_bytes: bytes, recorded_hash: str) -> None:
    cache = run_dir / "cache" / "1_1.json"
    cache.parent.mkdir(parents=True)
    cache.write_bytes(cache_bytes)
    db = WEATHER.connect(run_dir / "ledger.sqlite")
    WEATHER.schema(db)
    with db:
        db.execute("""INSERT INTO cells(cell_id,lat,lon,status,attempts,cache_file,cache_sha256,updated_at)
          VALUES ('1_1',0,0,'failed',2,?,?, 'x')""", (str(cache), recorded_hash))
        db.execute("""INSERT INTO candidates(candidate_id,cell_id,event_date,event_ids,triggers,status,
          collection_status,updated_at) VALUES ('c1','1_1','2010-01-01','[1]','[]','valid','collected','x')""")
        db.execute("""INSERT INTO attempts(cell_id,attempt,started_at,finished_at,outcome,http_url,response_sha256)
          VALUES ('1_1',1,'x','x','success','u',?)""", (recorded_hash,))
    db.close()


class CellRepairTest(unittest.TestCase):
    def run_repair(self, cache_bytes: bytes, recorded_hash: str):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        run_dir = pathlib.Path(tmp.name)
        build_ledger(run_dir, cache_bytes, recorded_hash)
        db = WEATHER.connect(run_dir / "ledger.sqlite")
        before = WEATHER.reconcile_db(db); db.close()
        report = WEATHER.repair_cells(argparse.Namespace(run_dir=run_dir))
        db = sqlite3.connect(run_dir / "ledger.sqlite")
        state = db.execute("SELECT x.status,c.status FROM cells x JOIN candidates c USING(cell_id)").fetchone()
        repairs = db.execute("SELECT count(*) FROM cell_repairs").fetchone()[0]
        db.close()
        return before, report, state, repairs

    def test_stale_cell_detected_and_promoted_when_hash_matches(self):
        body = b'{"ok":1}'
        before, report, state, repairs = self.run_repair(body, hashlib.sha256(body).hexdigest())
        self.assertFalse(before["reconciled"])
        self.assertEqual(before["stale_cell_status"], {"cells": 1, "valid_candidates": 1})
        self.assertTrue(report["reconciled"])
        self.assertEqual(state, ("valid", "valid"))
        self.assertEqual(repairs, 1)

    def test_unverifiable_cache_sends_candidates_back_to_collection(self):
        _, report, state, repairs = self.run_repair(b'{"tampered":1}', "0" * 64)
        self.assertEqual(report["cell_repair"]["reset_to_pending"], 1)
        self.assertEqual(state, ("pending", "pending"))
        self.assertEqual(repairs, 1)


if __name__ == "__main__":
    unittest.main()
