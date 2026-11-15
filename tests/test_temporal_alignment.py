import datetime as dt
import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "weather_pipeline.py"
SPEC = importlib.util.spec_from_file_location("weather_pipeline", SCRIPT)
WEATHER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WEATHER)


class TemporalAlignmentTest(unittest.TestCase):
    def test_window_has_thirty_days_and_excludes_event_day(self):
        start, cutoff, dates = WEATHER.predictive_reference(dt.date(2017, 5, 8))
        self.assertEqual(start, dt.date(2017, 4, 8))
        self.assertEqual(cutoff, dt.date(2017, 5, 7))
        self.assertEqual(len(dates), 30)
        self.assertNotIn(dt.date(2017, 5, 8), dates)

    def test_new_year_boundary(self):
        start, cutoff, dates = WEATHER.predictive_reference(dt.date(2010, 1, 1))
        self.assertEqual(cutoff, dt.date(2009, 12, 31))
        self.assertEqual(start, dt.date(2009, 12, 2))
        self.assertEqual(dates, sorted(dates))

    def test_leap_day_boundary(self):
        start, cutoff, dates = WEATHER.predictive_reference(dt.date(2012, 3, 1))
        self.assertEqual(cutoff, dt.date(2012, 2, 29))
        self.assertEqual(len(set(dates)), 30)

    def test_power_request_fixes_lst(self):
        url = WEATHER.power_url(-22.5, -43.125)
        self.assertIn("time-standard=LST", url)
        self.assertIn("start=20010101", url)
        self.assertIn("end=20251231", url)


if __name__ == "__main__":
    unittest.main()
