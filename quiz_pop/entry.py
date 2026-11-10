"""One code entry for teacher-published quizzes and existing review games."""
import streamlit as st
from . import service, classroom


def _clear_code():
    st.session_state.pop('_quizpop_student_code',None)
    st.query_params.pop('review',None)
    st.query_params.pop('quiz',None)


def student_entry(user, code='join', *, standalone=True):
    if standalone and st.button('← 수업 대시보드로 돌아가기',key='quizpop_student_back'):
        _clear_code();st.rerun()
    try:
        service.authorize(user,role='student')
        # Old review links continue to use their own participant screen.
        if code != 'join' and classroom.code_kind(user,code)=='review':
            from review_core.view import student_entry as legacy_entry
            legacy_entry(user,code)
            return
        if code != 'join':
            if st.button('← 다른 참여코드 입력',key='quizpop_change_code'):
                _clear_code()
                if standalone: st.query_params['quiz']='join'
                st.rerun()
            classroom.join(user,code)
            st.session_state['_quizpop_student_code']=code
            from .view import student_quiz
            student_quiz(user,code)
            return
        st.markdown('<div style="background:#e9e1ff;border:3px solid #27243d;border-radius:24px;padding:24px;box-shadow:6px 6px #c5fb69;margin:10px 0 28px">'
                    '<span style="font-weight:800;color:#542acb">READY TO QUIZ</span>'
                    '<h2 style="margin:8px 0">선생님의 퀴즈에 참여해요</h2>'
                    '<p>선생님 화면에 보이는 숫자 6자리를 입력하면 준비된 문제를 바로 풀 수 있어요.</p></div>',unsafe_allow_html=True)
        with st.form('quizpop_join_form'):
            entered=st.text_input('6자리 참여코드',max_chars=6,placeholder='예: 123456',key='quizpop_join_input')
            if st.form_submit_button('퀴즈 참여',type='primary'):
                code=classroom.normalize_code(entered)
                kind=classroom.code_kind(user,code)
                if kind=='review':
                    from review_core import service as reviews
                    reviews.join(user,code)
                    st.query_params.pop('quiz',None);st.query_params['review']=code
                else:
                    classroom.join(user,code)
                    st.session_state['_quizpop_student_code']=code
                    if standalone:
                        st.query_params.pop('review',None);st.query_params['quiz']=code
                st.rerun()
        st.caption('퀴즈 생성과 참여코드 발급은 교사만 할 수 있습니다. 기존 복습 게임 참여코드도 사용할 수 있어요.')
    except (ValueError,PermissionError) as error:
        st.error(str(error))
        if code != 'join' and st.button('참여코드 다시 입력',key='quizpop_retry_code'):
            _clear_code()
            if standalone: st.query_params['quiz']='join'
            st.rerun()
