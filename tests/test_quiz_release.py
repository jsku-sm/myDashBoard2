import json
from pathlib import Path
import shutil
import pytest
from quiz_pop.release import release_issues

ROOT = Path(__file__).resolve().parents[1] / 'quiz_pop'


def test_release_is_consistent_and_includes_teacher_preview_and_publication():
    assert release_issues(ROOT) == []
    files = json.loads((ROOT / 'release_manifest.json').read_text())['files']
    js = next(p for p in files if p.startswith('frontend/assets/index-') and p.endswith('.js'))
    text = (ROOT / js).read_text()
    assert 'teacherPaper' in text and 'publication' in text


@pytest.mark.parametrize('target', ['service.py', 'view.py', 'frontend/index.html', 'javascript', 'manifest'])
def test_partial_upload_or_old_active_bundle_is_rejected(tmp_path, target):
    shutil.copytree(ROOT, tmp_path / 'quiz', ignore=shutil.ignore_patterns('source', '__pycache__'))
    root = tmp_path / 'quiz'
    if target == 'manifest':
        (root / 'release_manifest.json').unlink()
    else:
        if target == 'javascript':
            target = next(p for p in json.loads((root / 'release_manifest.json').read_text())['files'] if p.startswith('frontend/assets/index-') and p.endswith('.js'))
        (root / target).write_text('old version')
    assert release_issues(root)
