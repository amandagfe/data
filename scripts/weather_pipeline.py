#!/usr/bin/env python3
"""Pipeline rastreável para uma nova coleta POWER; não treina modelos.

Comandos:
  prepare  cria ledger, candidatos e exclusões a partir do catálogo v2;
  collect  coleta células em processo separado, com cache, retentativa e retomada;
  reconcile prova que todo candidato está em exatamente um estado terminal/pendente.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NON_WEATHER = {"earthquake", "mining", "construction", "dam_embankment_collapse", "leaking_pipe", "vibration", "volcano", "other"}
ACCURACY = {"exact", "1km", "5km", "10km", "25km"}
ACCURACY_ALIASES = {
    "known exactly": "exact", "known within 1 km": "1km",
    "known within 5 km": "5km", "known within 10 km": "10km",
}
PARAMETERS = ("PRECTOTCORR", "GWETTOP", "GWETROOT")
STATUSES = ("pending", "collecting", "valid", "excluded", "failed")
SUPPORTED_CATALOG_SCHEMAS = {2, 3}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=60)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db


def schema(db: sqlite3.Connection) -> None:
    db.executescript("""
    CREATE TABLE IF NOT EXISTS runs(
      run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, catalog_sha256 TEXT NOT NULL,
      catalog_schema INTEGER NOT NULL, rule_version TEXT NOT NULL,
      target_definition TEXT NOT NULL, time_standard TEXT NOT NULL,
      event_start TEXT NOT NULL, event_end TEXT NOT NULL,
      power_start TEXT NOT NULL, power_end TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS cells(
      cell_id TEXT PRIMARY KEY, lat REAL NOT NULL, lon REAL NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
      last_error TEXT, cache_file TEXT, cache_sha256 TEXT, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS candidates(
      candidate_id TEXT PRIMARY KEY, cell_id TEXT NOT NULL REFERENCES cells(cell_id), event_date TEXT NOT NULL,
      event_ids TEXT NOT NULL, triggers TEXT NOT NULL, status TEXT NOT NULL,
      collection_status TEXT NOT NULL, product TEXT, api_version TEXT, reference_start TEXT,
      reference_end TEXT, time_standard TEXT, validation TEXT, exclusion_reason TEXT,
      attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS attempts(
      id INTEGER PRIMARY KEY AUTOINCREMENT, cell_id TEXT NOT NULL, attempt INTEGER NOT NULL,
      started_at TEXT NOT NULL, finished_at TEXT, outcome TEXT NOT NULL, http_url TEXT,
      error TEXT, response_sha256 TEXT
    );
    CREATE TABLE IF NOT EXISTS event_decisions(
      event_id TEXT PRIMARY KEY, event_date TEXT, cell_id TEXT, candidate_id TEXT,
      status TEXT NOT NULL, reason TEXT, updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS candidates_cell ON candidates(cell_id);
    CREATE INDEX IF NOT EXISTS candidates_status ON candidates(status);
    """)


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cell_for(lat: float, lon: float) -> tuple[str, float, float]:
    lat_index, lon_index = round(lat / 0.5), round(lon / 0.625)
    return f"{lat_index}_{lon_index}", lat_index * 0.5, lon_index * 0.625


def candidate_id(cell_id: str, date: str) -> str:
    return hashlib.sha256(f"power-lst-v1|{cell_id}|{date}".encode()).hexdigest()[:24]


def normalized_accuracy(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return ACCURACY_ALIASES.get(text, text)


def valid_coordinate(lat, lon) -> bool:
    return (isinstance(lat, (int, float)) and not isinstance(lat, bool)
            and isinstance(lon, (int, float)) and not isinstance(lon, bool)
            and -90 <= lat <= 90 and -180 <= lon <= 180)


def prepare(args) -> dict:
    args.run_dir.mkdir(parents=True, exist_ok=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    catalog_schema = catalog.get("schema_version")
    if catalog_schema not in SUPPORTED_CATALOG_SCHEMAS:
        raise ValueError(f"schema de catálogo não suportado: {catalog_schema}")
    groups: dict[tuple[str, str], dict] = {}
    cells = {}
    decisions = []
    source_rows = eligible_rows = 0
    for event in catalog["events"]:
        source_rows += 1
        event_id = str(event.get("event_id") or f"source-row-{source_rows}")
        date = event.get("event_date")
        accuracy = normalized_accuracy(event.get("location_accuracy"))
        lat, lon = event.get("latitude"), event.get("longitude")
        reason = None
        if not date:
            reason = "missing_event_date"
        else:
            try:
                dt.date.fromisoformat(date)
            except (TypeError, ValueError):
                reason = "invalid_event_date"
        if reason is None and not (args.event_start <= date <= args.event_end):
            reason = "outside_configured_event_period"
        if reason is None and not valid_coordinate(lat, lon):
            reason = "missing_or_invalid_coordinate"
        if reason is None and accuracy not in ACCURACY:
            reason = "spatial_accuracy_not_supported_for_power_grid"
        if reason:
            decisions.append((event_id, date, None, None, "excluded_before_candidate", reason))
            continue
        eligible_rows += 1
        cell_id, cell_lat, cell_lon = cell_for(lat, lon)
        cells[cell_id] = (cell_lat, cell_lon)
        group = groups.setdefault((cell_id, date), {"event_ids": [], "triggers": set()})
        group["event_ids"].append(event_id)
        group["triggers"].add((event.get("landslide_trigger") or "unknown").strip().lower())
        decisions.append((event_id, date, cell_id, candidate_id(cell_id, date), "linked_candidate", None))

    ledger = args.run_dir / "ledger.sqlite"
    db = connect(ledger)
    schema(db)
    run_id = args.run_dir.name
    with db:
        db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            run_id, now(), file_hash(args.catalog), catalog_schema, "power-predictive-d-minus-1/v2",
            "evento na data civil D; atributos usam somente valores POWER LST até D-1 porque a hora/fuso do evento não é confiável",
            "LST", args.event_start, args.event_end, args.power_start, args.power_end,
        ))
        for cell_id, (lat, lon) in sorted(cells.items()):
            db.execute("INSERT OR IGNORE INTO cells(cell_id,lat,lon,updated_at) VALUES (?,?,?,?)", (cell_id, lat, lon, now()))
        for (cell_id, date), group in sorted(groups.items()):
            triggers = sorted(group["triggers"])
            excluded = all(trigger in NON_WEATHER for trigger in triggers)
            status = "excluded" if excluded else "pending"
            reason = "all_linked_records_have_explicit_non_weather_trigger" if excluded else None
            db.execute("""INSERT OR REPLACE INTO candidates
              (candidate_id,cell_id,event_date,event_ids,triggers,status,collection_status,exclusion_reason,updated_at)
              VALUES (?,?,?,?,?,?,?,?,?)""", (
                candidate_id(cell_id, date), cell_id, date, json.dumps(sorted(group["event_ids"])),
                json.dumps(triggers), status, "not_requested" if excluded else "pending", reason, now(),
            ))
        for event_id, date, cell_id, linked_candidate, status, reason in decisions:
            db.execute("""INSERT OR REPLACE INTO event_decisions
              (event_id,event_date,cell_id,candidate_id,status,reason,updated_at)
              VALUES (?,?,?,?,?,?,?)""", (event_id, date, cell_id, linked_candidate, status, reason, now()))
        db.execute("""UPDATE event_decisions SET status='linked_excluded_candidate',
          reason='all_linked_records_have_explicit_non_weather_trigger',updated_at=?
          WHERE candidate_id IN (SELECT candidate_id FROM candidates WHERE status='excluded')""", (now(),))
    report = reconcile_db(db)
    report.update({"source_rows": source_rows, "eligible_rows_before_trigger": eligible_rows, "cells_before_trigger": len(cells)})
    write_json(args.run_dir / "preparation.json", report)
    db.close()
    return report


def power_url(lat: float, lon: float, start: str = "20010101", end: str = "20251231") -> str:
    params = {
        "parameters": ",".join(PARAMETERS), "community": "AG", "longitude": f"{lon:.4f}",
        "latitude": f"{lat:.4f}", "start": start, "end": end,
        "time-standard": "LST", "format": "JSON",
    }
    return "https://power.larc.nasa.gov/api/temporal/daily/point?" + urllib.parse.urlencode(params)


def collect_cell(ledger: Path, cache_dir: Path, row: dict, retries: int,
                 power_start: str, power_end: str) -> tuple[str, str]:
    cell_id, lat, lon = row["cell_id"], row["lat"], row["lon"]
    url = power_url(lat, lon, power_start, power_end)
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{cell_id}.json"
    for attempt in range(1, retries + 1):
        started = now()
        db = connect(ledger)
        with db:
            db.execute("UPDATE cells SET status='collecting',attempts=attempts+1,updated_at=? WHERE cell_id=?", (started, cell_id))
            db.execute("UPDATE candidates SET status='collecting',collection_status='requesting',attempts=attempts+1,updated_at=? WHERE cell_id=? AND status NOT IN ('excluded','valid')", (started, cell_id))
            cursor = db.execute("INSERT INTO attempts(cell_id,attempt,started_at,outcome,http_url) VALUES (?,?,?,?,?)", (cell_id, attempt, started, "started", url))
            attempt_id = cursor.lastrowid
        db.close()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "DataDetectivesWeatherPipeline/1.0"})
            with urllib.request.urlopen(request, timeout=180) as response:
                body = response.read()
            payload = json.loads(body)
            parameters = payload["properties"]["parameter"]
            if not set(PARAMETERS) <= set(parameters):
                raise ValueError("missing_required_parameter")
            header = payload.get("header", {})
            if header.get("time_standard") != "LST":
                raise ValueError(f"unexpected_time_standard:{header.get('time_standard')}")
            digest = hashlib.sha256(body).hexdigest()
            temporary = target.with_suffix(".json.tmp")
            with temporary.open("wb") as stream:
                stream.write(body); stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, target)
            products = ",".join(header.get("sources", [])) or "not_reported"
            api_version = header.get("api", {}).get("version")
            validation = validate_candidates(ledger, cell_id, parameters, products, api_version)
            db = connect(ledger)
            with db:
                # O status da célula deriva de todos os seus candidatos, não só dos
                # validados nesta passada: uma retomada pode encontrar candidatos já válidos.
                has_valid = db.execute("SELECT EXISTS(SELECT 1 FROM candidates WHERE cell_id=? AND status='valid')", (cell_id,)).fetchone()[0]
                cell_status = "valid" if has_valid else "excluded"
                db.execute("UPDATE cells SET status=?,cache_file=?,cache_sha256=?,last_error=NULL,updated_at=? WHERE cell_id=?", (cell_status, str(target), digest, now(), cell_id))
                db.execute("UPDATE attempts SET finished_at=?,outcome='success',response_sha256=? WHERE id=?", (now(), digest, attempt_id))
            db.close()
            return cell_id, cell_status
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"[:1000]
            db = connect(ledger)
            with db:
                db.execute("UPDATE attempts SET finished_at=?,outcome='failed',error=? WHERE id=?", (now(), error, attempt_id))
                db.execute("UPDATE cells SET last_error=?,updated_at=? WHERE cell_id=?", (error, now(), cell_id))
                db.execute("UPDATE candidates SET collection_status='retry_pending',last_error=?,updated_at=? WHERE cell_id=? AND status='collecting'", (error, now(), cell_id))
            db.close()
            if attempt < retries:
                time.sleep(min(30, 2 ** attempt))
    db = connect(ledger)
    with db:
        db.execute("UPDATE cells SET status='failed',updated_at=? WHERE cell_id=?", (now(), cell_id))
        db.execute("UPDATE candidates SET status='failed',collection_status='failed',exclusion_reason='collection_failed_after_retries',updated_at=? WHERE cell_id=? AND status='collecting'", (now(), cell_id))
    db.close()
    return cell_id, "failed"


def value(series: dict, date: dt.date):
    return series.get(date.strftime("%Y%m%d"))


def predictive_reference(event_date: dt.date) -> tuple[dt.date, dt.date, list[dt.date]]:
    """Janela disponível no instante conservador: termina no dia LST anterior."""
    cutoff = event_date - dt.timedelta(days=1)
    rain_dates = [cutoff - dt.timedelta(days=offset) for offset in range(29, -1, -1)]
    return rain_dates[0], cutoff, rain_dates


def validate_candidates(ledger: Path, cell_id: str, parameters: dict, product: str, api_version: str | None) -> dict:
    db = connect(ledger)
    rows = db.execute("SELECT candidate_id,event_date FROM candidates WHERE cell_id=? AND status='collecting'", (cell_id,)).fetchall()
    valid = excluded = 0
    with db:
        for row in rows:
            event_date = dt.date.fromisoformat(row["event_date"])
            _, cutoff, rain_dates = predictive_reference(event_date)
            rain = [value(parameters["PRECTOTCORR"], date) for date in rain_dates]
            top = value(parameters["GWETTOP"], cutoff)
            root = value(parameters["GWETROOT"], cutoff)
            missing = ["rain_30d"] if any(item in (None, -999) for item in rain) else []
            if top in (None, -999): missing.append("gwettop_d_minus_1")
            if root in (None, -999): missing.append("gwetroot_d_minus_1")
            is_valid = not missing
            status = "valid" if is_valid else "excluded"
            reason = None if is_valid else "missing_power:" + ",".join(missing)
            db.execute("""UPDATE candidates SET status=?,collection_status='collected',product=?,api_version=?,
              reference_start=?,reference_end=?,time_standard='LST',validation=?,exclusion_reason=?,last_error=NULL,updated_at=?
              WHERE candidate_id=?""", (
                status, product, api_version, rain_dates[0].isoformat(), cutoff.isoformat(),
                "predictive_d_minus_1_complete" if is_valid else "predictive_d_minus_1_incomplete",
                reason, now(), row["candidate_id"],
            ))
            valid += int(is_valid); excluded += int(not is_valid)
    db.close()
    return {"valid": valid, "excluded": excluded}


@contextlib.contextmanager
def run_lock(run_dir: Path):
    # Um único escritor por execução: a retomada reabre células em andamento
    # e só é segura quando nenhum outro processo está coletando ou reparando.
    run_dir.mkdir(parents=True, exist_ok=True)
    lock = (run_dir / "collect.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise SystemExit(f"outro coletor já está ativo em {run_dir}; abortando sem alterar o ledger")
    try:
        yield
    finally:
        lock.close()


def collect(args) -> dict:
    with run_lock(args.run_dir):
        return _collect_locked(args)


def repair_cells(args) -> dict:
    """Corrige células cujo status ficou defasado em relação a candidatos válidos.

    Só promove a célula se o cache existir, o hash do arquivo for igual ao
    registrado e houver tentativa bem-sucedida com esse mesmo hash. Caso
    contrário, os candidatos voltam a pendente para nova coleta. Cada decisão
    fica na tabela ``cell_repairs``.
    """
    with run_lock(args.run_dir):
        ledger = args.run_dir / "ledger.sqlite"
        db = connect(ledger)
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS cell_repairs(
              id INTEGER PRIMARY KEY, cell_id TEXT NOT NULL, previous_status TEXT NOT NULL,
              new_status TEXT NOT NULL, reason TEXT NOT NULL, cache_sha256 TEXT, repaired_at TEXT NOT NULL)""")
        rows = db.execute("""SELECT x.cell_id,x.status,x.cache_file,x.cache_sha256 FROM cells x
          WHERE x.status!='valid' AND EXISTS(SELECT 1 FROM candidates c WHERE c.cell_id=x.cell_id AND c.status='valid')
          ORDER BY x.cell_id""").fetchall()
        outcome = {"promoted_to_valid": 0, "reset_to_pending": 0}
        with db:
            for row in rows:
                path = Path(row["cache_file"]) if row["cache_file"] else None
                if path is not None and not path.is_absolute():
                    path = ROOT / path
                ok = (path is not None and path.exists() and row["cache_sha256"]
                      and file_hash(path) == row["cache_sha256"]
                      and db.execute("SELECT EXISTS(SELECT 1 FROM attempts WHERE cell_id=? AND outcome='success' AND response_sha256=?)",
                                     (row["cell_id"], row["cache_sha256"])).fetchone()[0])
                if ok:
                    db.execute("UPDATE cells SET status='valid',last_error=NULL,updated_at=? WHERE cell_id=?", (now(), row["cell_id"]))
                    new, reason = "valid", "stale_cell_status_cache_hash_verified"
                    outcome["promoted_to_valid"] += 1
                else:
                    db.execute("UPDATE cells SET status='pending',updated_at=? WHERE cell_id=?", (now(), row["cell_id"]))
                    db.execute("""UPDATE candidates SET status='pending',collection_status='repair_recollect',updated_at=?
                      WHERE cell_id=? AND status='valid'""", (now(), row["cell_id"]))
                    new, reason = "pending", "stale_cell_status_cache_unverifiable"
                    outcome["reset_to_pending"] += 1
                db.execute("""INSERT INTO cell_repairs(cell_id,previous_status,new_status,reason,cache_sha256,repaired_at)
                  VALUES (?,?,?,?,?,?)""", (row["cell_id"], row["status"], new, reason, row["cache_sha256"], now()))
        report = reconcile_db(db)
        report["cell_repair"] = outcome
        write_json(args.run_dir / "reconciliation.json", report)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        db.close()
        return report


def _collect_locked(args) -> dict:
    ledger = args.run_dir / "ledger.sqlite"
    db = connect(ledger)
    schema(db)
    # Interrupções anteriores voltam a pendente; o histórico da tentativa permanece.
    with db:
        db.execute("""UPDATE attempts SET finished_at=?,outcome='interrupted',
          error='process_interrupted_before_terminal_status'
          WHERE outcome='started' AND finished_at IS NULL""", (now(),))
        db.execute("UPDATE cells SET status='pending' WHERE status='collecting'")
        db.execute("UPDATE candidates SET status='pending',collection_status='resume_pending' WHERE status='collecting'")
    run = db.execute("SELECT power_start,power_end FROM runs LIMIT 1").fetchone()
    if run is None:
        raise ValueError("ledger sem metadados; execute prepare primeiro")
    rows = [dict(row) for row in db.execute("""SELECT DISTINCT c.cell_id,c.lat,c.lon FROM cells c
      JOIN candidates e ON e.cell_id=c.cell_id WHERE e.status IN ('pending','failed') ORDER BY c.cell_id""")]
    db.close()
    if args.limit_cells is not None:
        rows = rows[:args.limit_cells]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(collect_cell, ledger, args.run_dir / "cache", row, args.retries,
                               run["power_start"], run["power_end"]) for row in rows]
        for future in concurrent.futures.as_completed(futures):
            cell_id, status = future.result()
            print(json.dumps({"cell_id": cell_id, "status": status}), flush=True)
    db = connect(ledger)
    report = reconcile_db(db)
    write_json(args.run_dir / "reconciliation.json", report)
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    db.close()
    return report


def reconcile_db(db: sqlite3.Connection) -> dict:
    counts = {status: db.execute("SELECT count(*) FROM candidates WHERE status=?", (status,)).fetchone()[0] for status in STATUSES}
    total = db.execute("SELECT count(*) FROM candidates").fetchone()[0]
    linked_rows = db.execute("SELECT event_ids FROM candidates").fetchall()
    event_links = sum(len(json.loads(row[0])) for row in linked_rows)
    active_cells = db.execute("SELECT count(DISTINCT cell_id) FROM candidates WHERE status!='excluded' OR collection_status='collected'").fetchone()[0]
    decision_counts = {row[0]: row[1] for row in db.execute(
        "SELECT status,count(*) FROM event_decisions GROUP BY status ORDER BY status")}
    exclusion_reasons = {row[0]: row[1] for row in db.execute(
        "SELECT reason,count(*) FROM event_decisions WHERE reason IS NOT NULL GROUP BY reason ORDER BY reason")}
    # Candidato válido em célula não válida seria descartado no treino sem aviso.
    stale_cells, stale_candidates = db.execute("""SELECT count(DISTINCT x.cell_id),count(c.candidate_id)
      FROM cells x JOIN candidates c ON c.cell_id=x.cell_id
      WHERE x.status!='valid' AND c.status='valid'""").fetchone()
    return {
        "generated_at": now(), "candidate_total": total, "status_counts": counts,
        "reconciled": sum(counts.values()) == total and stale_cells == 0,
        "silent_loss": total - sum(counts.values()),
        "stale_cell_status": {"cells": stale_cells, "valid_candidates": stale_candidates},
        "linked_event_rows": event_links, "candidate_cells": active_cells,
        "source_event_decisions": sum(decision_counts.values()),
        "event_decision_counts": decision_counts, "event_exclusion_reasons": exclusion_reasons,
        "rule": "predictive features end at POWER LST D-1; same-day D is excluded because event time/zone is not reliable",
    }


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--catalog", type=Path, default=ROOT / "data" / "catalog.json")
    prep.add_argument("--run-dir", type=Path, required=True)
    prep.add_argument("--event-start", default="2007-01-01")
    prep.add_argument("--event-end", default="2025-12-31")
    prep.add_argument("--power-start", default="20010101")
    prep.add_argument("--power-end", default="20251231")
    get = sub.add_parser("collect")
    get.add_argument("--run-dir", type=Path, required=True)
    get.add_argument("--workers", type=int, default=3)
    get.add_argument("--retries", type=int, default=5)
    get.add_argument("--limit-cells", type=int)
    rec = sub.add_parser("reconcile")
    rec.add_argument("--run-dir", type=Path, required=True)
    rep = sub.add_parser("repair-cells")
    rep.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare": result = prepare(args)
    elif args.command == "collect": result = collect(args)
    elif args.command == "repair-cells": result = repair_cells(args)
    else:
        db = connect(args.run_dir / "ledger.sqlite"); result = reconcile_db(db)
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)"); db.close()
        write_json(args.run_dir / "reconciliation.json", result)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("reconciled", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
