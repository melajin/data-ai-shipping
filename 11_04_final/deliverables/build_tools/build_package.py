from pathlib import Path
import hashlib
import html
import json
import re
import shutil
import markdown

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'deliverables/rounds_001_002_team_package'
SOURCE = Path('D:/repos/fishing-track-classification/coach/gpt/rank1_experiments_20261104')
OUT.mkdir(parents=True, exist_ok=True)
copied = []


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''): h.update(b)
    return h.hexdigest()


def copy(src, rel, purpose):
    src = Path(src)
    dst = OUT / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    assert sha(src) == sha(dst)
    copied.append({'original_path': str(src), 'package_path': str(rel).replace('\\', '/'), 'sha256': sha(dst), 'purpose': purpose})


def write(rel, content):
    p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding='utf-8')


for rnd in ('round_001', 'round_002'):
    for p in sorted((ROOT / 'rounds' / rnd).rglob('*')):
        if not p.is_file() or any(x in p.parts for x in ('__pycache__', '.pycache', 'tmp', 'temp')): continue
        if p.suffix == '.pyc' or p.name == 'startup_sessions.json': continue
        copy(p, p.relative_to(ROOT), f'{rnd} original evidence; archival scripts are not portable launchers')
for name in ('AGENTS.md', 'CYCLE_PROTOCOL.md', 'STATUS.json', 'EXPERIMENT_LEDGER.csv', 'NEXT_SESSION.md', 'USER_PAUSE.md', 'README.md'):
    if (ROOT / name).exists(): copy(ROOT / name, Path('project_state') / name, 'Paused project state snapshot')
for p in (ROOT / 'environments/round_002_catboost').glob('*'):
    if p.is_file() and (p.suffix == '.log' or p.name in ('environment.json', 'requirements-freeze.txt')):
        copy(p, Path('environment/round_002') / p.name, 'Original execution environment evidence; no virtualenv or wheels')
for fold in range(3):
    copy(SOURCE / f'artifacts/exp01/fold_{fold}_features.npz', f'inputs/development/fold_{fold}_features.npz', '5897 development vessels only; fixed X304 fold matrix')
    for seed in (1, 7, 42, 2024, 2026):
        for folder, ext in (('models', 'txt'), ('seed_predictions', 'npz')):
            rel = f'{folder}/fold_{fold}_seed_{seed}.{ext}'
            copy(SOURCE / 'artifacts/exp01/sqrt_macro' / rel, f'historical_baseline/{rel}', 'Historical five-seed baseline replay for round001')
copy(SOURCE / 'artifacts/exp01/sqrt_macro/outer_predictions.csv', 'historical_baseline/outer_predictions.csv', 'Historical ensemble predictions')
validation_path = SOURCE / 'reports/exp01/data_validation.json'
validation = json.loads(validation_path.read_text(encoding='utf-8-sig'))
for path, meta in validation['input_hashes'].items():
    p = Path(path)
    if re.fullmatch(r'fold_[012]_t5.csv', p.name):
        assert sha(p) == meta['sha256']
        copy(p, Path('inputs/t5') / p.name, 'CSV parser precision replay; development rows only')
assert len(list((OUT / 'inputs/t5').glob('*.csv'))) == 3
result = json.loads((ROOT / 'rounds/round_002/artifacts/result.json').read_text(encoding='utf-8'))
for key, meta in result['source_hashes'].items():
    p = Path(meta['path'])
    if p.is_relative_to(SOURCE):
        assert sha(p) == meta['sha256']
        copy(p, Path('provenance/original_sources') / p.relative_to(SOURCE), 'Historical source snapshot, not an automatic training entrypoint')
extra = SOURCE / 'reports/exp01/provenance_addendum.json'
if extra.exists(): copy(extra, 'provenance/provenance_addendum.json', 'Historical data provenance and limitations')
copy(Path(__file__).parent / 'verify_package.py', 'reproduce/verify_package.py', 'Portable read-only replay verifier')
write('environment/requirements-verification.txt', 'numpy==2.2.5\npandas==2.2.3\nlightgbm==4.7.0\ncatboost==1.2.10\n')
write('provenance/COPY_ORIGINS.json', json.dumps(copied, ensure_ascii=False, indent=2))

