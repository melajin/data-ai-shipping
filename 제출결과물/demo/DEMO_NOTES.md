# Test B 제출용 데모영상

- 영상: `TestB_demo_20261106.mp4`
- 재생시간: **2분 8초 (128.00초)**
- 파일 크기: **636,424 bytes**
- 형식: MP4, H.264/yuv420p, 1280×720, 10fps, 무음. 화면의 단계 제목과 명령·출력으로 진행을 설명한다.
- 녹화일: 2026-11-06 (KST)
- 제출 파일은 위 MP4와 이 안내문이다. `_production/`은 녹화 스크립트·도구·실행 로그·검수 증거 보관용이다.

## 녹화 방식과 선택 이유

Python 3.13.3의 Tkinter 전용 실행 창에서 실제 자식 프로세스를 실행하고, 해당 프로세스의 stdout/stderr를 도착하는 대로 표시했다. 이 창을 FFmpeg 9.0.2의 Windows `gdigrab`으로 연속 캡처했다. 결과 확인은 실제 생성된 JSON/CSV를 읽는 보조 명령으로 수행했다. 보조 코드는 점수 계산·학습을 하지 않는다.

시스템에 FFmpeg가 없어 `imageio-ffmpeg==0.8.1`에 포함된 실행 파일을 제작 폴더에만 설치했다. 시스템 PATH와 분석 의존성은 변경하지 않았다. 전용 창 캡처는 개인 데스크톱·알림·사용자 경로를 배제하고, 긴 실행 출력도 읽기 쉽게 표시하기 위해 선택했다. 녹화 후 터미널 프레임을 합성하거나 저장 로그로 실행 장면을 재연한 영상이 아니다. 실행 대기시간을 포함해 배속·장면 편집 없이 기록했다. 화면 외곽의 DPI 여백만 캡처 필터로 잘랐다.

영상의 환경 확인은 설치 버전 대조이며, 의존성 설치 장면은 포함하지 않는다. 환경·결과 조회 보조 명령과 본 실행·단위 테스트의 총 6개 프로세스가 모두 종료코드 0으로 끝났다.

## 영상에 담긴 단계

시각은 초 단위 근사이며, 각 명령의 실제 출력과 종료코드를 표시한다.

| 영상 위치 | 단계 | 확인 내용 |
|---|---|---|
| 00:01–00:12 | 환경 확인 | Python 3.13.3, CPU 경로, requirements.txt와 numpy 2.2.5 / pandas 2.2.3 / pyarrow 24.0.0 / scipy 1.15.3의 설치 버전 일치 |
| 00:12–01:00 | 본 실행 | `python src/run_analysis.py --output results/demo_run`, 10척 단위 실제 진행 출력, 46,705행·100척 재계산 및 저장 기준 결과 전수 대조 |
| 01:00–01:12 | 생성 파일 확인 | `scored_rows.parquet`, `candidates.csv`, `summary.json`; 완료 상태·행/선박 수·이번 실행 telemetry |
| 01:12–01:31 | parity 확인 | JSON의 parity 전체 블록. 네 점수의 최대 절대차 0.0, 결측 마스크·상태·후보시각·원행번호 불일치 0, 후보점수 최대 절대차 0.0, 전체 검사 통과 |
| 01:31–01:52 | 후보 1척 확인 | `median_peak_rank` 사례, 순위 50, 후보시각 원문 `20250201 6`, 종합점수·세 구성점수·과거 관측 수 |
| 01:52–02:08 | 단위 테스트 | `python -m unittest discover -s tests -v`, 4개 테스트 `ok`, 최종 `OK` |

후보 화면의 값은 새 `candidates.csv`에서 직접 읽었다: `score=0.5542566126917833`, `s_zone=0.0`, `s_change=0.8256686808446103`, `s_gap=0.8371011572307396`, `component_count=3`, `prior_observation_count=85`, `n_observations=121`. 선박 식별자와 좌표는 표시하지 않았다.

이번 실행의 성능 수치는 새 `results/demo_run/summary.json`의 `telemetry`에 기록된 **39.96530410000014초**, **298.1484375MiB**이다. 녹화와 동시에 실행한 결과이며 기존 실행의 33.4초를 이번 측정값으로 사용하지 않았다. 최대 프로세스 메모리는 분석 프로세스의 수치이며 녹화 도구를 포함한 전체 시스템 사용량이 아니다.

## 사용 도구와 명령

저장소 루트에서 준비·녹화를 수행했다.

```powershell
python -m pip install --disable-pip-version-check --no-deps --target 제출결과물/demo/_production/tools imageio-ffmpeg
python 제출결과물/demo/_production/record_demo.py
```

설치 결과는 imageio-ffmpeg 0.8.1 / FFmpeg 9.0.2이다. `record_demo.py`가 실제 실행한 캡처 인수는 `_production/capture_command.json`에 보존했다. 아래는 데모 폴더를 기준으로 경로만 상대화한 같은 FFmpeg 명령이다.

