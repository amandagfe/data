#!/usr/bin/env python3
"""Resolve e verifica datas WMS das camadas GIBS usadas pela interface."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WMS = "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi"
LAYERS = {
    "rain": {"id": "IMERG_Precipitation_Rate", "overlay": True, "legend": "https://gibs.earthdata.nasa.gov/legends/GPM_Precipitation_Rate_H.png"},
    "soil": {"id": "SMAP_L4_Analyzed_Root_Zone_Soil_Moisture", "overlay": True, "legend": "https://gibs.earthdata.nasa.gov/legends/SMAP_Analyzed_Soil_Moisture_H.png"},
    "haz": {"id": "NDH_Landslide_Hazard_Distribution_2000", "overlay": True, "legend": "https://gibs.earthdata.nasa.gov/legends/NDH_Landslide_Hazard_Distribution_2000_H.png"},
    "sat": {"id": "VIIRS_NOAA20_CorrectedReflectance_TrueColor", "overlay": False, "legend": None},
}


def fetch(params: dict) -> tuple[bytes, str, str]:
    url = WMS + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "DataDetectivesGIBSAudit/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read(), response.headers.get_content_type(), response.geturl()


def date_available(value: str, definition: str) -> bool:
    for item in (part.strip() for part in definition.split(",")):
        if not item: continue
        if "/" not in item and item[:10] == value: return True
        parts = item.split("/")
        if len(parts) >= 2 and parts[0][:10] <= value <= parts[1][:10]: return True
    return False


def layer_dimensions(root: ET.Element) -> dict:
    ns = {"wms": "http://www.opengis.net/wms"}
    output = {}
    for layer in root.findall(".//wms:Layer", ns):
        name = layer.findtext("wms:Name", namespaces=ns)
        if not name: continue
        dimension = next((item for item in layer.findall("wms:Dimension", ns) if item.attrib.get("name") == "time"), None)
        output[name] = None if dimension is None else {
            "default": dimension.attrib.get("default"), "units": dimension.attrib.get("units"),
            "nearest_value": dimension.attrib.get("nearestValue"), "values": (dimension.text or "").strip(),
        }
    return output


def verify_image(layer: dict, selected: str | None) -> dict:
    params = {"SERVICE": "WMS", "REQUEST": "GetMap", "VERSION": "1.3.0", "LAYERS": layer["id"],
              "CRS": "EPSG:4326", "BBOX": "-90,-180,90,180", "WIDTH": 64, "HEIGHT": 32,
              "FORMAT": "image/png" if layer["overlay"] else "image/jpeg", "TRANSPARENT": "true" if layer["overlay"] else "false"}
    if selected: params["TIME"] = selected
    body, content_type, url = fetch(params)
    image = content_type.startswith("image/") and (body.startswith(b"\x89PNG") or body.startswith(b"\xff\xd8"))
    return {"ok": image, "content_type": content_type, "bytes": len(body), "url": url}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desired-date", default=(dt.date.today() - dt.timedelta(days=1)).isoformat())
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "gibs.json")
    args = parser.parse_args()
    body, _, capabilities_url = fetch({"SERVICE": "WMS", "REQUEST": "GetCapabilities", "VERSION": "1.3.0"})
    dimensions = layer_dimensions(ET.fromstring(body))
    result = {"schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "capabilities_url": capabilities_url, "desired_time": args.desired_date, "layers": {}}
    for key, base in LAYERS.items():
        dimension = dimensions.get(base["id"])
        selected = None; fallback = False; reason = None; represented = None
        if dimension:
            if date_available(args.desired_date, dimension["values"]):
                selected = args.desired_date; reason = "desired_date_listed_in_capabilities"
            else:
                selected = (dimension.get("default") or "")[:10] or None
                fallback = True; reason = "desired_date_not_listed;used_capabilities_default"
            represented = selected if selected and date_available(selected, dimension["values"]) else None
        else:
            reason = "layer_has_no_time_dimension"
        verification = verify_image(base, selected)
        result["layers"][key] = {**base, "temporal": dimension is not None, "desired_time": args.desired_date if dimension else None,
            "requested_time": selected, "represented_time": represented, "fallback": fallback, "selection_reason": reason,
            "capabilities": dimension, "verification": verification}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: {field: layer[field] for field in ("requested_time", "represented_time", "fallback")}
                      | {"image_ok": layer["verification"]["ok"]} for key, layer in result["layers"].items()}))
    return 0 if all(layer["verification"]["ok"] for layer in result["layers"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
