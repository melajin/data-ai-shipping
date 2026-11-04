"""Offline dashboard for the explicitly synthetic sample experiment.

The HTML carries its data once, as inert JSON. User-provided text never enters
HTML markup or executable JavaScript. It does not calculate speed or connect
separate trajectory parts.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


def _json_ready(value: Any) -> Any:
    """Keep JSON data strict; unavailable numeric results are represented by null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _safe_json(value: Any) -> str:
    serialized = json.dumps(_json_ready(value), ensure_ascii=False, allow_nan=False,
                            separators=(",", ":"))
    # A JSON script element is still parsed by the HTML parser. Escape its end
    # marker and characters that may be interpreted in embedded/script contexts.
    for character, escaped in (("&", "\\u0026"), ("<", "\\u003c"),
                               (">", "\\u003e"), ("\u2028", "\\u2028"),
                               ("\u2029", "\\u2029")):
        serialized = serialized.replace(character, escaped)
    return serialized


def write_dashboard(report: Mapping[str, Any] | None,
                    predictions: Sequence[Mapping[str, Any]] | None,
                    output_path: str | Path) -> Path:
    """Write a self-contained UTF-8 HTML dashboard and return its path.

    Optional/missing report fields and an empty prediction collection remain
    viewable. Path authorization is the caller's responsibility. This function
    only creates the requested parent directory and writes the requested file.
    """
    if report is not None and not isinstance(report, Mapping):
        raise TypeError("report must be a mapping or None")
    if predictions is not None and (not isinstance(predictions, Sequence)
                                    or isinstance(predictions, (str, bytes))):
        raise TypeError("predictions must be a sequence or None")
    payload = _safe_json({"report": report or {}, "predictions": predictions or []})
    html = _HTML.replace("__DASHBOARD_PAYLOAD__", payload)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path