readme = '''# 1·2차 결과 및 팀원 전달 패키지

먼저 **[통합 결과보고서](01_통합결과보고서.html)** 를 브라우저에서 여세요. 같은 내용의 Markdown 원본도 있습니다. 두 회차의 전체 결과보고서를 통합본 뒤에 수록했으며, 원문·코드·설정·예측·모델·검증 기록은 폴더별로 보존했습니다.

**현재 상태: 2차 완료 후 사용자 요청으로 일시정지. 3차 실행·학습·자동 인계는 시작하지 않았습니다.**

## 핵심 결과

| 구분 | 정답 / 5,897 | micro-F1 | macro-F1 | 해석 |
|---|---:|---:|---:|---|
| 1차 기존 5-seed LightGBM 재현 | 3,497 | 0.593013 | 0.525272 | 새 학습 없음; CSV 정밀도 변경 후 정답 수 동일 |
| 2차 재학습 LightGBM seed42 | 3,476 | 0.589452 | 0.519210 | 2차 비교 기준 |
| 2차 CatBoost | 3,424 | 0.580634 | 0.468922 | 채택 거절 |
| 2차 fold별 선택 혼합 | 3,474 | 0.589113 | 0.506168 | 채택 거절 |

모두 반복 노출된 개발 OUTER 점수입니다. 독립 평가·공식 제출 점수가 아니며 목표 0.7은 달성하지 못했습니다. 1차 5-seed 저장 모델과 2차 seed42 재학습은 조건이 달라 두 행의 차이를 단일 알고리즘 효과로 해석할 수 없습니다.

## 구성

| 위치 | 내용 |
|---|---|
| `01_통합결과보고서.html/.md` | 해석·수치·한계·실패 이력·3차 검토안 + 1차/2차 전체 보고서 |
| `rounds/round_001` | CSV 정밀도 진단, 저장 모델 재현, 로그와 검토 |
| `rounds/round_002` | 실험 코드·최종 설정·실패/수정 이력·모델 6개·확률·검토 |
| `historical_baseline` | 1차 재현에 사용한 저장 LightGBM 15개 및 seed별 확률 |
| `inputs/development` | 5,897개 개발 선박의 fold별 고정 X304 특징·라벨·역할 |
| `inputs/t5` | 1차 CSV 정밀도 점검에 사용한 T5 CSV 3개 |
| `reproduce` | 학습 없는 패키지 검증 스크립트 |
| `environment` | 실행 환경 기록, 원래 freeze, 재검증용 requirements |
| `provenance` | 원본 위치→패키지 위치·SHA256 및 역사적 소스 |
| `project_state` | 일시정지 및 다음 단계 문서의 스냅샷 |
| `delivery_review` | 별도 검토자의 전달 패키지 검토 |
| `validation` | 이 패키지에서 수행한 재검증 결과 |
| `MANIFEST.json` | 파일별 크기 및 SHA256 |

## 팀원 재검증 순서

ZIP을 완전히 풀고 폴더에서 터미널을 엽니다. Python 3.13.3 / Windows가 원래 실행 환경입니다. 다른 환경에서의 동일성은 별도 확인이 필요합니다.

1. 추가 패키지 없이 무결성만 확인: `python -B reproduce/verify_package.py --hash-only`
2. 가상환경을 만들어 `pip install -r environment/requirements-verification.txt` 실행. 인터넷/패키지 설치가 필요합니다. CSV 정밀도 재현에는 1차 환경의 pandas 2.2.3을 사용합니다. 2차 환경에 기록된 pandas 3.1.0은 기본 파싱이 달라 이 검증을 그대로 재현하지 못합니다. 원본 `requirements-freeze.txt`에는 작성자 PC의 wheel 경로가 있으므로 그대로 설치용으로 쓰지 않습니다.
3. 저장 확률로 지표·ID·alpha·혼합식을 재검증: `python -B reproduce/verify_package.py`
4. 저장 모델 21개 재로딩 및 OUTER 추론, CSV 정밀도 비교까지 확인: `python -B reproduce/verify_package.py --models`

검증기는 패키지 상대경로만 사용하며 학습하지 않습니다. 출력은 JSON이며 필요하면 `> my_verification.json`으로 별도 저장하세요. `MANIFEST.json`은 자기 자신과 `validation/`, `delivery_review/`를 제외한 고정 콘텐츠를 검증합니다. 전체 ZIP의 SHA256은 ZIP 옆 파일에 있습니다.

원래 학습/실행 코드는 역사적 증거로 보존되어 작성자 PC의 절대경로를 포함합니다. 그대로 실행하지 마세요. 재학습을 재개하려면 사용자 재개 지시를 받은 뒤 경로와 자원·평가 계약을 다시 고정해야 합니다. 패키지는 고정 특징에서의 추론과 결과 재검증까지 자체 완결됩니다. 원자료부터 특징을 생성하는 전체 파이프라인의 재현을 보장하지 않습니다.

## 전달 범위와 데이터 설명

- 클래스 순서(0~3): 연안복합, 자망, 통발, 채낚기연승낚시. NPZ에서 `allow_pickle=False`로 읽을 수 있습니다.
- X304 = F156 156열 + T5 10열 + behavior_without_obs_days 68열 + local_rel 70열. 정확한 열 이름과 순서는 NPZ `feature_names`가 기준입니다.
- 각 fold 입력은 개발 선박 5,897개이며 FIT/INNER/OUTER 역할이 있습니다. 이들을 중복 합쳐 17,691개의 독립 평가 표본으로 세면 안 됩니다. OUTER를 fold별 한 번씩 모으면 5,897개입니다.
- 원자료, 보호 holdout의 개별 특징·라벨·예측, 대용량 가상환경·wheel, 캐시, 관련 없는 세션 대화, 자동 다음 세션 시작 스크립트는 포함하지 않았습니다. 기록의 holdout 경로/해시는 과거 메타데이터이며 holdout 자체가 아닙니다.
- 원본 절대경로는 출처 추적을 위한 기록입니다. 첨부 개발 자료에는 선박 ID와 정답이 포함되므로 연구팀 전달 범위에 맞게 취급하세요.
- 동적 T5 생성부터 CSV까지의 전체 동등성은 미측정입니다. 이전 S6 0.59183의 차이 원인은 확정되지 않았습니다.
- 3차 관련 아이디어 원문과 검토안은 `rounds/round_002/references/algorithm_variant_ideas.md`, `IDEA_REVIEW_AND_ROUND003.md`, `NEXT_SESSION_DRAFT.md`에 있습니다. 미래 TabICL 체크포인트/학습환경/전체 데이터는 이 패키지 범위에 포함하지 않습니다.

## 팀원이 설명할 수 있어야 하는 사항

1. micro-F1과 macro-F1이 다른 이유 및 통발 재현율 저하가 채택 판단에 미친 영향.
2. INNER_ES, INNER_SELECT, OUTER의 역할과 혼합계수 선택 시 OUTER를 배제하는 이유.
3. CSV 값의 작은 차이가 확률을 바꾸면서 최종 분류는 바꾸지 않을 수 있는 이유.
4. 저장 모델 재현 성공과 독립 데이터 성능 보장은 서로 다른 주장이라는 점.
'''
write('00_README.md', readme)

