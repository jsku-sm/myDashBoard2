# 퀴즈 v2 검증 결과

## 실행
Python 3.13.5 · pytest · 로컬 파일 백엔드/모의 HTTP 백엔드 · 실제 Chromium.
실제 GitHub나 운영 학생 기록을 사용하지 않았습니다.

실행한 테스트:
```bash
python -m pytest -q tests/test_concept_quiz.py tests/test_quiz_math.py tests/test_quiz_revision_v2.py tests/test_quiz_dashboard_browser.py tests/test_quiz_student_visual_browser.py tests/test_evaluation_plan_edit.py tests/test_evaluation_plan_visuals.py tests/test_main_navigation.py tests/test_module_cleanup.py tests/test_tools_menu.py tests/test_snorkl_integration.py --tb=short --color=no
```

최종 결과: **488 passed, 1 skipped in 9.21s**.

### 통과 범위
- 16개 단원 문항 유형 중복 방지, 1~10문항 상한, 유형 소진 시 축소
- 112개 원본 문항 생성 가족의 수학적 정답 계산을 독립 계산과 대조
- 제목/발문/보기/유형 검증, 중복 발문·유형 차단
- 1·3·6·7문항의 제출·정규화 점수와 결과 공개
- 기존 10문항 저장/채점/다운로드 유지, 옛 초안의 명시적 중복 정리
- 학생 기록 JSON 버튼 미표시, 교사 기록 다운로드 유지
- 교사 전용 문항 내보내기, 다른 교사/학생/위조 역할 접근 차단
- 개별 문항 DOCX, 전체 DOCX, 학생/교사 HTML, Word 개별문항 ZIP
- 파일의 정답 포함 설정, 학생 식별정보 제외, HTML 문자열 이스케이프
- 파일 준비 후 선택 변경 시 이전 결과 폐기
- 25명 동시 응답의 로컬 모의 시험, 저장 실패·수정 충돌 등 기존 시험
- 기존 평가계획 편집·시각화, 메뉴 정리, 소노클 연결 회귀 검사
- Chromium 대시보드/학생 카드 HTML: 390·768·1440px, 스크롤, O/X,
  다크 모드, 키보드 라디오 선택, 스크립트 문자열 안전 표시

### 문서/미리보기
- 학생 Word 7문항 3쪽, 교사 Word 7문항+해설 4쪽: LibreOffice로 렌더링하여 모든 페이지 검토
- Chromium에서 UI 헬퍼 출력으로 PC/모바일 예시 렌더링
- 브라우저에서 문제만 HTML의 문항 수와 정답 구역 미포함 확인
- 폰트 파일은 포함하지 않음

### 제한/미검증
- Streamlit 런타임 설치를 시도했으나 이 환경의 패키지 경로에서 설치할 수 없었음.
- `tests/test_tools_menu.py`는 Streamlit 미설치로 모듈 단위 skip.
- `tests/test_app_catalog.py`는 AppTest 의존으로 수집 오류가 발생하여 최종 실행 목록에서 제외.
- 실제 Streamlit 전체 앱, 실제 배포 CSS/위젯 DOM, 실계정 GitHub 쓰기, 학교 네트워크, 실제 아이패드 검증은 수행하지 않음.
- 모의 UI 검사를 실제 Streamlit 테스트로, HTML 브라우저 검사를 실제 아이패드 검사로 간주하지 않음.
- 출제 유형은 명시적 문항은행 분류이며, 교사가 자유롭게 수정한 모든 문장의 의미적 중복을 AI로 판정하지 않음.
- 앱/학교별 비공개 저장 권한과 장기 보관 정책은 기존 운영 설정을 따름.

실제 GitHub 저장소와 배포 앱은 이번 작업에서 변경하지 않았습니다.