_HTML = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light">
<title>항적 모델 실험실 · 합성 샘플</title>
<style>
:root{--ink:#142d46;--muted:#647587;--teal:#087f8c;--blue:#3d67c7;--purple:#8255b4;--line:#dfe7ed;--page:#f3f6f8;--amber:#9b6517;--red:#b14044;--radius:18px}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font-family:"Segoe UI","Malgun Gothic",system-ui,sans-serif;font-size:14px;line-height:1.6}button,input,select{font:inherit}button,select{cursor:pointer}button:focus-visible,input:focus-visible,select:focus-visible,summary:focus-visible{outline:3px solid #60bcc6;outline-offset:3px}button{border:1px solid var(--line);border-radius:9px;background:white;color:var(--ink);padding:8px 13px}button:hover{border-color:var(--teal)}button:disabled{opacity:.4;cursor:default}a{color:var(--teal)}h1,h2,h3,p{margin:0}h1{font-size:clamp(26px,3.4vw,40px);letter-spacing:-1.5px;line-height:1.25}h2{font-size:18px;letter-spacing:-.4px}h3{font-size:14px}canvas{display:block;width:100%;height:370px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}th,td{padding:11px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}th{font-size:12px;color:var(--muted);font-weight:600;background:#f8fafb}tbody tr:last-child td{border-bottom:0}td.numeric,th.numeric{text-align:right}select,input{width:100%;padding:10px 12px;border:1px solid #cfdbe3;border-radius:10px;background:#fff;color:var(--ink);min-width:0}input::placeholder{color:#8796a4}label{display:block;font-size:12px;font-weight:600;color:var(--muted);margin-bottom:5px}small,.small{font-size:12px}.muted{color:var(--muted)}.mono{font-family:Consolas,monospace}.wrap{max-width:1510px;margin:auto;padding:36px 36px 42px}.eyebrow{font-size:11px;font-weight:750;letter-spacing:2px;color:var(--teal);margin-bottom:11px}.header{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;margin-bottom:22px}.subtitle{color:var(--muted);margin-top:10px;max-width:810px}.header-tags{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap;max-width:350px}.tag{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;padding:5px 10px;background:white;font-size:11px;white-space:nowrap}.tag.teal{color:var(--teal);border-color:#b9dfe1;background:#edf9f9}.tag.amber{color:var(--amber);border-color:#e8d8b4;background:#fff8e7}.tag.red{color:var(--red);border-color:#e8c0c0;background:#fff1f1}.banner{border:1px solid #cde1e5;background:#eaf5f6;border-radius:12px;padding:13px 17px;display:flex;gap:12px;margin-bottom:22px;color:#365766}.banner strong{color:var(--teal);white-space:nowrap}.cards{display:grid;grid-template-columns:1.1fr 1fr 1fr 1fr;gap:15px;margin-bottom:22px}.card,.panel{background:white;border:1px solid var(--line);border-radius:var(--radius);box-shadow:0 2px 5px #15394b03}.card{padding:20px 22px;min-width:0}.card-label{font-size:12px;color:var(--muted);margin-bottom:8px}.card-value{font-size:31px;font-weight:650;letter-spacing:-1px;line-height:1.25;overflow-wrap:anywhere}.card-value.model{font-size:23px;letter-spacing:-.6px}.card-note{color:var(--muted);font-size:12px;margin-top:9px}.section-label{font-size:11px;color:var(--muted);letter-spacing:1.6px;font-weight:700;margin:29px 0 12px}.workspace{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,1fr);gap:18px;align-items:start}.panel{padding:22px;min-width:0}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;margin-bottom:17px}.panel-head p{font-size:12px;color:var(--muted);margin-top:4px}.filters{display:grid;grid-template-columns:150px 150px 1fr;gap:10px;margin-bottom:12px}.picker{display:grid;grid-template-columns:1fr auto auto;gap:8px;align-items:end}.picker-note{margin:7px 0 15px;font-size:12px;color:var(--muted)}.sample-meta{display:flex;flex-wrap:wrap;gap:7px;margin:13px 0}.sample-title{font-size:16px;font-weight:650;overflow-wrap:anywhere}.canvas-box{border:1px solid var(--line);border-radius:12px;background:#fbfdfe;overflow:hidden}.chart-note{font-size:12px;color:var(--muted);margin-top:10px}.legend{display:flex;flex-wrap:wrap;gap:8px 15px;margin:12px 0 5px}.legend-item{display:inline-flex;gap:6px;align-items:center;font-size:12px;color:var(--muted)}.dot{width:9px;height:9px;display:inline-block;border-radius:50%;flex:none}.end-symbol{width:8px;height:8px;background:#648294;transform:rotate(45deg);display:inline-block}.start-symbol{width:9px;height:9px;border:2px solid #648294;border-radius:50%;display:inline-block}.table-scroll{overflow:auto;border:1px solid var(--line);border-radius:10px;margin-top:15px}.right-stack{display:grid;gap:18px}.prediction{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:19px}.prediction>div{background:#f5f8fa;padding:12px;border-radius:10px;min-width:0}.prediction strong{display:block;font-size:17px;overflow-wrap:anywhere}.prob-row{display:grid;grid-template-columns:100px minmax(20px,1fr) 58px;gap:10px;align-items:center;margin:13px 0;font-size:12px}.prob-track{height:10px;border-radius:6px;background:#edf2f5;overflow:hidden}.prob-bar{height:100%;border-radius:6px}.prob-value{text-align:right;font-variant-numeric:tabular-nums}.anomaly-score{font-size:28px;font-weight:650;letter-spacing:-.8px}.anomaly-status{display:flex;justify-content:space-between;align-items:center;gap:8px}.threshold{border-top:1px solid var(--line);margin-top:14px;padding-top:13px;font-size:12px}.callout{background:#f3f7fa;border-radius:9px;padding:11px 12px;margin-top:13px;font-size:12px;color:#516d81}.callout.warn{background:#fff7e8;color:#835c24}.empty{padding:28px 20px;text-align:center;color:var(--muted);font-size:13px}.reason{font-size:12px;color:var(--amber);margin-top:9px;overflow-wrap:anywhere}.feature-table td{padding:8px 10px;font-size:12px}.feature-table td:first-child{max-width:260px;white-space:normal;overflow-wrap:anywhere}.details-grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.loss-canvas{height:285px}.select-small{width:auto;min-width:110px;padding:7px 10px;font-size:12px}.confusion-table th,.confusion-table td{text-align:center;white-space:normal;padding:12px 9px}.confusion-table td{font-weight:650}.selected-row{background:#edf8f8}.selected-mark{color:var(--teal);margin-left:8px;font-size:11px}.insights{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:18px}.insight-value{font-size:24px;font-weight:650;letter-spacing:-.5px;margin:10px 0 5px}.limitations{margin:10px 0 0;padding-left:19px;font-size:13px;color:var(--muted)}.limitations li{margin:5px 0}.footer{display:flex;gap:15px;justify-content:space-between;color:var(--muted);font-size:11px;border-top:1px solid var(--line);margin-top:26px;padding-top:17px}.footer div{max-width:850px}details{margin-top:15px}summary{cursor:pointer;color:var(--teal);font-size:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f9fa;padding:15px;border-radius:8px;font-size:11px;max-height:300px;overflow:auto}.error{border:1px solid #e5b6b6;background:#fff2f2;color:var(--red);padding:16px;border-radius:12px;margin:15px 0}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}[hidden]{display:none!important}
@media(max-width:1100px){.wrap{padding:25px 22px}.workspace{grid-template-columns:minmax(0,1.4fr) minmax(290px,1fr)}.filters{grid-template-columns:1fr 1fr}.search-filter{grid-column:1/-1}.card{padding:17px}.card-value{font-size:27px}}
@media(max-width:850px){.workspace,.details-grid,.insights{grid-template-columns:1fr}.right-stack{grid-template-columns:1fr 1fr}.features-panel{grid-column:1/-1}.header{display:block}.header-tags{justify-content:flex-start;max-width:none;margin-top:15px}.cards{grid-template-columns:1fr 1fr}.banner{display:block}.banner strong{display:block;margin-bottom:4px}.panel{padding:18px}.footer{display:block}.footer>span{display:block;margin-top:8px}}
@media(max-width:560px){.wrap{padding:20px 12px}.right-stack{grid-template-columns:1fr}.features-panel{grid-column:auto}.cards{gap:10px}.card{padding:15px}.card-value{font-size:26px}.card-value.model{font-size:18px}.filters{grid-template-columns:1fr 1fr}.picker{grid-template-columns:1fr auto auto}.picker button{padding:10px}.panel-head{gap:8px}canvas{height:330px}.loss-canvas{height:260px}.subtitle{font-size:13px}.prediction strong{font-size:15px}.prob-row{grid-template-columns:87px 1fr 51px}.footer{font-size:10px}}
</style>
</head>
<body>
<main class="wrap">
  <header class="header">
    <div><div class="eyebrow">TRAJECTORY MODEL LAB / S0</div><h1>항적 모델 실험실</h1><p class="subtitle">경로의 기하 특징으로 합성 유형을 분류하고, 모델의 예측 근거와 분포 변화에 대한 반응을 살펴봅니다.</p></div>
    <div class="header-tags"><span class="tag teal">합성 실험 · SYNTHETIC</span><span class="tag">지역 XY · m</span><span class="tag" id="seed-tag">시드 미확인</span><span class="tag">오프라인 실행</span></div>
  </header>
  <div class="banner"><strong>실제 자료 평가 전</strong><span id="source-note">정답은 생성 경로 유형입니다. 공식 조업 분류·사고 판정 성능이 아니며, 좌표는 실제 지도가 아닙니다.</span></div>
  <noscript><div class="error">이 HTML의 필터와 그래프를 보려면 브라우저의 JavaScript를 활성화하세요. 외부 네트워크 연결은 필요하지 않습니다.</div></noscript>
  <div class="error" id="dashboard-error" role="alert" hidden></div>
  <section class="cards" aria-label="핵심 결과">
    <article class="card"><div class="card-label">검증 분할로 선택한 모델</div><div class="card-value model" id="model-name">미확인</div><div class="card-note" id="model-note">후보·epoch 선택: validation</div></article>
    <article class="card"><div class="card-label">TEST · 정확도</div><div class="card-value" id="test-accuracy">—</div><div class="card-note" id="test-count">유효 평가 표본 미확인</div></article>
    <article class="card"><div class="card-label">TEST · Macro F1</div><div class="card-value" id="test-f1">—</div><div class="card-note">클래스별 F1의 동일 가중 평균</div></article>
    <article class="card"><div class="card-label">STRESS − TEST · 정확도 변화</div><div class="card-value" id="shift-delta">—</div><div class="card-note" id="shift-note">사전 고정된 합성 조건 변화</div></article>
  </section>
  <div class="section-label">01 / 표본과 예측 근거</div>
  <section class="workspace">
    <article class="panel">
      <div class="panel-head"><div><h2>부분선 경로 탐색</h2><p>부분선의 경계와 예측 결과를 함께 확인합니다.</p></div><span class="tag teal" id="sample-count">0개 표본</span></div>
      <div class="filters">
        <div><label for="filter-split">데이터 분할</label><select id="filter-split"></select></div>
        <div><label for="filter-class">합성 정답 유형</label><select id="filter-class"></select></div>
        <div class="search-filter"><label for="filter-search">표본 / 선박 ID 검색</label><input type="search" id="filter-search" placeholder="ID 일부를 입력" autocomplete="off"></div>
      </div>
      <div class="picker"><div><label for="sample-picker">표본 선택</label><select id="sample-picker" aria-describedby="picker-note"></select></div><button id="previous-sample" type="button" aria-label="이전 표본">←</button><button id="next-sample" type="button" aria-label="다음 표본">→</button></div>
      <p class="picker-note" id="picker-note" aria-live="polite">표본을 불러오는 중입니다.</p>
      <div class="sample-title" id="sample-title">선택한 표본 없음</div><div class="sample-meta" id="sample-meta"></div>
      <div class="canvas-box"><canvas id="track-canvas" role="img" aria-label="선택한 표본의 지역 XY 부분선 경로. 각 부분선은 독립적으로 그려집니다."></canvas></div>
      <div class="legend" id="part-legend"></div>
      <div class="legend"><span class="legend-item"><span class="start-symbol"></span>부분선 시작</span><span class="legend-item"><span class="end-symbol"></span>부분선 끝</span></div>
      <p class="chart-note">X와 Y 축은 같은 축척의 미터 단위입니다. 단절된 부분선은 연결하지 않습니다. 실제 속력·가속도는 계산하지 않습니다.</p>
      <div class="table-scroll"><table aria-label="부분선별 기하 계산"><thead><tr><th>부분선</th><th class="numeric">점 수</th><th class="numeric">길이 · m</th><th class="numeric">변위 · m</th><th class="numeric">직선성</th></tr></thead><tbody id="part-table"></tbody></table></div>
    </article>
    <div class="right-stack">
      <article class="panel"><div class="panel-head"><div><h2>유형 분류</h2><p>합성 정답과 보정된 모델 확률</p></div><span class="tag" id="prediction-status">미확인</span></div><div class="prediction"><div><span class="small muted">합성 정답</span><strong id="true-label">—</strong></div><div><span class="small muted">모델 예측</span><strong id="predicted-label">—</strong></div></div><div id="probabilities"></div><p class="reason" id="abstention-reason" hidden></p><p class="chart-note" id="temperature-note">온도 보정은 calibration 분할에서 수행합니다.</p></article>
      <article class="panel"><div class="panel-head"><div><h2>학습 분포로부터의 거리</h2><p>최소 제곱 Mahalanobis 점수</p></div></div><div class="anomaly-status"><div class="anomaly-score" id="anomaly-score">—</div><span class="tag" id="anomaly-flag">판단 불가</span></div><div class="threshold" id="anomaly-threshold">검증 분할 임계값 미확인</div><p class="chart-note" id="anomaly-distribution"></p><div class="callout warn">점수와 임계값 초과 여부는 <strong>사고 확률이나 사고 판정이 아닙니다.</strong> 생성 조건 변화와 입력 차이에도 높아질 수 있습니다.</div></article>
      <article class="panel features-panel"><div class="panel-head"><div><h2>입력 특징</h2><p>경로 기하만 사용 · 결측은 미확인으로 표시</p></div></div><div class="table-scroll" style="margin-top:0"><table class="feature-table" aria-label="특징값과 단위"><thead><tr><th>특징</th><th class="numeric">값</th><th>단위</th></tr></thead><tbody id="feature-table"></tbody></table></div><details><summary>관측 품질 정보</summary><pre id="quality-text">미확인</pre></details></article>
    </div>
  </section>
  <div class="section-label">02 / 학습과 평가</div>
  <section class="details-grid">
    <article class="panel"><div class="panel-head"><div><h2>혼동행렬</h2><p>행: 합성 정답 · 열: 모델 예측 · 유보 제외</p></div><div><label class="visually-hidden" for="confusion-split">혼동행렬 분할</label><select id="confusion-split" class="select-small"><option value="test">TEST</option><option value="stress">STRESS</option></select></div></div><div id="confusion-matrix"></div><p class="chart-note" id="confusion-note"></p></article>
    <article class="panel"><div class="panel-head"><div><h2>선택 모델의 학습 곡선</h2><p id="loss-caption">Train / validation NLL · 낮을수록 좋음</p></div><span class="tag" id="epoch-tag">epoch 미확인</span></div><div class="canvas-box"><canvas class="loss-canvas" id="loss-canvas" role="img" aria-label="선택 모델의 train 및 validation NLL 학습 곡선"></canvas></div><div class="legend"><span class="legend-item"><span class="dot" style="background:var(--teal)"></span>Train NLL</span><span class="legend-item"><span class="dot" style="background:var(--blue)"></span>Validation NLL</span></div><p class="chart-note">Validation NLL이 가장 낮은 checkpoint를 복원합니다. 표시된 곡선의 마지막 epoch와 선택 epoch는 다를 수 있습니다.</p></article>
  </section>
  <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>분할별 성능</h2><p>평가 가능한 정답·예측만 사용합니다. 빈 평가의 지표는 미확인으로 표시합니다.</p></div><span class="tag">Test로 후보 재선택 없음</span></div><div class="table-scroll" style="margin-top:0"><table aria-label="분할별 성능"><thead><tr><th>분할</th><th class="numeric">표본</th><th class="numeric">선박 그룹</th><th class="numeric">유보</th><th class="numeric">정확도</th><th class="numeric">Macro F1</th><th class="numeric">NLL</th><th class="numeric">Brier</th></tr></thead><tbody id="metrics-table"></tbody></table></div><p class="chart-note" id="baseline-note"></p></section>
  <section class="panel" style="margin-top:18px"><div class="panel-head"><div><h2>고정 후보 비교</h2><p>Validation 기준 비교 · 최종 평가와 온도 보정 전 지표</p></div></div><div class="table-scroll" style="margin-top:0"><table aria-label="분류 모델 후보 비교"><thead><tr><th>모델</th><th class="numeric">은닉 폭</th><th class="numeric">L2</th><th class="numeric">선택 epoch</th><th class="numeric">Validation 정확도</th><th class="numeric">Macro F1</th><th class="numeric">NLL</th></tr></thead><tbody id="candidate-table"></tbody></table></div></section>
  <section class="insights">
    <article class="panel"><h2>학습과 최종 평가의 차이</h2><div class="insight-value" id="gap-value">—</div><p class="muted small" id="gap-note">Train − test 정확도 차이 · 유효 평가 결과가 필요합니다.</p><div class="callout">학습자료 성능은 새로운 선박에 대한 성능을 보장하지 않습니다. 분할별 선박 그룹을 분리해 같은 선박의 정보가 평가에 섞이지 않도록 합니다.</div></article>
    <article class="panel"><h2>합성 조건 변화의 한계</h2><div class="insight-value" id="stress-value">—</div><p class="muted small">Stress 정확도 · 사전 고정 배율 / 잡음 / 누락 / 단절 변화</p><div class="callout">Test와 stress는 선박 그룹이 다르고 네 조건이 함께 변합니다. 성능 차이 전체를 교란의 순수 효과나 과적합의 증거로 해석할 수 없습니다. 실제 해역·장비·조업 라벨의 일반화와 사고 탐지 성능은 별도 검증이 필요합니다.</div></article>
  </section>
  <section class="panel" style="margin-top:18px"><h2>해석과 학습 점검</h2><ul class="limitations" id="limitations-list"></ul><div class="callout">설명해 보기: 어떤 기하 특징이 유형을 나누는가? 부분선 경계를 지우면 무엇이 달라지는가? 조건 변화에서 확률과 분포 거리의 반응이 서로 다른 이유는 무엇인가?</div><details><summary>실행·분할 감사 정보</summary><pre id="audit-text">미확인</pre></details></section>
  <footer class="footer"><div>이 화면은 합성 샘플의 코드 실행·계산 결과를 탐색합니다. 실제 데이터 평가나 장치 실험 결과로 해석하지 않습니다. 외부 지도, 폰트, 라이브러리와 네트워크 요청을 사용하지 않습니다.</div><span id="runtime-note">독립 실행 HTML · S0</span></footer>
</main>
<script id="dashboard-data" type="application/json">__DASHBOARD_PAYLOAD__</script>
<script>
"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const object = value => value && typeof value === "object" && !Array.isArray(value) ? value : {};
  const array = value => Array.isArray(value) ? value : [];
  const number = value => typeof value === "number" && Number.isFinite(value) ? value : null;
  const string = value => value === null || value === undefined ? "미확인" : String(value);
  const format = (value, digits = 3) => number(value) === null ? "미확인" : value.toLocaleString("ko-KR", {maximumFractionDigits:digits});
  const percent = value => number(value) === null ? "—" : (value * 100).toFixed(1) + "%";
  const delta = value => number(value) === null ? "—" : (value > 0 ? "+" : "") + (value * 100).toFixed(1) + " pp";
  const set = (id, value) => { byId(id).textContent = string(value); };
  const element = (tag, text, className) => { const node = document.createElement(tag); if (text !== undefined) node.textContent = string(text); if (className) node.className = className; return node; };
  const cell = (row, value, numeric = false) => { const node = element("td", value, numeric ? "numeric" : ""); row.appendChild(node); return node; };
  const emptyRow = (body, columns, message) => { const row = element("tr"); const node = cell(row, message); node.colSpan = columns; node.className = "empty"; body.appendChild(row); };
  const addOption = (select, value, text) => { const option = element("option", text); option.value = String(value); select.appendChild(option); };
  const colors = ["#087f8c", "#3d67c7", "#8255b4", "#c17825", "#bf5465", "#488260"];
  const splitNames = {train:"TRAIN · 학습", validation:"VALIDATION · 선택", calibration:"CALIBRATION · 보정", test:"TEST · 최종 평가", stress:"STRESS · 조건 변화"};
  const classLabels = {straight:"직진형 · straight", sweep:"굴곡형 · sweep", turn:"회전형 · turn"};
  const featureLabels = {log1p_total_length_m:"로그 변환 총 길이", mean_part_straightness:"부분선 평균 직선성", mean_abs_turn_rad:"평균 절대 회전각", turn_direction_concentration:"회전 방향 집중도", std_turn_rad:"회전각 표준편차", max_abs_turn_rad:"최대 절대 회전각", mean_part_spread_ratio:"부분선 평균 퍼짐 비율", mean_part_chord_deviation_ratio:"부분선 평균 현 이탈 비율"};
  let report = {}, records = [], names = [], selectedCandidate = {}, selectedName = "미확인", filtered = [], current = null;

  function className(label) {
    if (label === null || label === undefined) return "미확인";
    const index = number(label);
    const name = index !== null && names[index] !== undefined ? string(names[index]) : null;
    return name === null ? "유형 " + string(label) : Object.hasOwn(classLabels,name) ? classLabels[name] : name;
  }
  function metrics(split) { return object(object(report.metrics)[split]); }
  function metricDifference(left, right) { const a = number(left), b = number(right); return a === null || b === null ? null : a-b; }
  function supportCount(metric) { const values = array(metric.support).map(number).filter(v => v !== null); return values.length ? values.reduce((a,b) => a+b, 0) : null; }

  function renderSummary() {
    const selection = report.selected_model;
    selectedName = typeof selection === "string" ? selection : string(object(selection).name);
    selectedCandidate = array(report.candidates).map(object).find(candidate => candidate.name === selectedName) || object(selection);
    const test = metrics("test"), stress = metrics("stress");
    set("model-name", selectedName);
    set("model-note", "Validation으로 선택 · 온도 T=" + format(report.temperature));
    set("seed-tag", "시드 " + string(report.seed));
    set("test-accuracy", percent(test.accuracy)); set("test-f1", percent(test.macro_f1));
    const interval=object(object(test.ci95).accuracy);
    set("test-count", "유효 정답 " + format(supportCount(test), 0) + "개" + (number(interval.low)!==null&&number(interval.high)!==null ? " · 95% CI " + percent(interval.low) + "–" + percent(interval.high) : " · 평가용 선박 분리"));
    set("shift-delta", delta(metricDifference(stress.accuracy, test.accuracy)));
    set("shift-note", "Stress " + percent(stress.accuracy) + " · test 대비 pp");
    set("stress-value", percent(stress.accuracy));
    set("gap-value", delta(metricDifference(metrics("train").accuracy, test.accuracy)));
    set("gap-note", "Train " + percent(metrics("train").accuracy) + " − test " + percent(test.accuracy) + " · 정확도 차이");
    set("temperature-note", "Calibration 온도 T=" + format(report.temperature) + " · 확률은 사고 확률이 아닙니다.");
    const anomaly = object(report.anomaly), threshold = number(anomaly.threshold);
    const source = anomaly.threshold_source === "validation_95_percentile" ? "Validation 점수의 95백분위" : string(anomaly.threshold_source);
    set("anomaly-threshold", "임계값 " + format(threshold) + " · " + source);
    set("anomaly-distribution", "임계값 초과 비율 · test " + percent(object(anomaly.test).flag_rate) + " / stress " + percent(object(anomaly.stress).flag_rate));
    if (report.source_type !== "synthetic") {
      set("source-note", "출처 필드: " + string(report.source_type) + ". 이 화면은 합성 실험용입니다. 결과의 출처를 확인하세요. 실제 지도·조업·사고 성능은 검증하지 않습니다.");
    }
    const runtime = object(report.runtime);
    const seconds = number(runtime.elapsed_seconds) ?? number(runtime.seconds);
    set("runtime-note", "S0 · " + string(report.schema_version) + (seconds === null ? "" : " · " + format(seconds, 2) + "초"));
  }

  function initializeFilters() {
    const splitSelect = byId("filter-split"), classSelect = byId("filter-class");
    addOption(splitSelect, "all", "전체 분할");
    const splits = [...new Set(records.map(record => string(record.split)))];
    const ordered = [...Object.keys(splitNames).filter(split => splits.includes(split)), ...splits.filter(split => !Object.hasOwn(splitNames,split))];
    ordered.forEach(split => addOption(splitSelect, split, splitNames[split] || split));
    if (splits.includes("test")) splitSelect.value = "test";
    addOption(classSelect, "all", "전체 유형");
    names.forEach((name, index) => addOption(classSelect, index, className(index)));
    addOption(classSelect, "unknown", "정답 미확인");
    [splitSelect, classSelect].forEach(control => control.addEventListener("change", filterRecords));
    byId("filter-search").addEventListener("input", filterRecords);
    byId("sample-picker").addEventListener("change", () => selectSample(Number(byId("sample-picker").value)));
    byId("previous-sample").addEventListener("click", () => selectSample(Number(byId("sample-picker").value)-1));
    byId("next-sample").addEventListener("click", () => selectSample(Number(byId("sample-picker").value)+1));
    set("sample-count", format(records.length,0) + "개 표본");
    filterRecords();
  }
  function filterRecords() {
    const split = byId("filter-split").value, label = byId("filter-class").value, search = byId("filter-search").value.trim().toLowerCase();
    const previous = current;
    filtered = records.filter(record => (split === "all" || string(record.split) === split)
      && (label === "all" || (label === "unknown" ? record.true_label === null || record.true_label === undefined : string(record.true_label) === label))
      && (!search || (string(record.sample_id) + " " + string(record.vessel_id)).toLowerCase().includes(search)));
    const picker = byId("sample-picker"); picker.replaceChildren();
    filtered.forEach((record,index) => addOption(picker,index,string(record.sample_id) + " · " + string(record.vessel_id) + " · " + className(record.true_label)));
    picker.disabled = filtered.length === 0;
    if (!filtered.length) addOption(picker, "", "조건에 맞는 표본 없음");
    const priorIndex = filtered.indexOf(previous);
    selectSample(priorIndex < 0 ? 0 : priorIndex);
  }
  function selectSample(index) {
    const position = filtered.length ? Math.max(0,Math.min(index,filtered.length-1)) : -1;
    current = position < 0 ? null : filtered[position];
    if (current) byId("sample-picker").value = String(position);
    byId("previous-sample").disabled = position <= 0;
    byId("next-sample").disabled = position < 0 || position >= filtered.length-1;
    set("picker-note", filtered.length ? format(filtered.length,0) + "개 검색 결과 · " + (position+1) + " / " + filtered.length : "표본이 없거나 필터에 맞는 표본이 없습니다. 다른 분할·유형·검색어를 선택하세요.");
    renderSample();
  }

  function renderSample() {
    const record = current || {}, status = record.status, available = Boolean(current);
    set("sample-title", available ? string(record.sample_id) : "선택한 표본 없음");
    const meta = byId("sample-meta"); meta.replaceChildren();
    if (available) ["선박 " + string(record.vessel_id), splitNames[record.split] || string(record.split), "출처 " + string(record.source_type), array(record.parts).length + "개 부분선"].forEach(text => meta.appendChild(element("span",text,"tag")));
    set("true-label", available ? className(record.true_label) : "—");
    set("predicted-label", available ? (status === "abstained" || record.predicted_label === null ? "판단 유보" : className(record.predicted_label)) : "—");
    const badge = byId("prediction-status"); badge.textContent = !available ? "미선택" : status === "abstained" ? "판단 유보" : status === "ok" ? "예측 완료" : "상태 미확인";
    badge.className = "tag" + (status === "abstained" ? " amber" : status === "ok" ? " teal" : "");
    const reason = byId("abstention-reason"); reason.hidden = !record.reason; reason.textContent = record.reason ? "사유: " + string(record.reason) : "";
    const probabilityBox = byId("probabilities"); probabilityBox.replaceChildren();
    const probabilities = array(record.probabilities);
    if (!probabilities.length) probabilityBox.appendChild(element("div", available ? "클래스 확률 없음 · 입력 또는 상태를 확인하세요." : "표본을 선택하면 클래스 확률을 표시합니다.","empty"));
    else names.forEach((name,index) => {
      const row = element("div",undefined,"prob-row"), track = element("div",undefined,"prob-track"), bar = element("div",undefined,"prob-bar");
      const value = number(probabilities[index]); bar.style.width = (value === null ? 0 : Math.max(0,Math.min(1,value))*100) + "%"; bar.style.backgroundColor = colors[index % colors.length];
      track.appendChild(bar); row.append(element("span",className(index)),track,element("span",value === null ? "미확인" : percent(value),"prob-value")); probabilityBox.appendChild(row);
    });
    set("anomaly-score", number(record.anomaly_score) === null ? "—" : format(record.anomaly_score));
    const flag = byId("anomaly-flag");
    flag.textContent = record.anomaly_flag === true ? "임계값 초과" : record.anomaly_flag === false ? "임계값 이하" : "판단 불가";
    flag.className = "tag" + (record.anomaly_flag === true ? " amber" : record.anomaly_flag === false ? " teal" : "");
    const features = byId("feature-table"); features.replaceChildren();
    const values = array(record.features), featureNames = array(report.feature_names), featureUnits = report.feature_units;
    const count = Math.max(featureNames.length, values.length);
    for (let index=0;index<count;index++) { const row=element("tr"), name=featureNames[index] ?? "feature_"+index; const unit=Array.isArray(featureUnits) ? featureUnits[index] : object(featureUnits)[name]; const featureCell=cell(row,Object.hasOwn(featureLabels,name)?featureLabels[name]:name); featureCell.title=string(name); cell(row,format(values[index]),true); cell(row,unit === "" || unit === "dimensionless" ? "무차원" : unit ?? "미확인"); features.appendChild(row); }
    if (!count) emptyRow(features,3,"특징 정보 없음");
    set("quality-text", record.quality === null || record.quality === undefined ? "미확인" : JSON.stringify(record.quality,null,2));
    const table = byId("part-table"), legend = byId("part-legend"); table.replaceChildren(); legend.replaceChildren();
    array(record.parts).forEach((part,index) => {
      const partMetric = object(array(record.part_metrics)[index]), row=element("tr");
      cell(row,"부분선 " + (index+1)); cell(row,array(part).length,true); cell(row,format(partMetric.length_m),true); cell(row,format(partMetric.displacement_m),true); cell(row,format(partMetric.straightness),true); table.appendChild(row);
      const item=element("span",undefined,"legend-item"), dot=element("span",undefined,"dot"); dot.style.backgroundColor=colors[index%colors.length]; item.append(dot,element("span","부분선 " + (index+1))); legend.appendChild(item);
    });
    if (!array(record.parts).length) emptyRow(table,5,"표시할 부분선 없음");
    drawTrack();
  }

  function prepareCanvas(id) {
    const canvas = byId(id), bounds=canvas.getBoundingClientRect(), width=Math.max(220,bounds.width), height=Math.max(200,bounds.height), ratio=Math.min(window.devicePixelRatio || 1,3);
    canvas.width=Math.round(width*ratio); canvas.height=Math.round(height*ratio);
    const ctx=canvas.getContext("2d"); if (!ctx) return null;
    ctx.setTransform(ratio,0,0,ratio,0,0); ctx.clearRect(0,0,width,height); ctx.font="11px 'Segoe UI', 'Malgun Gothic', sans-serif"; return {ctx,width,height};
  }
  function chartEmpty(chart,message) { if (!chart) return; const {ctx,width,height}=chart; ctx.fillStyle="#647587";ctx.textAlign="center";ctx.fillText(message,width/2,height/2); }
  function tickStep(range,count=5) { const raw=range/count, power=Math.pow(10,Math.floor(Math.log10(raw))), ratio=raw/power; return (ratio<=1?1:ratio<=2?2:ratio<=5?5:10)*power; }
  function ticks(min,max,count=5) { const step=tickStep(max-min,count), result=[]; for(let value=Math.ceil(min/step)*step;value<=max+step*1e-7&&result.length<30;value+=step) result.push(Math.abs(value)<step*1e-7 ? 0 : value); return result; }
  function tickText(value) { return value.toLocaleString("ko-KR",{maximumFractionDigits:3}); }
  function validPoint(point) { return Array.isArray(point) && number(point[0]) !== null && number(point[1]) !== null; }
  function drawTrack() {
    const chart=prepareCanvas("track-canvas"); if(!chart)return;
    const parts=array(object(current).parts), points=parts.flatMap(part=>array(part).filter(validPoint));
    if(!points.length){chartEmpty(chart,"표시할 유효 XY 좌표가 없습니다.");return;}
    const {ctx,width,height}=chart, margin={left:67,right:27,top:26,bottom:54}, pw=width-margin.left-margin.right, ph=height-margin.top-margin.bottom;
    let minX=Infinity,maxX=-Infinity,minY=Infinity,maxY=-Infinity;
    points.forEach(point=>{minX=Math.min(minX,point[0]);maxX=Math.max(maxX,point[0]);minY=Math.min(minY,point[1]);maxY=Math.max(maxY,point[1]);});
    const rangeX=Math.max(maxX-minX,1),rangeY=Math.max(maxY-minY,1),scale=Math.min(pw/(rangeX*1.18),ph/(rangeY*1.18));
    const centerX=(minX+maxX)/2,centerY=(minY+maxY)/2, worldLeft=centerX-pw/(2*scale),worldRight=centerX+pw/(2*scale),worldBottom=centerY-ph/(2*scale),worldTop=centerY+ph/(2*scale);
    const x=value=>margin.left+(value-worldLeft)*scale,y=value=>margin.top+(worldTop-value)*scale;
    ctx.lineWidth=1;ctx.textAlign="center";ctx.fillStyle="#7b8d9a";
    ticks(worldLeft,worldRight,Math.max(3,Math.floor(pw/100))).forEach(value=>{ctx.strokeStyle="#e7eef2";ctx.beginPath();ctx.moveTo(x(value),margin.top);ctx.lineTo(x(value),margin.top+ph);ctx.stroke();ctx.fillText(tickText(value),x(value),height-30);});
    ctx.textAlign="right";
    ticks(worldBottom,worldTop,5).forEach(value=>{ctx.strokeStyle="#e7eef2";ctx.beginPath();ctx.moveTo(margin.left,y(value));ctx.lineTo(width-margin.right,y(value));ctx.stroke();ctx.fillText(tickText(value),margin.left-10,y(value)+4);});
    ctx.strokeStyle="#b8cad5";ctx.strokeRect(margin.left,margin.top,pw,ph);ctx.fillStyle="#496579";ctx.textAlign="center";ctx.fillText("지역 X · m",margin.left+pw/2,height-9);ctx.save();ctx.translate(15,margin.top+ph/2);ctx.rotate(-Math.PI/2);ctx.fillText("지역 Y · m",0,0);ctx.restore();
    ctx.save();ctx.beginPath();ctx.rect(margin.left,margin.top,pw,ph);ctx.clip();
    // Each original part starts a new path. An invalid point also breaks the
    // drawing, so a missing coordinate cannot silently bridge a gap.
    parts.forEach((part,index)=>{
      const pts=array(part),color=colors[index%colors.length];ctx.strokeStyle=color;ctx.lineWidth=2.5;ctx.lineJoin="round";ctx.lineCap="round";ctx.beginPath();let pen=false;
      pts.forEach(point=>{if(!validPoint(point)){pen=false;return;} if(pen)ctx.lineTo(x(point[0]),y(point[1]));else ctx.moveTo(x(point[0]),y(point[1]));pen=true;});ctx.stroke();
      const first=pts.find(validPoint),last=[...pts].reverse().find(validPoint); if(!first)return;
      ctx.fillStyle="white";ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();ctx.arc(x(first[0]),y(first[1]),4.5,0,Math.PI*2);ctx.fill();ctx.stroke();
      ctx.fillStyle=color;ctx.beginPath();ctx.moveTo(x(last[0]),y(last[1])-5);ctx.lineTo(x(last[0])+5,y(last[1]));ctx.lineTo(x(last[0]),y(last[1])+5);ctx.lineTo(x(last[0])-5,y(last[1]));ctx.closePath();ctx.fill();
    });ctx.restore();
  }

  function renderConfusion() {
    const split=byId("confusion-split").value, metric=metrics(split), matrix=array(metric.confusion), container=byId("confusion-matrix");container.replaceChildren();
    if(!matrix.length){container.appendChild(element("div","혼동행렬 정보가 없습니다.","empty"));set("confusion-note","유효 평가 결과를 확인하세요.");return;}
    const table=element("table",undefined,"confusion-table"), head=element("thead"), header=element("tr"), corner=element("th","정답 ↓ / 예측 →");corner.scope="col";header.appendChild(corner);
    const size=Math.max(names.length,matrix.length,...matrix.map(row=>array(row).length));
    for(let index=0;index<size;index++){const th=element("th",className(index));th.scope="col";header.appendChild(th);}head.appendChild(header);table.appendChild(head);
    const body=element("tbody"),max=Math.max(1,...matrix.flatMap(row=>array(row).map(value=>number(value)??0)));
    for(let rowIndex=0;rowIndex<size;rowIndex++){const row=element("tr"),th=element("th",className(rowIndex));th.scope="row";row.appendChild(th);for(let column=0;column<size;column++){const value=number(array(matrix[rowIndex])[column]),td=cell(row,value===null?"—":format(value,0));if(value!==null)td.style.backgroundColor="rgba(8,127,140,"+(0.04+0.30*value/max)+")";}body.appendChild(row);}table.appendChild(body);
    const scroll=element("div",undefined,"table-scroll");scroll.appendChild(table);container.appendChild(scroll);table.setAttribute("aria-label",split+" 혼동행렬");
    const support=supportCount(metric);set("confusion-note",split.toUpperCase()+" · 유효 정답 "+format(support,0)+"개 · 정확도 "+percent(metric.accuracy)+" · Macro F1 "+percent(metric.macro_f1));
  }
  function drawLoss() {
    const chart=prepareCanvas("loss-canvas");if(!chart)return;const history=array(selectedCandidate.history).map(object), points=history.filter(item=>number(item.epoch)!==null&&(number(item.train_nll)!==null||number(item.val_nll)!==null));
    set("epoch-tag","선택 epoch "+string(selectedCandidate.best_epoch));set("loss-caption",selectedName+" · Train / validation NLL");
    if(!points.length){chartEmpty(chart,"선택 모델의 학습 이력이 없습니다.");return;}
    const {ctx,width,height}=chart,m={left:58,right:22,top:22,bottom:44},pw=width-m.left-m.right,ph=height-m.top-m.bottom;
    const epochs=points.map(item=>item.epoch),values=points.flatMap(item=>[number(item.train_nll),number(item.val_nll)]).filter(value=>value!==null),minEpoch=Math.min(...epochs),maxEpoch=Math.max(minEpoch+1,...epochs),minValue=Math.min(0,...values),maxValue=Math.max(minValue+.01,...values)*1.07;
    const x=value=>m.left+(value-minEpoch)/(maxEpoch-minEpoch)*pw,y=value=>m.top+(maxValue-value)/(maxValue-minValue)*ph;
    ctx.fillStyle="#7b8d9a";ctx.textAlign="right";ctx.strokeStyle="#e7eef2";ctx.lineWidth=1;
    ticks(minValue,maxValue,4).forEach(value=>{ctx.beginPath();ctx.moveTo(m.left,y(value));ctx.lineTo(width-m.right,y(value));ctx.stroke();ctx.fillText(tickText(value),m.left-8,y(value)+4);});ctx.textAlign="center";
    ticks(minEpoch,maxEpoch,5).forEach(value=>ctx.fillText(tickText(value),x(value),height-23));ctx.fillText("Epoch",m.left+pw/2,height-6);ctx.strokeStyle="#b8cad5";ctx.strokeRect(m.left,m.top,pw,ph);
    [["train_nll",colors[0]],["val_nll",colors[1]]].forEach(([key,color])=>{ctx.strokeStyle=color;ctx.lineWidth=2;ctx.beginPath();let pen=false;points.forEach(item=>{const value=number(item[key]);if(value===null){pen=false;return;}if(pen)ctx.lineTo(x(item.epoch),y(value));else ctx.moveTo(x(item.epoch),y(value));pen=true;});ctx.stroke();});
    const best=number(selectedCandidate.best_epoch);if(best!==null&&best>=minEpoch&&best<=maxEpoch){ctx.save();ctx.setLineDash([4,4]);ctx.strokeStyle="#8a9aa6";ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x(best),m.top);ctx.lineTo(x(best),m.top+ph);ctx.stroke();ctx.restore();}
  }
  function renderTables() {
    const body=byId("metrics-table");body.replaceChildren();
    Object.keys(splitNames).forEach(split=>{const metric=metrics(split),summary=object(object(report.split_summary)[split]),row=element("tr");cell(row,splitNames[split]);cell(row,format(summary.samples,0),true);cell(row,format(summary.groups,0),true);cell(row,format(summary.abstained,0),true);cell(row,percent(metric.accuracy),true);cell(row,percent(metric.macro_f1),true);cell(row,format(metric.nll),true);cell(row,format(metric.brier),true);body.appendChild(row);});
    const baseline=object(report.majority_baseline),before=object(object(report.before_calibration).test);set("baseline-note","다수 클래스 기준선 · test 정확도 "+percent(object(baseline.test).accuracy)+" · stress 정확도 "+percent(object(baseline.stress).accuracy)+". 기준선은 train에서 정한 클래스를 사용합니다. Test NLL: 보정 전 "+format(before.nll)+" → 보정 후 "+format(metrics("test").nll)+".");
    const candidates=byId("candidate-table");candidates.replaceChildren();
    array(report.candidates).map(object).forEach(candidate=>{const row=element("tr"),metric=object(candidate.validation_metrics),name=cell(row,candidate.name);if(candidate.name===selectedName){row.className="selected-row";name.appendChild(element("span","선택","selected-mark"));}cell(row,format(candidate.hidden,0),true);cell(row,format(candidate.l2,4),true);cell(row,format(candidate.best_epoch,0),true);cell(row,percent(metric.accuracy),true);cell(row,percent(metric.macro_f1),true);cell(row,format(metric.nll),true);candidates.appendChild(row);});
    if(!array(report.candidates).length)emptyRow(candidates,7,"후보 비교 정보 없음");
    const limitations=byId("limitations-list");limitations.replaceChildren();
    const defaults=["정답 straight / sweep / turn은 생성 경로 유형이며 공식 조업 코드가 아닙니다.","입력은 지역 XY의 기하 특징입니다. 시뮬레이션 시각은 실제 관측 시각이 아닙니다.","전처리·분류·분포 기준은 train에 적합하고, validation은 선택, calibration은 온도 보정에 사용합니다.","실제 자료에서 좌표·라벨·시간 계약과 일반화 성능을 별도로 확인해야 합니다."];
    defaults.forEach(text=>limitations.appendChild(element("li",text)));
    const additions=Array.isArray(report.limitations)?report.limitations:report.limitations?[report.limitations]:[];
    additions.forEach(value=>limitations.appendChild(element("li",typeof value==="object"?JSON.stringify(value):value)));
    set("audit-text",JSON.stringify({source_type:report.source_type??null,schema_version:report.schema_version??null,seed:report.seed??null,split_summary:report.split_summary??null,anomaly:report.anomaly??null,audit:report.audit??null,runtime:report.runtime??null},null,2));
  }
  try {
    const payload=object(JSON.parse(byId("dashboard-data").textContent));report=object(payload.report);records=array(payload.predictions).filter(record=>record&&typeof record==="object"&&!Array.isArray(record));
    names=array(report.class_names);if(!names.length)names=["straight","sweep","turn"];
    renderSummary();renderTables();initializeFilters();renderConfusion();drawLoss();
    byId("confusion-split").addEventListener("change",renderConfusion);
    let resizeFrame;window.addEventListener("resize",()=>{cancelAnimationFrame(resizeFrame);resizeFrame=requestAnimationFrame(()=>{drawTrack();drawLoss();});});
  } catch(error) {
    const warning=byId("dashboard-error");warning.hidden=false;warning.textContent="화면 데이터를 표시하지 못했습니다. JSON 계약과 실행 결과를 확인하세요. "+(error instanceof Error ? error.message : "알 수 없는 오류");
  }
})();
</script>
</body>
</html>
'''
