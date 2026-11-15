"""Audita, sem alterar, os artefatos de dados publicados pelo Data Detectives.

Uso:
    python3 scripts/audit_data.py
    python3 scripts/audit_data.py --summary
    python3 scripts/audit_data.py --strict
    python3 scripts/audit_data.py --raw-glc caminho/export.csv --strict

O script só usa a biblioteca padrão. Ele audita os JSONs processados presentes no
repositório e, opcionalmente, compara um CSV bruto informado explicitamente.
"""

from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RAIN = {"downpour", "rain", "continuous_rain", "monsoon", "tropical_cyclone"}
NON_WEATHER = {
    "earthquake", "mining", "construction", "dam_embankment_collapse",
    "leaking_pipe", "vibration", "volcano", "other",
}
DEFAULT_PLACE = {"name": "Petrópolis", "lat": -22.505, "lng": -43.1786}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    rad = math.pi / 180
    value = (
        math.sin((lat2 - lat1) * rad / 2) ** 2
        + math.cos(lat1 * rad)
        * math.cos(lat2 * rad)
        * math.sin((lng2 - lng1) * rad / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(value))


def valid_date(year: int, month: int, day: int) -> bool:
    try:
        dt.date(year, month, day)
        return True
    except (TypeError, ValueError):
        return False


def parse_glc_date(value: str | None) -> dt.date | None:
    value = (value or "").strip()
    for fmt in ("%m/%d/%Y %I:%M:%S %p", "%m/%d/%Y %H:%M:%S", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def duplicate_stats(keys: list[tuple]) -> dict:
    counts = collections.Counter(keys)
    repeated = [count for count in counts.values() if count > 1]
    return {
        "duplicate_groups": len(repeated),
        "extra_rows": sum(count - 1 for count in repeated),
        "largest_group": max(repeated, default=1),
    }


def audit_catalog(catalog: dict, model_cells: set[tuple[int, int]], oni_keys: set[int]) -> tuple[dict, list[str]]:
    problems: list[str] = []
    schema_version = catalog.get("schema_version", 1)
    legacy = schema_version < 2
    rows = catalog.get("pts", []) if legacy else catalog.get("events", [])
    triggers = catalog.get("trig", []) if legacy else []
    countries = catalog.get("ctys", []) if legacy else []

    shape_invalid = sum(not isinstance(row, list) or len(row) != 8 for row in rows) if legacy else 0
    invalid_coordinates = 0
    missing_coordinates = 0
    invalid_trigger_refs = 0
    invalid_country_refs = 0
    invalid_dates = 0
    missing_dates = 0
    negative_deaths = 0
    exact_keys = []
    event_keys = []
    years = collections.Counter()
    months = collections.Counter()
    country_counts = collections.Counter()
    trigger_counts = collections.Counter()
    structural_associated = 0
    structural_unassociated = 0
    oni_associated = 0
    oni_unassociated = 0
    training_period = 0
    deaths = 0

    decoded = []
    event_ids = []
    missing_fatalities = 0
    missing_accuracy = 0
    for row in rows:
        row_date_missing = False
        row_date_invalid = False
        coordinates_invalid = False
        if legacy:
            if not isinstance(row, list) or len(row) != 8:
                continue
            lat, lng, year, month, fatal, trigger_idx, country_idx, day = row
            event_id = None
            accuracy = None
            fatal_known = True
            if not isinstance(trigger_idx, int) or not (0 <= trigger_idx < len(triggers)):
                invalid_trigger_refs += 1
                trigger = None
            else:
                trigger = triggers[trigger_idx]
            if not isinstance(country_idx, int) or not (0 <= country_idx < len(countries)):
                invalid_country_refs += 1
                country = None
            else:
                country = countries[country_idx]
            row_date_missing = not year or not month or not day
        else:
            required = {"event_id", "event_date", "latitude", "longitude", "location_accuracy", "fatality_count"}
            if not isinstance(row, dict) or not required.issubset(row):
                shape_invalid += 1
                continue
            event_id = row.get("event_id")
            if event_id:
                event_ids.append(event_id)
            lat, lng = row.get("latitude"), row.get("longitude")
            parsed = None
            try:
                parsed = dt.date.fromisoformat(row.get("event_date") or "")
            except (TypeError, ValueError):
                pass
            year, month, day = (parsed.year, parsed.month, parsed.day) if parsed else (0, 0, 0)
            fatal_known = row.get("fatality_count") is not None
            fatal = row.get("fatality_count") if fatal_known else 0
            if not fatal_known:
                missing_fatalities += 1
            accuracy = row.get("location_accuracy")
            if accuracy is None:
                missing_accuracy += 1
            trigger = (row.get("landslide_trigger") or "unknown").strip().lower()
            country = row.get("country_name") or ""
            row_date_missing = not row.get("event_date")
            row_date_invalid = bool(row.get("event_date")) and parsed is None
        coordinates_missing = lat is None or lng is None
        if coordinates_missing:
            missing_coordinates += 1
        elif not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
            invalid_coordinates += 1
            coordinates_invalid = True
        if trigger:
            trigger_counts[trigger] += 1
        if country:
            country_counts[country] += 1
        if row_date_missing:
            missing_dates += 1
        elif row_date_invalid or not all(isinstance(value, int) for value in (year, month, day)) or not valid_date(year, month, day):
            invalid_dates += 1
        years[year] += 1
        months[month] += 1
        if fatal < 0:
            negative_deaths += 1
        deaths += fatal
        exact_keys.append(tuple(row) if legacy else json.dumps(row, sort_keys=True, ensure_ascii=False))
        event_keys.append((lat, lng, year, month, day))
        decoded.append((lat, lng, year, month, day, fatal, trigger, country, event_id, accuracy, fatal_known))

        if 2007 <= year <= 2017 and not coordinates_missing and not coordinates_invalid:
            training_period += 1
            cell_key = (math.floor(lat), math.floor(lng))
            if cell_key in model_cells:
                structural_associated += 1
            else:
                structural_unassociated += 1
            oni_key = year * 12 + month - 1
            if month and oni_key in oni_keys:
                oni_associated += 1
            else:
                oni_unassociated += 1

    if shape_invalid or invalid_coordinates or invalid_trigger_refs or invalid_country_refs:
        problems.append("catalog_schema_or_reference_error")
    if invalid_dates:
        problems.append("catalog_invalid_or_missing_dates")
    if negative_deaths:
        problems.append("catalog_negative_deaths")

    sample = DEFAULT_PLACE.copy()
    nearby = [
        event
        for event in decoded
        if isinstance(event[0], (int, float)) and isinstance(event[1], (int, float))
        and haversine(sample["lat"], sample["lng"], event[0], event[1]) <= 250
    ]
    sample_cell = (math.floor(sample["lat"]), math.floor(sample["lng"]))

    result = {
        "schema_version": schema_version,
        "artifact_records": len(rows),
        "raw_records": None,
        "raw_valid_records": None,
        "raw_discarded_records": None,
        "raw_counts_reason": "CSV bruto ausente do repositorio",
        "shape_invalid": shape_invalid,
        "invalid_coordinates": invalid_coordinates,
        "missing_coordinates": missing_coordinates,
        "invalid_trigger_references": invalid_trigger_refs,
        "invalid_country_references": invalid_country_refs,
        "invalid_or_missing_dates": invalid_dates,
        "missing_dates": missing_dates,
        "negative_deaths": negative_deaths,
        "zero_recorded_deaths": sum(event[5] == 0 and event[10] for event in decoded),
        "missing_fatality_count_preserved": missing_fatalities,
        "missing_location_accuracy_preserved": missing_accuracy,
        "event_id_duplicates": duplicate_stats([(value,) for value in event_ids]),
        "missing_event_ids": len(rows) - len(event_ids) if not legacy else None,
        "recorded_deaths_sum": deaths,
        "year_min": min(years, default=None),
        "year_max": max(years, default=None),
        "records_2007_2017": training_period,
        "records_before_2007": sum(count for year, count in years.items() if year < 2007),
        "exact_duplicate_rows": duplicate_stats(exact_keys),
        "same_coordinate_date_candidates": duplicate_stats(event_keys),
        "countries_nonempty": len(country_counts),
        "triggers": len(trigger_counts),
        "rain_classified_records": sum(trigger_counts[name] for name in RAIN),
        "structural_join": {
            "key": "floor(latitude), floor(longitude)",
            "eligible_records": training_period,
            "associated": structural_associated,
            "unassociated": structural_unassociated,
            "multiplication": "nenhuma; lookup direto por chave unica de celula",
        },
        "oni_join": {
            "key": "year*12 + month - 1",
            "eligible_records": training_period,
            "associated": oni_associated,
            "unassociated": oni_unassociated,
            "multiplication": "nenhuma; Map com uma entrada por mes central",
        },
        "interface_sample": {
            **sample,
            "radius_km": 250,
            "catalog_records": len(nearby),
            "recorded_deaths": sum(event[5] for event in nearby),
            "year_min": min((event[2] for event in nearby), default=None),
            "year_max": max((event[2] for event in nearby), default=None),
            "direct_structural_cell": list(sample_cell),
            "structural_cell_found": sample_cell in model_cells,
        },
    }
    if not legacy and (result["event_id_duplicates"]["extra_rows"] or result["missing_event_ids"]):
        problems.append("catalog_event_identity_error")
    return result, problems


def audit_raw_glc(path: Path, catalog: dict) -> dict:
    """Compara um CSV GLC bruto com a transformação de build_catalog.py."""
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        rows = list(reader)

    raw_exact = collections.Counter(tuple(row.get(name, "") for name in fieldnames) for row in rows)
    ids = [row.get("event_id", "") for row in rows]
    id_counts = collections.Counter(value for value in ids if value)
    transformed = []
    invalid_coordinates = 0
    invalid_dates = 0
    fatality_parse_errors = 0
    years = collections.Counter()
    location_accuracy = collections.Counter()
    prepare_events_eligible = 0
    prepare_event_keys = []
    prepare_power_cells = set()
    trigger_weather_rows = 0
    trigger_weather_keys = []
    structural_eligible = 0
    accepted_accuracy = {"exact", "1km", "5km", "10km", "25km"}

    for row in rows:
        location_accuracy[row.get("location_accuracy", "")] += 1
        try:
            lat = float(row["latitude"])
            lng = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            invalid_coordinates += 1
            continue
        date = row.get("event_date", "") or ""
        try:
            year, month, day = int(date[6:10]), int(date[0:2]), int(date[3:5])
            if not valid_date(year, month, day):
                raise ValueError
        except (TypeError, ValueError):
            invalid_dates += 1
            year = month = day = 0
        fatality = row.get("fatality_count", "")
        try:
            fatality = int(float(fatality)) if fatality.strip() else 0
        except (AttributeError, ValueError):
            fatality_parse_errors += 1
            fatality = 0
        trigger = (row.get("landslide_trigger") or "unknown").strip().lower()
        country = row.get("country_name") or ""
        transformed.append((round(lat, 2), round(lng, 2), year, month, fatality, trigger, country, day))
        years[year] += 1
        if 2007 <= year <= 2017:
            structural_eligible += 1
            if row.get("location_accuracy") in accepted_accuracy:
                prepare_events_eligible += 1
                power_cell = (round(lat / 0.5), round(lng / 0.625))
                event_key = (*power_cell, year, month, day)
                prepare_power_cells.add(power_cell)
                prepare_event_keys.append(event_key)
                if trigger not in NON_WEATHER:
                    trigger_weather_rows += 1
                    trigger_weather_keys.append(event_key)

    if catalog.get("schema_version") == 2:
        local_events = catalog.get("events", [])
        reproduction_mismatches = 0
        for index, (raw, local) in enumerate(zip(rows, local_events), start=2):
            parsed = parse_glc_date(raw.get("event_date"))
            expected_fatality = None
            try:
                if (raw.get("fatality_count") or "").strip():
                    value = float(raw["fatality_count"])
                    expected_fatality = int(value) if value.is_integer() else value
            except ValueError:
                expected_fatality = "parse-error"
            expected = {
                "event_id": (raw.get("event_id") or "").strip() or None,
                "source_row": index,
                "event_date": parsed.isoformat() if parsed else None,
                "latitude": float(raw["latitude"]),
                "longitude": float(raw["longitude"]),
                "location_accuracy": (raw.get("location_accuracy") or "").strip() or None,
                "fatality_count": expected_fatality,
                "source_name": (raw.get("source_name") or "").strip() or None,
                "source_url": (raw.get("source_link") or "").strip() or None,
            }
            actual = {
                "event_id": local.get("event_id"),
                "source_row": local.get("source_row"),
                "event_date": local.get("event_date"),
                "latitude": local.get("latitude"),
                "longitude": local.get("longitude"),
                "location_accuracy": local.get("location_accuracy"),
                "fatality_count": local.get("fatality_count"),
                "source_name": local.get("source", {}).get("name"),
                "source_url": local.get("source", {}).get("url"),
            }
            if expected != actual:
                reproduction_mismatches += 1
        matched = min(len(rows), len(local_events)) - reproduction_mismatches
        local_decoded_count = len(local_events)
        reproduction = {
            "schema_version": 2,
            "local_records": len(local_events),
            "raw_records": len(rows),
            "records_checked_in_source_order": min(len(rows), len(local_events)),
            "matched_required_traceability_fields": matched,
            "mismatched_required_traceability_fields": reproduction_mismatches,
            "compatible_with_build_catalog_py": len(rows) == len(local_events) and reproduction_mismatches == 0,
        }
        caveat = "a compatibilidade é verificável pelo hash do bruto e pelo manifesto gravados no catálogo v2"
    elif catalog.get("schema_version", 1) >= 3:
        integrated_events = catalog.get("events", [])
        integrated_ids = {str(event.get("event_id")) for event in integrated_events if event.get("event_id") is not None}
        raw_ids = {str(row.get("event_id")) for row in rows if row.get("event_id")}
        origins = collections.Counter(event.get("catalog_origin") for event in integrated_events)
        reproduction = {
            "schema_version": catalog.get("schema_version"),
            "policy": catalog.get("source", {}).get("policy"),
            "raw_glc_ids": len(raw_ids),
            "raw_glc_ids_preserved": len(raw_ids & integrated_ids),
            "integrated_records": len(integrated_events),
            "integrated_unique_ids": len(integrated_ids),
            "origins": dict(origins),
            "compatible_with_integrate_coolr_catalog_py": (
                raw_ids <= integrated_ids
                and len(integrated_events) == len(integrated_ids)
                and origins.get("coolr_supersedes_local") == 11030
                and origins.get("coolr_only") == 3720
                and origins.get("glc_local_only") == 3
            ),
        }
        caveat = "o GLC bruto valida a preservação dos 11.033 IDs locais; os oito hashes COOLR são verificados por integrate_coolr_catalog.py"
    else:
        triggers = catalog.get("trig", [])
        countries = catalog.get("ctys", [])
        local_decoded = []
        for lat, lng, year, month, fatality, trigger_idx, country_idx, day in catalog.get("pts", []):
            local_decoded.append((lat, lng, year, month, fatality, triggers[trigger_idx], countries[country_idx], day))
        raw_counter = collections.Counter(transformed)
        local_counter = collections.Counter(local_decoded)
        intersection = raw_counter & local_counter
        matched = sum(intersection.values())
        local_decoded_count = len(local_decoded)
        reproduction = {
            "schema_version": 1,
            "local_records": len(local_decoded),
            "transformed_raw_records": len(transformed),
            "multiset_matched": matched,
            "local_unmatched": len(local_decoded) - matched,
            "transformed_raw_unmatched": len(transformed) - matched,
            "compatible_with_build_catalog_py": matched == len(local_decoded) == len(transformed),
        }
        caveat = "compatibilidade da transformação não prova que este foi o arquivo usado originalmente; o artefato não registra hash de entrada"

    return {
        "path": str(path),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "fields": fieldnames,
        "field_count": len(fieldnames),
        "records": len(rows),
        "valid_coordinate_records": len(transformed),
        "discarded_invalid_coordinates": invalid_coordinates,
        "invalid_dates_encoded_as_zero_by_catalog_builder": invalid_dates,
        "fatality_parse_errors_encoded_as_zero_for_audit": fatality_parse_errors,
        "year_min": min((year for year in years if year), default=None),
        "year_max": max(years, default=None),
        "exact_raw_duplicates": duplicate_stats([tuple(row.get(name, "") for name in fieldnames) for row in rows]),
        "duplicate_event_ids": duplicate_stats([(value,) for value in ids if value]),
        "missing_event_ids": sum(not value for value in ids),
        "location_accuracy": dict(sorted(location_accuracy.items())),
        "prepare_events_eligible_rows": prepare_events_eligible,
        "prepare_events_power_cells": len(prepare_power_cells),
        "prepare_events_unique_cell_dates": len(set(prepare_event_keys)),
        "prepare_events_rows_collapsed_by_cell_date": prepare_events_eligible - len(set(prepare_event_keys)),
        "trigger_weather_eligible_rows": trigger_weather_rows,
        "trigger_weather_power_cells": len({key[:2] for key in trigger_weather_keys}),
        "trigger_weather_unique_cell_dates_before_power_quality_filters": len(set(trigger_weather_keys)),
        "trigger_weather_rows_collapsed_by_cell_date": trigger_weather_rows - len(set(trigger_weather_keys)),
        "structural_training_eligible_rows": structural_eligible,
        "catalog_reproduction": reproduction,
        "caveat": caveat,
    }


def audit_enso(enso: dict) -> tuple[dict, set[int], list[str]]:
    problems: list[str] = []
    rows = enso.get("oni", [])
    keys = []
    invalid_rows = 0
    nonfinite_values = 0
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            invalid_rows += 1
            continue
        year, month, value = row
        if not isinstance(year, int) or not isinstance(month, int) or not 1 <= month <= 12:
            invalid_rows += 1
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            nonfinite_values += 1
        keys.append(year * 12 + month - 1)
    duplicates = duplicate_stats([(key,) for key in keys])
    sorted_keys = sorted(set(keys))
    gaps = sum(b - a - 1 for a, b in zip(sorted_keys, sorted_keys[1:]))
    if invalid_rows or nonfinite_values or duplicates["extra_rows"] or gaps:
        problems.append("enso_sequence_or_schema_error")
    updated = enso.get("updated")
    try:
        dt.date.fromisoformat(updated)
        updated_valid = True
    except (TypeError, ValueError):
        updated_valid = False
        problems.append("enso_invalid_updated_date")
    result = {
        "records": len(rows),
        "invalid_rows": invalid_rows,
        "nonfinite_values": nonfinite_values,
        "duplicate_month_keys": duplicates,
        "missing_months_between_first_last": gaps,
        "strictly_increasing": keys == sorted(keys) and len(keys) == len(set(keys)),
        "first": rows[0] if rows else None,
        "last": rows[-1] if rows else None,
        "source": enso.get("source"),
        "download_date": updated,
        "download_date_valid": updated_valid,
        "note": "updated e data de execucao do coletor; nao e data oficial de publicacao",
    }
    return result, set(keys), problems


def audit_models(models: dict) -> tuple[dict, set[tuple[int, int]], list[str]]:
    problems: list[str] = []
    grid = models.get("grid", {})
    cells = grid.get("cells", [])
    grid_v2 = int(grid.get("schema_version", 0)) >= 2
    cell_keys = []
    invalid_rows = 0
    invalid_values = 0
    all_values = []
    p2_values = []
    cell_lookup = {}
    for row in cells:
        if not isinstance(row, list) or len(row) != 14:
            invalid_rows += 1
            continue
        lat, lng, *values = row
        if not isinstance(lat, int) or not isinstance(lng, int) or not (-90 <= lat <= 89) or not (-180 <= lng <= 179):
            invalid_rows += 1
        if any(not isinstance(value, int) or not 0 <= value <= 1000 for value in values):
            invalid_values += 1
        key = (lat, lng)
        cell_keys.append(key)
        all_values.extend(values)
        probs = [value / 1000 for value in values]
        p2 = max(probs) if grid_v2 else 1 - math.prod(1 - value for value in probs)
        p2_values.append(p2)
        cell_lookup[key] = {"monthly": probs, "p2": p2}
    cell_dupes = duplicate_stats(cell_keys)
    if invalid_rows or invalid_values or cell_dupes["extra_rows"]:
        problems.append("structural_grid_schema_or_duplicate_error")

    trigger = models.get("trig", {})
    features = trigger.get("feat", [])
    trees = trigger.get("trees", [])
    tree_invalid = 0
    for tree in trees:
        fields = ("f", "th", "l", "r", "v", "ml", "leaf")
        lengths = [len(tree.get(field, [])) for field in fields]
        if not lengths or min(lengths) == 0 or len(set(lengths)) != 1:
            tree_invalid += 1
            continue
        size = lengths[0]
        for index, is_leaf in enumerate(tree["leaf"]):
            if not is_leaf:
                if not 0 <= tree["f"][index] < len(features):
                    tree_invalid += 1
                    break
                if not 0 <= tree["l"][index] < size or not 0 <= tree["r"][index] < size:
                    tree_invalid += 1
                    break
    thresholds = trigger.get("thr", {})
    threshold_values = [thresholds.get(name) for name in ("elev", "alto", "muito")]
    monotonic_thresholds = all(isinstance(value, (int, float)) for value in threshold_values) and threshold_values == sorted(threshold_values)
    if tree_invalid or not monotonic_thresholds:
        problems.append("trigger_model_structure_error")

    petr_key = (math.floor(DEFAULT_PLACE["lat"]), math.floor(DEFAULT_PLACE["lng"]))
    petr = cell_lookup.get(petr_key)
    result = {
        "structural": {
            "cells": len(cells),
            "invalid_rows": invalid_rows,
            "invalid_monthly_values": invalid_values,
            "duplicate_cell_keys": cell_dupes,
            "monthly_value_min": min(all_values, default=None),
            "monthly_value_max": max(all_values, default=None),
            "zero_monthly_values": sum(value == 0 for value in all_values),
            "p2_min": min(p2_values, default=None),
            "p2_max": max(p2_values, default=None),
            "metrics_n_cells": grid.get("metrics", {}).get("n_cells"),
            "metrics_matches_rows": grid.get("metrics", {}).get("n_cells") == len(cells),
            "aggregate_rule": "maximum monthly uncalibrated score" if grid_v2 else "1-product(1-p_month)",
            "p2_assumption": None if grid_v2 else "independencia mensal nao validada",
            "petrópolis": None if petr is None else {"cell": list(petr_key), **petr},
        },
        "trigger": {
            "features": len(features),
            "feature_names": features,
            "trees": len(trees),
            "invalid_trees": tree_invalid,
            "thresholds": thresholds,
            "thresholds_monotonic": monotonic_thresholds,
            "metrics": trigger.get("metrics", {}),
            "probability_calibrated": False,
            "calibration_evidence": None,
        },
    }
    return result, set(cell_keys), problems


def audit_static_configuration() -> dict:
    app = (ROOT / "app.js").read_text(encoding="utf-8")
    gibs = json.loads((DATA / "gibs.json").read_text(encoding="utf-8"))
    return {
        "power_time_standard_explicit": "time-standard=" in app,
        "power_default_consequence": "LST conforme documentacao da API na ausencia do parametro",
        "gibs_time_parameter": {key: layer.get("requested_time") for key, layer in gibs["layers"].items()},
        "gibs_represented_time": {key: layer.get("represented_time") for key, layer in gibs["layers"].items()},
        "gibs_fallback": {key: layer.get("fallback") for key, layer in gibs["layers"].items()},
        "raw_training_files_present": {
            "glc_csv": any((DATA / "sources" / "glc").rglob("*Global_Landslide*csv")),
            "countries_110m": (ROOT / "countries-110m.json").exists(),
            "train_events": (ROOT / "train_events.json").exists(),
            "power_directory": (ROOT / "power").is_dir(),
        },
    }


def run(raw_glc: Path | None = None) -> tuple[dict, list[str]]:
    paths = {name: DATA / f"{name}.json" for name in ("catalog", "enso", "models", "gibs")}
    payloads = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}

    enso, oni_keys, enso_problems = audit_enso(payloads["enso"])
    models, model_cells, model_problems = audit_models(payloads["models"])
    catalog, catalog_problems = audit_catalog(payloads["catalog"], model_cells, oni_keys)
    problems = enso_problems + model_problems + catalog_problems
    result = {
        "audit_date": dt.date.today().isoformat(),
        "scope": "artefatos processados versionados; fontes brutas ausentes nao auditadas",
        "artifacts": {
            name: {"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for name, path in paths.items()
        },
        "catalog": catalog,
        "enso": enso,
        "models": models,
        "static_configuration": audit_static_configuration(),
        "hard_problems": problems,
    }
    if raw_glc is not None:
        result["raw_glc_comparison"] = audit_raw_glc(raw_glc, payloads["catalog"])
    return result, problems


def summary(result: dict) -> str:
    catalog = result["catalog"]
    structural = result["models"]["structural"]
    return "\n".join(
        [
            f"catalog_records={catalog['artifact_records']}",
            f"catalog_exact_duplicate_extra_rows={catalog['exact_duplicate_rows']['extra_rows']}",
            f"catalog_same_coordinate_date_candidate_extra_rows={catalog['same_coordinate_date_candidates']['extra_rows']}",
            f"structural_join_associated={catalog['structural_join']['associated']}",
            f"structural_join_unassociated={catalog['structural_join']['unassociated']}",
            f"oni_join_associated={catalog['oni_join']['associated']}",
            f"oni_join_unassociated={catalog['oni_join']['unassociated']}",
            f"structural_cells={structural['cells']}",
            f"enso_records={result['enso']['records']}",
            f"hard_problems={len(result['hard_problems'])}",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", action="store_true", help="imprime apenas contagens principais")
    parser.add_argument("--strict", action="store_true", help="retorna codigo 1 se houver erro estrutural")
    parser.add_argument("--raw-glc", type=Path, help="CSV GLC bruto para comparar com data/catalog.json")
    args = parser.parse_args()
    result, problems = run(args.raw_glc)
    print(summary(result) if args.summary else json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if args.strict and problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
