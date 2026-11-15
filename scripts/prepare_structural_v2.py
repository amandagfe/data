#!/usr/bin/env python3
"""Prepara cortes estruturais sem ajustar ou promover modelos."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAIN = {"downpour", "rain", "continuous_rain", "monsoon", "tropical_cyclone"}
ROLES = {
    "selection_train": ((2007, 2012), (2013, 2014), "development"),
    "selection_spatial_validation": ((2007, 2012), (2013, 2014), "validation"),
    "selection_temporal_validation": ((2007, 2014), (2015, 2016), "development"),
    "final_temporal_test": ((2007, 2016), (2017, 2018), "development"),
    "final_spatial_test": ((2007, 2016), (2017, 2018), "test"),
}
EVENT_PERIOD = (2007, 2025)
PRODUCTION_FEATURE_YEARS = (2007, 2025)
SUPPORTED_CATALOG_SCHEMAS = {2, 3}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def partition(cell: tuple[int, int]) -> str:
    block = (cell[0] // 5, cell[1] // 5)
    bucket = int(hashlib.sha256(f"structural-spatial-v1|{block[0]}|{block[1]}".encode()).hexdigest()[:8], 16) % 100
    return "development" if bucket < 80 else "validation" if bucket < 90 else "test"


def event_rows(catalog: dict) -> list[dict]:
    rows = []
    for event in catalog["events"]:
        date = event.get("event_date")
        lat, lon = event.get("latitude"), event.get("longitude")
        if (not date or not ("2007-01-01" <= date <= "2025-12-31")
                or not isinstance(lat, (int, float)) or isinstance(lat, bool)
                or not isinstance(lon, (int, float)) or isinstance(lon, bool)
                or not (-90 <= lat <= 90 and -180 <= lon <= 180)):
            continue
        rows.append({
            "event_id": str(event.get("event_id")),
            "cell": (math.floor(lat), math.floor(lon)),
            "year": int(date[:4]), "month": int(date[5:7]),
            "fatality": event.get("fatality_count"),
            "rain": (event.get("landslide_trigger") or "").strip().lower() in RAIN,
        })
    return rows


def aggregate(events: list[dict], years: tuple[int, int]) -> dict:
    count = collections.Counter(); count_month = collections.Counter()
    fatalities = collections.Counter(); fatalities_known = collections.Counter(); fatalities_missing = collections.Counter()
    rain = collections.Counter(); trigger_known = collections.Counter(); active_years = collections.defaultdict(set)
    for event in events:
        if not years[0] <= event["year"] <= years[1]: continue
        cell = event["cell"]
        count[cell] += 1; count_month[cell, event["month"]] += 1; active_years[cell].add(event["year"])
        rain[cell] += int(event["rain"]); trigger_known[cell] += 1
        if event["fatality"] is None: fatalities_missing[cell] += 1
        else: fatalities[cell] += event["fatality"]; fatalities_known[cell] += 1
    return {"count": count, "month": count_month, "fatalities": fatalities, "fatalities_known": fatalities_known,
            "fatalities_missing": fatalities_missing, "rain": rain, "trigger_known": trigger_known, "active_years": active_years}


def nearby(counter, cell, radius, month=None, exclude_center=False):
    total = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if exclude_center and dx == dy == 0: continue
            key = (cell[0] + dy, ((cell[1] + dx + 180) % 360) - 180)
            total += counter[(key, month)] if month is not None else counter[key]
    return total


def features(agg: dict, cell: tuple[int, int], month: int, years: tuple[int, int]) -> dict:
    duration = years[1] - years[0] + 1
    local = agg["count"][cell]
    n1 = nearby(agg["count"], cell, 1, exclude_center=True)
    n2 = nearby(agg["count"], cell, 2, exclude_center=True) - n1
    region_count = local + n1
    known_triggers = nearby(agg["trigger_known"], cell, 1)
    known_fatalities = nearby(agg["fatalities_known"], cell, 1)
    fatality_missing = nearby(agg["fatalities_missing"], cell, 1)
    lat, lon = cell[0] + 0.5, cell[1] + 0.5
    active = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            active |= agg["active_years"].get((cell[0] + dy, ((cell[1] + dx + 180) % 360) - 180), set())
    return {
        "event_rate_cell_year": local / duration,
        "event_rate_cell_month_year": agg["month"][(cell, month)] / duration,
        "event_rate_neighbors_1_year": n1 / duration,
        "event_rate_neighbors_1_month_year": nearby(agg["month"], cell, 1, month, True) / duration,
        "event_rate_neighbors_2_year": n2 / duration,
        "fatalities_region_log1p": math.log1p(nearby(agg["fatalities"], cell, 1)),
        "fatality_values_known": known_fatalities,
        "fatality_values_missing": fatality_missing,
        "rain_trigger_fraction": nearby(agg["rain"], cell, 1) / known_triggers if known_triggers else None,
        "rain_trigger_missing": int(known_triggers == 0),
        "active_years_region": len(active),
        "has_local_history": int(local > 0),
        "latitude": lat, "abs_latitude": abs(lat),
        "sin_longitude": math.sin(math.radians(lon)), "cos_longitude": math.cos(math.radians(lon)),
        "sin_month": math.sin(2 * math.pi * month / 12), "cos_month": math.cos(2 * math.pi * month / 12),
    }


def role_summary(events, cells, role, spec):
    feature_years, label_years, required_partition = spec
    role_cells = [cell for cell in cells if partition(cell) == required_partition]
    positives = {(event["cell"], event["month"]) for event in events if label_years[0] <= event["year"] <= label_years[1]}
    on_domain = sum((cell, month) in positives for cell in role_cells for month in range(1, 13))
    return {"feature_years": feature_years, "label_years": label_years, "spatial_partition": required_partition,
            "cells": len(role_cells), "examples": len(role_cells) * 12, "positive_cell_months": on_domain}


def materialize(path: Path, events: list[dict], cells: list[tuple[int, int]], limit: int | None) -> int:
    written = 0
    with path.open("w", encoding="utf-8") as stream:
        for role, spec in ROLES.items():
            feature_years, label_years, required_partition = spec
            role_cells = [cell for cell in cells if partition(cell) == required_partition]
            if limit is not None: role_cells = role_cells[:limit]
            agg = aggregate(events, feature_years)
            positives = {(event["cell"], event["month"]) for event in events if label_years[0] <= event["year"] <= label_years[1]}
            for cell in role_cells:
                for month in range(1, 13):
                    row = {"role": role, "cell": cell, "month": month, "target": int((cell, month) in positives),
                           "features": features(agg, cell, month, feature_years)}
                    stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
                    written += 1
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "catalog.json")
    parser.add_argument("--grid", type=Path, default=ROOT / "data" / "grids" / "land-1deg.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--materialize", type=Path)
    parser.add_argument("--limit-cells", type=int)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8")); grid = json.loads(args.grid.read_text(encoding="utf-8"))
    if catalog.get("schema_version") not in SUPPORTED_CATALOG_SCHEMAS or not grid.get("independent_of_event_records"):
        raise ValueError("entradas não satisfazem os contratos estruturais")
    events = event_rows(catalog); cells = [tuple(cell) for cell in grid["cells"]]; cell_set = set(cells)
    off_grid_events = [event for event in events if event["cell"] not in cell_set]
    off_grid = len(off_grid_events)
    report = {
        "schema_version": 1, "catalog": {"path": str(args.catalog), "sha256": sha256(args.catalog)},
        "grid": {"path": str(args.grid), "sha256": sha256(args.grid), "cells": len(cells), "independent_of_events": True},
        "event_period": list(EVENT_PERIOD), "events_2007_2025": len(events),
        "event_rows_inside_grid": len(events) - off_grid,
        "event_rows_outside_grid": off_grid,
        "outside_grid_event_ids": [event["event_id"] for event in off_grid_events],
        "outside_grid_policy": "excluded without coordinate relocation; source records remain preserved in catalog.json",
        "spatial_partitions": dict(collections.Counter(partition(cell) for cell in cells)),
        "roles": {role: role_summary(events, cells, role, spec) for role, spec in ROLES.items()},
        "leakage_controls": {
            "domain": "fixed land grid derived without event records",
            "feature_cutoff": "every feature aggregation ends before its label interval",
            "learned_transformations": "fit only on selection_train/development; refit separately inside each future CV cut",
            "selection_allowed": ["selection_train", "selection_spatial_validation", "selection_temporal_validation"],
            "selection_forbidden": ["final_temporal_test", "final_spatial_test"],
            "unseen_cells": "retained with zero history, has_local_history=0 and rain_trigger_fraction=null plus missing indicator",
        },
        "production": {
            "feature_years": list(PRODUCTION_FEATURE_YEARS),
            "forecast_horizon": [2026, 2027],
            "uses_final_tests_for_selection": False,
            "note": "production refit may use all eligible events only after model choices are frozen from selection roles and final tests are reported",
        },
        "training_performed": False,
    }
    if args.materialize:
        args.materialize.parent.mkdir(parents=True, exist_ok=True)
        report["materialized_rows"] = materialize(args.materialize, events, cells, args.limit_cells)
        report["materialized_file"] = str(args.materialize)
        report["materialized_sha256"] = sha256(args.materialize)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "grid_cells": len(cells), "events": len(events), "off_grid": off_grid,
                      "materialized_rows": report.get("materialized_rows", 0)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
