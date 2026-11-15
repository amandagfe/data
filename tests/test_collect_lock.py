import argparse
import fcntl
import importlib.util
import pathlib
import tempfile
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "weather_pipeline.py"
SPEC = importlib.util.spec_from_file_location("weather_pipeline_lock", SCRIPT)
WEATHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WEATHER)


class CollectLockTest(unittest.TestCase):
    def test_second_collector_aborts_without_touching_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp)
            with (run_dir / "collect.lock").open("w") as held:
                fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                args = argparse.Namespace(run_dir=run_dir, workers=1, retries=1, limit_cells=None)
                with self.assertRaises(SystemExit) as raised:
                    WEATHER.collect(args)
                self.assertIn("outro coletor", str(raised.exception))
            # A trava impede até a criação do ledger.
            self.assertFalse((run_dir / "ledger.sqlite").exists())


if __name__ == "__main__":
    unittest.main()
