from pathlib import Path
import hashlib
p = Path('dist/TikTokLiveRecorder.exe')
if not p.exists(): raise SystemExit('Compile o EXE antes.')
sha = hashlib.sha256(p.read_bytes()).hexdigest()
p.with_suffix('.exe.sha256').write_text(f'{sha}  {p.name}\n', encoding='ascii')
print('SHA-256 criado:', p.with_suffix('.exe.sha256'))