summary = '''# 선박 조업 분류 1·2차 통합 결과보고서

대상: 개발 OUTER 5,897척, X304 고정 특징, 4개 업종 분류. 작성 목적: 결과 공유·팀원 재검증·후속 판단. 실험은 실제 데이터의 소프트웨어 평가이며 하드웨어 실측이 아닙니다. 학습자의 설명·해석 역량 달성 여부는 별도로 확인하지 않았습니다.

## 결론

1차는 기존 5-seed LightGBM의 micro-F1 **0.593013**을 재현했습니다. CSV 부동소수점 파싱 정밀도는 일부 확률에 영향을 주었지만 최종 분류와 정답 수를 바꾸지 않았습니다. 이 진단만으로 과거 점수 차이의 원인을 확정할 수 없습니다.

2차는 LightGBM 3개와 CatBoost 3개를 학습해 비교했습니다. CatBoost와 혼합 모두 기준 모델보다 정답 수가 적고 통발 재현율이 악화되어 **채택하지 않았습니다**. 목표 micro-F1 0.7 미달이며 사용자 요청에 따라 **2차 완료 후 일시정지**했습니다. 3차를 실행하지 않았습니다.

## 1·2차 결과 비교

| 회차 / 조건 | 정답 수 | micro-F1 | macro-F1 | 비교 의미 |
|---|---:|---:|---:|---|
| 1차 저장 5-seed LightGBM | 3,497 / 5,897 | 0.5930133966 | 0.5252719739 | 기존 모델 재현, 새 학습 없음 |
| 1차 round_trip CSV 파싱 | 3,497 / 5,897 | 0.5930133966 | 0.5252719739 | 파싱 정밀도 민감도 진단 |
| 2차 seed42 LightGBM 재학습 | 3,476 / 5,897 | 0.5894522639 | 0.5192103043 | 2차의 동시 비교 기준 |
| 2차 CatBoost | 3,424 / 5,897 | 0.5806342208 | 0.4689224222 | 기준 대비 정답 52개 감소 |
| 2차 fold별 혼합 | 3,474 / 5,897 | 0.5891131084 | 0.5061678494 | 기준 대비 정답 2개 감소 |

1차와 2차는 seed 구성·학습/조기종료 조건이 다릅니다. 두 회차 기준 점수의 차이는 직접적인 성능 개선/악화 실험으로 해석하지 않습니다. 모든 점수는 반복 노출된 개발 OUTER이며 독립 평가나 공식 제출 성적이 아닙니다.

## 1차에서 확인한 내용

- pandas 기본 CSV 파싱의 T5 10열과 고정 NPZ의 값·NaN 마스크가 일치했습니다.
- 기본 파싱과 round_trip 파싱 간 최대 값 차이는 약 8.88e-16이었습니다.
- 저장 모델 15개(3 folds × 5 seeds)의 확률을 재현했습니다. 저장 앙상블 평균과의 최대 차이는 약 2.22e-16입니다.
- 정밀도 변경 시 단일 모델 전체 개발 행 기준 최대 확률 변화는 약 0.004175, pooled OUTER 앙상블 최대 변화는 약 0.001202입니다. 두 수치는 집계 범위가 다릅니다.
- OUTER 앙상블에서 확률이 달라진 행은 15개였지만 argmax 변경·정답 이득·정답 손실은 모두 0개였습니다.
- 전체 동적 T5 생성 경로는 보호 데이터 경계를 넘지 않기 위해 실행하지 않았습니다. 동적 생성→CSV의 동등성은 미측정이고 과거 S6 0.59183의 원인은 미해결입니다.

## 2차 실험 조건과 결과 해석

고정 X304, 동일 FIT 역할과 seed42를 사용했습니다. fold별 INNER 787개를 seed20261105로 ES 393개와 SELECT 394개로 나누었습니다. LightGBM은 FIT의 역제곱근 클래스 가중치와 macro-F1 조기종료를 사용했고, CatBoost는 가중치 없이 Accuracy 조기종료를 사용했습니다. 따라서 결과는 모델·가중치·조기종료가 함께 다른 파이프라인 비교입니다.

혼합식은 `(1-alpha) * LightGBM + alpha * CatBoost`입니다. alpha 후보 0/0.25/0.5/0.75/1 중 INNER_SELECT 정답 수를 최대화하고 동점이면 작은 값을 선택했습니다. OUTER 추론 전에 선택을 고정했으며 fold별 값은 **[1.0, 0.0, 0.5]**입니다.

| 기준 LightGBM 대비 | 새로 맞힌 수 | 새로 틀린 수 | 순증 | micro-F1 차이 | 개발 OUTER bootstrap 95% 구간 |
|---|---:|---:|---:|---:|---|
| CatBoost | 271 | 323 | -52 | -0.008818 | [-0.016792, -0.000678] |
| 혼합 | 138 | 140 | -2 | -0.000339 | [-0.005766, 0.005087] |

구간은 선박 단위 5,000회 bootstrap(seed20261105) 결과입니다. 원래 실험 기록의 구간을 인용했으며 전달 패키지 검증에서 bootstrap을 다시 계산하지 않았습니다. 개발 집합 반복 사용에 따른 선택 편향을 제거하지 않습니다.

| 클래스 재현율 | LightGBM | CatBoost | 혼합 |
|---|---:|---:|---:|
| 연안복합 | 0.818151 | 0.861301 | 0.838356 |
| 자망 | 0.440972 | 0.397321 | 0.427083 |
| 통발 | 0.129341 | 0.033533 | 0.092216 |
| 채낚기연승낚시 | 0.714286 | 0.634921 | 0.698413 |

채택 조건은 micro-F1 +0.005 이상, 차이 신뢰구간 하한 >0, macro-F1·클래스 재현율·관측일 구간 micro-F1의 하락 각각 0.03 이내였습니다. 두 후보 모두 조건을 통과하지 못했습니다. 특히 통발 재현율 하락은 CatBoost 약 0.095808, 혼합 약 0.037126으로 허용 하락 0.03을 넘었습니다.

## 실패·수정·검증 이력

1차 보조 재현의 첫 실행은 fold2 예상 행 수를 1,966으로 잘못 둔 검사 때문에 실패했고, 실제 1,965로 바로잡은 재실행은 exit0으로 완료했습니다. 최초 주 실행의 OS 종료코드는 확인되지 않아 성공 코드로 단정하지 않습니다.

2차 첫 시도는 LightGBM fold0을 완료한 뒤 CatBoost 생성자 feature_names 호환성 오류가 발생했습니다. 두 번째는 Pool로 수정한 후 가중치 없는 데이터에서 명시적 Accuracy:use_weights=false 옵션이 거절되어 학습 반복 전 실패했습니다. 세 번째는 가중치 없이 Accuracy로 수정하고 기존 LightGBM fold0을 재사용하여 나머지 5개를 완료했습니다. 총 성공 모델은 6개이며 최종 exit0입니다. 사전 검토에서 발견된 빈 SELECT 인덱스 문제는 학습 전에 수정했습니다.

기록된 실행 시간 합은 약 294.58초(이전 시도 포함; 설치·관리 제외)로 30분 연산 제한 내입니다. 관리 세션의 최초 45분 목표는 호환성 수정 및 완료 지시 반영으로 초과했으며 준수했다고 주장하지 않습니다.

독립 코드·결과 검토는 protocol PASS, overall CONDITIONAL, adoption REJECT입니다. 저장 모델 재로딩 확률·입력 해시·5,897개 OUTER ID·지표·혼합식·alpha를 검증했습니다. 이 검토는 독립 평가 데이터에서의 성능 검증을 뜻하지 않습니다. 모델/effort 요청값과 실행 환경 증거는 원본 `model_runtime_evidence.json`에 구분되어 있습니다.

## 3차 검토안과 팀원 인계

사용자가 제공한 「알고리즘 변형 아이디어」를 검토한 문서와 원문을 첨부했습니다. 보존된 제안은 TabICL A(F156) 계열의 기존 확률 및 R0 정책 비교를 먼저 확인하고, 조건이 갖춰지면 M4 출력 Linear 직접 조정과 rank2 LoRA 비교를 검토하는 순서입니다. 현재 S6 X304와 A F156은 다른 실험 계열이며 섞어서 결론 내리지 않습니다. 체크포인트·런타임·컨텍스트 가용성과 개선 효과는 아직 확정되지 않았습니다.

이 계획은 실행 결과가 아닙니다. 3차는 사용자의 명시적 재개 지시 후 범위를 다시 고정해야 합니다. 원문 아이디어와 `IDEA_REVIEW_AND_ROUND003.md`, `NEXT_SESSION_DRAFT.md`가 상세 기준이며 현재 일시정지 지시가 모든 과거 자동 인계 문구보다 우선합니다.

팀원은 `00_README.md`의 순서로 파일 무결성, 저장 확률, 모델 재로딩을 검증할 수 있습니다. 패키지는 원자료·보호 holdout을 포함하지 않으며 고정 개발 특징 이후의 추론과 지표 재현을 지원합니다. 전체 특징 생성이나 새로운 학습의 자동 실행 패키지는 아닙니다.

## 부록: 회차별 전체 보고서

아래에는 기존 두 보고서의 전체 본문을 수록했습니다. 전달 패키지에 맞춰 링크만 조정했으며 절대경로로 기록된 역사적 참조는 원문으로 남아 있을 수 있습니다. 원래 Markdown 파일도 `rounds/`에 보존했습니다.
'''

