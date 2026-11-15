#!/usr/bin/env python3
"""Treina um candidato meteorológico v2 a partir de uma execução POWER concluída.

O script não faz coleta, não altera ``data/models.json`` e não usa o dia
civil do evento. Todas as janelas terminam em D-1 LST. As transformações de
percentil usam uma referência fixa anterior aos rótulos (2001–2006).
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import math
import platform
import sqlite3
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


FEATURES = [
    "rain_d_minus_1", "rain_3d", "rain_7d", "rain_14d", "rain_30d",
    "rain_antecedent_30d_excluding_7d", "percentile_rain_1d",
    "percentile_rain_3d", "percentile_rain_7d", "percentile_rain_14d",
    "surface_soil_wetness_d_minus_1", "root_soil_wetness_d_minus_1",
    "percentile_surface_soil_wetness", "percentile_root_soil_wetness",
    "reference_annual_rain", "rain_7d_over_reference_p95",
]
PARAMETERS = [
    {"max_leaf_nodes": 12, "min_samples_leaf": 50, "l2_regularization": 1.0},
    {"max_leaf_nodes": 24, "min_samples_leaf": 50, "l2_regularization": 1.0},
    {"max_leaf_nodes": 24, "min_samples_leaf": 100, "l2_regularization": 5.0},
]
REFERENCE_START = dt.date(2001, 1, 1)
REFERENCE_END = dt.date(2006, 12, 31)
CONTROL_RATIO = 4


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def spatial_partition(cell_id: str) -> str:
    """Separa blocos POWER vizinhos, e não eventos individuais."""
    lat_index, lon_index = map(int, cell_id.split("_"))
    block = (lat_index // 10, lon_index // 8)  # cerca de 5° x 5°
    value = int(hashlib.sha256(
        f"weather-spatial-v2|{block[0]}|{block[1]}".encode()
    ).hexdigest()[:8], 16) % 100
    return "development" if value < 70 else "validation" if value < 85 else "test"


def role_for(cell_id: str, year: int) -> str | None:
    partition = spatial_partition(cell_id)
    if 2007 <= year <= 2016:
        if partition == "development":
            return "selection_train"
        if partition == "validation":
            return "selection_spatial_validation"
    if 2017 <= year <= 2019 and partition == "development":
        return "selection_temporal_validation"
    if 2020 <= year <= 2025:
        if partition in {"development", "validation"}:
            return "final_temporal_test"
        return "final_spatial_test"
    return None


def date_range(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def rolling_sum(values: np.ndarray, window: int) -> np.ndarray:
    good = ~np.isnan(values)
    sums = np.concatenate(([0.0], np.cumsum(np.nan_to_num(values))))
    counts = np.concatenate(([0], np.cumsum(good.astype(np.int32))))
    result = np.full(len(values), np.nan)
    indices = np.arange(window - 1, len(values))
    total = sums[indices + 1] - sums[indices + 1 - window]
    complete = counts[indices + 1] - counts[indices + 1 - window] == window
    result[indices] = np.where(complete, total, np.nan)
    return result


def percentile(sorted_values: np.ndarray, value: float) -> float:
    return float(np.searchsorted(sorted_values, value, side="right") / len(sorted_values))


def quantile(sorted_values: np.ndarray, q: float) -> float:
    return float(sorted_values[math.floor(q * (len(sorted_values) - 1))])


def power_arrays(payload: dict) -> tuple[dt.date, np.ndarray, np.ndarray, np.ndarray]:
    parameters = payload["properties"]["parameter"]
    keys = sorted(parameters["PRECTOTCORR"])
    if not keys:
        raise ValueError("POWER sem datas")
    start = dt.datetime.strptime(keys[0], "%Y%m%d").date()
    expected = [(start + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(len(keys))]
    if keys != expected:
        raise ValueError("série POWER não é diária/contígua")
    arrays = []
    for name in ("PRECTOTCORR", "GWETTOP", "GWETROOT"):
        array = np.asarray([parameters[name].get(key, np.nan) for key in keys], dtype=float)
        array[array == -999] = np.nan
        arrays.append(array)
    return start, arrays[0], arrays[1], arrays[2]


def cell_feature_function(payload: dict):
    start, rain, top, root = power_arrays(payload)
    r3, r7, r14, r30 = (rolling_sum(rain, size) for size in (3, 7, 14, 30))
    ref_lo = (REFERENCE_START - start).days
    ref_hi = (REFERENCE_END - start).days + 1
    if ref_lo < 0 or ref_hi > len(rain):
        raise ValueError("série POWER não cobre a referência 2001–2006")
    references = []
    for array in (rain, r3, r7, r14, top, root):
        values = np.sort(array[ref_lo:ref_hi][~np.isnan(array[ref_lo:ref_hi])])
        if len(values) < 300:
            raise ValueError("referência 2001–2006 insuficiente")
        references.append(values)
    annual_rain = float(np.mean(references[0]) * 365.25)
    rain7_p95 = quantile(references[2], 0.95)

    def features(reference_date: dt.date) -> list[float] | None:
        # reference_date é sempre D-1 para casos e a data simulada para controles.
        index = (reference_date - start).days
        if index < 29 or index >= len(rain):
            return None
        values = [rain[index], r3[index], r7[index], r14[index], r30[index], top[index], root[index]]
        if any(np.isnan(value) for value in values):
            return None
        return [
            values[0], values[1], values[2], values[3], values[4], values[4] - values[2],
            percentile(references[0], values[0]), percentile(references[1], values[1]),
            percentile(references[2], values[2]), percentile(references[3], values[3]),
            values[5], values[6], percentile(references[4], values[5]),
            percentile(references[5], values[6]), annual_rain,
            values[2] / max(1.0, rain7_p95),
        ]

    return features


def deterministic_controls(cell_id: str, event_date: dt.date, blocked: set[dt.date], count: int,
                           observation_end: dt.date | None = None) -> list[dt.date]:
    year = event_date.year
    start, end = dt.date(year, 1, 1), dt.date(year, 12, 31)
    if observation_end is not None:
        end = min(end, observation_end)
    choices = [date for date in date_range(start, end) if date not in blocked]
    seed = int(hashlib.sha256(f"controls-v2|{cell_id}|{event_date}".encode()).hexdigest()[:16], 16)
    rng = np.random.default_rng(seed)
    if len(choices) < count:
        return []
    return [choices[index] for index in rng.choice(len(choices), count, replace=False)]


def load_dataset(run_dir: Path):
    ledger = run_dir / "ledger.sqlite"
    db = sqlite3.connect(ledger); db.row_factory = sqlite3.Row
    run = dict(db.execute("SELECT * FROM runs LIMIT 1").fetchone())
    counts = dict(db.execute("SELECT status,count(*) FROM candidates GROUP BY status"))
    if counts.get("pending", 0) or counts.get("collecting", 0) or counts.get("failed", 0):
        raise ValueError(f"coleta não concluída: {counts}")
    rows = db.execute("""SELECT candidate_id,cell_id,event_date,event_ids,triggers
      FROM candidates WHERE status='valid' ORDER BY cell_id,event_date""").fetchall()
    all_event_dates = collections.defaultdict(set)
    for row in db.execute("SELECT cell_id,event_date FROM candidates"):
        all_event_dates[row["cell_id"]].add(dt.date.fromisoformat(row["event_date"]))
    observation_end = max(date for dates in all_event_dates.values() for date in dates)
    by_cell = collections.defaultdict(list)
    for row in rows:
        by_cell[row["cell_id"]].append(dict(row))
    cell_rows = {row["cell_id"]: dict(row) for row in db.execute(
        "SELECT cell_id,cache_file,cache_sha256 FROM cells WHERE status='valid'")}
    provenance = [dict(row) for row in db.execute("""SELECT product,api_version,time_standard,count(*) AS candidates
      FROM candidates WHERE status='valid' GROUP BY product,api_version,time_standard
      ORDER BY product,api_version,time_standard""")]
    db.close()

    samples = collections.defaultdict(lambda: {"X": [], "y": [], "cell": [], "date": [], "candidate": []})
    exclusions = collections.Counter(); controls_seen = set()
    for cell_id, candidates in by_cell.items():
        cell = cell_rows.get(cell_id)
        if not cell or not cell["cache_file"]:
            exclusions["valid_candidate_without_valid_cell_cache"] += len(candidates); continue
        cache_path = Path(cell["cache_file"])
        if not cache_path.is_absolute():
            cache_path = Path.cwd() / cache_path
        if sha256(cache_path) != cell["cache_sha256"]:
            exclusions["cache_hash_mismatch"] += len(candidates); continue
        try:
            make_features = cell_feature_function(json.loads(cache_path.read_text(encoding="utf-8")))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            exclusions["invalid_cache_for_training"] += len(candidates); continue
        # Controles não podem cair perto de nenhum registro do ledger, inclusive
        # candidatos excluídos por gatilho não meteorológico.
        event_dates = all_event_dates[cell_id]
        blocked = {date + dt.timedelta(days=offset) for date in event_dates for offset in range(-10, 11)}
        for row in candidates:
            event_date = dt.date.fromisoformat(row["event_date"])
            role = role_for(cell_id, event_date.year)
            case = make_features(event_date - dt.timedelta(days=1))
            if case is None:
                exclusions["case_features_incomplete"] += 1; continue
            target_roles = ["production_all"]
            if role is None:
                exclusions["reserved_from_evaluation_roles_but_kept_for_production"] += 1
            else:
                target_roles.append(role)
            for target_role in target_roles:
                target = samples[target_role]
                target["X"].append(case); target["y"].append(1); target["cell"].append(cell_id)
                target["date"].append(event_date.isoformat()); target["candidate"].append(row["candidate_id"])
            for control_date in deterministic_controls(
                    cell_id, event_date, blocked, CONTROL_RATIO, observation_end):
                control = make_features(control_date - dt.timedelta(days=1))
                if control is None:
                    exclusions["control_features_incomplete"] += 1; continue
                for target_role in target_roles:
                    control_key = (target_role, cell_id, control_date)
                    if control_key in controls_seen:
                        continue
                    controls_seen.add(control_key)
                    target = samples[target_role]
                    target["X"].append(control); target["y"].append(0); target["cell"].append(cell_id)
                    target["date"].append(control_date.isoformat()); target["candidate"].append(None)
    for values in samples.values():
        values["X"] = np.asarray(values["X"], dtype=np.float32)
        values["y"] = np.asarray(values["y"], dtype=np.uint8)
    return run, counts, samples, exclusions, observation_end, provenance


def balanced_weights(y):
    positives, negatives = int(y.sum()), int(len(y) - y.sum())
    if not positives or not negatives:
        raise ValueError("papel sem as duas classes")
    return np.where(y == 1, len(y) / (2 * positives), len(y) / (2 * negatives))


def make_model(params):
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, early_stopping=False, random_state=7, **params
    )


def evaluate(y, score, base):
    return {
        "n": int(len(y)), "cases": int(y.sum()), "controls": int(len(y) - y.sum()),
        "auc": float(roc_auc_score(y, score)),
        "average_precision": float(average_precision_score(y, score)),
        "brier": float(brier_score_loss(y, score)),
        "baseline_auc": float(roc_auc_score(y, base)),
        "baseline_average_precision": float(average_precision_score(y, base)),
    }


def export_trees(model) -> tuple[float, list[dict]]:
    trees = []
    for predictors in model._predictors:
        if len(predictors) != 1:
            raise ValueError("exportador suporta somente classificação binária")
        nodes = predictors[0].nodes
        trees.append({
            "f": nodes["feature_idx"].astype(int).tolist(),
            "th": [float(value) for value in nodes["num_threshold"]],
            "l": nodes["left"].astype(int).tolist(), "r": nodes["right"].astype(int).tolist(),
            "v": [float(value) for value in nodes["value"]],
            "ml": nodes["missing_go_to_left"].astype(int).tolist(),
            "leaf": nodes["is_leaf"].astype(int).tolist(),
        })
    return float(np.ravel(model._baseline_prediction)[0]), trees


def exported_predict(base: float, trees: list[dict], row: np.ndarray) -> float:
    raw = base
    for tree in trees:
        index = 0
        while not tree["leaf"][index]:
            value = row[tree["f"][index]]
            go_left = tree["ml"][index] if np.isnan(value) else value <= tree["th"][index]
            index = tree["l"][index] if go_left else tree["r"][index]
        raw += tree["v"][index]
    return 1 / (1 + math.exp(-raw))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-production-refit", action="store_true")
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)

    run, collection_counts, samples, exclusions, observation_end, provenance = load_dataset(args.run_dir)
    required = {"selection_train", "selection_spatial_validation", "selection_temporal_validation",
                "final_temporal_test", "final_spatial_test"}
    if not required <= samples.keys():
        raise ValueError(f"papéis ausentes: {sorted(required - samples.keys())}")
    train = samples["selection_train"]
    trials = []
    for params in PARAMETERS:
        model = make_model(params)
        model.fit(train["X"], train["y"], sample_weight=balanced_weights(train["y"]))
        validations = {}
        for role in ("selection_spatial_validation", "selection_temporal_validation"):
            data = samples[role]; score = model.predict_proba(data["X"])[:, 1]
            validations[role] = evaluate(data["y"], score, data["X"][:, 8])
        selection_score = float(np.mean([value["auc"] for value in validations.values()]))
        trials.append({"params": params, "selection_mean_auc": selection_score, "evaluations": validations})
    chosen = max(trials, key=lambda item: item["selection_mean_auc"])

    development_roles = ("selection_train", "selection_spatial_validation", "selection_temporal_validation")
    X_development = np.vstack([samples[role]["X"] for role in development_roles])
    y_development = np.concatenate([samples[role]["y"] for role in development_roles])
    evaluation_model = make_model(chosen["params"])
    evaluation_model.fit(X_development, y_development, sample_weight=balanced_weights(y_development))
    final_tests = {}
    for role in ("final_temporal_test", "final_spatial_test"):
        data = samples[role]; score = evaluation_model.predict_proba(data["X"])[:, 1]
        final_tests[role] = evaluate(data["y"], score, data["X"][:, 8])
    accepted = all(value["auc"] >= value["baseline_auc"] and
                   value["average_precision"] >= value["baseline_average_precision"]
                   for value in final_tests.values())

    importance_data = samples["final_temporal_test"]
    importance = permutation_importance(
        evaluation_model, importance_data["X"], importance_data["y"],
        scoring="roc_auc", n_repeats=2, random_state=7, n_jobs=1,
    )
    ranked_importance = sorted(zip(FEATURES, importance.importances_mean), key=lambda item: -item[1])
    joblib.dump(evaluation_model, args.output_dir / "evaluation-model.joblib")
    report = {
        "schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "accepted_for_manual_promotion" if accepted else "rejected_by_predeclared_baseline_gate",
        "run": {"directory": str(args.run_dir), "metadata": run, "collection_counts": collection_counts,
                "ledger_sha256": sha256(args.run_dir / "ledger.sqlite"), "provenance": provenance},
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scikit_learn": sklearn.__version__},
        "target": "registro de evento na data civil D; variáveis meteorológicas disponíveis até D-1 LST",
        "control_interpretation": "dias sem registro no ledger em uma janela de +/-10 dias; não comprovam ausência de deslizamento",
        "reference_period": [REFERENCE_START.isoformat(), REFERENCE_END.isoformat()],
        "catalog_observation_end_for_controls": observation_end.isoformat(),
        "roles": {role: {"examples": len(data["y"]), "cases": int(data["y"].sum()),
                          "controls": int(len(data["y"]) - data["y"].sum()),
                          "cells": len(set(data["cell"])),
                          "date_min": min(data["date"]), "date_max": max(data["date"])}
                  for role, data in samples.items()},
        "exclusions": dict(exclusions), "selection_trials": trials,
        "selected_params": chosen["params"], "final_tests": final_tests,
        "acceptance_gate": "AUC e average precision >= baseline de percentil de chuva 7d nos dois testes finais",
        "permutation_importance": [[name, float(value)] for name, value in ranked_importance],
        "production_refit_performed": False, "published_model_overwritten": False,
    }

    if accepted and not args.skip_production_refit:
        X_all = samples["production_all"]["X"]
        y_all = samples["production_all"]["y"]
        production_model = make_model(chosen["params"])
        production_model.fit(X_all, y_all, sample_weight=balanced_weights(y_all))
        base, trees = export_trees(production_model)
        check_indices = np.linspace(0, len(y_all) - 1, min(500, len(y_all)), dtype=int)
        native = production_model.predict_proba(X_all[check_indices])[:, 1]
        exported = np.asarray([exported_predict(base, trees, X_all[index]) for index in check_indices])
        max_difference = float(np.max(np.abs(native - exported)))
        if max_difference >= 1e-7:
            raise ValueError(f"paridade Python/JSON falhou: {max_difference}")
        control_scores = production_model.predict_proba(X_all[y_all == 0])[:, 1]
        thresholds = {name: float(np.quantile(control_scores, q, method="lower"))
                      for name, q in (("elev", 0.90), ("alto", 0.97), ("muito", 0.99))}
        artifact = {
            "schema_version": 2, "model_role": "weather_condition_similarity_score",
            "feat": FEATURES, "base": base, "trees": trees, "thr": thresholds,
            "imp": report["permutation_importance"], "metrics": final_tests,
            "feature_reference_period": ["2001-01-01", "2006-12-31"],
            "label_period": ["2007-01-01", observation_end.isoformat()],
            "temporal_rule": "all dynamic features end at D-1 LST",
            "warning": "uncalibrated similarity score; not probability, forecast, susceptibility, hazard or risk",
        }
        artifact_path = args.output_dir / "weather-v2.json"
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        joblib.dump(production_model, args.output_dir / "production-model.joblib")
        report["production_refit_performed"] = True
        report["production_examples"] = int(len(y_all)); report["production_cases"] = int(y_all.sum())
        report["production_places"] = len(set(samples["production_all"]["cell"]))
        report["export_parity_max_absolute_difference"] = max_difference
        report["candidate_artifact"] = {"path": str(artifact_path), "sha256": sha256(artifact_path)}

    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "status": report["status"],
                      "production_refit": report["production_refit_performed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
