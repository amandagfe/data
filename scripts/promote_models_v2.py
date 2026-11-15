#!/usr/bin/env python3
"""Promove manualmente dois artefatos v2 aceitos para ``data/models.json``.

Treinadores nunca chamam este script. A promoção verifica status, hashes e
paridade já registrada, preserva a versão anterior e grava de modo atômico.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_accepted(report_path: Path, expected_name: str) -> tuple[dict, dict, Path]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("status") != "accepted_for_manual_promotion":
        raise ValueError(f"{report_path}: candidato não aceito")
    if not report.get("production_refit_performed"):
        raise ValueError(f"{report_path}: refit de produção ausente")
    declared = report.get("candidate_artifact") or {}
    artifact_path = Path(declared.get("path", ""))
    if not artifact_path.is_absolute():
        # Os relatórios atuais registram caminhos relativos à raiz do projeto.
        artifact_path = Path.cwd() / artifact_path
    if artifact_path.name != expected_name or not artifact_path.is_file():
        raise ValueError(f"artefato esperado {expected_name} não encontrado")
    digest = sha256(artifact_path)
    if digest != declared.get("sha256"):
        raise ValueError(f"hash divergente em {artifact_path}")
    return report, json.loads(artifact_path.read_text(encoding="utf-8")), artifact_path


def structural_payload(report: dict, artifact: dict) -> dict:
    temporal = report["final_tests"]["final_temporal_test"]
    spatial = report["final_tests"]["final_spatial_test"]
    return {
        "schema_version": 2,
        "cells": artifact["cells"],
        "aggregation": "maximum monthly score; monthly scores are not combined as probabilities",
        "metrics": {
            "auc": spatial["auc"], "ap": spatial["average_precision"],
            "base_auc": spatial["baseline_auc"], "base_ap": spatial["baseline_average_precision"],
            "top10": spatial["top10_capture"], "base_top10": spatial["baseline_top10_capture"],
            "pos_rate": spatial["positive_rate"], "n_test": spatial["n"],
            "n_cells": report["grid"]["cells"],
            "spatial_test": spatial, "temporal_test": temporal,
        },
        "imp": artifact["imp"],
        "metadata": {
            "role": artifact["model_role"], "feature_period": artifact["feature_period"],
            "forecast_horizon": artifact["forecast_horizon"], "warning": artifact["warning"],
            "catalog_sha256": report["catalog"]["sha256"], "grid_sha256": report["grid"]["sha256"],
        },
    }


def weather_payload(report: dict, artifact: dict) -> dict:
    temporal = report["final_tests"]["final_temporal_test"]
    spatial = report["final_tests"]["final_spatial_test"]
    return {
        "schema_version": 2, "feat": artifact["feat"], "base": artifact["base"],
        "trees": artifact["trees"], "thr": artifact["thr"], "imp": artifact["imp"],
        "metrics": {
            "auc": spatial["auc"], "base_auc": spatial["baseline_auc"],
            "ap": spatial["average_precision"], "base_ap": spatial["baseline_average_precision"],
            "auc_time": temporal["auc"], "base_auc_time": temporal["baseline_auc"],
            "ap_time": temporal["average_precision"], "base_ap_time": temporal["baseline_average_precision"],
            "cases": report["production_cases"],
            "places": report["production_places"],
            "spatial_test": spatial, "temporal_test": temporal,
        },
        "metadata": {
            "role": artifact["model_role"], "feature_reference_period": artifact["feature_reference_period"],
            "label_period": artifact["label_period"], "temporal_rule": artifact["temporal_rule"],
            "warning": artifact["warning"], "ledger_sha256": report["run"]["ledger_sha256"],
            "export_parity_max_absolute_difference": report["export_parity_max_absolute_difference"],
        },
    }


def repository_state() -> dict:
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], check=True, capture_output=True, text=True
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], check=True, capture_output=True, text=True
        ).stdout)
        return {"commit": commit, "worktree_dirty_at_promotion": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "worktree_dirty_at_promotion": None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--structural-report", type=Path, required=True)
    parser.add_argument("--weather-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, required=True)
    parser.add_argument("--reports-dir", type=Path, required=True)
    args = parser.parse_args()

    sr, structural, structural_path = load_accepted(args.structural_report, "structural-v2.json")
    wr, weather, weather_path = load_accepted(args.weather_report, "weather-v2.json")
    if wr.get("export_parity_max_absolute_difference", 1) >= 1e-7:
        raise ValueError("paridade do artefato meteorológico não atende ao limite")
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    args.reports_dir.mkdir(parents=True, exist_ok=True)
    evidence_sources = {
        "structural-training.json": args.structural_report,
        "structural-preparation.json": args.structural_report.parent.parent / "manifest.json",
        "weather-training.json": args.weather_report,
        "weather-preparation.json": Path(wr["run"]["directory"]) / "preparation.json",
        "weather-reconciliation.json": Path(wr["run"]["directory"]) / "reconciliation.json",
    }
    evidence = {}
    for name, source in evidence_sources.items():
        if not source.is_file():
            raise ValueError(f"evidência de promoção ausente: {source}")
        destination = args.reports_dir / name
        shutil.copy2(source, destination)
        evidence[name] = {"path": str(destination), "sha256": sha256(destination)}
    payload = {
        "schema_version": 2,
        "release": {
            "version": "2026-11-15-v2", "generated_at": generated,
            "promotion": "manual_after_predeclared_gates",
            "repository": repository_state(),
            "code_sha256": {
                name: sha256(Path(__file__).resolve().parent / name)
                for name in ("train_structural_v2.py", "train_weather_v2.py", "promote_models_v2.py")
            },
            "evidence": evidence,
            "published_artifacts": {
                "structural": {"sha256": sha256(structural_path), "report_sha256": sha256(args.structural_report)},
                "weather": {"sha256": sha256(weather_path), "report_sha256": sha256(args.weather_report)},
            },
        },
        "grid": structural_payload(sr, structural),
        "trig": weather_payload(wr, weather),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.backup_dir.mkdir(parents=True, exist_ok=True)
        old_hash = sha256(args.output)
        backup = args.backup_dir / f"models-{old_hash[:16]}.json"
        if not backup.exists():
            shutil.copy2(args.output, backup)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    with temporary.open("rb") as stream:
        os.fsync(stream.fileno())
    os.replace(temporary, args.output)
    print(json.dumps({"output": str(args.output), "sha256": sha256(args.output),
                      "backup_dir": str(args.backup_dir)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
