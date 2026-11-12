# 진도관리 팝업 위치 수정

진도관리의 `주간 시간표`, `＋ 수업 기록`과 업무수첩의 `＋ 업무 기록`을 누르면 현재 화면에 보이는 해당 메뉴 영역의 중앙에 팝업을 배치합니다. 업무수첩 및 같은 입력창을 사용하는 수정·날짜 이동·자동 배치 창에도 적용됩니다.

## 변경 내용

- 긴 달력 iframe 전체 높이가 아니라 실제로 보이는 영역을 기준으로 팝업 위치와 최대 높이를 계산합니다.
- 페이지 스크롤, 화면 크기 변경, 확대, 모바일 키보드에 따른 화면 높이 변화를 반영합니다.
- 긴 입력 내용은 팝업 안에서 스크롤합니다. 닫기 버튼이 있는 상단 행은 팝업 내부에 고정합니다.
- 팝업을 열 때 제목에 초점을 주어, 화면 아래 입력란으로 자동 이동하는 일을 줄입니다.
- 팝업 크기가 달력 iframe 높이를 계속 늘리지 않도록 달력 본문 기준으로만 iframe 높이를 갱신합니다.
- 기존 7교시 시간표, 업무 체크박스, 저장·수정·드래그 기능을 유지합니다.

## 적용

전체 코드 또는 변경 파일 중 하나를 사용합니다.

- `myDashBoard2_quizpop_updated.zip`: 이전 변경을 포함한 전체 코드.
- `teacher_planner_popup_fix.zip`: 이번 변경 파일만. 압축 내부 `myDashBoard2-main/`의 내용을 기존 프로젝트의 같은 경로에 덮어씁니다.

새 파일 `teacher_planner/frontend/dialog_viewport.mjs`도 반드시 함께 올려야 합니다. 별도 npm 빌드나 API 설정 변경은 필요하지 않습니다. 업로드 후 앱을 재시작하고 페이지를 새로고침하세요.

## 검증 범위

JavaScript 문법 검사, 기존 달력·폼·저장 오류·체크박스·7교시 DOM 검사 14개, 팝업 좌표·상단/중간/하단 스크롤·좁은 화면·키보드 높이·확대·스크롤 컨테이너·종료 정리 등 13개 검사, 총 **27개 통과**.

위치 검사는 가상 화면 크기와 좌표를 사용했습니다. 실제 Streamlit 브라우저 화면 및 iPad 키보드의 시각적 동작은 이 환경에서 확인하지 못했습니다. 운영 GitHub 업로드·Streamlit 배포도 수행하지 않았습니다.

## 구현 참고

직접 접근할 수 있는 상위 문서에서는 iframe 위치와 화면의 가시 영역을 읽습니다. 상위 문서에 접근할 수 없는 경우 브라우저의 IntersectionObserver가 제공하는 교차 영역으로 위치를 갱신합니다. 상위 페이지 DOM을 옮기거나 스타일을 변경하지 않습니다.

- [MDN VisualViewport](https://developer.mozilla.org/en-US/docs/Web/API/VisualViewport)
- [MDN Intersection Observer API](https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API)
