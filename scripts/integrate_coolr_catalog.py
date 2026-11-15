#!/usr/bin/env python3
"""Integra o snapshot COOLR Reports Points ao catálogo público.

Política explícita:
- mesmo event_id: a versão do snapshot COOLR substitui a linha GLC local;
- ID só no COOLR: é incluído;
- ID só no GLC local: é preservado e marcado como local_only;
- nenhuma deduplicação é feita por data ou coordenada.

O script verifica os hashes de todas as páginas contra o manifesto e grava a
saída atomicamente. Ele não altera modelos treinados.
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
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def portable(path: Path) -> str:
    """Caminho relativo à raiz do projeto, sem expor diretórios pessoais."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.name


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def number(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


def coordinate(value: Any, lower: float, upper: float) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if lower <= parsed <= upper else None


def csv_date(value: Any) -> str | None:
    raw = clean(value)
    if not raw:
        return None
    for pattern in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def arc_date(value: Any) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(float(value) / 1000, tz=timezone.utc).date().isoformat()


def load_snapshot(snapshot: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    pages = manifest["snapshot"]["pages"]
    features: list[dict[str, Any]] = []
    for expected in pages:
        path = snapshot / expected["file"]
        if sha256(path) != expected["sha256"]:
            raise ValueError(f"hash divergente: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        page_features = payload.get("features", [])
        if len(page_features) != expected["records"]:
            raise ValueError(f"contagem divergente: {path}")
        features.extend(page_features)
    if len(features) != manifest["snapshot"]["records"]:
        raise ValueError("contagem total do snapshot diverge do manifesto")
    return features


def coolr_event(feature: dict[str, Any], shared: bool, manifest_path: Path) -> dict[str, Any]:
    row = feature["attributes"]
    return {
        "event_id": clean(row.get("event_id")),
        "source_row": row.get("objectid"),
        "event_date": arc_date(row.get("event_date")),
        "event_date_raw": row.get("event_date"),
        "event_time": clean(row.get("event_time")),
        "latitude": coordinate(row.get("latitude"), -90, 90),
        "longitude": coordinate(row.get("longitude"), -180, 180),
        "location_accuracy": clean(row.get("location_accuracy")),
        "fatality_count": number(row.get("fatality_count")),
        "injury_count": number(row.get("injury_count")),
        "landslide_trigger": clean(row.get("landslide_trigger")),
        "country_name": clean(row.get("country_name")),
        "country_code": clean(row.get("country_code")),
        "admin_division_name": clean(row.get("admin_division_name")),
        "source": {"name": clean(row.get("source_name")), "url": clean(row.get("source_link"))},
        "import": {"source": clean(row.get("event_import_source")), "id": clean(row.get("event_import_id"))},
        "catalog_origin": "coolr_supersedes_local" if shared else "coolr_only",
        "lineage": {
            "component": "COOLR Reports Points",
            "objectid": row.get("objectid"),
            "manifest": portable(manifest_path),
        },
    }


def local_event(row: dict[str, str], source_row: int, manifest_path: Path) -> dict[str, Any]:
    return {
        "event_id": clean(row.get("event_id")),
        "source_row": source_row,
        "event_date": csv_date(row.get("event_date")),
        "event_date_raw": clean(row.get("event_date")),
        "event_time": clean(row.get("event_time")),
        "latitude": coordinate(row.get("latitude"), -90, 90),
        "longitude": coordinate(row.get("longitude"), -180, 180),
        "location_accuracy": clean(row.get("location_accuracy")),
        "fatality_count": number(row.get("fatality_count")),
        "injury_count": number(row.get("injury_count")),
        "landslide_trigger": clean(row.get("landslide_trigger")),
        "country_name": clean(row.get("country_name")),
        "country_code": clean(row.get("country_code")),
        "admin_division_name": clean(row.get("admin_division_name")),
        "source": {"name": clean(row.get("source_name")), "url": clean(row.get("source_link"))},
        "import": {"source": clean(row.get("event_import_source")), "id": clean(row.get("event_import_id"))},
        "catalog_origin": "glc_local_only",
        "lineage": {"component": "GLC local snapshot", "source_row": source_row, "manifest": portable(manifest_path)},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data/sources/coolr/2026-11-15/reports-points")
    parser.add_argument("--coolr-manifest", type=Path, default=ROOT / "data/sources/coolr/2026-11-15/manifest.json")
    parser.add_argument("--local-glc", type=Path, default=ROOT / "data/sources/glc/2026-11-15/Global_Landslide_Catalog_Export_rows.csv")
    parser.add_argument("--local-manifest", type=Path, default=ROOT / "data/sources/glc/2026-11-15/manifest.json")
    parser.add_argument("--land-template", type=Path, default=ROOT / "data/catalog.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data/catalog.json")
    args = parser.parse_args()

    coolr_manifest = json.loads(args.coolr_manifest.read_text(encoding="utf-8"))
    features = load_snapshot(args.snapshot, coolr_manifest)
    with args.local_glc.open(encoding="utf-8-sig", newline="") as stream:
        local_rows = [(line, row) for line, row in enumerate(csv.DictReader(stream), start=2)]
    local_by_id = {clean(row.get("event_id")): (line, row) for line, row in local_rows}
    current_ids = {clean(feature["attributes"].get("event_id")) for feature in features}
    if None in current_ids or len(current_ids) != len(features):
        raise ValueError("snapshot contém event_id ausente ou duplicado")

    events = [
        coolr_event(feature, clean(feature["attributes"].get("event_id")) in local_by_id, args.coolr_manifest)
        for feature in features
    ]
    for event_id in sorted(set(local_by_id) - current_ids, key=lambda value: int(value or 0)):
        line, row = local_by_id[event_id]
        events.append(local_event(row, line, args.local_manifest))

    ids = [event["event_id"] for event in events]
    if len(ids) != len(set(ids)):
        raise ValueError("a integração produziu IDs duplicados")
    countries = ["United States", "India", "Philippines", "China", "Nepal", "Brazil"]
    country_events = collections.Counter(event["country_name"] for event in events if event["country_name"])
    country_fatalities: collections.Counter[str] = collections.Counter()
    for event in events:
        if event["country_name"] and event["fatality_count"] is not None:
            country_fatalities[event["country_name"]] += event["fatality_count"]
    dates = [event["event_date"] for event in events if event["event_date"]]
    template = json.loads(args.land_template.read_text(encoding="utf-8"))
    origins = collections.Counter(event["catalog_origin"] for event in events)
    result = {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "policy": "coolr_reports_points_supersedes_same_event_id; preserve_local_only; never_deduplicate_by_date_or_coordinate",
            "records": len(events),
            "coolr_manifest": portable(args.coolr_manifest),
            "local_manifest": portable(args.local_manifest),
            "origins": dict(origins),
            "version": None,
            "license": None,
        },
        "events": events,
        "land": template["land"],
        "cmp": [[country, country_events[country], country_fatalities[country]] for country in countries],
        "quality": {
            "period": {"min": min(dates), "max": max(dates)},
            "missing_dates": sum(event["event_date"] is None for event in events),
            "invalid_coordinates": sum(event["latitude"] is None or event["longitude"] is None for event in events),
            "missing_event_id": 0,
            "duplicate_event_ids": [],
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
    print(json.dumps({"records": len(events), "origins": dict(origins), "quality": result["quality"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
