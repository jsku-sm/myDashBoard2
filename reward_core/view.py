"""Streamlit setup and the isolated arcade component; existing menus stay intact."""
from pathlib import Path
import logging
import streamlit as st
from config import CLASSES
from game_core.concept_quiz_catalog import UNITS, unit_info
from . import service as svc
from .catalog import GAMES, MODES, DIFFICULTIES

_component = None
CSS = '''<style>
.st-key-reward_setup {background:#f6f3ff;border:2px solid #24213d;border-radius:26px;padding:22px;box-shadow:6px 6px #caff38;color:#24213d;}
.st-key-reward_setup h3,.st-key-reward_setup label,.st-key-reward_setup p {color:#24213d;}
.st-key-reward_setup button[kind="primary"] {background:#5935ed;border:2px solid #24213d;border-radius:16px;min-height:48px;color:white;}
.reward-hero {border:3px solid #23213d;border-radius:26px;background:#caff38;padding:24px;margin:6px 0 26px;box-shadow:7px 7px #23213d;color:#23213d;}
.reward-hero h2 {color:#23213d;margin:8px 0;font-size:clamp(1.6rem,4vw,2.5rem);}
.reward-hero p {color:#23213d;margin:0;line-height:1.7;}
.reward-hero small {font-weight:900;letter-spacing:.15em;}
</style>'''


def show_paper(paper, editable=False, prefix=''):
    kept=[]
    for i,q in enumerate(paper):
        with st.expander(f"{i+1:02}. {q['topic_title']} · {q['standard']}"):
            keep=st.checkbox('이 문제 출제',value=True,key=f'{prefix}_{i}') if editable else True
            st.markdown(q['prompt'])
            for j,option in enumerate(q['options']): st.markdown(f"{'✅' if j==q['answer'] else '○'} {j+1}. {option}")
            st.markdown('**해설** · '+q['explanation'])
            st.markdown('**힌트** · '+q['hint'])
            if keep: kept.append(q)
    return kept


def page(user):
    st.markdown(CSS,unsafe_allow_html=True)
    st.markdown('<div class="reward-hero"><small>GOOD MATH · PLAY YOUR PROGRESS</small>'
                '<h2>단원 마무리 챌린지 ⚡</h2><p>3문제 맞히고, 90초 신나게!<br>나의 기록을 넘고, 친구들과 도전하고, 우리 반의 목표를 함께 채워요.</p></div>',unsafe_allow_html=True)
    if user.get('role')!='teacher':
        student_page(user); return
    key='_reward_teacher_'+user['id']
    code=st.session_state.get(key)
    if code:
        if st.button('← 활동 목록 · 새 활동 만들기',key='reward_teacher_back'):
            st.session_state.pop(key,None);st.rerun()
        with st.expander('출제 문제·정답 확인'):
            show_paper(svc.paper(user,code))
        live(user,code);return
    previous=svc.history(user)
    if previous:
        with st.expander('이전에 만든 활동 · 결과 다시 보기'):
            code=st.selectbox('활동', [r['code'] for r in previous],format_func=lambda c:next(f"{r['created_at']} · {r['title']} · {c}" for r in previous if r['code']==c))
            if st.button('활동 열기',key='reward_history_open'):st.session_state[key]=code;st.rerun()
    with st.container(key='reward_setup'):
        st.markdown('### 01 · 오늘 마친 단원을 골라요')
        subject=st.selectbox('과목',['공통수학1','공통수학2'],key='reward_subject')
        units=[k for k,v in UNITS.items() if v[0]==subject]
        unit=st.selectbox('단원',units,format_func=lambda k:UNITS[k][1],key='reward_unit_'+subject)
        info=unit_info(unit); names={t['id']:t['title'] for t in info['topics']}
        topics=st.multiselect('세부 주제 · 여러 개 선택 가능',list(names),default=list(names),format_func=names.get,key='reward_topics_'+unit)
        difficulty=st.radio('문제 난이도',list(DIFFICULTIES),format_func=lambda k:DIFFICULTIES[k][0],horizontal=True,key='reward_difficulty')
        config=(unit,tuple(topics),difficulty)
        draft_key='_reward_draft_'+user['id']
        if st.button('이 단원으로 문제 준비',type='primary',disabled=not topics):
            st.session_state[draft_key]=dict(config=config,paper=svc.prepare(user,unit,topics,difficulty),id=svc.uuid.uuid4().hex)
        draft=st.session_state.get(draft_key)
        if not draft or draft['config']!=config:
            st.info('단원과 주제를 선택한 다음 문제를 준비해 주세요. 설정이 바뀌면 문제를 다시 준비합니다.')
            return
        st.markdown('### 02 · 문제와 정답을 확인해요')
        st.caption('선택한 내용의 개념 확인·적용 문제입니다. 제외할 문제의 체크를 해제해 주세요. 학생에게는 현재 문제만 보입니다.')
        with st.expander(f"문제 {len(draft['paper'])}개 미리보기 · 출제할 문항 선택"):
            kept=show_paper(draft['paper'],True,'reward_keep_'+draft['id'])
        st.caption(f'출제할 문제 {len(kept)}개 · 힌트 정답도 인정 · 오답이 나와도 누적 정답 유지')
        st.markdown('### 03 · 어떤 도전을 할까요?')
        game=st.selectbox('게임',list(GAMES),format_func=lambda k:GAMES[k]['icon']+' '+GAMES[k]['title'])
        st.info(GAMES[game]['help'])
        mode=st.radio('참여 방식',list(MODES),format_func=MODES.get,horizontal=True)
        if mode=='solo':st.caption('학생은 3문제를 맞힐 때마다 5종 중 원하는 게임을 고릅니다. 개인 최고 기록은 게임별로 비교합니다.')
        elif mode=='rank':st.caption('모두 같은 게임·같은 코스에 도전합니다. 90초 한 판 최고 점수로 순위를 정하고, 동점은 같은 순위입니다.')
        else:st.caption('학급 전체 점수를 합칩니다. 시작할 때 입장한 인원에 맞춰 목표가 정해지고, 달성하면 모두 별 조각 5개와 협동 배지를 받아요.')
        c1,c2=st.columns(2)
        with c1:classes=st.multiselect('참여할 반',CLASSES,default=[CLASSES[0]])
        with c2:minutes=st.radio('전체 활동 시간',[5,10],format_func=lambda n:f'{n}분',horizontal=True)
        st.caption('학생이 입장한 뒤 교사가 시작합니다. 마지막 판은 남은 시간만 진행하며, 90초 미만의 판은 순위에서 제외합니다.')
        checked=st.checkbox('문제·정답과 출제 범위를 확인했습니다.',key='reward_checked_'+draft['id']+str(len(kept)))
        if st.button('참여코드 만들기',type='primary',disabled=not checked or len(kept)<3 or not classes,width='stretch'):
            code=svc.create(user,unit=unit,topics=topics,difficulty=difficulty,paper=kept,game=game,mode=mode,classes=classes,duration=minutes*60)
            st.session_state[key]=code;st.rerun()


