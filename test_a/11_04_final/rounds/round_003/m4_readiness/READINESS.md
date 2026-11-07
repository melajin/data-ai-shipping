# M4 준비 조사 — 2026-11-05 KST

R0 계산 종료 후 16:34:43–16:37:49 UTC경 알려진 경로만 조사했다. 정확한 종료 시각과 환경은 `readiness.json`에 있다. 신규 설치·모델 다운로드·원모델 추론·학습은 0회다.

**지정 체크포인트는 로컬에 있다.** `C:/Users/dlehs/.cache/huggingface/hub/models--jingang--TabICL/snapshots/4dcd344ece2c00be9e831fdd35bed57b5ad83e19/tabicl-classifier-v2-20260212.ckpt`, 110,368,038 bytes, SHA256 `bdc7dbd5e4ff21f8f0456fcf90c6b7cdf72dbea960f2d05b19bec19f9b3d4ed0`를 직접 확인했다. 파일을 모델로 로드하거나 추론하지는 않았다. 캐시를 수정하지 않았다.

현재 호스트의 Win32_VideoController는 AMD Radeon 780M Graphics를 보고했다. nvidia-smi는 PATH에서 발견되지 않았다. NVIDIA CUDA 실행 환경을 확인하지 못했으며 과거 RTX3060Ti 설명을 이 호스트 증거로 사용하지 않는다. WMI AdapterRAM 표시는 GPU 추론 가능 용량의 실측이 아니다.

시스템 Python3.13.3, round002 Python3.13.3, Codex 번들 Python3.12.14 세 환경의 설치 metadata를 조회했다. 모두 Torch/TabICL이 없었다. 다른 모든 개인 환경에 패키지가 없다는 전수 조사는 아니다. Python3.12.14 실행 파일은 `C:/Users/dlehs/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`다. 이를 읽기 전용 기반으로 작업루트 전용 venv를 만드는 후속이 가능하다.

공유 package의 여섯 fold model.pkl은 해당 경로에서 발견되지 않았다. saved preprocessor는 kind=`fit_median_and_raw_missing_flags`, median 길이156이며, 지문이 일치하는 코드도 결측 표시를 덧붙인다. 따라서 변환 후312열이라는 해석에 코드·저장상태 근거가 있다. run_settings의 no-missing-flags 설명과는 충돌한다. 실제 특징행·FIT 입력 순서·내부 클래스 permutation·원출력 재추론은 검증하지 않았으므로 정확 재현 완료로 쓰지 않는다.

`data/F156_train.csv`, `train_labels.csv`와 components의 train 파일들은 전체7372 행/holdout을 포함할 수 있다. 파일명·크기만 확인했으며 읽지 않았다. development_roles_long에는 개발5897척만 있지만 이 명부만으로 원모델의 FIT 입력 순서가 자동 복구되지는 않는다.

다음은 M4 학습이 아니라 **전용 CPU 환경 확보 → 체크포인트 로드/극소 합성 smoke → 개발 전용 입력 재현 경로 감사**다. 원출력 재현 이후 M4-a/b의 무변경·gradient·병합/reload, 마지막으로 한fold INNER pilot 순서를 유지한다. CPU 성능이나 원GPU 확률의 일치를 보장하지 않는다.

공식 배포 근거: [TabICL2.2.0 PyPI metadata](https://pypi.org/pypi/tabicl/2.2.0/json)는 Python>=3.10, Torch>=2.2를 명시한다. [PyTorch 과거 버전 안내](https://pytorch.org/get-started/previous-versions/)의2.6.0 CPU wheel 경로를 사용할 수 있다. 이번에는 공개 metadata만 읽었고 설치하지 않았다. PyPI 응답 원본·wheel SHA256은 `tabicl_2_2_0_pypi.json`에 저장했다. [공식 구현](https://github.com/soda-inria/tabicl)은 버전을 고정해 후속에서 확인한다.

초기 inline Python metadata probe는 PowerShell 인용 처리 때문에 SyntaxError가 났다. `probe_runtime.py` 파일로 옮긴 후 세 환경에서 종료코드0으로 확인했다. 이 실패는 패키지 실행 실패나 모델 오류가 아니며, 모델 실험 재시도도 아니다.
