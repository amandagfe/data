#!/usr/bin/env python3
"""Treina e avalia o modelo estrutural v2 sem promover o artefato publicado.

A seleção usa apenas os papéis selection_* preparados antes da abertura dos
testes finais. O refit de produção só é gerado depois de registrar as métricas
dos testes e continua em um diretório candidato separado de data/models.json.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

import prepare_structural_v2 as protocol


ROOT = Path(__file__).resolve().parents[1]
FEATURES = [
    "event_rate_cell_year", "event_rate_cell_month_year",
    "event_rate_neighbors_1_year", "event_rate_neighbors_1_month_year",
    "event_rate_neighbors_2_year", "fatalities_region_log1p",
    "fatality_values_known", "fatality_values_missing", "rain_trigger_fraction",
    "rain_trigger_missing", "active_years_region", "has_local_history",
    "latitude", "abs_latitude", "sin_longitude", "cos_longitude",
    "sin_month", "cos_month",
]
PARAMETERS = [
    {"max_leaf_nodes": 12, "min_samples_leaf": 80, "l2_regularization": 1.0},
    {"max_leaf_nodes": 24, "min_samples_leaf": 80, "l2_regularization": 1.0},
    {"max_leaf_nodes": 24, "min_samples_leaf": 160, "l2_regularization": 5.0},
]
ROLLING_WINDOWS = [
    ((2007, 2012), (2013, 2014)), ((2007, 2014), (2015, 2016)),
    ((2007, 2016), (2017, 2018)), ((2007, 2018), (2019, 2020)),
    ((2007, 2020), (2021, 2022)), ((2007, 2022), (2023, 2024)),
    # Corte adicional parcialmente sobreposto para que 2025 entre como rótulo
    # sem alterar o alvo fixo de dois anos.
    ((2007, 2023), (2024, 2025)),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matrix(events, cells, feature_years, label_years, partitions) -> tuple[np.ndarray, np.ndarray, list]:
    selected = [cell for cell in cells if protocol.partition(cell) in partitions]
    count = len(selected) * 12
    X = np.empty((count, len(FEATURES)), dtype=np.float32)
    y = np.empty(count, dtype=np.uint8)
    keys = []
    agg = protocol.aggregate(events, feature_years)
    positives = {(event["cell"], event["month"]) for event in events
                 if label_years[0] <= event["year"] <= label_years[1]}
    index = 0
    for cell in selected:
        for month in range(1, 13):
            values = protocol.features(agg, cell, month, feature_years)
            X[index] = [np.nan if values[name] is None else values[name] for name in FEATURES]
            y[index] = int((cell, month) in positives)
            keys.append((cell[0], cell[1], month)); index += 1
    return X, y, keys


def inference_matrix(events, cells, feature_years) -> tuple[np.ndarray, list]:
    X = np.empty((len(cells) * 12, len(FEATURES)), dtype=np.float32); keys = []
    agg = protocol.aggregate(events, feature_years); index = 0
    for cell in cells:
        for month in range(1, 13):
            values = protocol.features(agg, cell, month, feature_years)
            X[index] = [np.nan if values[name] is None else values[name] for name in FEATURES]
            keys.append((cell[0], cell[1], month)); index += 1
    return X, keys


def balanced_weights(y):
    positives = max(1, int(y.sum())); negatives = max(1, len(y) - positives)
    return np.where(y == 1, len(y) / (2 * positives), len(y) / (2 * negatives))


def baseline(X):
    return np.nan_to_num(X[:, 1]) + 0.5 * np.nan_to_num(X[:, 3]) + 0.1 * np.nan_to_num(X[:, 0])


def metrics(y, score, base) -> dict:
    order = np.argsort(-score)[:max(1, int(len(score) * 0.10))]
    base_order = np.argsort(-base)[:max(1, int(len(base) * 0.10))]
    positives = max(1, int(y.sum()))
    return {
        "n": int(len(y)), "positives": int(y.sum()), "positive_rate": float(y.mean()),
        "auc": float(roc_auc_score(y, score)), "average_precision": float(average_precision_score(y, score)),
        "brier": float(brier_score_loss(y, score)), "top10_capture": float(y[order].sum() / positives),
        "baseline_auc": float(roc_auc_score(y, base)),
        "baseline_average_precision": float(average_precision_score(y, base)),
        "baseline_top10_capture": float(y[base_order].sum() / positives),
    }


def build_model(params):
    return HistGradientBoostingClassifier(
        max_iter=200, learning_rate=0.05, random_state=7,
        early_stopping=False, **params,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=ROOT / "data" / "catalog.json")
    parser.add_argument("--grid", type=Path, default=ROOT / "data" / "grids" / "land-1deg.json")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--skip-production-refit", action="store_true")
    args = parser.parse_args(); args.output_dir.mkdir(parents=True, exist_ok=True)

    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    grid = json.loads(args.grid.read_text(encoding="utf-8"))
    events = protocol.event_rows(catalog); cells = [tuple(cell) for cell in grid["cells"]]
    cell_set = set(cells); events = [event for event in events if event["cell"] in cell_set]

    X_train, y_train, _ = matrix(events, cells, *protocol.ROLES["selection_train"][:2], {"development"})
    validation_sets = {}
    for role in ("selection_spatial_validation", "selection_temporal_validation"):
        feature_years, label_years, partition = protocol.ROLES[role]
        validation_sets[role] = matrix(events, cells, feature_years, label_years, {partition})[:2]

    trials = []
    for params in PARAMETERS:
        model = build_model(params); model.fit(X_train, y_train, sample_weight=balanced_weights(y_train))
        evaluations = {}
        for role, (X_valid, y_valid) in validation_sets.items():
            score = model.predict_proba(X_valid)[:, 1]
            evaluations[role] = metrics(y_valid, score, baseline(X_valid))
        selection_score = float(np.mean([value["auc"] for value in evaluations.values()]))
        trials.append({"params": params, "selection_score_mean_auc": selection_score, "evaluations": evaluations})
    chosen = max(trials, key=lambda item: item["selection_score_mean_auc"])

    # Refit de avaliação: somente intervalos anteriores a 2017 e sem a partição espacial de teste.
    X_spatial, y_spatial = validation_sets["selection_spatial_validation"]
    X_temporal, y_temporal = validation_sets["selection_temporal_validation"]
    X_development = np.vstack([X_train, X_spatial, X_temporal])
    y_development = np.concatenate([y_train, y_spatial, y_temporal])
    evaluation_model = build_model(chosen["params"])
    evaluation_model.fit(X_development, y_development, sample_weight=balanced_weights(y_development))

    final_tests = {}; test_arrays = {}
    for role in ("final_temporal_test", "final_spatial_test"):
        feature_years, label_years, partition = protocol.ROLES[role]
        X_test, y_test, _ = matrix(events, cells, feature_years, label_years, {partition})
        score = evaluation_model.predict_proba(X_test)[:, 1]
        final_tests[role] = metrics(y_test, score, baseline(X_test)); test_arrays[role] = (X_test, y_test)

    accepted = all(value["auc"] >= value["baseline_auc"] and
                   value["average_precision"] >= value["baseline_average_precision"]
                   for value in final_tests.values())
    largest_role = max(test_arrays, key=lambda role: len(test_arrays[role][1]))
    X_imp, y_imp = test_arrays[largest_role]
    if len(y_imp) > 100_000:
        rng = np.random.default_rng(7); chosen_rows = rng.choice(len(y_imp), 100_000, replace=False)
        X_imp, y_imp = X_imp[chosen_rows], y_imp[chosen_rows]
    importance = permutation_importance(evaluation_model, X_imp, y_imp, scoring="roc_auc", n_repeats=2,
                                        random_state=7, n_jobs=1)
    ranked_importance = sorted(zip(FEATURES, importance.importances_mean), key=lambda item: -item[1])

    report = {
        "schema_version": 1, "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "accepted_for_manual_promotion" if accepted else "rejected_by_predeclared_baseline_gate",
        "catalog": {"path": str(args.catalog), "sha256": sha256(args.catalog), "events_used": len(events)},
        "grid": {"path": str(args.grid), "sha256": sha256(args.grid), "cells": len(cells)},
        "environment": {"python": platform.python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__},
        "target": "registro de ao menos um evento na célula de 1 grau e mês em horizonte futuro de dois anos",
        "selection_trials": trials, "selected_params": chosen["params"], "final_tests": final_tests,
        "acceptance_gate": "AUC e average precision devem ser >= baseline nos testes temporal e espacial",
        "permutation_importance": [[name, float(value)] for name, value in ranked_importance],
        "production_refit_performed": False, "published_model_overwritten": False,
    }
    joblib.dump(evaluation_model, args.output_dir / "evaluation-model.joblib")

    if accepted and not args.skip_production_refit:
        chunks_X = []; chunks_y = []
        for feature_years, label_years in ROLLING_WINDOWS:
            X_part, y_part, _ = matrix(events, cells, feature_years, label_years,
                                       {"development", "validation", "test"})
            chunks_X.append(X_part); chunks_y.append(y_part)
        X_all = np.vstack(chunks_X); y_all = np.concatenate(chunks_y)
        production_model = build_model(chosen["params"])
        production_model.fit(X_all, y_all, sample_weight=balanced_weights(y_all))
        X_future, keys = inference_matrix(events, cells, protocol.PRODUCTION_FEATURE_YEARS)
        scores = production_model.predict_proba(X_future)[:, 1]
        rows = {}; 
        for (lat, lon, month), score in zip(keys, scores):
            rows.setdefault((lat, lon), [0] * 12)[month - 1] = int(round(float(score) * 1000))
        artifact = {
            "schema_version": 2, "model_role": "structural_record_recurrence_score",
            "forecast_horizon": [2026, 2027], "feature_period": [2007, 2025],
            "cells": [[lat, lon] + values for (lat, lon), values in sorted(rows.items())],
            "metrics": final_tests, "imp": report["permutation_importance"],
            "warning": "uncalibrated score; not probability, susceptibility, hazard or risk",
        }
        artifact_path = args.output_dir / "structural-v2.json"
        artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        joblib.dump(production_model, args.output_dir / "production-model.joblib")
        report["production_refit_performed"] = True
        report["production_training_examples"] = int(len(y_all))
        report["production_positive_examples"] = int(y_all.sum())
        report["candidate_artifact"] = {"path": str(artifact_path), "sha256": sha256(artifact_path), "cells": len(rows)}

    report_path = args.output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(report_path), "status": report["status"],
                      "production_refit": report["production_refit_performed"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
