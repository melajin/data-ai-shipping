#!/usr/bin/env python3
"""Check an explicit synthetic geometry contract using Python's standard library.

This is an educational fixed-contract example, never real competition data or a
feature pipeline. Only planar XY coordinates in metres, confirmed point order
within each part, preserved part boundaries, and absent measured timestamps and
labels are accepted. A claimed source type cannot prove a file's provenance.

Usage: python tools/check_synthetic_contract.py examples/fishing_contract_synthetic.json
       python tools/check_synthetic_contract.py INPUT --output REPORT.json
Exit codes: 0 = checks pass, 1 = hand-calculation mismatch, 2 = invalid contract/I/O.
The input is read without modification. No speed or accident score is computed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any


SCHEMA_VERSION = "synthetic_geometry_contract_v1"
COORDINATE_CONTRACT = {
    "system": "planar_xy",
    "axis_order": ["x", "y"],
    "unit": "m",
    "basis": "educational_assumption",
}
OBSERVATION_CONTRACT = {
    "point_order": "confirmed_within_each_part",
    "part_boundaries": "preserved_do_not_connect",
    "measured_timestamps": "absent",
    "fishing_labels": "absent",
    "anomaly_labels": "absent",
}


class ContractError(ValueError):
    """The input does not satisfy the synthetic-only educational contract."""


def _object(value: Any, keys: set[str], location: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ContractError(f"{location}: required keys are {', '.join(sorted(keys))}")
    return value


def _number(value: Any, location: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{location}: a finite number is required")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ContractError(f"{location}: a finite number is required") from exc
    if not math.isfinite(result) or (nonnegative and result < 0):
        raise ContractError(f"{location}: a finite{' nonnegative' if nonnegative else ''} number is required")
    return result


def _expected(value: Any, location: str, *, nullable: bool = False) -> None:
    record = _object(value, {"value", "hand_calculation"}, location)
    if not (nullable and record["value"] is None):
        _number(record["value"], f"{location}.value", nonnegative=True)
    if not isinstance(record["hand_calculation"], str) or not record["hand_calculation"].strip():
        raise ContractError(f"{location}.hand_calculation: an independent hand calculation is required")


def validate_contract(data: Any) -> None:
    """Reject unknown units, point order, real samples, and undeclared extra data."""
    _object(data, {
        "schema_version", "source_type", "metadata", "coordinate_contract",
        "observation_contract", "parts", "tolerance", "expected",
    }, "contract")
    if data["source_type"] != "synthetic_example":
        raise ContractError("source_type: only synthetic_example is accepted; real or unknown data is rejected")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ContractError(f"schema_version: must be {SCHEMA_VERSION}")
    if data["coordinate_contract"] != COORDINATE_CONTRACT:
        raise ContractError("coordinate_contract: requires planar_xy, axis order [x, y], metres (m), educational_assumption")
    if data["observation_contract"] != OBSERVATION_CONTRACT:
        raise ContractError("observation_contract: confirm order within each part, preserve boundaries, and declare timestamps and labels absent")
    meta = _object(data["metadata"], {"title", "statement", "not_real_competition_data"}, "metadata")
    if meta["not_real_competition_data"] is not True:
        raise ContractError("metadata.not_real_competition_data: must be true")
    for field in ("title", "statement"):
        if not isinstance(meta[field], str) or not meta[field].strip():
            raise ContractError(f"metadata.{field}: nonempty text is required")
    tolerance = _object(data["tolerance"], {"distance_absolute_m", "ratio_absolute"}, "tolerance")
    for key, value in tolerance.items():
        _number(value, f"tolerance.{key}", nonnegative=True)
    parts = data["parts"]
    if not isinstance(parts, list) or not parts:
        raise ContractError("parts: at least one explicitly separated part is required")
    ids: set[str] = set()
    for index, part in enumerate(parts):
        where = f"parts[{index}]"
        _object(part, {"id", "points"}, where)
        if not isinstance(part["id"], str) or not part["id"].strip() or part["id"] in ids:
            raise ContractError(f"{where}.id: a unique nonempty identifier is required")
        ids.add(part["id"])
        if not isinstance(part["points"], list) or len(part["points"]) < 2:
            raise ContractError(f"{where}.points: at least two ordered XY points are required")
        for point_index, point in enumerate(part["points"]):
            if not isinstance(point, list) or len(point) != 2:
                raise ContractError(f"{where}.points[{point_index}]: exactly two coordinates [x, y] are required")
            for axis, coordinate in zip(("x", "y"), point):
                _number(coordinate, f"{where}.points[{point_index}].{axis}")
    expected = _object(data["expected"], {
        "parts", "total_length_m", "forbidden_connection",
    }, "expected")
    if not isinstance(expected["parts"], list) or len(expected["parts"]) != len(parts):
        raise ContractError("expected.parts: one hand-calculation record per part is required")
    for index, (part, reference) in enumerate(zip(parts, expected["parts"])):
        where = f"expected.parts[{index}]"
        _object(reference, {"id", "segment_lengths_m", "length_m", "displacement_m", "straightness"}, where)
        if reference["id"] != part["id"]:
            raise ContractError(f"{where}.id: must match the corresponding part identifier")
        segments = reference["segment_lengths_m"]
        if not isinstance(segments, list) or len(segments) != len(part["points"]) - 1:
            raise ContractError(f"{where}.segment_lengths_m: one expectation per observed segment is required")
        for segment_index, segment in enumerate(segments):
            _expected(segment, f"{where}.segment_lengths_m[{segment_index}]")
        for key in ("length_m", "displacement_m", "straightness"):
            _expected(reference[key], f"{where}.{key}", nullable=key == "straightness")
    _expected(expected["total_length_m"], "expected.total_length_m")
    forbidden = _object(expected["forbidden_connection"], {"bridge_lengths_m", "wrong_connected_length_m"}, "expected.forbidden_connection")
    bridges = forbidden["bridge_lengths_m"]
    if not isinstance(bridges, list) or len(bridges) != len(parts) - 1:
        raise ContractError("expected.forbidden_connection.bridge_lengths_m: one expectation per artificial connection is required")
    for index, bridge in enumerate(bridges):
        _expected(bridge, f"expected.forbidden_connection.bridge_lengths_m[{index}]")
    _expected(forbidden["wrong_connected_length_m"], "expected.forbidden_connection.wrong_connected_length_m")


def _distance(first: list[float], second: list[float]) -> float:
    result = math.hypot(float(second[0]) - float(first[0]), float(second[1]) - float(first[1]))
    if not math.isfinite(result):
        raise ContractError("coordinate differences exceed the supported finite numeric range")
    return result


def _sum(values: list[float]) -> float:
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ContractError("length sum exceeds the supported finite numeric range") from exc
    if not math.isfinite(result):
        raise ContractError("length sum exceeds the supported finite numeric range")
    return result


def check_contract(data: Any) -> dict[str, Any]:
    """Compute within-part geometry; compare with separately supplied expectations."""
    validate_contract(data)
    checks: list[dict[str, Any]] = []
    counterexample_checks: list[dict[str, Any]] = []

    def compare(name: str, actual: float | None, reference: dict[str, Any], *, ratio: bool = False,
                destination: list[dict[str, Any]] = checks) -> None:
        expected = reference["value"]
        tolerance = data["tolerance"]["ratio_absolute" if ratio else "distance_absolute_m"]
        difference = None if actual is None or expected is None else actual - float(expected)
        passed = (actual is None and expected is None) if difference is None else abs(difference) <= tolerance
        destination.append({
            "quantity": name, "unit": "dimensionless" if ratio else "m",
            "expected": expected, "actual": actual, "signed_difference": difference,
            "absolute_difference": None if difference is None else abs(difference),
            "tolerance": tolerance, "passed": passed,
            "undefined_reason": "zero_observed_length" if actual is None else None,
            "hand_calculation": reference["hand_calculation"],
            "condition": "D/L is undefined when L=0" if ratio else "planar XY Euclidean distance in metres",
        })

    computed_parts = []
    for part, reference in zip(data["parts"], data["expected"]["parts"]):
        points = part["points"]
        segments = [_distance(first, second) for first, second in zip(points, points[1:])]
        length = _sum(segments)
        displacement = _distance(points[0], points[-1])
        straightness = displacement / length if length > 0 else None
        computed_parts.append({
            "id": part["id"], "segment_lengths_m": segments, "length_m": length,
            "displacement_m": displacement, "straightness": straightness,
        })
        for index, (actual, expected) in enumerate(zip(segments, reference["segment_lengths_m"])):
            compare(f"{part['id']}.segment_lengths_m[{index}]", actual, expected)
        compare(f"{part['id']}.length_m", length, reference["length_m"])
        compare(f"{part['id']}.displacement_m", displacement, reference["displacement_m"])
        compare(f"{part['id']}.straightness", straightness, reference["straightness"], ratio=True)
    total_length = _sum([part["length_m"] for part in computed_parts])
    compare("total_length_m", total_length, data["expected"]["total_length_m"])

    # This deliberately wrong operation is isolated from all observed quantities.
    artificial_bridges = [_distance(first["points"][-1], second["points"][0])
                          for first, second in zip(data["parts"], data["parts"][1:])]
    wrong_length = _sum([total_length, *artificial_bridges])
    forbidden_reference = data["expected"]["forbidden_connection"]
    for index, (actual, expected) in enumerate(zip(artificial_bridges, forbidden_reference["bridge_lengths_m"])):
        compare(f"artificial_bridge_lengths_m[{index}]", actual, expected, destination=counterexample_checks)
    compare("wrong_connected_length_m", wrong_length, forbidden_reference["wrong_connected_length_m"], destination=counterexample_checks)
    passed = all(check["passed"] for check in [*checks, *counterexample_checks])
    return {
        "report_type": "synthetic_geometry_independent_check",
        "source_type": "synthetic_example",
        "not_real_competition_data": True,
        "conditions": {"coordinate_contract": data["coordinate_contract"], "observation_contract": data["observation_contract"]},
        "assumptions": [
            "좌표는 교육용으로 가정한 평면 XY이며 단위는 미터다.",
            "각 부분선 안의 점 순서는 확인된 예제 순서이며 부분선 경계는 보존한다.",
            "실측 시각·조업 라벨·이상 라벨은 없다.",
        ],
        "limitations": [
            "실제 대회자료가 아니며 실제 좌표계·측정 오차·조업 성능을 검증하지 않는다.",
            "길이는 주어진 점을 이은 관측 꺾은선의 길이이며 연속 운동 전체 길이를 보장하지 않는다.",
            "허용오차는 손계산 기대값과 코드 계산값의 수치 비교 조건이며 실측 정확도가 아니다.",
            "source_type 표시는 계약상 선언이다. 이 검사기는 외부 자료의 실제 출처를 입증하지 않는다.",
        ],
        "reproducibility": {"randomness": "none_fixed_coordinates", "numeric_method": "stdlib math.hypot and math.fsum; absolute tolerances"},
        "technical_status": {"contract_validation": "passed", "calculation_check": "passed" if passed else "failed", "verification_kind": "code_calculation_only", "real_observation_validation": "not_performed"},
        "learning_status": {"achievement": "unverified", "questions": [
            "부분선 사이 거리를 더하면 왜 관측 길이가 아닌가?",
            "부분선 하나를 평행이동하면 길이 합계와 금지연결 반례 값은 각각 어떻게 달라지는가?",
            "실측 시각이 없을 때 길이만으로 무엇을 설명할 수 없는가?",
        ]},
        "observed_geometry": {"parts": computed_parts, "total_length_m": total_length},
        "checks": checks,
        "forbidden_connection_educational_counterexample": {
            "is_observed_feature": False,
            "explanation": "금지연결 교육반례: 표시된 부분선 목록 순서로 끝점과 다음 시작점을 임의 연결하면 관측되지 않은 이동을 더한다. 이 순서는 실제 부분선 간 시간 순서나 연결의 증거가 아니다.",
            "artificial_bridge_lengths_m": artificial_bridges,
            "wrong_connected_length_m": wrong_length,
            "checks": counterexample_checks,
        },
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"JSON: duplicate key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ContractError(f"JSON: nonfinite numeric constant {value} is not allowed")


def _check_output_path(source: Path, output: Path) -> None:
    if source.resolve() == output.resolve() or (output.exists() and os.path.samefile(source, output)):
        raise ContractError("output: must differ from the input source; source overwrite is forbidden")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="explicit synthetic educational contract JSON")
    parser.add_argument("--output", type=Path, help="write JSON report to a separate file (default: stdout)")
    args = parser.parse_args(argv)
    try:
        if args.output:
            _check_output_path(args.input, args.output)
        source_bytes = args.input.read_bytes()
        data = json.loads(source_bytes.decode("utf-8-sig"), object_pairs_hook=_unique_object, parse_constant=_reject_constant)
        report = check_contract(data)
        report["reproducibility"]["input_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        encoded = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        if args.output:
            # Recheck aliases before opening; no input-writing operation exists.
            _check_output_path(args.input, args.output)
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
        return 0 if report["technical_status"]["calculation_check"] == "passed" else 1
    except (ContractError, OSError, UnicodeError, json.JSONDecodeError) as exc:
        sys.stderr.write(f"synthetic_contract_error: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
