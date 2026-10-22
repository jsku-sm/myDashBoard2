# 방과후 학생 화면 연결 — 검증 결과

실행일: 2026-10-22
기준 소스: `myDashBoard2_afterschool_v2_full.zip`
검증은 가상 사용자·임시 로컬 파일로 수행했습니다. 실제 10101 학생 계정이나 학교 데이터에 접근하지 않았습니다.

## 결과

| 검사 | 결과 |
|---|---|
| Python 원본 160개 구문 분석 | 통과 |
| 신규 학생 연결 검사 | 31개 통과 |
| 기존 방과후 서비스·UI 대역 검사 | 115개 통과 |
| 기존 방과후 HTML Chromium 검사 | 11개 통과 |
| 방과후 합계 | **157개 통과** |
| 별도 선택 회귀 검사 | **366개 통과, 기존 실패 1개** |
| 선택 검사의 총합 | **523개 통과, 기존 실패 1개, 모듈 2개 건너뜀** |

## 신규 검증 시나리오

- 가상 학생 `10101`을 공통수학2의 `5기`에 배정 → 해당 과목에서만 조회 가능.
- 교사 자료와 과제의 동일 ID·본문·첨부를 학생이 읽고 내려받음.
- `자료·과제 / 질문·댓글 / 내 과제 제출` 메뉴 표시와 본인 답안 제출.
- 다른 학생의 개인 답안·피드백·비공개 질문, 미공개 초안, 다른 기수 데이터 차단.
- 기존 준비 중 기수와 비공개 글은 조회만으로 변경되지 않음.
- 교사가 선택한 글만 공개, 선택하지 않은 초안과 기존 파일 유지.
- 준비 중/학생 접근 종료의 재개는 교사가 명시적으로 요청해야 함.
- 읽기 전용 기수를 빠른 공개 버튼으로 임의 재개하지 않음.
- 학생 및 다른 교사의 기수 공개·진단 접근 차단.
- 다른 기수의 글이나 버전이 오래된 글을 섞은 요청은 변경 전에 거부.
- 저장 실패시 `SavePendingError` 및 기존 재시도 흐름 유지.
- 새 기수 기본 운영 중, 게시글 공개 등록과 초안 저장의 구분.
- 미리보기는 자료를 저장하거나 기수를 공개하지 않음.
- 개인 제출 메뉴에서 제출/재제출 가능, 읽기 전용에서는 입력 폼 없음.
- 예전 세션 메뉴명 `내 제출 확인`을 `내 과제 제출`로 호환.
- 교사 배정 후 학생 화면의 접근 변경 감지와 전체 재실행 요청.
- 게시물 변경은 안내만 표시해 미전송 답안 폼의 강제 재실행을 피함.
- 접근 종료/배정 취소 시 UI 갱신 요청 및 서버 서비스의 자료 요청 거부.
- 새로고침 서명에 다른 학생의 답안·비공개 질문이나 초안 정보가 영향을 주지 않음.
- 다른 학생 한 명을 추가한 것은 이미 참여 중인 학생의 폼을 강제 재실행하지 않음.
- 임시 로컬 백엔드를 다시 열어 기수·명단·공개 상태·기존 글 보존 확인.
- 기수 설정에 state가 누락된 부분 수정 시 과거 비공개/종료 상태를 보존.

## 실행 명령

```bash
python -m pytest -q \
 tests/test_afterschool_student_connection.py \
 tests/test_afterschool.py tests/test_afterschool_v2.py \
 tests/test_afterschool_app.py tests/test_afterschool_browser.py \
 tests/test_afterschool_v2_browser.py --disable-warnings -rs
```

결과: `157 passed, 1 skipped`.

```bash
python -m pytest -q \
 tests/test_concept_quiz.py tests/test_quiz_revision_v2.py \
 tests/test_quiz_math.py tests/test_evaluation_plan_edit.py \
 tests/test_evaluation_plan_visuals.py tests/test_main_navigation.py \
 tests/test_tools_menu.py tests/test_teacher_progress.py --disable-warnings -rs
```

결과: `1 failed, 366 passed, 1 skipped`.

## 기존 실패 확인

실패 항목:
`tests/test_concept_quiz.py::test_source_integration_and_no_classroom_resurrection`

사유: 기준 ZIP에도 남아 있는 `classroom_core/` 디렉터리를 전부 제거했는지 검사하는 구형 테스트입니다. **수정 전 ZIP을 별도 경로에 풀어 같은 테스트를 실행했고 동일하게 실패함을 확인**했습니다. 이번 패치에서 이 디렉터리를 추가하거나 클래스룸 메뉴를 다시 연결하지 않았습니다. 방과후 수정과 무관한 파일 삭제는 하지 않았습니다.

## 시험하지 못한 범위

- Streamlit 전체 앱과 프레임워크의 실제 탭·폼·자동 갱신 동작.
- 실제 GitHub 계정 토큰, 배포 저장소에 대한 커밋과 재시작 후 복구.
- 학생 아이패드 Safari, 학교 네트워크, 백그라운드 탭에서의 갱신 주기.
- 서로 다른 배포 서버/독립 앱 사이의 동기화.

런타임에 Streamlit이 설치되어 있지 않았고, 설치 시 패키지 서버 DNS 연결에 실패했습니다. 따라서 `test_afterschool_app.py`, `test_tools_menu.py`는 건너뛰었습니다. 서비스/UI 대역 검사 통과를 실제 Streamlit 실행 통과라고 보고하지 않습니다. Chromium 검사는 기존 HTML 컴포넌트 스타일·다운로드 UI의 브라우저 시험이며 전체 앱 실행은 아닙니다.

## 배포 후 필수 확인

1. 테스트용 교사/학생을 서로 다른 브라우저 창으로 로그인.
2. 공통수학2의 운영 중 5기에 학생 배정, 학생 과목 화면에 탭과 기수 표시 확인.
3. 자료 1개·과제 1개 공개 → 학생이 실제로 읽고 파일을 내려받는지 확인.
4. 내 과제 제출에서 답안 제출 → 교사가 같은 제출물을 확인.
5. 배정하지 않은 학생은 탭 미표시, 타 학생 답안 열람 차단 확인.
6. 읽기 전용·접근 종료 및 재접속·기존 공개 상태 보존 확인.
7. 저장 미확인 경고가 없는지, GitHub에 기록이 남는지 확인.
