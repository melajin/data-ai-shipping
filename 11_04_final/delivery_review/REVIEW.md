# Delivery package review — rounds 001–002

Status: **staging package reviewed; final ZIP CRC/SHA check pending with the package owner.** Review path: `deliverables/rounds_001_002_team_package`. This review covers the assembled staging directory and the verifier evidence there. It does not access raw data, holdout rows, or personal directories. No experiment or training was started.

## Report accuracy

The combined Markdown and HTML report, README, and source round reports agree on the central results and their limits:

- Round 001 saved five-seed replay: 3,497/5,897 correct, micro-F1 0.5930133966, macro-F1 0.5252719739; no new training. The exploratory 0.5933526 result is not adopted.
- Round 001 parser sensitivity is described with the right boundary: cached T5 matches default pandas parsing; round-trip parsing changes some probabilities but not OUTER argmax or correct count. Dynamic T5 parity and historical `.59183` attribution remain unresolved.
- Round 002 same-round seed-42 LightGBM baseline: 3,476/5,897 (micro-F1 0.5894522639); CatBoost: 3,424 (0.5806342208); fold-local blend: 3,474 (0.5891131084). Neither candidate is adopted. The report identifies previously exposed development OUTER data, and does not treat its bootstrap intervals as independent evidence.
- Round 001’s five-seed replay and round 002’s seed-42 refit are not presented as a direct causal comparison. The report also preserves the API failure/recovery history, six successful model-fit accounting, and effective pause after round 002.

I checked the HTML’s visible source for the same key result strings and pause language: 9 tables, 21 headings, and no Unicode replacement characters. The report does not claim hardware validation, official scoring, independent validation, or learner understanding.

## Package content and boundaries

The package contains 198 manifest-listed immutable files totaling 200,364,097 bytes. Coverage includes both original reports and reviews; round 001 execution artifacts; round 002 code/configuration, six models, probabilities, logs and review; all 15 saved round 001 baseline models and seed predictions; the three fixed development X304 NPZs and three T5 CSVs; provenance/environment records; and pause/status/next-step and algorithm-idea handoff documents.

I compared the manifest path set with staging files, excluding the documented `MANIFEST.json`, `validation/`, and `delivery_review/` exclusions: 198 eligible files, 0 missing, 0 unlisted, and 0 malformed SHA-256 values. No `..` or absolute archive paths were found. `python -B reproduce/verify_package.py --hash-only` passed with 198 files verified. The manifest intentionally excludes itself and the two generated review/validation directories; the full-ZIP sidecar hash is still required for archive integrity.

The package contains no raw data or individual holdout features, labels, or predictions. No venv, site-packages, wheel, bytecode, cache/temp directory, or suspiciously named secret/credential file was found. The source/path audit is not a comprehensive secret-content audit. Historical source/config/logs retain absolute paths, and the README discloses that. The original requirements freeze includes a local wheel URI and is clearly marked as unsuitable for direct installation.

No automatic round-003 launcher or `Start-NextSession.ps1` is included. Historical, manually invoked round-002 launcher wrappers and runner scripts are preserved as execution evidence; the README explicitly says not to execute original run code. They do not trigger a next session automatically.

At the time of this review, the README-listed `delivery_review/` directory had not yet been copied into staging. Its contents are outside the manifest by design; include these review files before making the ZIP. `validation/` contains `model_replay.json`, `model_replay.stderr.txt`, and `VALIDATION_NOTES.md`.

## Portable verifier and replay evidence

`reproduce/verify_package.py` uses package-relative paths, resolves each manifest target and checks it stays under the package root, then verifies each file size and SHA-256. `--hash-only` uses only the Python standard library. The full verifier reads NPZ files with `allow_pickle=False`, checks input/config hashes, OUTER ID/label alignment, metrics, selected alphas and blend arithmetic. `--models` reloads and replays models; the script contains no fit/train call or external-data path. It requires pandas 2.2.3 for the round 001 CSV-default-parser comparison and asserts that version explicitly.

The first package replay under round 002’s pandas 3.1.0 failed at the default-CSV equality assertion before model prediction. The packaging requirements were pinned to pandas 2.2.3; this was documented as a verification-environment correction, not an experiment change. The final replay used the existing base Python 3.13.3 environment with pandas 2.2.3, NumPy 2.2.5, LightGBM 4.7.0 and CatBoost 1.2.10 added from the existing round 002 environment. It was not a clean-machine install test.

`validation/model_replay.json` records **PASS**: 198 manifest files checked; 21 model replays had max probability delta 0; saved metrics and frozen alphas `[1.0, 0.0, 0.5]` were reproduced; default-reader T5 matched X304; round-trip OUTER ensemble max probability deltas by fold were 0.0003664421, 0.0009529510, and 0.0012018579, with zero argmax changes. Bootstrap intervals were not recalculated. The package owner separately confirmed all three T5 CSVs have 5,897 unique IDs.

## Remaining limits and handoff

Round 001/002 results remain development computations and saved-model replay, not independent performance evidence. Dynamic T5 parity, historical `.59183` attribution, and independent evaluation status remain unresolved. No actual hardware measurement is included. The current-user pause is represented in `project_state/USER_PAUSE.md` and status; round 003 is a written future plan only.

The requested reviewer configuration was `gpt-6-luna` at `xhigh`. Current-session host/runtime evidence was unavailable, so actual model/effort execution is unverified. The package’s `model_runtime_evidence.json` concerns prior turns and is not evidence for this review.

Final archive CRC/SHA and ZIP extraction integrity were not checked here; the package owner is checking those separately.