def adjust_report(text, rnd):
    # Redirect references inside the project to the packaged tree when present.
    def link(m):
        target = m.group(2).strip('<>')
        normalized = target.replace('\\', '/')
        rootstr = ROOT.as_posix()
        if normalized.lower().startswith(rootstr.lower() + '/'):
            rel = normalized[len(rootstr)+1:]
            if (OUT / rel).exists(): return f'[{m.group(1)}](<{rel}>)'
        if not re.match(r'^(?:[a-zA-Z]:|https?://|#)', normalized):
            candidate = OUT / 'rounds' / rnd / normalized
            if candidate.exists(): return f'[{m.group(1)}](<{candidate.relative_to(OUT).as_posix()}>)'
        return m.group(0)
    return re.sub(r'\[([^\]]+)\]\(([^\n]+?)\)', link, text)

full = summary
for rnd in ('round_001', 'round_002'):
    report = (ROOT / 'rounds' / rnd / 'ROUND_REPORT.md').read_text(encoding='utf-8-sig')
    full += '\n\n---\n\n' + adjust_report(report, rnd)
write('01_통합결과보고서.md', full)
body = markdown.markdown(full, extensions=['tables', 'fenced_code', 'toc'])
style = 'body{font-family:Malgun Gothic,Apple SD Gothic Neo,Arial,sans-serif;max-width:1100px;margin:40px auto;padding:0 24px;color:#1c2838;line-height:1.75}h1,h2,h3{line-height:1.35;color:#123a59}h1{border-bottom:3px solid #187e93;padding-bottom:16px}h2{margin-top:44px}table{border-collapse:collapse;width:100%;font-size:.91em;margin:22px 0}th,td{border:1px solid #cbd5df;padding:9px;text-align:left}th{background:#edf4f8}tr:nth-child(even){background:#f8fafb}code{background:#eff2f5;padding:2px 4px;overflow-wrap:anywhere}pre{white-space:pre-wrap;background:#eff2f5;padding:16px}a{color:#096d96;overflow-wrap:anywhere}hr{margin:60px 0;border:1px solid #ccd9e2}@media print{body{margin:0;max-width:none;font-size:10pt}h1,h2,h3{break-after:avoid}tr{break-inside:avoid}}'
write('01_통합결과보고서.html', '<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>1·2차 통합 결과보고서</title><style>'+style+'</style></head><body>'+body+'</body></html>')
manifest = {'format_version': 1, 'scope': 'Immutable content; excludes MANIFEST.json itself, validation/ and delivery_review/ to avoid recursive checks', 'files': []}
for p in sorted(OUT.rglob('*')):
    if p.is_file() and p.name != 'MANIFEST.json' and p.relative_to(OUT).parts[0] not in ('validation', 'delivery_review'):
        manifest['files'].append({'path': p.relative_to(OUT).as_posix(), 'bytes': p.stat().st_size, 'sha256': sha(p)})
write('MANIFEST.json', json.dumps(manifest, ensure_ascii=False, indent=2))
print(json.dumps({'package': str(OUT), 'files': len(manifest['files']), 'uncompressed_bytes': sum(x['bytes'] for x in manifest['files'])}, ensure_ascii=True))
