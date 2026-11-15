#!/usr/bin/env python3
"""Analisa o snapshot COOLR Reports Points preservado por audit_coolr.py."""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def local_date(value: str) -> str | None:
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S"):
        try: return dt.datetime.strptime(value, fmt).date().isoformat()
        except ValueError: pass
    return None


def arc_date(value) -> str | None:
    if value is None: return None
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc).date().isoformat()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data" / "sources" / "coolr" / "2026-11-15" / "reports-points")
    parser.add_argument("--local-glc", type=Path, default=ROOT / "data" / "sources" / "glc" / "2026-11-15" / "Global_Landslide_Catalog_Export_rows.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "sources" / "coolr" / "2026-11-15" / "analysis.json")
    args = parser.parse_args()
    features = []
    for page in sorted(args.snapshot.glob("page-*.json")):
        features.extend(json.loads(page.read_text(encoding="utf-8"))["features"])
    current = {str(feature["attributes"]["event_id"]): feature for feature in features}
    with args.local_glc.open(encoding="utf-8-sig", newline="") as stream:
        local = {row["event_id"]: row for row in csv.DictReader(stream)}
    common = set(current) & set(local)
    dates = [arc_date(feature["attributes"].get("event_date")) for feature in features]
    dates = [value for value in dates if value]
    changes = collections.Counter()
    for event_id in common:
        old = local[event_id]; new = current[event_id]["attributes"]
        if local_date(old.get("event_date", "")) != arc_date(new.get("event_date")): changes["event_date"] += 1
        if float(old["latitude"]) != new.get("latitude") or float(old["longitude"]) != new.get("longitude"): changes["coordinates"] += 1
        if (old.get("location_accuracy") or "") != (new.get("location_accuracy") or ""): changes["location_accuracy"] += 1
        if (old.get("source_name") or "") != (new.get("source_name") or ""): changes["source_name"] += 1
    def mismatch(feature):
        geometry = feature.get("geometry") or {}; attributes = feature["attributes"]
        values = (geometry.get("x"), geometry.get("y"), attributes.get("longitude"), attributes.get("latitude"))
        return any(value is None for value in values) or abs(values[0] - values[2]) > 1e-6 or abs(values[1] - values[3]) > 1e-6

    def invalid_coordinate(feature):
        lat, lon = feature["attributes"].get("latitude"), feature["attributes"].get("longitude")
        return lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180)

    geometry_mismatch = sum(mismatch(feature) for feature in features)
    result = {
        "version": None, "license": None,
        "metadata_note": "FeatureServer did not expose a semantic dataset version or an explicit reuse license in the audited metadata; verify terms before redistribution.",
        "records": len(features), "unique_event_ids": len(current), "event_date_present": len(dates),
        "event_period": {"min": min(dates) if dates else None, "max": max(dates) if dates else None},
        "invalid_coordinates": sum(invalid_coordinate(feature) for feature in features),
        "geometry_attribute_mismatches": geometry_mismatch,
        "location_accuracy": dict(collections.Counter(f["attributes"].get("location_accuracy") or "<missing>" for f in features)),
        "event_import_source": dict(collections.Counter(f["attributes"].get("event_import_source") or "<missing>" for f in features).most_common()),
        "source_name_top20": dict(collections.Counter(f["attributes"].get("source_name") or "<missing>" for f in features).most_common(20)),
        "comparison_local_glc": {"common_event_ids": len(common), "only_current": len(set(current) - set(local)),
                                 "only_local": len(set(local) - set(current)), "changed_fields_within_common": dict(changes)},
        "integration_decision": "not_integrated; shared IDs and changed records require an explicit version/duplicate policy",
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["comparison_local_glc"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
