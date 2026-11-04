from pathlib import Path
root=Path(__file__).resolve().parents[1]
folder=root/'docs/competition_20261019'
old=folder/'01_데이터구조와_실측집계.md'
new=folder/'01_데이터구조와_직접집계.md'
if old.exists():
    assert not new.exists()
    old.rename(new)
for path in [root/'2026 데이터 분석대회 데이터 분석 정리.md',*folder.glob('*.md'),root/'tmp/build_competition_notes.py']:
    text=path.read_text(encoding='utf-8').replace('01_데이터구조와_실측집계.md','01_데이터구조와_직접집계.md')
    if path==new:
        text=text.replace('전체 코드 체계·라벨 부여 규칙 미확인','전체 코드 체계·라벨 부여 규칙 미확인. 매시간 행동 상태인지 선박 업종인지, 선박 내 불변인지도 미확인')
        text=text.replace('정확한 샘플 출처·추출 방식·개정 버전도','점과 부분선의 시간 순서·생성 규칙, 정확한 샘플 출처·추출 방식·개정 버전도')
    if path.name=='02_분석해석과_다음단계.md':
        text=text.replace('점별 시각·샘플링 의미가 확인돼야 함','점별 시각·샘플링 의미가 확인돼야 함')
        text=text.replace('사고 정보가 없는 행을 정상 정답으로 바꾸지 않는다。','사고 정보가 없는 행을 정상 정답으로 바꾸지 않는다。')
        text=text.replace('실제 제출 단위·식별키·파일 형식은 정식 규격을 더 확인해야 한다。','실제 제출 단위·식별키·파일 형식은 정식 규격을 더 확인해야 한다。')
        text=text.replace('실제 제출 단위·식별키·파일 형식은 정식 규격을 더 확인해야 한다.','실제 제출 단위·식별키·파일 형식은 정식 규격을 더 확인해야 한다. 시간대 전체 항적을 사용했다면 그 시간대 종료와 처리 지연 이전에 판단할 수 있었다고 주장할 수 없다.')
    if path.name=='04_파일목록과_검증기록.md':
        text=text.replace('| 문서 내용 조사 |','| 핵심 MD 내용 조사; 그 외 목록·해시 보존 |')
        text=text.replace('| 텍스트 추출·관련 부분 조사 |','| 텍스트 추출; 핵심 PDF 관련 부분 조사 |')
        text=text.replace('참가신청서 HWP와 포스터의 세부 일정·제출 조건은 이번 요약에서 판단하지 않았다.','참가신청서 HWP와 포스터의 세부 일정·제출 조건은 이번 요약에서 판단하지 않았다. Markdown 내용 대조는 09·12·13 및 중요도 TXT를 중심으로 했으며, 알고리즘 설명·08 적합성 문서는 목록·해시만 보존했다. 시각 대조는 공지 이미지 4장과 PDF 이해가이드 p.16·최종 제안서 가이드 p.3을 확인했다.')
    path.write_text(text,encoding='utf-8')
print('Renamed direct-count note and clarified inspection scope.')
