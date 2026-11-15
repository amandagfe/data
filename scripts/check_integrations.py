#!/usr/bin/env python3
"""Verifica contratos mínimos das integrações públicas usadas pelo site.

Uso:
    python3 scripts/check_integrations.py
    python3 scripts/check_integrations.py --strict

O script faz somente requisições de leitura e imprime JSON. Falha de rede é
registrada como tal; ``--strict`` retorna código diferente de zero se algum
contrato não puder ser confirmado.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAT, LON = -22.505, -43.1786
USER_AGENT = "DataDetectivesAudit/1.0 (local reproducibility check)"


def fetch(url: str, *, timeout: int = 30) -> tuple[bytes, dict[str, str], str]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(), dict(response.headers.items()), response.geturl()


def get_json(base: str, params: dict) -> tuple[dict, dict[str, str], str]:
    url = base + "?" + urllib.parse.urlencode(params)
    raw, headers, final_url = fetch(url)
    return json.loads(raw), headers, final_url


def close(a: float, b: float, tolerance: float) -> bool:
    return math.isfinite(a) and abs(a - b) <= tolerance


def check_power() -> dict:
    params = {
        "parameters": "PRECTOTCORR,GWETTOP,GWETROOT,T2M",
        "community": "AG",
        "longitude": LON,
        "latitude": LAT,
        "start": "20261101",
        "end": "20261110",
        "format": "JSON",
    }
    data, _, url = get_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point", params
    )
    historical_params = {**params, "start": "20010101", "end": "20010103"}
    historical, _, historical_url = get_json(
        "https://power.larc.nasa.gov/api/temporal/daily/point", historical_params
    )
    parameter = data.get("properties", {}).get("parameter", {})
    expected = set(params["parameters"].split(","))
    found = set(parameter)
    dates = sorted(set.intersection(*(set(values) for values in parameter.values()))) if parameter else []
    geometry = data.get("geometry", {}).get("coordinates", [])
    header = data.get("header", {})
    historical_header = historical.get("header", {})
    units = {
        name: metadata.get("units")
        for name, metadata in data.get("parameters", {}).items()
    }
    passed = (
        expected <= found
        and len(dates) == 10
        and header.get("time_standard") == "LST"
        and len(geometry) >= 2
        and close(float(geometry[0]), LON, 0.01)
        and close(float(geometry[1]), LAT, 0.01)
        and bool(header.get("sources"))
        and "MERRA2" in historical_header.get("sources", [])
    )
    return {
        "ok": passed,
        "url": url,
        "api_version": header.get("api", {}).get("version"),
        "recent_sources": header.get("sources", []),
        "historical_2001_sources": historical_header.get("sources", []),
        "historical_sample_url": historical_url,
        "time_standard": header.get("time_standard"),
        "coordinates": geometry,
        "dates": [dates[0], dates[-1]] if dates else [],
        "date_count": len(dates),
        "parameters": sorted(found),
        "units": units,
        "fill_value": header.get("fill_value"),
    }


def check_elevation() -> dict:
    delta = 0.0025
    lats = [LAT, LAT, LAT, LAT + delta, LAT - delta]
    lons = [LON, LON + delta, LON - delta, LON, LON]
    data, _, url = get_json(
        "https://api.open-meteo.com/v1/elevation",
        {"latitude": ",".join(map(str, lats)), "longitude": ",".join(map(str, lons))},
    )
    values = data.get("elevation", [])
    return {
        "ok": len(values) == 5 and all(isinstance(value, (int, float)) for value in values),
        "url": url,
        "sample_count": len(values),
        "elevation_m": values,
    }


def check_geocoding() -> dict:
    data, _, url = get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": "Petrópolis", "count": 5, "language": "pt", "format": "json"},
    )
    results = data.get("results", [])
    first = results[0] if results else {}
    passed = (
        bool(first)
        and close(float(first.get("latitude", float("nan"))), LAT, 0.02)
        and close(float(first.get("longitude", float("nan"))), LON, 0.02)
    )
    return {
        "ok": passed,
        "url": url,
        "result_count": len(results),
        "first": {key: first.get(key) for key in ("id", "name", "latitude", "longitude", "country")},
        "ambiguity_note": "a interface escolhe o primeiro entre resultados possivelmente homônimos",
    }


def check_nominatim() -> dict:
    data, _, url = get_json(
        "https://nominatim.openstreetmap.org/reverse",
        {"lat": LAT, "lon": LON, "zoom": 10, "format": "jsonv2", "accept-language": "pt"},
    )
    return {
        "ok": bool(data.get("display_name")),
        "url": url,
        "display_name": data.get("display_name"),
        "osm_type": data.get("osm_type"),
        "licence": data.get("licence"),
    }


def check_gibs() -> dict:
    metadata = json.loads((ROOT / "data" / "gibs.json").read_text(encoding="utf-8"))
    results = []
    for key, layer_meta in metadata["layers"].items():
        layer = layer_meta["id"]
        image_format = "image/png" if layer_meta["overlay"] else "image/jpeg"
        params = {
            "SERVICE": "WMS",
            "REQUEST": "GetMap",
            "VERSION": "1.3.0",
            "LAYERS": layer,
            "STYLES": "",
            "FORMAT": image_format,
            "TRANSPARENT": "TRUE" if layer_meta["overlay"] else "FALSE",
            "CRS": "EPSG:4326",
            "BBOX": "-23.5,-44.2,-21.5,-42.2",
            "WIDTH": 16,
            "HEIGHT": 16,
        }
        if layer_meta.get("requested_time"):
            params["TIME"] = layer_meta["requested_time"]
        raw, headers, url = fetch(
            "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?"
            + urllib.parse.urlencode(params)
        )
        content_type = headers.get("Content-Type", "")
        results.append({
            "key": key,
            "layer": layer,
            "ok": content_type.startswith("image/") and (raw.startswith(b"\x89PNG") or raw.startswith(b"\xff\xd8")),
            "content_type": content_type,
            "bytes": len(raw),
            "url": url,
            "time_parameter": layer_meta.get("requested_time"),
            "represented_time": layer_meta.get("represented_time"),
            "fallback": layer_meta.get("fallback"),
        })
    return {"ok": all(item["ok"] for item in results), "layers": results}


def check_oni() -> dict:
    local = json.loads((ROOT / "data" / "enso.json").read_text(encoding="utf-8"))
    last_local = local["oni"][-1]
    raw, _, url = fetch(
        "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
    )
    lines = raw.decode("ascii", errors="replace").splitlines()
    rows = [line.split() for line in lines[1:] if line.strip()]
    last_remote = rows[-1]
    remote = {"season": last_remote[0], "year": int(last_remote[1]), "oni": float(last_remote[-1])}
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    local_season = seasons[int(last_local[1]) - 1]
    passed = (
        last_local[0] == remote["year"]
        and local_season == remote["season"]
        and close(float(last_local[2]), remote["oni"], 1e-9)
    )
    return {
        "ok": passed,
        "url": url,
        "remote_rows": len(rows),
        "remote_latest": remote,
        "local_latest": {"year": last_local[0], "central_month": last_local[1], "season": local_season, "oni": last_local[2]},
        "local_download_date": local.get("updated"),
    }


def run_check(name: str, function) -> dict:
    try:
        return function()
    except Exception as exc:  # rede/contrato externo: deve aparecer no relatório
        return {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    checks = {
        "nasa_power": run_check("nasa_power", check_power),
        "open_meteo_elevation": run_check("open_meteo_elevation", check_elevation),
        "open_meteo_geocoding": run_check("open_meteo_geocoding", check_geocoding),
        "nominatim_reverse": run_check("nominatim_reverse", check_nominatim),
        "nasa_gibs": run_check("nasa_gibs", check_gibs),
        "noaa_oni": run_check("noaa_oni", check_oni),
    }
    output = {
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sample": {"name": "Petrópolis", "latitude": LAT, "longitude": LON},
        "all_ok": all(item.get("ok") is True for item in checks.values()),
        "checks": checks,
        "not_checked": {
            "telegram": "funcionalidade removida e desativada; não existe integração externa a testar"
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.strict and not output["all_ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
