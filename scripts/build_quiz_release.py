"""Run after rebuilding quiz_pop/source. Writes only the release manifest."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / 'quiz_pop'
paths = [root / n for n in ('service.py', 'view.py', 'release.py')]
paths.extend(sorted(p for p in (root / 'frontend').rglob('*') if p.is_file()))
files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
(root / 'release_manifest.json').write_text(json.dumps({'schema': 1, 'release': '2026-11-13-audit-fixes', 'files': files}, indent=2) + '\n', encoding='utf-8')
print('quiz_pop 실행 파일 묶음: ' + str(len(files)) + '개')
