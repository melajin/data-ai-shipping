"""Local abstention comparison only; no model fitting or source modification."""
import csv
import hashlib
import json
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = next((ROOT / 'testB').glob('*/first_results/candidate_A.csv'))
SUB = SOURCE.with_name('testB_submission_candidate.csv')
LABEL = ROOT / 'testB/final/round_012_20261106/review_packet_001/development_B0_predictions_82RFIDs.csv'

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def write(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

inputs = [SOURCE, SUB, LABEL]
hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
rows, submission, labels = read(SOURCE), read(SUB), read(LABEL)
scores = {r['rfid_id']: float(r['score']) for r in rows}
label_ids = {r['rfid_id'] for r in labels}
assert len(rows) == len(scores) == len(submission) == 100
assert set(scores) == {r['rfid_id'] for r in submission}
assert len(label_ids) == 82
assert all(0 <= s <= 1 for s in scores.values())
threshold = 0.6  # transparent exploratory cutoff, not calibrated accident probability
sweep = []
for t in [0.0, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 1.0]:
    yes = [s for s in scores.values() if s >= t]
    no = [s for s in scores.values() if s < t]
    sweep.append(dict(threshold=t, accident_count=len(yes), abstain_count=len(no),
                      accident_score_median=statistics.median(yes) if yes else '',
                      abstain_score_median=statistics.median(no) if no else '',
                      comparable_label_ids=len(set(scores) & label_ids), label_agreement='NA'))
write('threshold_comparison.csv', sweep)
write('vessel_decisions.csv', [dict(rfid_id=r['rfid_id'], original_peak_score=r['score'],
      threshold=threshold, accident_prediction=int(scores[r['rfid_id']] >= threshold),
      abstain=int(scores[r['rfid_id']] < threshold), original_time=r['A'],
      retained_time=r['A'] if scores[r['rfid_id']] >= threshold else '') for r in rows])
for r in submission:
    if scores[r['rfid_id']] < threshold:
        for col in list(r)[1:]:
            r[col] = ''
write('submission_abstention_EXPLORATORY.csv', submission)
chosen = next(r for r in sweep if r['threshold'] == threshold)
report = (f"탐색 임계값: 기존 선박별 이상항적 최고점 ≥ {threshold:.2f} / 사고판정 {chosen['accident_count']}척 / "
          f"비사고판정(기각·전 예측칸 공란) {chosen['abstain_count']}척. 사고판정군/기각군의 기존 점수 중앙값은 "
          f"{chosen['accident_score_median']:.6f}/{chosen['abstain_score_median']:.6f}이다. "
          "민감도 비교는 0.50→75/25척, 0.55→50/50척, 0.65→22/78척이다. "
          f"기존 82 RFID와 테스트 100척의 ID 교집합은 {len(set(scores) & label_ids)}척이므로 라벨 일치율은 산출 불가다. "
          "0.60은 공란 처리를 실행·비교하기 위한 탐색 기준이며 최적화되거나 사고확률로 보정된 값이 아니다. "
          "점수로 직접 분리했으므로 두 군의 점수 차이는 사고 식별력의 검증이 아니며, 기각은 실제 무사고의 확인을 뜻하지 않는다. "
          "공식 F1 개선은 미확인이고 기존 100/82·60/55 분모와 원본은 유지했다.\n")
(OUT / 'RESULT.md').write_text(report, encoding='utf-8')
assert all(hashlib.sha256(p.read_bytes()).hexdigest() == hashes[str(p)] for p in inputs)
assert sum(bool(r[list(r)[1]]) for r in submission) == chosen['accident_count']
(OUT / 'summary.json').write_text(json.dumps(dict(chosen=chosen, selection='exploratory fixed cutoff; no label optimization',
    input_sha256=hashes, run_time=datetime.now().astimezone().isoformat(),
    memory='Pre-run OS check: 3888728 KiB available; stdlib CSV analysis of 100 + 328 rows, estimated peak <50 MiB; no training or large loads.'), indent=2), encoding='utf-8')
print(json.dumps(chosen))
