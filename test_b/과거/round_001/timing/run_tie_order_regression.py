"""Run the synthetic A tie-order regression and refresh Round 001 timing evidence."""
from __future__ import annotations
import hashlib, json, platform, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN = HERE / "round_001/run_003"
RUN.mkdir(parents=True, exist_ok=True)
CODE = HERE / "timing_interface.py"
def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""): h.update(b)
    return h.hexdigest()

def main() -> int:
    started = datetime.now(timezone.utc).astimezone().isoformat()
    proc = subprocess.run([sys.executable, str(CODE), "--self-check"], cwd=str(HERE), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    (RUN / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (RUN / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    code_hash = sha(CODE)
    report = json.loads(proc.stdout) if proc.returncode == 0 else {}
    process = {
      "started_at": started, "ended_at": datetime.now(timezone.utc).astimezone().isoformat(),
      "argv": [sys.executable, str(CODE), "--self-check"], "exit_code": proc.returncode,
      "stdout": str(RUN / "stdout.log"), "stderr": str(RUN / "stderr.log"),
      "code": {"path": str(CODE), "size_bytes": CODE.stat().st_size, "sha256": code_hash},
      "scope": "synthetic test rows only; no actual score/event inputs read",
    }
    (RUN / "process_result.json").write_text(json.dumps(process, ensure_ascii=False, indent=2), encoding="utf-8")
    env = {"python": sys.version, "executable": sys.executable, "platform": platform.platform(),
           "requested_model": "gpt-6-luna", "requested_effort": "xhigh",
           "runtime_receipt": "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts/W2_start.json",
           "runtime_observation": "Orca start receipt reports gpt-6-luna/xhigh; provider internal runtime not independently introspected"}
    (RUN / "environment.json").write_text(json.dumps(env, ensure_ascii=False, indent=2), encoding="utf-8")
    if proc.returncode != 0:
        print(json.dumps({"exit_code": proc.returncode, "process_result": str(RUN / "process_result.json")}))
        return proc.returncode

    report_path = HERE / "readiness_report.md"
    text = report_path.read_text(encoding="utf-8")
    text = text.replace("동점은 시간순 최초", "A 동점은 원입력 순서에서 최초 최대값(idxmax semantics)이며, 원입력 순서를 보존한 채 A를 정한 뒤 시간 정렬은 B/C 구간 탐색에만 적용")
    text = text.replace("합성 검사 7종이 실제 종료코드 0으로 통과했다(경계 비교 gt/ge, 정렬·동점, 누락 간격 분절, NaN 분절, 중복시각 추적/지속시간, C=B, 점수 결측).",
        "합성 검사 8종이 실제 종료코드 0으로 통과했다(경계 비교 gt/ge, 정렬 구간 탐색, 원입력순 동점 A가 시간순 최초와 다른 사례, 누락 간격 분절, NaN 분절, 중복시각 추적/지속시간, C=B, 점수 결측).")
    if "원입력 순서에서 최초 최대값(idxmax semantics)" not in text or "합성 검사 8종" not in text:
        raise RuntimeError("readiness report alignment text was not updated")
    report_path.write_text(text, encoding="utf-8")

    summary_path = HERE / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["synthetic_checks"] = {"status": report.get("status"), "checks": report.get("checks"),
                                   "actual_exit_code": proc.returncode, "log": str(RUN / "stdout.log")}
    summary["tie_break_contract"] = "A = first maximum in original input order (idxmax); original order retained for A; time-sorted rows are used only for B/C segment search"
    summary["timing_interface_sha256"] = code_hash
    summary["tie_order_regression_exit_code"] = proc.returncode
    summary.setdefault("round_output_hashes", {})["timing_interface.py"] = code_hash
    summary["round_output_hashes"]["readiness_report.md"] = sha(report_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    lineage_path = HERE / "code_lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["round_copy"]["sha256"] = code_hash
    lineage["round_copy"]["size_bytes"] = CODE.stat().st_size
    lineage["round_copy"]["change"] = "A tie selects first maximum in original input order (idxmax semantics), with source order retained; time sorting is limited to B/C segment search. Persistence row minimum counts unique timestamps."
    lineage["verification"] = {"command": "python testB/round_001/timing/run_tie_order_regression.py",
                                "actual_exit_code": proc.returncode, "checks": report.get("checks"),
                                "process_record": str(RUN / "process_result.json"),
                                "runtime_model_receipt": "26_11_5/testb_next_experiment_20261105/integration/runtime_receipts/W2_start.json"}
    lineage_path.write_text(json.dumps(lineage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": proc.returncode, "checks": report.get("checks"), "code_sha256": code_hash,
                      "process_result": str(RUN / "process_result.json")}, ensure_ascii=False))
    return proc.returncode

if __name__ == "__main__": raise SystemExit(main())
