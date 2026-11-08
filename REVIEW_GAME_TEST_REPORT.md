# 전시학습 확인 변경 및 검증 기록

## 변경 범위

기준: 사용자가 첨부한 `myDashBoard2-main (6)(2).zip`.

| 파일 | 변경 |
|---|---|
| `views/tools.py` | 기존 퀴즈 분기 안에 교사 전용 하위 메뉴 추가 |
| `app.py` | 로그인과 권한 검사 이후 QR 참여 경로, 학생 참여코드 바로가기 |
| `storage.py` | 복습 테이블 등록·분할 저장·민감 데이터 접근 제한·학생 자료함 갱신 |
| `record_core/archive.py` | 학생 games 자료함에 복습 기록과 문제 세트 묶음 저장 |
| `record_core/evidence.py` | 복습 응답을 교사가 확인할 학습 근거로 연결 |
| `review_core/` | 게임 서버·문제 생성·교사 화면·JS/CSS 게임 UI 및 수식 자원 |
| `tests/test_review_games.py`, `tests/test_review_menu.py` | 게임 기능·권한·동시성·저장·메뉴 회귀 검사 |
| `README.md`, `REVIEW_GAME_GUIDE.md` | 새 기능 안내 |

실제 학생 계정·데이터·Secrets를 수정하지 않았습니다. ZIP에는 QA 전용 가상 계정 실행 파일, 임시 데이터, npm 설정, Python 캐시를 포함하지 않습니다. Blooket의 로고나 캐릭터 이미지를 복제하지 않았으며 UI는 자체 CSS·JS와 기기 이모지로 구성했습니다. 수식 표시용 KaTeX 0.16.22의 원래 라이선스를 vendor 폴더에 포함했습니다.

## 자동 검사

다음 명령에서 **326개 통과**. 실행 환경의 anyio/pytest 호환성 경고 1개가 있었으며 검사 실패는 없었습니다.

```bash
python -m pytest -q tests/test_review_games.py tests/test_review_menu.py tests/test_tools_menu.py tests/test_main_navigation.py tests/test_student_record_vault.py tests/test_game_learning.py
node --check review_core/frontend/game.js
python -m compileall -q app.py storage.py views/tools.py review_core record_core/archive.py record_core/evidence.py
```

주요 확인 항목:

- 5개 게임의 시작·제출·종료·정답/오답/미응답 집계.
- 25명 동시 입장·제출 모의 실행, 중복 탭 제출·보상 요청의 중복 점수 방지.
- 교사 전용 메뉴, 다른 교사의 방 접근 차단, 학생의 전체 답안·다른 학생 상세 정보 접근 차단.
- 학급 대상 제한, 계정 권한 재확인, 비밀번호 변경 필요 계정·학급 잠금 처리.
- 서버 제한시간 이후 제출 거부, 진행 중 신규 입장 차단, 기존 학생 재접속.
- 팀 균형 배정, 공동 순위, 문제별 응답 분포, 함께 풀기·정답 공개 전환.
- 서버 저장 자료를 다시 불러왔을 때 문제·응답·결과 유지.
- 원격 API를 대체한 시험 환경에서 실제 GitHubBackend 일괄 저장과 학생 암호화 묶음 생성. 저장 실패 시 성공으로 표시하지 않고 다음 시도에서 반영.
- 파일 추출·입력 검증, AI 요청 구조와 자료 전달 계약, CSV 수식 실행 방지.

이는 동시성 기능 검사이며 실제 교실 네트워크에서 25명이 접속하는 부하 시험은 아닙니다. AI 생성 검사는 모의 응답을 사용했습니다.

## 브라우저 확인

로컬 Streamlit 앱에서 교사 1명, 가상 학생 2명의 별도 브라우저 탭으로 확인했습니다.

1. 기본 문제은행 → 문항 검토 → 방 생성 → QR·참여코드 표시.
2. 학생 대기실 → 교사 시작 → 학생 화면 전환.
3. 정답·오답 제출, 보물상자 보상, 교사 진행 상황 반영.
4. 교사 종료 → 학급 순위·개인 정답/오답/미응답 구분.
5. 오답 문제 공동 열람과 정답·해설 공개.
6. 저장된 방 다시 열기, 전체화면 확대 및 원래 화면 복귀.

검증 데이터: 학생 A는 2문제 중 정답 1·오답 1·미응답 0, 학생 B는 정답 0·오답 1·미응답 1. 화면의 학급 합계와 개인 결과가 일치했습니다. 가상 학생 기록은 배포 ZIP에 포함하지 않았습니다.

실제 사용자 로그인, 실제 OpenAI 호출, 실제 비공개 GitHub 저장소, 실제 Streamlit Cloud 배포, iPad Safari 기기 실행은 이 환경에서 확인하지 않았습니다. 처음 배포할 때 사용 안내의 시험 순서를 따라 확인하세요.

## 첨부 원본에서 이미 있던 검사 실패

범위를 넓혀 기존 `tests/test_concept_quiz.py`를 실행했을 때 아래 5개가 실패했습니다. 동일 파일을 수정하지 않은 첨부 원본에 실행해도 같은 실패가 재현되어 이번 변경에서는 관련 코드를 수정하지 않았습니다.

- `test_real_github_flush_batches_student_files_without_network`
- `test_failed_remote_save_not_reported_durable_and_release_not_leaked`
- `test_remote_rate_error_does_not_create_four_extra_commits`
- `test_pending_draft_and_new_publish_are_not_visible_to_students`
- `test_source_integration_and_no_classroom_resurrection`

앞의 4개는 기존 시험용 GitHub 모형에 현재 저장 계층이 요구하는 암호화 자료함 설정이 없는 문제입니다. 마지막은 원본에 존재하는 `classroom_core` 폴더가 없어야 한다는 오래된 검사 조건입니다. 위 326개 통과를 저장소 전체 검사의 통과로 해석하지 않습니다.
