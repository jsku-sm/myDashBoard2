"""FINAL5 deployment and real view-function tests (no Streamlit installation/network).

A recording test double checks rendered call contents; this is not a full browser
or Streamlit-runtime test. Source functions are compiled from the actual files.
"""
import ast
import html
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'GOOD_RECORDS_1.1_FINAL5'


def function(path, name, namespace):
    tree = ast.parse((ROOT/path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(ROOT/path), 'exec'), namespace)
    return namespace[name]


def preflight():
    tree=ast.parse((ROOT/'app.py').read_text())
    ns={'Path':Path, '__file__':str(ROOT/'app.py')}
    nodes=[]
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id in ('DASHBOARD_UPDATE','_UPDATE_FILES') for t in n.targets):
            nodes.append(n)
        if isinstance(n,ast.FunctionDef) and n.name=='dashboard_update_issues': nodes.append(n)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'preflight','exec'),ns)
    return ns


class CaptureUI:
    def __init__(self): self.calls=[]; self.session_state={}
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def markdown(self,value,**kw): self.calls.append(('markdown',value))
    def caption(self,value,**kw): self.calls.append(('caption',value))
    def columns(self,spec,**kw): return [self for _ in range(spec if isinstance(spec,int) else len(spec))]
    def container(self,*args,**kw): return self
    def form(self,*args,**kw): return self
    def text_input(self,*args,**kw): return ''
    def form_submit_button(self,*args,**kw): return False
    def tabs(self,labels): self.calls.append(('tabs',labels)); return [self]*len(labels)
    def error(self,value,**kw): self.calls.append(('error',value))
    def warning(self,value,**kw): self.calls.append(('warning',value))


def test_final5_complete_deployment():
    ns=preflight()
    assert ns['DASHBOARD_UPDATE']==VERSION
    assert ns['dashboard_update_issues'](ROOT)==[]


@pytest.mark.parametrize('relative',preflight()['_UPDATE_FILES'])
def test_missing_any_required_file_is_reported(tmp_path,relative):
    ns=preflight()
    for name in ns['_UPDATE_FILES']:
        target=tmp_path/name; target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('# '+VERSION)
    (tmp_path/relative).unlink()
    issues=ns['dashboard_update_issues'](tmp_path)
    assert len(issues)==1 and relative in issues[0]


def test_previous_file_with_same_name_detected(tmp_path):
    ns=preflight()
    for name in ns['_UPDATE_FILES']:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text('# '+VERSION)
    (tmp_path/'views/record.py').write_text('def tab_record(): pass')
    issues=ns['dashboard_update_issues'](tmp_path)
    assert len(issues)==1 and '이전 파일' in issues[0]


def test_login_function_renders_requested_title_and_build():
    st=CaptureUI()
    ns={'st':st,'time':SimpleNamespace(time=lambda:0),'DASHBOARD_UPDATE':VERSION,
        'login_bg':SimpleNamespace(html=lambda:''),'db':SimpleNamespace(get_backend=lambda:SimpleNamespace(is_local=False))}
    function('app.py','login_page',ns)()
    rendered=' '.join(str(v) for k,v in st.calls)
    assert 'Good쌤을 만나,' in rendered and '수학이 달라졌다' in rendered
    assert '생각하는 수학 시간' not in rendered
    assert VERSION in rendered


def test_sidebar_function_renders_requested_motto():
    st=CaptureUI()
    function('ui.py','sidebar_header',{'st':st,'html':html})('구쌤의 수학 교실',{'name':'가상교사','role':'teacher'})
    rendered=' '.join(v for k,v in st.calls)
    assert '스스로 발견한 가능성과 자신감' in rendered
    assert '함께 생각하는 수학</small>' not in rendered
    assert '구쌤의 수학 교실' in rendered


def test_teacher_route_calls_record_tab():
    st=CaptureUI();hits=[]
    ns={'st':st,'ui':SimpleNamespace(page_title=lambda *a:None)}
    for name in ['tab_teaching_progress','tab_afterschool','tab_lock','tab_announcements','tab_observe','tab_points','tab_record','tab_roster','tab_settings']:
        ns[name]=(lambda *a,_name=name: hits.append(_name))
    function('views/teacher.py','page',ns)({'role':'teacher'})
    assert hits.count('tab_record')==1
    assert any('📝 생기부 생성기' in value for kind,value in st.calls if kind=='tabs')


def test_student_cannot_enter_teacher_route():
    st=CaptureUI()
    function('views/teacher.py','page',{'st':st})({'role':'student'})
    assert ('error','선생님만 볼 수 있는 화면이에요.') in st.calls


def test_legacy_record_entrypoint_delegates_to_new_renderer():
    hits=[]
    function('views/record.py','tab_record',{'render':lambda:hits.append(True)})()
    assert hits==[True]


def test_record_version_visible_even_when_archive_not_connected():
    st=CaptureUI()
    class Service:
        def __init__(self,*args): pass
        def actor(self): raise PermissionError('교사만 접근')
    ns={'st':st,'VERSION':VERSION,'db':SimpleNamespace(_ready_backend=lambda:object()),
        'AIConfig':SimpleNamespace(from_values=lambda values:None),'values':lambda:{},
        'RecordService':Service,'ArchiveError':ValueError}
    function('record_core/view.py','render',ns)()
    assert any(VERSION in v for k,v in st.calls if k=='caption')
    assert ('warning','교사만 접근') in st.calls


def test_entrypoint_still_executes_app_py():
    source=(ROOT/'streamlit_app.py').read_text()
    assert 'with_name("app.py")' in source and 'runpy.run_path' in source


def test_preflight_runs_before_existing_modules_imported():
    source=(ROOT/'app.py').read_text()
    assert source.index('_update_issues = dashboard_update_issues()')<source.index('import auth')
    assert 'st.stop()' in source[source.index('if _update_issues:'):source.index('import auth')]


def test_new_feature_buttons_exist_in_reachable_workspace():
    source=(ROOT/'record_core/view.py').read_text()
    for label in ['학생별 작성하기','학생 자료파일 불러오기','선택한 파일만 AI 분석',
                  '확인한 근거로 AI 참고 초안 작성','교사 최종 확인본 저장']:
        assert label in source
