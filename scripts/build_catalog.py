#!/usr/bin/env python3
"""Constrói o catálogo público v2 sem colapsar a identidade dos eventos.

O arquivo bruto é somente leitura. A saída é escrita de forma atômica e mantém
IDs, nulidade, precisão espacial declarada e referências de origem.
"""

from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def number(value: str | None) -> float | int | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def coordinate(value: str | None, lower: float, upper: float) -> float | None:
    try:
        parsed = float((value or "").strip())
    except ValueError:
        return None
    return parsed if lower <= parsed <= upper else None


def date_iso(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def load_land(path: Path):
    with path.open(encoding="utf-8") as stream:
        payload = json.load(stream)
    if payload.get("type") == "Topology":
        return payload
    if "land" in payload:
        return payload["land"]
    raise ValueError(f"{path}: não contém Topology nem a chave land")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("land", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()

    manifest = None
    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest_file = manifest.get("file")
        expected = manifest_file.get("sha256") if isinstance(manifest_file, dict) else manifest.get("sha256")
        actual = sha256(args.source)
        if expected and expected != actual:
            raise ValueError("hash do CSV não corresponde ao manifesto")

    events = []
    country_events: collections.Counter[str] = collections.Counter()
    country_fatalities: collections.Counter[str] = collections.Counter()
    invalid_dates = invalid_coordinates = 0
    fieldnames = []
    with args.source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fieldnames = reader.fieldnames or []
        for source_row, row in enumerate(reader, start=2):
            latitude = coordinate(row.get("latitude"), -90, 90)
            longitude = coordinate(row.get("longitude"), -180, 180)
            event_date = date_iso(row.get("event_date"))
            if latitude is None or longitude is None:
                invalid_coordinates += 1
            if event_date is None:
                invalid_dates += 1
            fatalities = number(row.get("fatality_count"))
            injuries = number(row.get("injury_count"))
            country = text(row.get("country_name"))
            if country:
                country_events[country] += 1
                if fatalities is not None:
                    country_fatalities[country] += fatalities
            events.append(
                {
                    "event_id": text(row.get("event_id")),
                    "source_row": source_row,
                    "event_date": event_date,
                    "event_date_raw": text(row.get("event_date")),
                    "event_time": text(row.get("event_time")),
                    "latitude": latitude,
                    "longitude": longitude,
                    "location_accuracy": text(row.get("location_accuracy")),
                    "fatality_count": fatalities,
                    "injury_count": injuries,
                    "landslide_trigger": text(row.get("landslide_trigger")),
                    "country_name": country,
                    "country_code": text(row.get("country_code")),
                    "admin_division_name": text(row.get("admin_division_name")),
                    "source": {
                        "name": text(row.get("source_name")),
                        "url": text(row.get("source_link")),
                    },
                    "import": {
                        "source": text(row.get("event_import_source")),
                        "id": text(row.get("event_import_id")),
                    },
                }
            )

    ids = [event["event_id"] for event in events if event["event_id"]]
    id_counts = collections.Counter(ids)
    duplicate_ids = sorted(key for key, count in id_counts.items() if count > 1)
    dates = [event["event_date"] for event in events if event["event_date"]]
    countries = ["United States", "India", "Philippines", "China", "Nepal", "Brazil"]
    result = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "file": str(args.source),
            "sha256": sha256(args.source),
            "manifest": str(args.manifest) if args.manifest else None,
            "records": len(events),
            "fields": fieldnames,
        },
        "events": events,
        "land": load_land(args.land),
        "cmp": [[country, country_events[country], country_fatalities[country]] for country in countries],
        "quality": {
            "period": {"min": min(dates) if dates else None, "max": max(dates) if dates else None},
            "invalid_dates": invalid_dates,
            "invalid_coordinates": invalid_coordinates,
            "missing_event_id": len(events) - len(ids),
            "duplicate_event_ids": duplicate_ids,
            "missing_location_accuracy": sum(not event["location_accuracy"] for event in events),
            "missing_fatality_count": sum(event["fatality_count"] is None for event in events),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, separators=(",", ":"))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, args.output)
    print(json.dumps({"records": len(events), "output": str(args.output), "quality": result["quality"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
