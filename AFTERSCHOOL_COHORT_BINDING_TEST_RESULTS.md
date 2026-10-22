# 방과후 기수 선택·명단 연결 — 검증 결과

## 기준과 실제 변경 범위

- 기준: `myDashBoard2_afterschool_student_link_full.zip`.
- 실행 파일 수정: `views/afterschool.py`, `afterschool_core/presentation.py`.
- 실행 파일 추가: `afterschool_core/admin_navigation.py`.
- 기존 `service.py`, `schema.py`, `storage.py`, `views/math_class.py`는 변경하지 않았습니다.
- 데이터·Secrets·운영 저장소·배포 사이트는 변경하지 않았습니다.

## 오류 재현과 수정

수정 전 신규 회귀 검사 2개 실패, 수정 후 동일 검사 2개 통과.
1. 1기 선택 → 5기 생성 → 다음 화면: 수정 전에는 1기가 선택된 상태 유지. 수정 후 5기 참여 학생으로 이동.
2. 5기 선택 → 화면 위젯 키 정리를 모의 재현 → 돌아오기: 수정 전 첫 번째 기수로 복귀. 수정 후 별도 세션 선택값으로 5기 복원.

기존 데이터 저장 서비스는 기수 ID별 `members_json`을 사용하고 있었습니다. 실제 운영 명단의 오배정을 확정하거나 자동 재배정한 것은 아닙니다.

## 실행한 검사

| 범위 | 결과 |
|---|---|
| 방과후 신규 회귀 검사 | 20개 통과 |
| 방과후 로직·권한·파일 저장·UI 테스트 대역 검사 | 166개 통과 (위 신규 검사 포함) |
| 방과후 Chromium HTML·다운로드 컴포넌트 검사 포함 | 총 177개 통과 |
| 선택한 기존 기능 회귀 검사 | 556개 통과, 7개 실패, 2개 모듈 건너뜀 |
| Python 소스 AST 문법 검사 | 162개 파일 통과 |

숫자는 각각 별도 실행 범위이며 서로 합산하면 안 됩니다. Chromium 검사는 HTML/컴포넌트 수준으로 전체 Streamlit 화면 검사와 다릅니다.

### 핵심 14명 시나리오

- 1기에 가상 학생 6명 배정.
- 교사 화면에서 5기 생성 후 자동으로 5기 학생 배정 화면 이동.
- 여러 명 추가 기능으로 다른 가상 학생 14명을 선택.
- 저장 후 1기 6명·5기 14명을 각 기수 ID와 현재 배정 명단에서 대조.
- 교사 자료 등록 UI에서 5기용 글과 파일 등록.
- 배정된 14명 모두 동일 5기 게시글·첨부 열람 가능.
- 나머지 학생은 5기 글·첨부 접근 거절.
- 별도 시험에서 두 기수에 함께 참여한 학생을 5기에서 제외: 5기 13명, 다른 기수 유지, 과거 과제 제출 보존.
- 로컬 파일 저장소를 다시 열어 각 기수의 `members_json` 복원 확인.

### 기존 테스트 변경

`tests/test_afterschool_v2.py`의 생성·설정 수정 검사는 새 기수 생성 직후 참여 학생으로 자동 이동하는 새 동작에 맞게 설정 메뉴를 선택하도록 변경했습니다. 기수 설정 확인 체크박스도 기수·버전별 키로 검사합니다. 서비스 권한 검사를 완화하거나 실패를 숨긴 변경은 아닙니다.

## 선택 회귀 검사 실패 7건

다음은 클래스룸 잔여 파일이 없어야 한다는 구형 정리 검사입니다.
- `test_concept_quiz.py::test_source_integration_and_no_classroom_resurrection` 1건.
- `test_module_cleanup.py::test_no_runtime_import_of_deleted_modules`의 구형 클래스룸 화면 파일 5건.
- `test_module_cleanup.py::test_old_feature_files_are_not_shipped` 1건.

동일 원본 ZIP을 별도 폴더에 그대로 추출하여 이 실패 항목이 포함된 검사를 다시 실행했고, 원본에서도 동일하게 **7개 실패·88개 통과**를 확인했습니다. 이번 패치가 클래스룸 코드를 추가하거나 메뉴를 복구한 것은 아닙니다. 해당 파일 삭제는 이번 방과후 명단 연결 변경 범위에서 제외했습니다. 실제 배포 전체가 정상이라고 단정하지 않습니다.

## 수행하지 못한 검증

- Streamlit 전체 앱/AppTest: 패키지 미설치. 설치 시 DNS 오류로 실패.
- 실제 Google/GitHub 계정·운영 저장소의 5기 명단 확인.
- 실제 GitHub 쓰기·동시 독립 배포 간 병합.
- 학교 네트워크·실제 아이패드.
- 이미 운영 자료에 발생한 오배정의 자동 교정.

실제 5기 14명은 패치 적용 후 학번·이름을 확인해야 합니다. 학생 수 14를 코드에 하드코딩하지 않았습니다.

## 재현 명령

```bash
python -m pytest tests/test_afterschool_cohort_binding.py -q
python -m pytest tests/test_afterschool.py tests/test_afterschool_v2.py tests/test_afterschool_student_connection.py tests/test_afterschool_cohort_binding.py tests/test_afterschool_browser.py tests/test_afterschool_v2_browser.py -q
```

참고한 공식 문서: Streamlit Session State 및 Widget behavior. 실제 지원 최소 버전 1.55에 없는 새로운 `persist_state` 인자는 사용하지 않았습니다.
- https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- https://docs.streamlit.io/develop/concepts/architecture/widget-behavior
