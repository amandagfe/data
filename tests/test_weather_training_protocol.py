import datetime as dt
import importlib.util
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "train_weather_v2.py"
SPEC = importlib.util.spec_from_file_location("train_weather_v2", SCRIPT)
TRAIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAIN)


class WeatherTrainingProtocolTests(unittest.TestCase):
    def payload(self):
        start, end = dt.date(2001, 1, 1), dt.date(2007, 1, 10)
        rain, top, root = {}, {}, {}
        current = start
        while current <= end:
            key = current.strftime("%Y%m%d")
            rain[key] = 1.0
            top[key] = 0.4
            root[key] = 0.5
            current += dt.timedelta(days=1)
        return {"properties": {"parameter": {
            "PRECTOTCORR": rain, "GWETTOP": top, "GWETROOT": root,
        }}}

    def test_features_for_event_end_at_previous_day(self):
        payload = self.payload()
        # Chuva no próprio dia D não pode alterar atributos calculados em D-1.
        payload["properties"]["parameter"]["PRECTOTCORR"]["20070110"] = 999.0
        features = TRAIN.cell_feature_function(payload)(dt.date(2007, 1, 9))
        self.assertEqual(features[0], 1.0)
        self.assertEqual(features[2], 7.0)
        self.assertEqual(features[4], 30.0)

    def test_controls_are_deterministic_and_outside_blocked_dates(self):
        event = dt.date(2020, 6, 10)
        blocked = {event + dt.timedelta(days=offset) for offset in range(-10, 11)}
        first = TRAIN.deterministic_controls("10_20", event, blocked, 4)
        second = TRAIN.deterministic_controls("10_20", event, blocked, 4)
        self.assertEqual(first, second)
        self.assertTrue(all(date not in blocked for date in first))

    def test_controls_do_not_cross_catalog_observation_end(self):
        event = dt.date(2025, 5, 10)
        end = dt.date(2025, 5, 18)
        controls = TRAIN.deterministic_controls("10_20", event, set(), 20, end)
        self.assertTrue(all(date <= end for date in controls))

    def test_roles_keep_final_spatial_partition_out_of_selection(self):
        test_cell = next(
            f"{lat}_{lon}" for lat in range(-20, 20) for lon in range(-20, 20)
            if TRAIN.spatial_partition(f"{lat}_{lon}") == "test"
        )
        self.assertIsNone(TRAIN.role_for(test_cell, 2016))
        self.assertEqual(TRAIN.role_for(test_cell, 2025), "final_spatial_test")


if __name__ == "__main__":
    unittest.main()
