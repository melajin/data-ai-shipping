"""Decode the whole recording and extract each completed live stage for review."""
from pathlib import Path
import json
import re
import subprocess

base = Path(__file__).resolve().parent
ffmpeg = next((base / 'tools/imageio_ffmpeg/binaries').glob('ffmpeg*.exe'))
done = json.loads((base / 'recording_done.json').read_text(encoding='utf-8'))
video = base.parent / done['video']
probe = subprocess.run([str(ffmpeg), '-hide_banner', '-i', str(video)], capture_output=True, text=True, encoding='utf-8')
(base / 'video_metadata.txt').write_text(probe.stderr, encoding='utf-8')
duration = re.search(r'Duration: (\d+):(\d+):([\d.]+)', probe.stderr)
assert duration
seconds = int(duration[1]) * 3600 + int(duration[2]) * 60 + float(duration[3])
assert seconds <= 180
assert '1280x720' in probe.stderr and '10 fps' in probe.stderr and 'h264' in probe.stderr
assert 'Audio:' not in probe.stderr
decode = subprocess.run([str(ffmpeg), '-v', 'error', '-threads', '2', '-i', str(video), '-f', 'null', '-'],
                        capture_output=True, text=True, encoding='utf-8')
assert decode.returncode == 0 and not decode.stderr.strip(), decode.stderr
for i, step in enumerate(done['timeline'], 1):
    when = step['completed_seconds'] + 3
    subprocess.run([str(ffmpeg), '-v', 'error', '-n', '-ss', str(when), '-i', str(video),
                    '-frames:v', '1', '-update', '1', str(base / f'stage_{i}.png')], check=True)
    assert step['exit_code'] == 0
evidence = dict(duration_seconds=seconds, bytes=video.stat().st_size, resolution='1280x720',
                fps=10, codec='H.264 / yuv420p', audio=False, decode_exit_code=decode.returncode,
                decode_errors=decode.stderr, recorded_commands=len(done['timeline']),
                all_command_exit_codes_zero=True)
(base / 'video_validation.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
print(json.dumps(evidence, indent=2))