def student_page(user):
    key='_reward_student_'+user['id'];code=st.session_state.get(key)
    if code:
        if st.button('← 다른 활동 참여',key='reward_student_change'):st.session_state.pop(key,None);st.rerun()
        live(user,code);return
    with st.form('reward_join'):
        entered=st.text_input('선생님의 6자리 참여코드',max_chars=6,placeholder='예: 123456')
        if st.form_submit_button('챌린지 참여',type='primary'):
            code=entered.strip();svc.join(user,code);st.session_state[key]=code;st.rerun()
    st.caption('선생님이 단원과 게임을 설정한 뒤 알려 주신 코드로 참여해요. 왼쪽 메뉴의 참여코드 입력도 사용할 수 있어요.')
    records(user)


def records(user, student_id=None):
    b=svc.db._ready_backend()
    with b.lock:
        target=svc.profiles._target(user,b,student_id)
        rows=[r for r in b.read('reward_attempts') if r['student_id']==target['id']]
        room_ids={r['room_id'] for r in rows}
        for r in b.read('reward_rooms'):
            if r['id'] in room_ids:svc.settle(b,r)
        rows=[r for r in b.read('reward_attempts') if r['student_id']==target['id']]
        rooms={r['id']:r for r in b.read('reward_rooms')}
        profile=svc.json.loads(svc.profiles._row(b,target)['state_json'])
    if not rows:return
    st.markdown('#### 단원 마무리 챌린지 기록')
    report=[]
    for row in rows:
        state=svc.json.loads(row['state_json']);room=rooms.get(row['room_id'],{})
        report.append({'단원':room.get('title',''),'정답':state['correct'],'다시 도전':state['wrong'],'힌트':state['hints'],
                       '게임 횟수':len(state['runs']),'별 조각':sum(r['coins'] for r in state['runs'])+profile.get('reward_arcade',{}).get('awards',{}).get('coop:'+row['room_id'],0),'최근 활동':row['updated_at']})
    st.dataframe(report,hide_index=True,width='stretch')


@st.fragment(run_every=2)
def live(user, code):
    global _component
    try:
        view=svc.snapshot(user,code)
        if _component is None:
            import streamlit.components.v1 as components
            _component=components.declare_component('good_reward_arcade',path=str(Path(__file__).with_name('frontend')))
        key='_reward_event_'+user['id']+'_'+code
        event=_component(view=view,ack=st.session_state.get(key),error=st.session_state.get(key+'_error',''),
                         key='reward_live_'+user['id']+'_'+code,default=None)
        if isinstance(event,dict) and event.get('id') and event['id']!=st.session_state.get(key):
            st.session_state[key]=event['id'];st.session_state.pop(key+'_error',None)
            try:
                if event.get('action') in ('start','end'):svc.control(user,code,event['action'])
                else:svc.act(user,code,event)
            except (ValueError,PermissionError) as exc:st.session_state[key+'_error']=str(exc)
            except Exception:
                logging.getLogger(__name__).exception('Reward arcade operation failed')
                st.session_state[key+'_error']='기록을 반영하지 못했어요. 연결 후 다시 시도해 주세요.'
            # A component event may arrive during a full app rerun (navigation
            # or reconnect), where Streamlit disallows a fragment-only rerun.
            try:
                st.rerun(scope='fragment')
            except st.errors.StreamlitAPIException:
                st.rerun()
        status=svc.save_status(user,code)
        if status['local']:st.caption('로컬 시험 저장 · 실제 수업에는 기존 GitHub 저장 설정을 사용해 주세요.')
        elif status['pending']:st.caption('서버 반영 완료 · GitHub 영구 저장 대기 중')
        else:st.caption('☁️ 현재 기록 저장 완료')
        if status['error']:st.warning('저장소 연결을 확인해 주세요. 기록 저장을 다시 시도할 수 있습니다.')
        if st.button('기록 저장 확인 · 다시 시도',key='reward_flush_'+code):
            status=svc.flush(user,code)
            if status['pending']:st.warning('아직 저장 대기 중입니다. 연결을 확인해 주세요.')
            else:st.success('현재 기록의 저장 상태를 확인했어요.')
        if user.get('role')=='teacher' and view['status']=='ended':
            st.download_button('학급 결과 · 문항별 응답 CSV',svc.csv_export(user,code),file_name=f'reward_{code}_results.csv',mime='text/csv',key='reward_csv_'+code)
    except (ValueError,PermissionError) as exc:st.error(str(exc))
