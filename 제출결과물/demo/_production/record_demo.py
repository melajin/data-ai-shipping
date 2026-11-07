"""Record an actual live subprocess-output window with FFmpeg gdigrab."""
from pathlib import Path
import ctypes
import datetime
import hashlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGE = ROOT / 'deliverables/testb_system_20261106'
DEMO = HERE.parent
FFMPEG = next((HERE / 'tools/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
PREVIEW = '--preview' in sys.argv
TITLE = 'Test B - Live execution capture'
VIDEO = HERE / 'preview.mp4' if PREVIEW else DEMO / 'TestB_demo_20261106.mp4'
ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
events = []
messages = queue.Queue()

def preflight(stage):
    class Status(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
            (key, ctypes.c_ulonglong) for key in ('total', 'available', 'total_page', 'available_page',
                                                'total_virtual', 'available_virtual', 'extended')]
    status = Status()
    status.length = ctypes.sizeof(status)
    assert ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    evidence = dict(stage=stage, checked_at=datetime.datetime.now().astimezone().isoformat(),
                    available_mib=status.available / 2**20, expected_combined_peak_mib=1024,
                    reserve_mib=640,
                    estimate_basis='Analysis prior measured 299 MiB, budget 512; FFmpeg 2 threads + Tk budget 512; 10 fps streaming, no frame accumulation')
    proc = subprocess.run(['powershell', '-NoProfile', '-Command',
        'Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 6 ProcessName,WorkingSet64 | ConvertTo-Json -Compress'],
        capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    evidence['other_processes'] = json.loads(proc.stdout)
    events.append(evidence)
    (HERE / ('preview_memory.json' if PREVIEW else 'memory_checks.json')).write_text(json.dumps(events, indent=2), encoding='utf-8')
    if status.available / 2**20 < 1664:
        raise MemoryError('Deferred: available RAM below combined budget + reserve')

def hashes():
    result = {}
    for folder in ('inputs', 'references', 'results/reproduction_001', 'reports'):
        for path in sorted((PACKAGE / folder).rglob('*')):
            if path.is_file():
                h = hashlib.sha256()
                with path.open('rb') as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        h.update(chunk)
                result[path.relative_to(PACKAGE).as_posix()] = h.hexdigest()
    return result

preflight('before recorder setup')
if not PREVIEW:
    if VIDEO.exists() or (PACKAGE / 'results/demo_run').exists():
        raise FileExistsError('Refusing to overwrite existing video or demo_run')
    before = hashes()
    (HERE / 'protected_before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
    helpers = PACKAGE / 'results/demo_tools'
    helpers.mkdir(exist_ok=False)
    shutil.copy2(HERE / 'inspect_result.py', helpers / 'inspect_result.py')

root = tk.Tk()
root.title(TITLE)
root.geometry('1280x720+0+0')
root.overrideredirect(True)
root.attributes('-topmost', True)
root.configure(bg='#0d1523')
tk.Label(root, text='2026 DATA·AI 분석 경진대회  |  TEST B', font=('Malgun Gothic', -25, 'bold'),
         fg='#f5f7fb', bg='#0d1523', anchor='w').place(x=30, y=17, width=1220, height=40)
stage = tk.StringVar(value='녹화 준비  ·  실제 실행 출력')
tk.Label(root, textvariable=stage, font=('Malgun Gothic', -18), fg='#63d9d0',
         bg='#0d1523', anchor='w').place(x=32, y=63, width=1216, height=30)
cmd = tk.StringVar(value='')
tk.Label(root, textvariable=cmd, font=('Consolas', -18), fg='#f4d27d',
         bg='#182437', anchor='w', padx=12).place(x=30, y=104, width=1220, height=44)
output = tk.Text(root, font=('Consolas', -18), fg='#e5edf8', bg='#101b2c',
                 borderwidth=0, highlightthickness=0, padx=14, pady=12, wrap='char', spacing1=1)
output.place(x=30, y=159, width=1220, height=495)
footer = tk.StringVar(value='고정 기준선 사후 재현  ·  실제 명령 실행 화면  ·  CPU 전용')
tk.Label(root, textvariable=footer, font=('Malgun Gothic', -16), fg='#aab8cc',
         bg='#0d1523', anchor='w').place(x=32, y=670, width=1216, height=30)
timeline = []
start = 0

def poll():
    try:
        while True:
            kind, value = messages.get_nowait()
            if kind == 'stage':
                title, command = value
                stage.set(title)
                cmd.set('> ' + command)
                output.delete('1.0', 'end')
            elif kind == 'text':
                output.insert('end', value)
                output.see('end')
            elif kind == 'footer':
                footer.set(value)
            elif kind == 'close':
                root.destroy()
                return
    except queue.Empty:
        pass
    root.after(40, poll)

def execute(title, args, hold):
    command = 'python ' + ' '.join(args)
    messages.put(('stage', (title, command)))
    entry = dict(stage=title, command=command, start_seconds=time.monotonic() - start)
    timeline.append(entry)
    time.sleep(1)
    p = subprocess.Popen([sys.executable, '-u', *args], cwd=PACKAGE, env=ENV,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
    lines = []
    for line in p.stdout:
        lines.append(line)
        messages.put(('text', line))
    code = p.wait()
    entry.update(exit_code=code, output=''.join(lines), completed_seconds=time.monotonic() - start)
    messages.put(('text', f'\n[process exit code: {code}]\n'))
    if code:
        raise RuntimeError('Recorded command failed')
    time.sleep(hold)

def record():
    global start
    capture = None
    try:
        time.sleep(1)
        preflight('immediately before capture and analysis')
        args = [str(FFMPEG), '-hide_banner', '-n', '-f', 'gdigrab', '-framerate', '10',
                '-draw_mouse', '0', '-i', 'title=' + TITLE, '-vf', 'crop=1280:720:0:0', '-an', '-c:v', 'libx264',
                '-preset', 'veryfast', '-crf', '18', '-threads', '2', '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', str(VIDEO)]
        (HERE / ('preview_capture_command.json' if PREVIEW else 'capture_command.json')).write_text(json.dumps(args, indent=2), encoding='utf-8')
        log = (HERE / ('preview_ffmpeg.log' if PREVIEW else 'ffmpeg.log')).open('w', encoding='utf-8')
        capture = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        start = time.monotonic()
        time.sleep(1)
        if capture.poll() is not None:
            raise RuntimeError('Capture failed; see FFmpeg log')
        helper = 'results/demo_tools/inspect_result.py'
        if PREVIEW:
            messages.put(('stage', ('미리보기  ·  화면 크기 및 글자 확인', 'python --version')))
            p = subprocess.run([sys.executable, '--version'], capture_output=True, text=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
            messages.put(('text', p.stdout))
            time.sleep(3)
        else:
            execute('1 / 6  환경 확인  ·  requirements.txt와 설치 버전 대조', [helper, 'environment'], 10)
            execute('2 / 6  본 실행  ·  재계산과 저장 기준 결과 전수 대조',
                    ['src/run_analysis.py', '--output', 'results/demo_run'], 6)
            execute('3 / 6  생성 파일 확인  ·  이번 실행의 summary.json', [helper, 'outputs'], 11)
            execute('4 / 6  재현 검증  ·  parity 블록 전체 확인', [helper, 'parity'], 18)
            messages.put(('footer', '사후 후보 검토  ·  점수는 사고 확률이 아니며 후보시각은 확정 사고시각이 아닙니다'))
            execute('5 / 6  후보 1척 확인  ·  종합점수 / 세 구성점수 / 과거 관측 수', [helper, 'candidate'], 19)
            preflight('immediately before unit tests; analysis finished')
            messages.put(('footer', '검증 범위: 저장 결과 재현 + 단위 테스트  ·  공식 사고 성능 및 실시간 검증과 구분'))
            execute('6 / 6  단위 테스트  ·  python unittest 실제 실행',
                    ['-m', 'unittest', 'discover', '-s', 'tests', '-v'], 13)
        capture.stdin.write(b'q\n')
        capture.stdin.flush()
        code = capture.wait(timeout=30)
        log.close()
        assert code == 0
        if not PREVIEW:
            after = hashes()
            (HERE / 'protected_after.json').write_text(json.dumps(after, indent=2), encoding='utf-8')
            assert before == after, 'Protected files changed'
            (HERE / 'integrity.json').write_text(json.dumps(dict(protected_files=len(before), all_unchanged=True), indent=2), encoding='utf-8')
        (HERE / ('preview_done.json' if PREVIEW else 'recording_done.json')).write_text(json.dumps(
            dict(video=VIDEO.name, timeline=timeline, capture_exit_code=code), indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception as exc:
        (HERE / 'error.txt').write_text(repr(exc), encoding='utf-8')
        if capture and capture.poll() is None:
            capture.stdin.write(b'q\n')
            capture.stdin.flush()
            capture.wait(timeout=30)
    finally:
        messages.put(('close', None))

root.after(40, poll)
threading.Thread(target=record, daemon=True).start()
root.mainloop()
