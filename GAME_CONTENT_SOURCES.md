# 목차·문항 구성 출처

확인일: 2026-10-24. 학교에서 사용하는 대표저자는 사용자에게서 제공되지 않았습니다. 홍진곤 기본 표시와 전인태 전환을 지원합니다.

## 공식 목차

천재교과서·천재교육 고등 교과서 소개:
- 고등 목록: https://text.tsherpa.co.kr/high/index.html
- 공통수학1·2 전인태: https://text.tsherpa.co.kr/high/book.html?bookcode=text-high-math-10-ma-01
- 공통수학1·2 홍진곤: https://text.tsherpa.co.kr/high/book.html?bookcode=text-high-math-10-ma-02

공식 페이지에 연결된 목차 이미지(눈으로 확인한 대·중·소단원):
- 전인태 공통수학1: https://text.tsherpa.co.kr/resource/main/textbook/img/high/book/book-hc01-02-01-01.jpg
- 전인태 공통수학2: https://text.tsherpa.co.kr/resource/main/textbook/img/high/book/book-hc01-02-01-02.jpg
- 홍진곤 공통수학1: https://text.tsherpa.co.kr/resource/main/textbook/img/high/book/book-hc02-02-01-01.jpg
- 홍진곤 공통수학2: https://text.tsherpa.co.kr/resource/main/textbook/img/high/book/book-hc02-02-01-02.jpg

앱에는 목차 제목만 구조화했습니다. 출판사 목차 이미지·교과서 본문·문제집 원문을 번들에 복사하지 않았습니다. 세부 주제·격려 문구·예시 문항·게임 캐릭터·게임판은 앱용 구성입니다. ‘세부 주제’는 교과서가 제공하는 추가 분류라고 주장하지 않습니다.

## 문항

최신 첨부 앱의 `quiz_core/bank.py`에 있던 개념 문항 틀을 재사용하고, 다항식 나눗셈·연립방정식/부등식·거리·원과 직선·집합·반례 관련 틀을 보완했습니다. 외부 AI 서비스를 실행 중 호출하지 않습니다. 각 세부 주제에 맞는 틀을 지정하고 숫자와 조건을 바꾸어 5문제를 구성합니다.

기본 문항의 정답 검산과 보기 중복·범위 검사는 자동 검사로 확인했습니다. 이는 교사가 추가한 모든 자연어 문항의 의미적 정답을 자동 검증한다는 뜻이 아닙니다. 교사 문항은 명시적으로 검토하고 공개해야 합니다. 교사의 학습지 배포 권한, 학생 개인정보 포함 여부도 업로드 때 확인하도록 했습니다.

## 실행 프레임워크 참고

- Streamlit Session State: https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- Streamlit forms: https://docs.streamlit.io/develop/api-reference/execution-flow/st.form_submit_button

진행 상태는 브라우저 세션만으로 보존하지 않고 기존 GitHub 저장 계층에 기록합니다. 아직 제출하지 않은 위젯 값까지 다른 기기에 복구하는 것은 아닙니다.
