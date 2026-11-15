#!/usr/bin/env python3
"""Consulta os serviços oficiais atuais do COOLR sem integrar catálogos.

Por padrão, registra somente metadados e contagens. A opção de snapshot baixa as
páginas brutas de COOLR Reports Points em um diretório novo e imutável.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = "https://gis.earthdata.nasa.gov/portal/rest/services/Landslides"
SERVICES = {
    "reports_points": f"{BASE}/COOLR_Reports_Points/FeatureServer/0",
    "reports_polygons": f"{BASE}/COOLR_Reports_Polygons/FeatureServer/0",
    "events_points": f"{BASE}/COOLR_Events_Points/FeatureServer/0",
    "events_polygons": f"{BASE}/COOLR_Events_Polygons/FeatureServer/0",
}


def request(url: str, params: dict | None = None) -> tuple[bytes, str]:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "DataDetectivesAudit/1.0"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read(), response.geturl()


def json_request(url: str, params: dict | None = None) -> dict:
    body, _ = request(url, params)
    payload = json.loads(body)
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"snapshot imutável já existe: {path}")
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    path.chmod(0o444)


def service_summary(name: str, url: str) -> dict:
    metadata = json_request(url, {"f": "json"})
    count = json_request(f"{url}/query", {"where": "1=1", "returnCountOnly": "true", "f": "json"})["count"]
    return {
        "name": name,
        "url": url,
        "count_at_audit": count,
        "geometry_type": metadata.get("geometryType"),
        "spatial_reference": metadata.get("extent", {}).get("spatialReference"),
        "max_record_count": metadata.get("maxRecordCount"),
        "fields": [{key: field.get(key) for key in ("name", "type", "alias", "length")} for field in metadata.get("fields", [])],
        "copyright": metadata.get("copyrightText"),
        "description": metadata.get("description"),
        "editing_info": metadata.get("editingInfo"),
    }


def local_ids(path: Path) -> set[str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {(row.get("event_id") or "").strip() for row in csv.DictReader(stream) if (row.get("event_id") or "").strip()}


def snapshot_reports(destination: Path, page_size: int, existing_ids: set[str]) -> dict:
    url = SERVICES["reports_points"]
    pages = []
    records = 0
    current_ids: set[str] = set()
    import_ids: set[str] = set()
    offset = 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "orderByFields": "objectid ASC",
            "resultOffset": offset,
            "resultRecordCount": page_size,
            "f": "json",
        }
        body, requested_url = request(f"{url}/query", params)
        payload = json.loads(body)
        if "error" in payload:
            raise RuntimeError(payload["error"])
        features = payload.get("features", [])
        if not features:
            break
        path = destination / f"page-{len(pages) + 1:04d}.json"
        atomic_write(path, body)
        for feature in features:
            attributes = feature.get("attributes", {})
            event_id = str(attributes.get("event_id") or "").strip()
            import_id = str(attributes.get("event_import_id") or "").strip()
            if event_id:
                current_ids.add(event_id)
            if import_id:
                import_ids.add(import_id)
        pages.append({
            "file": path.name,
            "bytes": len(body),
            "sha256": digest(body),
            "records": len(features),
            "request_url": requested_url,
        })
        records += len(features)
        offset += len(features)
        if len(features) < page_size:
            break
    return {
        "records": records,
        "pages": pages,
        "unique_event_ids": len(current_ids),
        "duplicate_or_missing_event_ids": records - len(current_ids),
        "overlap_with_local_glc_by_event_id": len(existing_ids & current_ids),
        "overlap_with_local_glc_by_event_import_id": len(existing_ids & import_ids),
        "integration_decision": "not_integrated_pending_event-level_duplicate_review",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "sources" / "coolr" / datetime.now().date().isoformat() / "manifest.json")
    parser.add_argument("--snapshot-reports-points", action="store_true")
    parser.add_argument("--local-glc", type=Path, default=ROOT / "data" / "sources" / "glc" / "2026-11-15" / "Global_Landslide_Catalog_Export_rows.csv")
    parser.add_argument("--page-size", type=int, default=2000)
    args = parser.parse_args()

    audited_at = datetime.now(timezone.utc).isoformat()
    services = {name: service_summary(name, url) for name, url in SERVICES.items()}
    result = {
        "manifest_schema": "data-detectives-coolr-audit/v1",
        "audited_at_utc": audited_at,
        "official_overview": "https://gpm.nasa.gov/applications/landslides/coolr",
        "scope_note": "COOLR contains report-based and event-based components; local GLC coverage is not COOLR coverage.",
        "services": services,
        "snapshot": None,
    }
    if args.snapshot_reports_points:
        destination = args.output.parent / "reports-points"
        result["snapshot"] = snapshot_reports(destination, args.page_size, local_ids(args.local_glc))
    body = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True).encode()
    atomic_write(args.output, body)
    print(json.dumps({
        "output": str(args.output),
        "counts": {name: value["count_at_audit"] for name, value in services.items()},
        "snapshot_records": result["snapshot"]["records"] if result["snapshot"] else 0,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
