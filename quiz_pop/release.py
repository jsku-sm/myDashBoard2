"""Check the shipped server/frontend pair before displaying a quiz component."""
import hashlib
import json
from pathlib import Path
import re


def release_issues(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    try:
        manifest = json.loads((root / 'release_manifest.json').read_text(encoding='utf-8'))
        files = manifest['files']
        if manifest['schema'] != 1 or not isinstance(files, dict):
            raise ValueError()
        required = {'service.py', 'view.py', 'frontend/index.html'}
        index = (root / 'frontend/index.html').read_text(encoding='utf-8')
        assets = re.findall(r'(?:src|href)=["\']\./(assets/[^"\']+\.(?:js|css))["\']', index)
        if not assets or not any(a.endswith('.js') for a in assets):
            raise ValueError()
        required.update('frontend/' + a for a in assets)
        if not required.issubset(files):
            raise ValueError()
    except (OSError, ValueError, TypeError, KeyError):
        return ['퀴즈 실행 파일 목록이 없거나 맞지 않습니다.']
    issues = []
    for relative, digest in files.items():
        path = root / relative
        if not path.resolve().is_relative_to(root.resolve()):
            return ['퀴즈 실행 파일 경로를 확인해 주세요.']
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            issues.append(relative + ' · 파일 없음')
            continue
        if actual != digest:
            issues.append(relative + ' · 버전 불일치')
    return issues


def require_release():
    issues = release_issues()
    if issues:
        raise ValueError('퀴즈 업데이트 파일이 일부 빠졌거나 서로 다릅니다. '
                         '선생님이 수정본의 quiz_pop 폴더를 코드 저장소의 같은 위치에 적용해야 합니다. '
                         + ' / '.join(issues[:4]))
