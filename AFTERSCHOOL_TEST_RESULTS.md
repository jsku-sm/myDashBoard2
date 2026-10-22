# 방과후 게시판 수정본 — 검증 결과

기준: 사용자 업로드 `myDashBoard2-main.zip`. 실제 배포와 GitHub 원격 자료 변경 없음.
검사일: 2026-10-22.

## 실행한 검사

### 새 기능 검사: 73개 통과, 실제 Streamlit 검사 모듈 1개 건너뜀

```bash
python -m pytest -q tests/test_afterschool.py tests/test_afterschool_browser.py tests/test_afterschool_app.py --disable-warnings
```

- Python 서비스/권한/저장/UI 제어 대역 검사 67개.
- 실제 Chromium 파일 전달 컴포넌트 검사 6개.
- `test_afterschool_app.py`: Streamlit 런타임이 없어 건너뜀. 통과로 계산하지 않음.

확인한 내용:
- 빈 상태에서 교사가 기수 생성, 같은 학년도의 중복 기수명 방지, 학년도별 분리.
- 두 기수 동시 배정, 미배정 탭 숨김, 공통수학1에는 방과후 탭 미추가.
- 학생 계정 위조·역할 회수·계정 삭제·최초 비밀번호 변경 미완료·다른 교사 접근 거부.
- 준비/운영/읽기전용/접근종료 네 상태의 읽기·쓰기 권한.
- 원본 명단을 학생에게 전송하지 않음; 일반 저장소 함수로 새 게시판 권한을 우회하는 수정 차단.
- 기수 명단 변경 버전 확인, 검색 필터 밖의 기존 학생 배정 유지.
- 자료 초안, 비공개 질문과 댓글의 동일 공개 범위, 댓글 닫기, 작성자/교사의 삭제.
- 학생별 제출물 소유권, 최초/수정 제출 이력, 교사 피드백, 읽기전용 기록 보존.
- 마감 직전/정각/기한 후 제출, 기한 후 제출 허용 설정.
- 명단 제외 직후 새 자료·첨부 요청 차단, 재배정 시 과거 기록 열람.
- 파일 확장자/서명/크기/경로 기본 검증, 파일 해시 불일치 처리, 임의 파일 ID 미수용.
- 네트워크 실패 대역으로 저장 성공 오표시 방지, 중복 요청 처리, 저장 재확인.
- 로컬 CSV를 다시 열어 기수·댓글·과제·첨부 기록 복원.
- 25명 동시 제출/반복 요청 로컬 시험에서 유실·중복 0건. GitHub 부하 시험은 아님.
- 생성/명단 배정/학생 질문/제출 폼 조작을 Streamlit 대역으로 검사.
- 파일 컴포넌트의 390/768/1280px 폭, 키보드 조작, 권한 거부 안내, 파일 저장,
  Blob 기반 전송, 다른 파일로 전환 시 이전 준비 링크 제거, 문자열 안전 표시.

### 관련 회귀 검사와 함께: 439개 통과, 원본 동일 실패 1개

```bash
python -m pytest -q tests/test_teacher_progress.py tests/test_concept_quiz.py \
  tests/test_quiz_math.py tests/test_quiz_revision_v2.py tests/test_main_navigation.py \
  tests/test_evaluation_plan_edit.py tests/test_evaluation_plan_visuals.py \
  tests/test_afterschool.py tests/test_afterschool_browser.py --disable-warnings
```

실패:
`tests/test_concept_quiz.py::test_source_integration_and_no_classroom_resurrection`

실패 이유는 업로드 원본에 `classroom_core/` 디렉터리가 존재하는데, 과거 테스트는 이 디렉터리가 없어야 한다고 검사하기 때문입니다.
사용자 원본 ZIP을 별도 폴더로 그대로 추출한 뒤 **같은 테스트를 원본에도 실행해 동일 실패를 확인**했습니다.
방과후 수정에서 클래스룸 메뉴를 활성화하거나 새로 복원한 것이 아닙니다.
이 검사를 통과했다고 보고하지 않으며, 무관한 원본 폴더를 임의로 지우지 않았습니다.

### 문법

원본을 포함한 Python 소스 155개를 AST 파싱해 문법 오류가 없음을 확인했습니다.
새 실행용 자바스크립트는 Chromium에서 실제 실행했습니다.

## 검증하지 못한 내용

- 전체 Streamlit 앱 실행/실제 인증 세션·업로드 위젯 동작. 런타임 설치를 시도했으나 패키지 저장소 네트워크 접근 불가.
- 실제 GitHub 토큰으로 첨부 저장·커밋·재시작 복원.
- 실제 학교 Wi-Fi·아이패드 Safari의 업로드/다운로드와 화면 배치.
- 실사용 학생 정보 및 학교 개인정보 정책 승인.
- 다중 앱 서버 동시 편집. 기존 저장소는 단일 앱 서버를 전제로 함.

브라우저 검사는 개별 파일 전달 컴포넌트에 대한 것이며, 전체 Streamlit 앱이 배포에서 정상 작동함을 증명하는 것은 아닙니다.
적용 후 두 기수와 미배정 학생을 포함한 가상 계정으로 접근·읽기전용·저장 복원 시나리오를 먼저 시험하세요.
