#!/usr/bin/env python3
"""Deriva uma grade terrestre fixa de 1° do TopoJSON, sem ler eventos."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def decode_arc(topology: dict, index: int, cache: dict[int, list]) -> list:
    original = index
    reverse = index < 0
    index = ~index if reverse else index
    if index not in cache:
        scale = topology["transform"]["scale"]
        translate = topology["transform"]["translate"]
        x = y = 0
        points = []
        for dx, dy in topology["arcs"][index]:
            x += dx; y += dy
            points.append((x * scale[0] + translate[0], y * scale[1] + translate[1]))
        cache[index] = points
    points = cache[index]
    return list(reversed(points)) if reverse else points


def ring(topology: dict, indexes: list[int], cache: dict) -> list:
    output = []
    for index in indexes:
        points = decode_arc(topology, index, cache)
        output.extend(points if not output else points[1:])
    return output


def polygons(topology: dict) -> list:
    land = topology["objects"]["land"]
    geometries = land.get("geometries", [land])
    cache = {}
    result = []
    for geometry in geometries:
        raw = geometry["arcs"]
        if geometry["type"] == "Polygon":
            raw = [raw]
        for polygon in raw:
            rings = [ring(topology, indexes, cache) for indexes in polygon]
            xs = [point[0] for point in rings[0]]; ys = [point[1] for point in rings[0]]
            result.append((min(xs), min(ys), max(xs), max(ys), rings))
    return result


def inside_ring(x: float, y: float, points: list) -> bool:
    inside = False
    j = len(points) - 1
    for i, (xi, yi) in enumerate(points):
        xj, yj = points[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def center_on_land(lon: float, lat: float, shapes: list) -> bool:
    for minx, miny, maxx, maxy, rings in shapes:
        if minx <= lon <= maxx and miny <= lat <= maxy and inside_ring(lon, lat, rings[0]):
            if not any(inside_ring(lon, lat, hole) for hole in rings[1:]):
                return True
    return False


def coastline_cells(shapes: list) -> set[tuple[int, int]]:
    """Rasteriza o contorno com margem de uma célula, sem usar eventos."""
    result = set()
    for _, _, _, _, rings in shapes:
        for points in rings:
            for a, b in zip(points, points[1:]):
                x0, y0 = a; x1, y1 = b
                dx = x1 - x0
                if dx > 180: dx -= 360
                elif dx < -180: dx += 360
                steps = max(1, math.ceil(max(abs(dx), abs(y1 - y0)) * 4))
                for step in range(steps + 1):
                    fraction = step / steps
                    x = ((x0 + dx * fraction + 180) % 360) - 180
                    y = y0 + (y1 - y0) * fraction
                    base = (math.floor(y), math.floor(x))
                    for dy in (-2, -1, 0, 1, 2):
                        for dx_cell in (-2, -1, 0, 1, 2):
                            lat = base[0] + dy
                            lon = ((base[1] + dx_cell + 180) % 360) - 180
                            if -90 <= lat < 90:
                                result.add((lat, lon))
    return result


def segment_intersects_box(a, b, minx, miny, maxx, maxy) -> bool:
    """Teste Liang–Barsky entre um segmento e a célula fechada."""
    x0, y0 = a; x1, y1 = b; dx, dy = x1 - x0, y1 - y0
    low, high = 0.0, 1.0
    for p, q in ((-dx, x0 - minx), (dx, maxx - x0), (-dy, y0 - miny), (dy, maxy - y0)):
        if p == 0:
            if q < 0: return False
            continue
        t = q / p
        if p < 0: low = max(low, t)
        else: high = min(high, t)
        if low > high: return False
    return True


def intersects_land_cell(lon: int, lat: int, shapes: list) -> bool:
    minx, miny, maxx, maxy = lon, lat, lon + 1, lat + 1
    samples = ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy), (lon + 0.5, lat + 0.5))
    for px0, py0, px1, py1, rings in shapes:
        if px1 < minx or px0 > maxx or py1 < miny or py0 > maxy:
            continue
        outer = rings[0]
        if any(inside_ring(x, y, outer) and not any(inside_ring(x, y, hole) for hole in rings[1:]) for x, y in samples):
            return True
        if any(minx <= x <= maxx and miny <= y <= maxy for x, y in outer):
            return True
        if any(segment_intersects_box(outer[i - 1], outer[i], minx, miny, maxx, maxy) for i in range(len(outer))):
            return True
    return False


def index_shapes(shapes: list) -> dict[tuple[int, int], list]:
    """Indexa apenas células tocadas pelo bbox; evita testar 64.800×todos os polígonos."""
    indexed = collections.defaultdict(list)
    for shape in shapes:
        minx, miny, maxx, maxy, _ = shape
        lat_start = max(-90, math.floor(miny))
        lat_end = min(89, math.floor(maxy))
        lon_start = max(-180, math.floor(minx))
        lon_end = min(179, math.floor(maxx))
        for lat in range(lat_start, lat_end + 1):
            for lon in range(lon_start, lon_end + 1):
                indexed[(lat, lon)].append(shape)
    return indexed


def unwrap(points: list) -> list:
    output = []
    offset = 0
    previous = None
    for lon, lat in points:
        value = lon + offset
        if previous is not None:
            if value - previous > 180:
                offset -= 360; value -= 360
            elif value - previous < -180:
                offset += 360; value += 360
        output.append((value, lat)); previous = value
    return output


def fill_ring(points: list) -> set[tuple[int, int]]:
    """Preenche centros de células por varredura horizontal."""
    points = unwrap(points)
    result = set()
    min_lat = max(-90, math.floor(min(y for _, y in points)))
    max_lat = min(89, math.floor(max(y for _, y in points)))
    for lat in range(min_lat, max_lat + 1):
        y = lat + 0.5
        crossings = []
        for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
            if (y0 > y) == (y1 > y):
                continue
            crossings.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
        crossings.sort()
        for start, end in zip(crossings[0::2], crossings[1::2]):
            first = math.ceil(start - 0.5)
            last = math.floor(end - 0.5)
            for lon in range(first, last + 1):
                result.add((lat, ((lon + 180) % 360) - 180))
    return result


def boundary_cells(points: list) -> set[tuple[int, int]]:
    result = set(); points = unwrap(points)
    for (x0, y0), (x1, y1) in zip(points, points[1:] + points[:1]):
        steps = max(1, math.ceil(max(abs(x1 - x0), abs(y1 - y0)) * 4))
        for step in range(steps + 1):
            fraction = step / steps
            lon = ((math.floor(x0 + (x1 - x0) * fraction) + 180) % 360) - 180
            lat = math.floor(y0 + (y1 - y0) * fraction)
            if -90 <= lat < 90:
                result.add((lat, lon))
    return result


def rasterize(shapes: list) -> set[tuple[int, int]]:
    result = set()
    for _, _, _, _, rings in shapes:
        polygon = fill_ring(rings[0])
        for hole in rings[1:]:
            polygon.difference_update(fill_ring(hole))
        result.update(polygon)
        for points in rings:
            result.update(boundary_cells(points))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--topology", type=Path,
                        default=ROOT / "data" / "sources" / "natural-earth" / "land-50m.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "grids" / "land-1deg.json")
    args = parser.parse_args()
    topology = json.loads(args.topology.read_text(encoding="utf-8"))
    shapes = polygons(topology)
    # O produto é voltado a regiões onde o catálogo e o uso civil fazem sentido.
    # A Antártica é excluída por uma fronteira geográfica fixa, não pelos eventos.
    cells = [[lat, lon] for lat, lon in sorted(rasterize(shapes)) if lat >= -60]
    try:
        source_file = str(args.topology.resolve().relative_to(ROOT))
    except ValueError:
        source_file = str(args.topology)
    output = {
        "schema_version": 2,
        "definition": "célula de 1 grau que intersecta terra no contorno Natural Earth 1:50m, exceto Antártica ao sul de 60°S; sem consulta a registros de eventos",
        "independent_of_event_records": True,
        "excluded_region": "Antarctica south of 60 degrees S",
        "source": {"file": source_file, "sha256": sha256(args.topology), "json_pointer": "/objects/land"},
        "cells": cells,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "cells": len(cells)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
