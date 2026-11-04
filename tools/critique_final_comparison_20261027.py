#!/usr/bin/env python3
"""Run the sealed, once-only S0 comparison on ten fresh generator seeds.

Development chooses at most one primary comparison. All nine declared models
are measured, including when there is no primary. Final scores never select a
new model. Only ``FinalSeedGate.get`` can generate final data in this runner.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fishing_demo.data import generate_dataset
from fishing_demo.models import classification_metrics
from fishing_demo.pipeline import save_json
from tools import critique_comparison_20261027 as development

FINAL_SEEDS = tuple(range(12101, 12111))
INIT_SEEDS = (42, 137)
BOOTSTRAP_SEED = 20261027
BOOTSTRAP_REPETITIONS = 2000
PROTOCOL_SCHEMA = "fishing_critique_final_protocol_v1"
FREEZE_SCHEMA = "fishing_critique_final_freeze_v1"
RESULT_SCHEMA = "fishing_critique_final_results_v1"
METRICS = ("accuracy", "macro_f1", "nll", "brier")
FINAL_CRITERIA = {
    "normal_macro_f1_delta_min": -.01,
    "shift_macro_f1_delta_min": .05,
    "positive_shift_seed_min": 8,
    "same_denominators": True,
    "finite_metrics": True,
    "shift_bootstrap_lower_strictly_above": 0,
    "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
    "bootstrap_seed": BOOTSTRAP_SEED,
    "confidence_level": .95,
    "aggregation_unit": "generator_seed_after_mean_of_two_initializations",
}
DISPLAY_NAMES = (
    "기준 MLP 400", "MLP 1200", "MLP L2 .001", "MLP L2 .01", "선형", "ExtraTrees",
    "가상 시간 추가", "보폭 추가", "시간 간격만 추가",
)


def _read_json(path):
    def reject_constant(value):
        raise ValueError(f"nonfinite JSON constant: {value}")
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream, parse_constant=reject_constant)


def _artifact(directory, relative):
    if not isinstance(relative, str) or not relative:
        raise ValueError("artifact path must be a nonempty relative path")
    directory = Path(directory).resolve()
    relative_path = Path(relative)
    path = (directory / relative_path).resolve()
    if relative_path.is_absolute() or directory not in path.parents:
        raise ValueError("artifact path must remain inside its output directory")
    return path


def _check_hash(path, expected):
    if not isinstance(expected, str) or development.sha256(path) != expected:
        raise ValueError(f"artifact hash mismatch: {Path(path).name}")


def _sidecar_matches(path, expected):
    if Path(path).read_text(encoding="ascii").strip() != expected:
        raise ValueError(f"hash sidecar mismatch: {Path(path).name}")


def _declared_models():
    models = (development.BASELINE, *development.CANDIDATES)
    if (len(models) != 9 or len({item["name"] for item in models}) != 9
            or tuple(development.RESERVED_FINAL_SEEDS) != FINAL_SEEDS
            or tuple(development.INIT_SEEDS) != INIT_SEEDS):
        raise ValueError("comparison requires the fixed nine models and final/init seed schedule")
    required = {"tools/critique_final_comparison_20261027.py", "tests/test_critique_final_comparison.py"}
    if not required.issubset(development.SOURCE_FILES):
        raise ValueError("both final runner and final tests must be in the source freeze")
    return models


def _verify_run_artifacts(directory, row, config, sources, phase):
    """Verify saved probabilities against metrics, labels, IDs and model metadata."""
    if row.get("candidate") != config["name"] or row.get("phase") != phase:
        raise ValueError("run record differs from its declared model or phase")
    if not row.get("reload_raw_and_calibrated_probabilities_identical"):
        raise ValueError("run is missing exact raw/calibrated model reload verification")
    model_path = _artifact(directory, row["model_path"])
    predictions_path = _artifact(directory, row["predictions_path"])
    _check_hash(model_path, row["model_sha256"])
    _check_hash(predictions_path, row["predictions_sha256"])
    bundle = _read_json(model_path)
    if (bundle.get("config") != config or bundle.get("source_sha256") != sources
            or bundle.get("phase") != phase or bundle.get("source_type") != "synthetic"
            or bundle.get("data_seed") != row["data_seed"] or bundle.get("init_seed") != row["init_seed"]
            or bundle.get("dataset_sha256") != row["dataset_sha256"]
            or development.digest(bundle.get("preprocessor")) != row["preprocessor_sha256"]):
        raise ValueError("saved model metadata differs from its run evidence")
    temperature = bundle.get("temperature")
    if (isinstance(temperature, bool) or not isinstance(temperature, (int, float))
            or not np.isfinite(temperature) or temperature <= 0 or row.get("temperature") != temperature):
        raise ValueError("saved model needs the recorded finite positive calibration temperature")
    groups = [set(bundle[key]) for key in ("fit_groups", "selection_groups", "calibration_groups")]
    if any(not group for group in groups) or any(groups[a] & groups[b] for a in range(3) for b in range(a + 1, 3)):
        raise ValueError("train, validation and calibration groups must be nonempty and separate")
    if config["backend"] == "extratrees":
        classifier = bundle.get("classifier", {})
        tree_path = model_path.with_suffix(".pkl")
        if classifier.get("file") != tree_path.name:
            raise ValueError("tree state must be the same-stem adjacent artifact")
        _check_hash(tree_path, classifier.get("sha256"))
    predictions = _read_json(predictions_path)
    if not isinstance(predictions, list):
        raise ValueError("saved predictions must be a list")
    identities, seen = [], set()
    for prediction in predictions:
        if (prediction.get("generator_seed") != row["data_seed"] or prediction.get("init_seed") != row["init_seed"]
                or prediction.get("source_type") != "synthetic" or prediction.get("split") not in ("test", "stress")):
            raise ValueError("saved prediction differs from its run identity")
        key = (prediction["split"], prediction["sample_id"])
        if key in seen:
            raise ValueError("duplicate evaluation row in saved predictions")
        seen.add(key)
        identities.append([prediction["sample_id"], prediction["vessel_id"], prediction["split"],
                           prediction.get("true_label"), prediction.get("status")])
    for split, role in (("test", "normal"), ("stress", "shift")):
        selected = [item for item in predictions if item["split"] == split]
        usable = [item for item in selected if item.get("status") == "ok"]
        labeled = [item for item in usable if type(item.get("true_label")) is int and 0 <= item["true_label"] < 3]
        metric = row["metrics"][role]
        before = row["before_calibration"][role]
        if (len(selected) != metric["total"] or len(usable) != metric["valid"]
                or len(selected) - len(usable) != metric["abstained"]
                or len(labeled) != metric["evaluated_labeled"] or not labeled):
            raise ValueError("saved prediction evaluation denominators differ from metrics")
        if any(item.get("status") not in ("ok", "abstained") for item in selected):
            raise ValueError("unknown prediction validity status")
        if any(item.get("probabilities") is not None or item.get("predicted_label") is not None
               for item in selected if item.get("status") == "abstained"):
            raise ValueError("abstentions must not carry model probabilities")
        values = np.asarray([item["probabilities"] for item in labeled], dtype=float)
        if (values.shape != (len(labeled), 3) or not np.isfinite(values).all() or (values < 0).any()
                or not np.allclose(values.sum(axis=1), 1.0, rtol=0, atol=1e-12)):
            raise ValueError("saved probabilities must be finite three-class distributions")
        if any(item.get("predicted_label") != int(p.argmax()) for item, p in zip(labeled, values)):
            raise ValueError("saved predicted class differs from probability argmax")
        actual = classification_metrics(np.asarray([item["true_label"] for item in labeled]), values)
        if (actual["support"] != metric["support"] or actual["confusion"] != metric["confusion"]
                or any(not np.isclose(actual[key], metric[key], rtol=0, atol=1e-12) for key in METRICS)):
            raise ValueError("saved probabilities do not reproduce recorded metrics")
        ids_hash = development.digest([[row["data_seed"], item["sample_id"]] for item in labeled])
        if ids_hash != metric["evaluation_row_sha256"]:
            raise ValueError("evaluation row IDs differ from the recorded denominator hash")
        if (before["confusion"] != metric["confusion"] or before["support"] != metric["support"]
                or before["accuracy"] != metric["accuracy"] or before["macro_f1"] != metric["macro_f1"]):
            raise ValueError("positive temperature must preserve classification argmax")
    return development.digest(identities)


def validate_development(directory, *, expected_sources=None):
    """Read and verify complete development evidence without changing its choice."""
    directory = Path(directory).resolve()
    models = _declared_models()
    sources = development.source_hashes() if expected_sources is None else dict(expected_sources)
    if set(sources) != set(development.SOURCE_FILES) or development.source_hashes() != sources:
        raise ValueError("current sources differ from the development source contract")
    protocol_path, results_path = directory / "protocol.json", directory / "results.json"
    protocol, results = _read_json(protocol_path), _read_json(results_path)
    protocol_hash = development.sha256(protocol_path)
    _sidecar_matches(directory / "protocol.sha256", protocol_hash)
    expected_protocol = development.protocol_payload(sources, started_at=protocol.get("started_at_utc"))
    if protocol != expected_protocol or results.get("protocol") != protocol or results.get("protocol_sha256") != protocol_hash:
        raise ValueError("development protocol/results differ from the fixed current source contract")
    if results.get("schema_version") != "fishing_critique_comparison_results_v1" or results.get("source_type") != "synthetic":
        raise ValueError("expected complete synthetic development comparison results")
    checks = results.get("checks", {})
    required_checks = {"sealed_protocol_unchanged", "sources_unchanged", "source_snapshot_matches",
                       "only_new_development_data_generated", "same_denominators",
                       "literal_same_train_only_preprocessor_per_family",
                       "all_raw_and_calibrated_reload_predictions_identical", "all_prespecified_candidates_completed"}
    if not required_checks.issubset(checks) or not all(value is True for value in checks.values()):
        raise ValueError("development comparison is incomplete or failed its audit")
    stages = results.get("stage_results")
    if not isinstance(stages, list) or [stage.get("candidate") for stage in stages] != list(models):
        raise ValueError("development must contain baseline and all eight fixed candidates in declaration order")
    baseline_records = stages[0]["records"]
    identities = {}
    for stage, config in zip(stages, models):
        summary = development.summarize_candidate(baseline_records, stage["records"])
        if summary != stage.get("summary"):
            raise ValueError("development summary does not reproduce from its six paired records")
        for row in stage["records"]:
            identity = _verify_run_artifacts(directory, row, config, sources, "development")
            seed = row["data_seed"]
            if seed in identities and identities[seed] != identity:
                raise ValueError("development candidates must use identical evaluation rows, labels and validity")
            identities[seed] = identity
    selected = results.get("selected_development_candidate")
    if selected != development.select_candidate(stages[1:]):
        raise ValueError("recorded development choice differs from the prespecified selection procedure")
    expected_outcome = "development_candidate_selected_final_not_run" if selected else "no_development_candidate_meets_criteria"
    if results.get("outcome") != expected_outcome or results.get("final", {}).get("executed") is not False:
        raise ValueError("development results are incomplete or already contain a final evaluation")
    if [event.get("seed") for event in results.get("generation_events", [])] != list(development.DEV_SEEDS):
        raise ValueError("development generation events differ from the sealed schedule")
    for name, expected in sources.items():
        _check_hash(_artifact(directory / "source_snapshot", name), expected)
    run_evidence_path = directory / "run_evidence.json"
    run_evidence = _read_json(run_evidence_path)
    if (run_evidence.get("protocol_sha256") != protocol_hash or run_evidence.get("checks") != checks
            or run_evidence.get("outcome") != expected_outcome):
        raise ValueError("development completion evidence does not agree with results")
    artifact_hashes = run_evidence.get("artifact_sha256", {})
    required_artifacts = {"results.json", "protocol.json", "protocol.sha256"}
    required_artifacts.update(f"source_snapshot/{name}" for name in sources)
    if not required_artifacts.issubset(artifact_hashes):
        raise ValueError("development completion evidence is missing essential artifact hashes")
    for relative, expected in artifact_hashes.items():
        _check_hash(_artifact(directory, relative), expected)
    return {"path": str(directory), "results_sha256": development.sha256(results_path),
            "protocol_sha256": protocol_hash, "run_evidence_sha256": development.sha256(run_evidence_path),
            "source_snapshot_sha256": dict(sources), "selected_development_candidate": copy.deepcopy(selected),
            "completed_model_count": len(stages), "records_per_model": len(development.DEV_SEEDS) * len(INIT_SEEDS),
            "development_selection_recomputed_matches_recorded": True}


def final_protocol_payload(sources, development_evidence, *, started_at):
    models = _declared_models()
    return {"schema_version": PROTOCOL_SCHEMA, "source_type": "synthetic", "started_at_utc": started_at,
            "source_sha256_before_run": dict(sources), "development": copy.deepcopy(development_evidence),
            "baseline": copy.deepcopy(models[0]), "candidates": copy.deepcopy(list(models[1:])),
            "training_procedure": copy.deepcopy(development.TRAINING_PROCEDURE),
            "development_selection_procedure": copy.deepcopy(development.SELECTION_PROCEDURE),
            "primary_candidate": copy.deepcopy(development_evidence["selected_development_candidate"]),
            "final_data_seeds": list(FINAL_SEEDS), "init_seeds": list(INIT_SEEDS),
            "retired_final_seeds_excluded": list(development.RETIRED_FINAL_SEEDS),
            "final_criteria": copy.deepcopy(FINAL_CRITERIA),
            "evaluation_roles": {"test": "final_normal", "stress": "final_shift"},
            "all_nine_models_run_when_primary_is_none": True,
            "candidate_selection_from_final_scores": False,
            "additional_tuning_after_final": False,
            "primary_scope": "only_the_development_selected_candidate_versus_baseline_or_none",
            "other_comparisons": "auxiliary_exploratory_unadjusted_for_multiple_comparisons",
            "intervals": {"method": "generator_seed_paired_percentile_bootstrap",
                          "initializations_averaged_before_resampling": True,
                          "resampled_seed_count": len(FINAL_SEEDS), "repetitions": BOOTSTRAP_REPETITIONS,
                          "seed": BOOTSTRAP_SEED, "level": .95, "metrics": list(METRICS),
                          "roles": ["normal", "shift"], "multiplicity_adjustment": "none"},
            "artifacts": ["source_snapshot", "datasets", "models", "predictions", "per_run_events", "results"],
            "failure_policy": "preserve_artifacts_stop_on_error_no_resume_no_replacement_seeds_no_reselection",
            "scope": "S0_synthetic_only_no_real_data_no_external_collection_no_hardware_simulated_timing_only"}


def freeze_payload(protocol, protocol_sha256, *, frozen_at):
    return {"schema_version": FREEZE_SCHEMA, "frozen_at_utc": frozen_at,
            "protocol_sha256": protocol_sha256,
            "source_sha256": copy.deepcopy(protocol["source_sha256_before_run"]),
            "development": copy.deepcopy(protocol["development"]),
            "baseline": copy.deepcopy(protocol["baseline"]), "candidates": copy.deepcopy(protocol["candidates"]),
            "primary_candidate": copy.deepcopy(protocol["primary_candidate"]),
            "training_procedure": copy.deepcopy(protocol["training_procedure"]),
            "development_selection_procedure": copy.deepcopy(protocol["development_selection_procedure"]),
            "final_data_seeds": list(FINAL_SEEDS), "init_seeds": list(INIT_SEEDS),
            "final_criteria": copy.deepcopy(FINAL_CRITERIA), "intervals": copy.deepcopy(protocol["intervals"]),
            "other_comparisons": protocol["other_comparisons"],
            "candidate_selection_from_final_scores": False,
            "no_final_data_generated_before_freeze": True}


class FinalSeedGate:
    """Fail closed before a verified protocol, freeze and unchanged development."""

    def __init__(self, expected_sources, development_evidence, protocol_path):
        self.expected_sources = dict(expected_sources)
        self.development_evidence = copy.deepcopy(development_evidence)
        self.protocol_path = Path(protocol_path)
        self.protocol_sha256 = None
        self.freeze_path = None
        self.freeze_sha256 = None
        self.cache, self.calls = {}, []

    def unlock_final(self, freeze_path):
        self.protocol_sha256 = development.sha256(self.protocol_path)
        self.freeze_path = Path(freeze_path)
        self.freeze_sha256 = development.sha256(self.freeze_path)
        try:
            self.verify()
        except Exception:
            self.freeze_path, self.freeze_sha256, self.protocol_sha256 = None, None, None
            raise

    def verify(self):
        if self.freeze_path is None:
            raise ValueError("final generation/fitting is forbidden before a verified freeze")
        _check_hash(self.protocol_path, self.protocol_sha256)
        _sidecar_matches(self.protocol_path.with_suffix(".sha256"), self.protocol_sha256)
        _check_hash(self.freeze_path, self.freeze_sha256)
        _sidecar_matches(self.freeze_path.with_suffix(".sha256"), self.freeze_sha256)
        if development.source_hashes() != self.expected_sources:
            raise ValueError("source changed after development or final freeze")
        protocol, frozen = _read_json(self.protocol_path), _read_json(self.freeze_path)
        expected = final_protocol_payload(self.expected_sources, self.development_evidence,
                                          started_at=protocol.get("started_at_utc"))
        if protocol != expected or frozen != freeze_payload(expected, self.protocol_sha256, frozen_at=frozen.get("frozen_at_utc")):
            raise ValueError("final protocol/freeze differs from its prespecified comparison")
        directory = Path(self.development_evidence["path"])
        for name, key in (("results.json", "results_sha256"), ("protocol.json", "protocol_sha256"),
                          ("run_evidence.json", "run_evidence_sha256")):
            _check_hash(directory / name, self.development_evidence[key])
        for name, expected_hash in self.expected_sources.items():
            _check_hash(_artifact(directory / "source_snapshot", name), expected_hash)
            _check_hash(_artifact(self.protocol_path.parent / "source_snapshot", name), expected_hash)

    def get(self, seed):
        if type(seed) is not int or seed not in FINAL_SEEDS:
            raise ValueError("only the ten fixed fresh final generator seeds are allowed")
        self.verify()
        if seed not in self.cache:
            before = development.utc_now()
            # The only final generator call in this module is below this gate.
            dataset = generate_dataset(seed=seed)
            prepared = development.prepare_dataset(dataset, seed)
            self.verify()
            target = self.protocol_path.parent / "datasets" / f"seed_{seed}.json"
            if target.exists():
                raise ValueError("refusing to replace an existing generated dataset")
            save_json(target, dataset)
            prepared["metadata"].update(dataset_path=target.relative_to(self.protocol_path.parent).as_posix(),
                                         dataset_file_sha256=development.sha256(target))
            self.cache[seed] = prepared
            self.calls.append({"seed": seed, "phase": "final", "verified_before_generation_at_utc": before,
                               "generated_at_utc": development.utc_now(), "freeze_sha256": self.freeze_sha256,
                               "protocol_sha256": self.protocol_sha256, "source_sha256": self.expected_sources,
                               "dataset_sha256": prepared["metadata"]["dataset_sha256"],
                               "dataset_file_sha256": prepared["metadata"]["dataset_file_sha256"]})
            save_json(self.protocol_path.parent / "generation_events.json", self.calls)
        return self.cache[seed]


def paired_bootstrap(values):
    """Percentile CI over the ten paired seed means, never over twenty fits."""
    values = np.asarray(values, dtype=float)
    if values.shape != (len(FINAL_SEEDS),) or not np.isfinite(values).all():
        raise ValueError("paired bootstrap requires exactly ten finite generator-seed differences")
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    means = values[rng.integers(0, len(values), size=(BOOTSTRAP_REPETITIONS, len(values)))].mean(axis=1)
    low, high = np.quantile(means, [.025, .975])
    return {"low": float(low), "high": float(high), "method": "generator_seed_paired_percentile_bootstrap",
            "repetitions": BOOTSTRAP_REPETITIONS, "seed": BOOTSTRAP_SEED, "seed_count": len(values),
            "confidence_level": .95, "multiplicity_adjustment": "none"}


def final_summary(baseline_records, candidate_records, *, is_primary=False):
    summary = development.summarize_candidate(baseline_records, candidate_records, seeds=FINAL_SEEDS,
                                              init_seeds=INIT_SEEDS, positive_seed_min=8)
    baseline = {(row["data_seed"], row["init_seed"]): row for row in baseline_records}
    candidate = {(row["data_seed"], row["init_seed"]): row for row in candidate_records}
    differences, intervals = [], {role: {} for role in ("normal", "shift")}
    for seed in FINAL_SEEDS:
        row = {"data_seed": seed}
        for role in ("normal", "shift"):
            row[role] = {}
            for metric in METRICS:
                before = float(np.mean([baseline[(seed, init)]["metrics"][role][metric] for init in INIT_SEEDS]))
                after = float(np.mean([candidate[(seed, init)]["metrics"][role][metric] for init in INIT_SEEDS]))
                row[role][metric] = {"baseline": before, "candidate": after, "delta": after - before}
        differences.append(row)
    for role in intervals:
        for metric in METRICS:
            intervals[role][metric] = paired_bootstrap([row[role][metric]["delta"] for row in differences])
    conditions = copy.deepcopy(summary["conditions"])
    conditions["shift_bootstrap_lower_above_zero"] = intervals["shift"]["macro_f1"]["low"] > 0
    summary.pop("eligible")
    summary.update(aggregation_unit=FINAL_CRITERIA["aggregation_unit"], per_seed_metric_differences=differences,
                   paired_bootstrap95=intervals, shift_paired_bootstrap95=intervals["shift"]["macro_f1"],
                   conditions=conditions, role="primary" if is_primary else "auxiliary_exploratory",
                   multiplicity_adjustment="none", primary_success=bool(all(conditions.values())) if is_primary else None)
    return summary


def primary_result(stages, selected):
    if selected is None:
        return {"candidate": None, "success": None, "reason": "개발 기준을 통과한 후보가 없어 주 비교가 없습니다."}
    matches = [stage for stage in stages if stage["candidate"] == selected]
    if len(matches) != 1 or matches[0]["summary"]["role"] != "primary":
        raise ValueError("the unchanged development choice must be the sole final primary")
    return {"candidate": copy.deepcopy(selected), "success": matches[0]["summary"]["primary_success"],
            "summary": copy.deepcopy(matches[0]["summary"])}


def _prepare_output(output_dir, development_dir):
    out, allowed = Path(output_dir).resolve(), (ROOT / "outputs").resolve()
    if allowed not in out.parents or out == development_dir or out in development_dir.parents:
        raise ValueError("final output must be a new child directory under project outputs, separate from development")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("final output must be empty; existing evidence cannot be overwritten")
    out.mkdir(parents=True, exist_ok=True)
    return out


def run(development_dir, output_dir):
    started = time.perf_counter()
    development_dir = Path(development_dir).resolve()
    sources = development.source_hashes()
    dev_evidence = validate_development(development_dir, expected_sources=sources)
    out = _prepare_output(output_dir, development_dir)
    protocol = final_protocol_payload(sources, dev_evidence, started_at=development.utc_now())
    protocol_path = out / "protocol.json"
    save_json(protocol_path, protocol)
    protocol_hash = development.sha256(protocol_path)
    protocol_path.with_suffix(".sha256").write_text(protocol_hash + "\n", encoding="ascii")
    for name in development.SOURCE_FILES:
        target = out / "source_snapshot" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    frozen = freeze_payload(protocol, protocol_hash, frozen_at=development.utc_now())
    freeze_path = out / "freeze.json"
    save_json(freeze_path, frozen)
    freeze_hash = development.sha256(freeze_path)
    freeze_path.with_suffix(".sha256").write_text(freeze_hash + "\n", encoding="ascii")
    gate = FinalSeedGate(sources, dev_evidence, protocol_path)
    gate.unlock_final(freeze_path)
    selected = dev_evidence["selected_development_candidate"]
    primary_name = selected["name"] if selected else "없음"
    print(f"최종 비교 동결 완료: 모델 9개, 생성 seed 10개, seed당 초기화 2개. 주 비교: {primary_name}", flush=True)
    result = {"schema_version": RESULT_SCHEMA, "source_type": "synthetic", "status": "running",
              "protocol": protocol, "protocol_sha256": protocol_hash,
              "freeze": {"path": "freeze.json", "sha256": freeze_hash, **frozen},
              "selected_development_candidate": copy.deepcopy(selected), "stage_results": [],
              "primary": {"candidate": copy.deepcopy(selected), "success": None},
              "final_scores_used_for_selection": False,
              "limitations": ["S0 합성 경로 유형 비교이며 실제 조업·사고·장치 검증이 아닙니다.",
                  "독립 통계 단위는 생성 seed 10개이며 초기화 20회를 독립 자료로 세지 않습니다.",
                  "주 비교 외 결과와 신뢰구간은 다중비교 보정 없는 보조·탐색 결과입니다.",
                  "최종 점수의 최고 모델로 다시 선택하거나 설정을 조정하지 않습니다.",
                  "가상 시간의 속력은 실제 속력이나 시간의 독립적인 도메인 효용을 입증하지 않습니다."]}
    events, identity_by_seed, baseline_records = [], {}, None
    save_json(out / "results.json", result)
    try:
        for config, display_name in zip(_declared_models(), DISPLAY_NAMES):
            rows = []
            stage = {"candidate": copy.deepcopy(config), "display_name": display_name,
                     "records": rows, "summary": None, "status": "running"}
            result["stage_results"].append(stage)
            save_json(out / "results.json", result)
            for data_seed in FINAL_SEEDS:
                prepared = gate.get(data_seed)
                for init_seed in INIT_SEEDS:
                    gate.verify()
                    prefix = f"{config['name']}_d{data_seed}_i{init_seed}"
                    for relative in (f"models/{prefix}.json", f"models/{prefix}.pkl", f"predictions/{prefix}.json"):
                        if (out / relative).exists():
                            raise ValueError("refusing to replace existing model/prediction evidence")
                    event = {"candidate": config["name"], "data_seed": data_seed, "init_seed": init_seed,
                             "phase": "final", "started_at_utc": development.utc_now(), "freeze_sha256": freeze_hash,
                             "protocol_sha256": protocol_hash, "source_sha256": sources}
                    events.append(event)
                    save_json(out / "per_run_events.json", events)
                    row = development._fit_one(prepared, config, data_seed, init_seed, out, sources, phase="final")
                    gate.verify()
                    identity = _verify_run_artifacts(out, row, config, sources, "final")
                    if data_seed in identity_by_seed and identity_by_seed[data_seed] != identity:
                        raise ValueError("all final models must share evaluation IDs, labels and validity")
                    identity_by_seed[data_seed] = identity
                    row["evaluation_identity_sha256"] = identity
                    record_path = out / "run_records" / f"{prefix}.json"
                    if record_path.exists():
                        raise ValueError("refusing to replace existing per-run metrics evidence")
                    save_json(record_path, row)
                    event.update(finished_at_utc=development.utc_now(), model_sha256=row["model_sha256"],
                                 predictions_sha256=row["predictions_sha256"], dataset_sha256=row["dataset_sha256"],
                                 evaluation_identity_sha256=identity, status="complete",
                                 record_path=record_path.relative_to(out).as_posix(),
                                 record_sha256=development.sha256(record_path))
                    rows.append(row)
                    save_json(out / "per_run_events.json", events)
            if baseline_records is None:
                baseline_records = rows
            stage.update(summary=final_summary(baseline_records, rows, is_primary=config == selected), status="complete")
            print(f"{display_name}: 보통 F1={stage['summary']['mean_metrics']['normal']['macro_f1']:.4f}, "
                  f"조건 변화 F1={stage['summary']['mean_metrics']['shift']['macro_f1']:.4f}, "
                  f"기준 대비 변화={stage['summary']['shift_mean_delta']:+.4f}", flush=True)
            save_json(out / "results.json", result)
        gate.verify()
        result["primary"] = primary_result(result["stage_results"], selected)
        all_rows = [row for stage in result["stage_results"] for row in stage["records"]]
        result["dataset_manifest"] = {str(seed): item["metadata"] for seed, item in gate.cache.items()}
        result["generation_events"] = gate.calls
        result["checks"] = {
            "sealed_protocol_and_freeze_unchanged": True, "development_evidence_unchanged": True,
            "sources_and_source_snapshots_unchanged": True,
            "exactly_ten_final_datasets_generated_after_freeze": [event["seed"] for event in gate.calls] == list(FINAL_SEEDS)
                and all(event["freeze_sha256"] == freeze_hash for event in gate.calls),
            "all_nine_fixed_models_completed": len(result["stage_results"]) == 9 and len(all_rows) == 180,
            "twenty_records_per_model": all(len(stage["records"]) == 20 for stage in result["stage_results"]),
            "same_evaluation_rows_labels_validity_and_denominators": len(identity_by_seed) == 10 and all(
                stage["summary"]["conditions"]["same_denominators"] for stage in result["stage_results"]),
            "same_train_only_preprocessor_per_feature_family": all(len({row["preprocessor_sha256"]
                for stage in result["stage_results"] if stage["candidate"]["family"] == family
                for row in stage["records"] if row["data_seed"] == seed}) == 1
                for family in development.TRAINING_PROCEDURE["feature_families"] for seed in FINAL_SEEDS),
            "all_raw_and_calibrated_reload_probabilities_identical": all(
                row["reload_raw_and_calibrated_probabilities_identical"] for row in all_rows),
            "development_primary_unchanged": result["primary"]["candidate"] == selected,
            "no_selection_from_final_scores": result["final_scores_used_for_selection"] is False,
        }
        if not all(result["checks"].values()):
            raise RuntimeError("final comparison audit failed")
        result["status"] = "complete"
        result["outcome"] = ("주 비교 없음·고정 비교 완료" if selected is None else
                               "주 비교 개선 기준 충족" if result["primary"]["success"] else "주 비교 개선 기준 미충족")
        result["runtime"] = {"seconds": time.perf_counter() - started, "python": platform.python_version(),
                             "python_executable": sys.executable, "numpy": np.__version__,
                             "sklearn": __import__("sklearn").__version__, "finished_at_utc": development.utc_now()}
        save_json(out / "results.json", result)
        save_json(out / "run_evidence.json", {"command":
            f'python tools/critique_final_comparison_20261027.py --development "{development_dir}" --out "{out}"',
            "protocol_sha256": protocol_hash, "freeze_sha256": freeze_hash, "development": dev_evidence,
            "checks": result["checks"], "runtime": result["runtime"], "outcome": result["outcome"],
            "artifact_sha256": {path.relative_to(out).as_posix(): development.sha256(path)
                                for path in sorted(out.rglob("*")) if path.is_file()}})
        print(f"{result['outcome']}; 저장 위치: {out}", flush=True)
        return result
    except Exception as exc:
        result.update(status="failed", generation_events=gate.calls,
                      error={"type": type(exc).__name__, "message": str(exc), "at_utc": development.utc_now(),
                             "artifacts_preserved": True, "automatic_retry_or_reselection": False})
        save_json(out / "results.json", result)
        save_json(out / "failure.json", result["error"])
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--development", type=Path, default=ROOT / "outputs/critique_comparison_20261027")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs/critique_comparison_20261027/final")
    args = parser.parse_args()
    try:
        run(args.development, args.out)
    except (ValueError, RuntimeError, OSError, ImportError, KeyError, TypeError) as exc:
        parser.exit(2, f"최종 비교 실패: {exc}\n")


if __name__ == "__main__":
    main()
