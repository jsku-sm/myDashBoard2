# 학생 공지 팝업 수정 및 생기부 작성기 점검

## 이번에 수정한 기능

교사가 게시한 공지가 학생 화면 가운데 나타나도록 수정했습니다.

- 연분홍·라벤더 색상의 둥근 편지 카드, 편지 봉투와 하트 장식.
- JavaScript로 작은 움직임을 주고 동작 줄이기 설정과 화면 숨김 상태에서는 움직임을 멈춤.
- 긴 공지와 여러 공지는 팝업 안에서 스크롤하여 열람.
- 학생의 현재 학급, 공지 공개 여부를 확인하는 기존 동작 유지.
- `확인했어요`로 읽은 공지는 반복 노출하지 않으며, 교사가 수정한 공지는 다시 표시.
- 공지 본문·학생 정보·읽음 기록은 장식용 JavaScript에 전달하지 않음.
- 다른 팝업에는 공지 전용 CSS를 적용하지 않음.

변경 파일: `announcement_ui.py`, `assets/announcement_letter.html`, `views/student_announcements.py`.
`tests/test_announcements.py`의 오래된 교사 메뉴 목록과 암호화 자료함 테스트 준비 상태도 현재 코드에 맞췄습니다.

## 적용

- 변경 파일만 적용하려면 `announcement_popup_update.zip`의 `myDashBoard2-main/` 안 내용을 기존 프로젝트 루트에 같은 경로로 덮어씁니다.
- 전체 코드는 `myDashBoard2_quizpop_updated.zip`에 반영했습니다. 기존 교사 업무수첩과 게임 등은 포함되어 있습니다.
- 별도 프런트엔드 빌드나 API 키 변경은 필요하지 않습니다.
- 실제 GitHub 업로드·Streamlit 운영 배포는 하지 않았습니다.

## 수다노트 저장 확인 결과

현재 코드 기준입니다. 운영 GitHub 저장소 조회는 연결 권한으로 접근되지 않아 실제 학생 파일의 존재나 최근 저장 성공 여부까지 확인하지 못했습니다. 조회 실패가 저장소나 데이터가 없다는 뜻은 아닙니다.

- 저장 대상 저장소: `jsku-sm/class-dashboard-data`
- 원본 CSV: `data/sudanotes/<학번>.csv`
- 자료함: `students/<학생 고유 해시>/sudanotes/<자료 ID 해시>/current.json.enc`
- 같은 자료의 암호화 변경 이력도 `history/`에 보관.
- 수다노트 제출은 `views/sudanote.py`에서 `record_core.checkpoint.append_confirmed`를 거칩니다. 저장 확인 실패 시 입력을 유지하고 재시도를 제공합니다.
- `storage.py`는 원본 CSV와 학생별 자료함을 연결합니다.
- 생기부 생성기의 자료 불러오기는 `RecordService.sync` → `RecordService.load` → `record_core.evidence.project`를 통해 수다노트 질문 1~5 응답을 근거 목록에 넣습니다. 과목·작성 기간 필터가 적용됩니다.

## 생기부 작성기 후속 반영

사용자가 확정한 학년도·학기·과목별 저장, 전체 자료 중 교사 선택, 학생별/선택 학생 일괄 AI 생성을 반영했습니다.
현재 진입점은 `record_core/writer_view.py`, 학기별 저장은 `record_core/semester.py`입니다.
항상 표시되는 생성 버튼, 교사 직접 수정, 전체 편집 표, 초안/완성본 저장 및 별도 CSV를 제공합니다.
자세한 사용법·검증·기재 지침 반영 상태는 `SCHOOL_RECORD_WRITER_UPDATE.md`를 참고하세요.

## 검증

공지 게시·학급 접근·팝업 확인·수정 공지 재노출·학생 홈·학생 자료함 관련 Python 검사 233개 통과. JavaScript 문법 검사 통과.
실제 브라우저의 화면 배치와 iPad 시각적 동작은 이 환경에서 확인하지 못했습니다. 배포 후 공지 한 건을 게시하여 가운데 정렬과 긴 본문 스크롤을 확인하세요.
