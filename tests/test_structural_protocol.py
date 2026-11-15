import importlib.util
import json
import pathlib
import unittest


SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "prepare_structural_v2.py"
SPEC = importlib.util.spec_from_file_location("prepare_structural_v2", SCRIPT)
STRUCTURAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STRUCTURAL)


class StructuralProtocolTest(unittest.TestCase):
    def test_published_grid_is_event_independent_and_excludes_antarctica(self):
        grid_path = pathlib.Path(__file__).resolve().parents[1] / "data" / "grids" / "land-1deg.json"
        grid = json.loads(grid_path.read_text(encoding="utf-8"))
        self.assertTrue(grid["independent_of_event_records"])
        self.assertEqual(grid["excluded_region"], "Antarctica south of 60 degrees S")
        self.assertTrue(all(lat >= -60 for lat, _ in grid["cells"]))

    def test_every_feature_window_ends_before_labels(self):
        for feature_years, label_years, _ in STRUCTURAL.ROLES.values():
            self.assertLess(feature_years[1], label_years[0])

    def test_spatial_block_is_not_split_between_partitions(self):
        self.assertEqual(STRUCTURAL.partition((-23, -44)), STRUCTURAL.partition((-21, -41)))

    def test_final_tests_are_not_selection_roles(self):
        selection = {name for name in STRUCTURAL.ROLES if name.startswith("selection_")}
        final = {name for name in STRUCTURAL.ROLES if name.startswith("final_")}
        self.assertTrue(selection.isdisjoint(final))
        self.assertEqual(final, {"final_temporal_test", "final_spatial_test"})

    def test_unseen_cell_uses_null_and_missing_indicator(self):
        empty = STRUCTURAL.aggregate([], (2007, 2012))
        result = STRUCTURAL.features(empty, (-23, -44), 1, (2007, 2012))
        self.assertEqual(result["has_local_history"], 0)
        self.assertIsNone(result["rain_trigger_fraction"])
        self.assertEqual(result["rain_trigger_missing"], 1)


if __name__ == "__main__":
    unittest.main()
