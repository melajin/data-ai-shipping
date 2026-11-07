"""Bounded availability-contract replay; this module never scores or emits alerts.

Only the last accepted observation per vessel is retained. An exact retry of that
observation is idempotent, even after another vessel advanced the decision clock.
Older retries are quarantined, not deduplicated across an unbounded history.
Geometry is checked as supplied; no paths, GPS samples, speeds or labels are made.
"""

from __future__ import annotations

import argparse
from collections import Counter
import ctypes
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
from typing import BinaryIO, Iterator


DISABLED_OPERATIONS = (
    "fleet_filter", "offhours_weight", "global_argmax", "accident_prediction",
    "external_delivery",
)
TIME_FIELDS = ("interval_start", "interval_end", "available_at", "decision_at")
SOURCE_TYPES = ("synthetic", "archive", "live")
STATUSES = ("observed_unscored", "abstained", "quarantined", "duplicate")
CONFIG_MAX_BYTES = 65536
IDENTIFIER_MAX_CHARS = 128
_TIMESTAMP = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


class ConfigError(ValueError):
    """The configuration cannot enable this bounded replay."""


class MemoryPreflightError(RuntimeError):
    """Fresh available RAM cannot satisfy the configured budget and reserve."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite_json_number")


def _parse_json(raw: bytes) -> object:
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def _keys(value: object, required: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != required:
        raise ConfigError(f"{name}: exact keys required: {', '.join(sorted(required))}")
    return value


def _exact(value: object, expected: object, name: str) -> None:
    # bool is an int subclass: equality alone would accept 0 for False.
    if type(value) is not type(expected) or value != expected:
        raise ConfigError(f"{name}: must be {expected!r}")


def validate_config(config: object) -> dict:
    """Validate and return a detached config; safety fields cannot be enabled."""
    cfg = _keys(config, {"schema_version", "mode", "scoring", "disabled_operations",
                         "input", "memory", "evaluation"}, "config")
    _exact(cfg["schema_version"], "testb_realtime_config_v1", "schema_version")
    _exact(cfg["mode"], "contract_replay", "mode")
    scoring = _keys(cfg["scoring"],
                    {"enabled", "adapter", "threshold", "calibration_status"}, "scoring")
    for key, expected in {"enabled": False, "adapter": None, "threshold": None,
                          "calibration_status": "unvalidated"}.items():
        _exact(scoring[key], expected, f"scoring.{key}")
    operations = cfg["disabled_operations"]
    if (not isinstance(operations, list)
            or any(type(item) is not str for item in operations)
            or len(operations) != len(DISABLED_OPERATIONS)
            or set(operations) != set(DISABLED_OPERATIONS)):
        raise ConfigError("disabled_operations: every approved operation must remain disabled")
    inputs = _keys(cfg["input"], {
        "timestamp_format", "real_time_basis_required", "real_availability_required",
        "unknown_availability_policy", "late_event_policy", "duplicate_policy",
    }, "input")
    for key, expected in {
        "timestamp_format": "iso8601_with_offset", "real_time_basis_required": "confirmed",
        "real_availability_required": "confirmed", "unknown_availability_policy": "abstain",
        "late_event_policy": "quarantine", "duplicate_policy": "idempotent_conflict_quarantine",
    }.items():
        _exact(inputs[key], expected, f"input.{key}")
    memory = _keys(cfg["memory"], {"max_vessels", "max_line_bytes", "estimated_peak_mib",
                                   "reserve_mib"}, "memory")
    bounds = {"max_vessels": (1, 10000), "max_line_bytes": (256, 65536),
              "estimated_peak_mib": (128, 1048576), "reserve_mib": (640, 1048576)}
    for key, (low, high) in bounds.items():
        if type(memory[key]) is not int or not low <= memory[key] <= high:
            raise ConfigError(f"memory.{key}: integer between {low} and {high} required")
    evaluation = _keys(cfg["evaluation"], {"label_status", "official_f1_enabled"}, "evaluation")
    _exact(evaluation["label_status"], "provisional", "evaluation.label_status")
    _exact(evaluation["official_f1_enabled"], False, "evaluation.official_f1_enabled")
    return json.loads(_canonical(cfg))


def load_config(path: str | Path) -> dict:
    """Read a small UTF-8 JSON config without an unbounded file read."""
    with Path(path).open("rb") as handle:
        raw = handle.read(CONFIG_MAX_BYTES + 1)
    if len(raw) > CONFIG_MAX_BYTES:
        raise ConfigError("config_file_too_large")
    try:
        return validate_config(_parse_json(raw))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ConfigError(str(exc)) from exc


def available_memory_bytes() -> int:
    """Read available physical RAM once; no polling or process intervention."""
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong),
                        ("total_physical", ctypes.c_ulonglong),
                        ("available_physical", ctypes.c_ulonglong),
                        ("total_pagefile", ctypes.c_ulonglong),
                        ("available_pagefile", ctypes.c_ulonglong),
                        ("total_virtual", ctypes.c_ulonglong),
                        ("available_virtual", ctypes.c_ulonglong),
                        ("available_extended", ctypes.c_ulonglong)]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise MemoryPreflightError("available_ram_unknown")
        return int(status.available_physical)
    try:
        with Path("/proc/meminfo").open("r", encoding="ascii") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError) as exc:
        raise MemoryPreflightError("available_ram_unknown") from exc
    raise MemoryPreflightError("available_ram_unknown")


def memory_preflight(config: dict) -> dict:
    """Fresh RAM gate. The 128 MiB minimum includes interpreter and bounded state."""
    memory = config["memory"]
    available = available_memory_bytes()
    expected = memory["estimated_peak_mib"] * 1024 ** 2
    reserve = memory["reserve_mib"] * 1024 ** 2
    evidence = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "available_bytes": available, "estimated_peak_bytes": expected,
        "reserve_bytes": reserve, "required_bytes": expected + reserve,
        "estimate_basis": "stdlib streaming; one <=64KiB row; <=10000 compact vessel states",
        "other_processes": "included in fresh OS available physical RAM; no processes terminated",
        "passed": available >= expected + reserve,
    }
    if not evidence["passed"]:
        raise MemoryPreflightError("insufficient_available_ram: " + json.dumps(evidence))
    return evidence


@dataclass(frozen=True, slots=True)
class _Accepted:
    event_id: str
    payload_digest: bytes
    interval_end: datetime


def _identifier(value: object) -> str | None:
    if (isinstance(value, str) and 0 < len(value) <= IDENTIFIER_MAX_CHARS
            and value.strip() and all(ord(char) >= 32 for char in value)):
        return value
    return None


def _timestamp(value: object, field: str) -> tuple[datetime | None, str | None, str | None]:
    if value is None or value == "" or value == "unknown":
        return None, "abstained", f"missing_{field}"
    if not isinstance(value, str) or len(value) > 64:
        return None, "quarantined", f"invalid_{field}"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None, "quarantined", f"invalid_{field}"
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, "abstained", f"timezone_unknown_{field}"
    if not _TIMESTAMP.fullmatch(value):
        return None, "quarantined", f"invalid_{field}"
    try:
        return parsed.astimezone(timezone.utc), None, None
    except (OverflowError, ValueError):
        return None, "quarantined", f"invalid_{field}"


def _geometry_reason(value: object) -> str | None:
    if not isinstance(value, dict):
        return "invalid_geometry"
    allowed = {"centroid_lon", "centroid_lat", "len_m", "bbox_m"}
    if set(value) - allowed:
        return "unsupported_geometry_field"
    for key, number in value.items():
        if type(number) not in (int, float):
            return f"invalid_geometry_{key}"
        try:
            finite = math.isfinite(number)
        except OverflowError:
            finite = False
        if not finite:
            return f"nonfinite_geometry_{key}"
        if key == "centroid_lon" and not -180 <= number <= 180:
            return "out_of_range_centroid_lon"
        if key == "centroid_lat" and not -90 <= number <= 90:
            return "out_of_range_centroid_lat"
        if key in ("len_m", "bbox_m") and number < 0:
            return f"negative_geometry_{key}"
    return None


class CausalReplay:
    """Pure bounded state machine; valid means observed, never normal or safe."""

    def __init__(self, config: dict):
        self.config = validate_config(config)
        self.config_digest = hashlib.sha256(_canonical(self.config)).hexdigest()
        self._vessels: dict[str, _Accepted] = {}
        self._decision_at: datetime | None = None

    @property
    def vessel_count(self) -> int:
        return len(self._vessels)

    def _result(self, row: object, status: str, reason: str, digest: str) -> dict:
        values = row if isinstance(row, dict) else {}
        source = values.get("source_type")
        if source not in SOURCE_TYPES:
            source = None
        result = {
            "schema_version": "testb_causal_decision_v1", "status": status,
            "reason": reason, "event_id": _identifier(values.get("event_id")),
            "vessel_id": _identifier(values.get("vessel_id")), "source_type": source,
            "time_basis": values.get("time_basis") if values.get("time_basis") in
            ("confirmed", "assumed", "unknown") else None,
            "availability_status": values.get("availability_status") if
            values.get("availability_status") in ("confirmed", "assumed", "unknown") else None,
            "evidence_level": ("synthetic_contract_check" if source == "synthetic" else
                               "availability_contract_only" if source else None),
            "input_digest": digest, "config_digest": self.config_digest,
            "score": None, "score_status": "disabled", "alarm": None,
            "alert_emitted": False,
        }
        for key in TIME_FIELDS:
            value = values.get(key)
            result[key] = value if isinstance(value, str) and len(value) <= 64 else None
        return result

    def reject(self, reason: str, input_digest: str) -> dict:
        return self._result(None, "quarantined", reason, input_digest)

    def decide(self, row: object, *, input_digest: str | None = None) -> dict:
        """Consume one JSON object without reading future rows or external sources."""
        try:
            payload = _canonical(row)
        except (TypeError, ValueError, RecursionError):
            return self.reject("invalid_json_value", input_digest or hashlib.sha256(b"").hexdigest())
        digest = hashlib.sha256(payload).digest()
        input_digest = input_digest or digest.hex()

        def result(status: str, reason: str) -> dict:
            return self._result(row, status, reason, input_digest)

        if not isinstance(row, dict):
            return result("quarantined", "record_not_object")
        if "score" in row:
            return result("quarantined", "scoring_disabled")
        if "references" in row and row["references"] != []:
            return result("quarantined", "unsupported_reference")
        allowed = {"event_id", "vessel_id", "source_type", "time_basis", "availability_status",
                   *TIME_FIELDS, "geometry", "references"}
        if set(row) - allowed:
            return result("quarantined", "unsupported_field")
        event_id, vessel_id = _identifier(row.get("event_id")), _identifier(row.get("vessel_id"))
        if event_id is None or vessel_id is None:
            return result("quarantined", "invalid_identifier")
        source = row.get("source_type")
        if source not in SOURCE_TYPES:
            return result("quarantined", "invalid_source_type")
        for field in ("time_basis", "availability_status"):
            value = row.get(field)
            if value is None or value in ("unknown", ""):
                return result("abstained", f"unconfirmed_{field}")
            if value not in ("confirmed", "assumed"):
                return result("quarantined", f"invalid_{field}")
            if source != "synthetic" and value != "confirmed":
                return result("abstained", f"unconfirmed_{field}")
        times = {}
        for field in TIME_FIELDS:
            parsed, status, reason = _timestamp(row.get(field), field)
            if status:
                return result(status, reason)
            times[field] = parsed
        if times["interval_start"] >= times["interval_end"]:
            return result("quarantined", "invalid_interval")
        if times["interval_end"] > times["available_at"]:
            return result("quarantined", "availability_before_interval_end")
        if times["available_at"] > times["decision_at"]:
            return result("quarantined", "not_available_at_decision")
        if "geometry" in row:
            reason = _geometry_reason(row["geometry"])
            if reason:
                return result("quarantined", reason)
        previous = self._vessels.get(vessel_id)
        if previous:
            if previous.event_id == event_id and previous.payload_digest == digest:
                return result("duplicate", "exact_last_accepted_retry")
            if previous.event_id == event_id or previous.interval_end == times["interval_end"]:
                return result("quarantined", "last_accepted_conflict")
            if times["interval_end"] < previous.interval_end:
                return result("quarantined", "late_vessel_interval")
        if self._decision_at is not None and times["decision_at"] < self._decision_at:
            return result("quarantined", "decision_clock_regression")
        if previous is None and len(self._vessels) >= self.config["memory"]["max_vessels"]:
            return result("abstained", "max_vessels_reached")
        # Update accepted state only after every contract guard has passed.
        self._vessels[vessel_id] = _Accepted(event_id, digest, times["interval_end"])
        self._decision_at = times["decision_at"]
        return result("observed_unscored", "availability_contract_satisfied_scoring_disabled")


def _bounded_lines(handle: BinaryIO, maximum: int, input_hash) -> Iterator[tuple[bytes | None, str]]:
    """Drain oversized lines in bounded chunks and still audit every source byte."""
    while True:
        chunk = handle.readline(maximum + 1)
        if not chunk:
            return
        line_hash = hashlib.sha256()
        input_hash.update(chunk)
        line_hash.update(chunk)
        if len(chunk) <= maximum:
            yield chunk, line_hash.hexdigest()
            continue
        while not chunk.endswith(b"\n"):
            chunk = handle.readline(maximum + 1)
            if not chunk:
                break
            input_hash.update(chunk)
            line_hash.update(chunk)
        yield None, line_hash.hexdigest()


def replay(config: dict, input_path: str | Path, output_path: str | Path) -> dict:
    """Stream JSONL into a new directory. Never overwrite existing paths or files."""
    engine = CausalReplay(config)
    input_path, output_path = Path(input_path), Path(output_path)
    if output_path.exists() or output_path.is_symlink():
        raise FileExistsError(f"output_already_exists: {output_path}")
    if not input_path.is_file():
        raise ValueError(f"input_not_file: {input_path}")
    preflight = memory_preflight(engine.config)
    counts, sources, reasons = Counter(), Counter(), Counter()
    input_hash = hashlib.sha256()
    # Open input before creating artifacts, and mkdir atomically reserves output.
    with input_path.open("rb") as source:
        output_path.mkdir(parents=True, exist_ok=False)
        with (output_path / "decisions.jsonl").open("x", encoding="utf-8", newline="\n") as target:
            for line_number, (raw, line_digest) in enumerate(
                    _bounded_lines(source, engine.config["memory"]["max_line_bytes"], input_hash), 1):
                if raw is None:
                    decision = engine.reject("line_too_large", line_digest)
                else:
                    try:
                        row = _parse_json(raw)
                    except (UnicodeError, ValueError, RecursionError):
                        decision = engine.reject("invalid_json", line_digest)
                    else:
                        decision = engine.decide(row, input_digest=line_digest)
                decision["line_number"] = line_number
                counts[decision["status"]] += 1
                sources[decision["source_type"] or "unknown"] += 1
                reasons[decision["reason"]] += 1
                target.write(json.dumps(decision, sort_keys=True, allow_nan=False) + "\n")
    summary = {
        "schema_version": "testb_causal_replay_summary_v1", "mode": "contract_replay",
        "input_digest": input_hash.hexdigest(), "config_digest": engine.config_digest,
        "digest_definition": {"input": "SHA256 exact JSONL file bytes",
                              "decision_input": "SHA256 exact line bytes including newline",
                              "config": "SHA256 canonical sorted compact ASCII JSON"},
        "counts": {status: counts[status] for status in STATUSES},
        "source_types": dict(sorted(sources.items())), "reason_counts": dict(sorted(reasons.items())),
        "total_records": sum(counts.values()), "tracked_vessels": engine.vessel_count,
        "scoring": engine.config["scoring"], "score_status": "disabled",
        "alarm": None, "alert_emitted": False, "evaluation": engine.config["evaluation"],
        "disabled_operations": list(DISABLED_OPERATIONS), "memory_preflight": preflight,
        "deduplication_horizon": "last accepted observation per vessel; older arrivals quarantined",
        "evidence_scope": "availability contract only; no detector or accident prediction validation",
    }
    with (output_path / "summary.json").open("x", encoding="utf-8", newline="\n") as target:
        json.dump(summary, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-config", action="store_true")
    args = parser.parse_args(argv)
    if args.check_config and (args.input is not None or args.output is not None):
        parser.error("--check-config does not consume --input or --output")
    if not args.check_config and (args.input is None or args.output is None):
        parser.error("--input and --output are required unless --check-config is used")
    try:
        config = load_config(args.config)
        if args.check_config:
            print(json.dumps({"status": "config_valid", "scoring_enabled": False,
                              "config_digest": hashlib.sha256(_canonical(config)).hexdigest()}))
        else:
            summary = replay(config, args.input, args.output)
            print(json.dumps({"status": "replay_complete", "counts": summary["counts"],
                              "score_status": "disabled", "alert_emitted": False}))
    except (OSError, ValueError, MemoryPreflightError) as exc:
        parser.exit(2, f"causal_replay: {exc}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
