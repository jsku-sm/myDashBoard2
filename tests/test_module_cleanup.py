"""Static removal regressions; no Streamlit, credentials or network required."""
import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BLOCKED = ('classroom_core', 'classroom_navigation', 'views.classroom')
APP_FILES = sorted([*ROOT.glob('*.py'), *ROOT.joinpath('views').glob('*.py'),
                    *ROOT.joinpath('think_app').glob('*.py')])


def _removed_import(name):
    return (name == 'classroom_core' or name.startswith('classroom_core.')
            or name == 'classroom_navigation'
            or name == 'views.classroom' or name.startswith('views.classroom_'))


@pytest.mark.parametrize('path', APP_FILES, ids=lambda p: p.relative_to(ROOT).as_posix())
def test_no_runtime_import_of_deleted_modules(path):
    tree = ast.parse(path.read_text('utf-8'))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(_removed_import(alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ''
            assert not _removed_import(module)
            if module == 'views':
                assert not any(alias.name.startswith('classroom') for alias in node.names)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in {'classroom_navigation', 'render_shared_records'}
            if isinstance(node.func, ast.Attribute) and node.func.attr == 'import_module':
                for arg in node.args:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        assert not _removed_import(arg.value)


def test_old_feature_files_are_not_shipped():
    assert not list((ROOT / 'classroom_core').rglob('*.py'))
    assert not (ROOT / 'classroom_navigation.py').exists()
    assert not list((ROOT / 'views').glob('classroom*.py'))
    assert not list((ROOT / 'tests').glob('test_classroom_*.py'))
    assert not list((ROOT / 'tests').glob('test_teaching_progress*.py'))
    assert not (ROOT / '.streamlit/classroom.secrets.toml.example').exists()
    for name in ('CLASSROOM_GUIDE.md', 'CLASSROOM_TEST_RESULTS.md',
                 'PROGRESS_BOARD_UPDATE.md', 'PROGRESS_BOARD_TEST_RESULTS.md', 'MENU_UPDATE.md'):
        assert not (ROOT / name).exists()


@pytest.mark.parametrize('name', [
    'think_app/classroom.py', 'think_app/classroom_ui.py', 'think_app/embedded.py',
    'views/snorkl.py', 'views/tools.py', 'snorkl_navigation.py', 'storage.py', 'auth.py',
    'views/math_class.py', 'views/sudanote.py', 'views/teacher.py', 'streamlit_app.py',
])
def test_shared_features_are_kept(name):
    assert (ROOT / name).is_file()


@pytest.mark.parametrize('name', ['app.py', 'views/math_class.py', 'views/sudanote.py', 'views/teacher.py'])
def test_no_bridge_controls_remain(name):
    text = (ROOT / name).read_text('utf-8')
    assert 'render_shared_records' not in text
    assert 'classroom_navigation' not in text
    assert '클래스룸 연결 기록 함께 보기' not in text


def test_runtime_dependencies_are_not_replaced_by_testing_stubs():
    text = (ROOT / 'requirements.txt').read_text('utf-8')
    for name in ('streamlit', 'cryptography', 'requests', 'openai'):
        assert any(line.startswith(name) for line in text.splitlines())
    assert 'playwright' not in (ROOT / 'requirements-dev.txt').read_text('utf-8')


def test_seven_school_classes_are_unchanged():
    tree = ast.parse((ROOT / 'config.py').read_text('utf-8'))
    values = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'CLASSES' for target in node.targets)]
    assert ast.literal_eval(values[0]) == [f'1-{number}' for number in range(1, 8)]