```powershell
& './_production/tools/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v9.0.2.exe' `
  -hide_banner -n -f gdigrab -framerate 10 -draw_mouse 0 `
  -i 'title=Test B - Live execution capture' `
  -vf 'crop=1280:720:0:0' -an -c:v libx264 -preset veryfast `
  -crf 18 -threads 2 -pix_fmt yuv420p -movflags +faststart TestB_demo_20261106.mp4
```

이 명령은 전용 창이 열린 상태에서 사용한다. 녹화 스크립트는 창 생성·명령 실행·캡처 종료를 함께 담당하며 기존 영상 또는 `results/demo_run`이 있으면 덮어쓰지 않는다. 원본 영상 재생에는 Python이나 FFmpeg 설치가 필요하지 않다.

## 분석 재현 명령

작업 디렉터리:

```text
D:\obsidian\claude\obsidian_export\DATA AI SHIPPING\deliverables\testb_system_20261106
```

영상에서 실제 실행한 명령:

```powershell
python results/demo_tools/inspect_result.py environment
python src/run_analysis.py --output results/demo_run
python results/demo_tools/inspect_result.py outputs
python results/demo_tools/inspect_result.py parity
python results/demo_tools/inspect_result.py candidate
python -m unittest discover -s tests -v
```

현재 `results/demo_run`은 이미 존재하므로 재실행 시에는 **아직 없는 새 폴더명**을 지정한다. 예를 들어 `results/demo_repeat_001`이 없을 때:

```powershell
python src/run_analysis.py --output results/demo_repeat_001
python results/demo_tools/inspect_result.py outputs results/demo_repeat_001
python results/demo_tools/inspect_result.py parity results/demo_repeat_001
python results/demo_tools/inspect_result.py candidate results/demo_repeat_001
python -m unittest discover -s tests -v
```

표시용 보조 스크립트 원본은 `_production/inspect_result.py`, 실행 복사본은 패키지의 새 `results/demo_tools/inspect_result.py`이다. 두 파일은 동일하다. 새 분석 결과는 `results/demo_run/`에만 생성했다. 모델 재학습과 점수 산식 변경은 수행하지 않았다.

## 보존·검수 기록

- `inputs/`, `references/`, `results/reproduction_001/`, `reports/`의 21개 파일을 청크 방식으로 SHA-256 대조했다. 녹화 전후 파일 목록과 해시가 모두 동일하다. 증거: `_production/protected_before.json`, `protected_after.json`, `integrity.json`.
- 분석·녹화 예상 합산 최대 메모리는 1,024MiB, 별도 여유는 640MiB로 잡았다. 근거는 기존 분석 실측 약 299MiB에 대해 분석 예산 512MiB, Tkinter 및 2스레드 FFmpeg 예산 512MiB를 배정한 것이다. 프레임을 메모리에 누적하지 않고 순차 인코딩했다. 녹화 직전 11:44:45 KST 가용 RAM은 4,003.47MiB였다. 테스트 직전에도 다시 확인했으며 시각·가용량·동시 프로세스는 `_production/memory_checks.json`에 기록했다. 사용자 프로세스는 종료하지 않았다.
- 영상 검수 직전 11:46:56 KST 가용 RAM 5,193.35MiB를 확인했다. 순차 디코딩과 한 장씩 화면 추출의 예상 메모리는 512MiB 이하로 잡았다.
- 전체 128초 영상의 디코딩 오류 0, 1280×720·H.264·10fps·무음 확인. 6개 단계 완료 화면을 추출해 필수 값과 글자 잘림을 확인했다. 영상에는 API Key, 개인 이름, 절대 로컬 경로, 선박 식별자·좌표가 표시되지 않는다. 상대 실행 경로만 표시한다.
- 실행 표준출력·종료코드·단계별 시각: `_production/recording_done.json`. 인코더 로그: `_production/ffmpeg.log`. 영상 검사: `_production/video_validation.json`, `stage_1.png`–`stage_6.png`.
- 독립 검토는 `demo_review` / `sol_review`에 GPT-6.1 Sol, high를 명시해 요청했고 도구가 `/root/demo_review` 생성을 반환했다. 이는 생성 요청의 증거이며 별도의 내부 실행 모델 계측 주장은 아니다.
- 독립 검토 결과: 6개 단계 PNG, 실행 로그, 영상 검사 기록 및 21개 보호 파일 해시 대조 통과. 검토자는 수정 필요 사항을 발견하지 않았다. 독립 검토 범위는 단계별 화면과 기록이며 전체 프레임 육안 재생 검토는 아니다.

이 영상은 고정 기준선의 **사후 재현과 단위 테스트**를 보여준다. 전체 관측기간 최고점의 후보시각은 확정 사고시각이 아니며 점수는 사고 확률이 아니다. 공식 F1·사고 탐지 성능·실시간 운용을 입증하는 영상으로 설명하지 않는다. 보고서/문서 본문은 수정하지 않았다.
