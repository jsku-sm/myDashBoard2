# 클래스룸 전용 코드 삭제 — 검증 범위

기준 원본: `myDashBoard2_no_classroom_menu_full.zip`.
작업 대상은 전달된 파일의 로컬 사본입니다. 운영 GitHub 저장소·배포 앱·실제 학생 기록은 변경하지 않았습니다.

## 실행한 검사

| 검사 | 결과 | 범위 |
| --- | --- | --- |
| Python 문법 검사 | 93개 소스 통과 | 앱 및 테스트 소스 컴파일. 앱을 실행한 것과는 다름 |
| 선택한 pytest 회귀 검사 | 214개 통과 | 일반 메뉴, 제거한 모듈 import 잔존 여부, 소노클 연결 설정·권한·공유 링크, 수업 모델, 교육과정, 이미지 검색 처리 |
| 정리 스크립트 통합·안전 검사 | 8개 통과 | 아래 시나리오; 임시 폴더와 가상 데이터 사용 |
| 소노클 JavaScript 검사 | 4개 스크립트 통과 | 필기판, 그래프, 문제 첨부, 영역 캡처. DOM·SDK 모의 환경 |
| 기존 파일 보존 대조 | 116개 원본 파일 바이트 동일 | 삭제/수정 대상 외 원본 파일 전부. `think_app/` 전체, 기존 auth/storage, 실행 의존성 포함 |

선택한 pytest 검사 214개와 정리 스크립트 검사 8개를 합해 222개입니다. 전체 저장소의 모든 테스트나 실제 사용자 환경을 통과했다는 뜻이 아닙니다.

### 정리 스크립트 검사 8개

- 업로드 원본 `myDashBoard2-main (3).zip`에 미리보기·적용·재실행.
- 진도표 수정본 `myDashBoard2_progress_full.zip`에 미리보기·적용·재실행.
- 메뉴 삭제본 `myDashBoard2_no_classroom_menu_full.zip`에 미리보기·적용·재실행.
- 원본과 다른 `app.py`가 있을 때 변경 없이 중단.
- 새 연결 모듈이 제거 대상 코드를 참조할 때 변경 없이 중단.
- 다른 프로젝트에서 실행 시 변경 없이 중단.
- 수정 경로가 심볼릭 링크이면 외부 파일을 변경하지 않고 중단.
- 중간 파일 저장 오류를 주입했을 때 원래 코드를 복원하고 백업 유지.

세 가지 원본 적용 검사에서 가상 `data/classroom/` 기록, 가상 사용자 CSV, 가상 Secrets, 가상 소노클 암호문 파일을 만들어 적용 전후 바이트가 같은지 확인했습니다. 운영 데이터는 사용하지 않았습니다.

## 실행 방법

앱 루트에서:

```bash
python -m pytest -q tests/test_main_navigation.py tests/test_module_cleanup.py tests/test_courses.py tests/test_curriculum.py tests/test_image_search.py tests/test_snorkl_integration.py
node tests/board_checks.cjs
node tests/graph_checks.cjs
node tests/question_capture_checks.cjs
node tests/region_capture_checks.cjs
```

Python 검사에는 pytest 등 테스트가 요구하는 설치 패키지가 필요합니다. Node 검사 결과는 브라우저·아이패드·마이크 권한 검증을 대신하지 않습니다.

## 실행하지 못한 검사

이 환경에는 Streamlit 런타임이 없고 필요한 패키지 설치도 완료하지 못했습니다. 따라서 전체 Streamlit 화면 실행, 교사·학생 실제 로그인, 실계정 GitHub 저장, Google Drive·AI 호출, 아이패드에서의 동작은 검증하지 않았습니다.

운영 적용 후에는 교사·학생 시험 계정으로 공통수학 게시판, 수다노트, 교사 관찰, 소노클 활동 열기·제출, 기존 자료 열람을 확인해야 합니다. 코드의 byte 동일성은 해당 외부 연결의 정상 동작을 보증하지 않습니다.
