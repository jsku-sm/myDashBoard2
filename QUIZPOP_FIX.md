# 퀴즈 만들기 버튼 수정본

## 이번 수정

- `퀴즈 만들기` 버튼의 클릭을 직접 처리하도록 변경했습니다. 키보드 제출도 같은 처리를 사용하며, 생성 중 중복 클릭으로 요청을 추가하지 않습니다.
- 입력·AI 설정 오류를 버튼 바로 아래에 표시하고 그 위치로 이동합니다. 기존에는 안내가 설정 영역 위쪽에 있어 버튼을 보고 있을 때 놓칠 수 있었습니다.
- 생성 시작 시 로딩 화면으로 이동합니다. 서버 실패 메시지도 Streamlit 화면에 함께 표시합니다.
- 기존 `[school_record_ai]`와 `[snorkl]`에만 API 키가 있을 때 퀴즈가 키를 찾지 못하는 경우를 재현하고 수정했습니다. `[openai]`, 최상위 `OPENAI_API_KEY`, 환경변수도 지원합니다.
- 키가 있는 구역의 모델을 함께 사용합니다. `[quiz_ai] model`로 퀴즈 모델만 따로 지정할 수 있습니다.
- API 키 인증, 모델 권한, 사용 한도, 요청 오류, 연결·시간 초과를 구별해 표시합니다. 원본 API 오류나 비밀키는 브라우저에 보내지 않습니다.
- 서버 응답 대기는 150초, 화면 대기는 180초로 맞추었습니다. 실패 시 임의의 다른 모델로 재호출하거나 유료 요청을 자동 반복하지 않습니다. 원본의 중복 문항 재출제는 유지합니다.

배포 앱의 로그와 실제 Secrets를 읽은 것은 아니므로, 선생님 화면에서 발생한 원인을 하나로 확정하지는 않았습니다. 이 수정본은 확인된 설정 누락과 무반응으로 보일 수 있는 클릭·오류 안내 처리를 함께 보완합니다.

## 적용

1. `quizpop_generation_fix.zip`을 내려받아 압축을 풉니다.
2. **코드 저장소 `jsku-sm/myDashBoard2`**에서 `app.py`가 보이는 첫 화면을 엽니다.
3. Add file → Upload files에서 압축을 푼 **`quiz_pop` 폴더 자체**를 끌어 놓습니다. 경로가 `quiz_pop/api.py`, `quiz_pop/frontend/index.html`처럼 표시되어야 합니다.
4. Commit changes 후 Streamlit 앱을 Reboot하고 브라우저를 새로고침합니다.
5. 교사 로그인 → 5. 수업도구 → 4. 퀴즈에서 3문항으로 생성해 봅니다. `퀴즈 AI 연결 설정`에서 읽은 API 설정 위치와 모델을 볼 수 있습니다.

기존 `quiz_pop` 폴더를 삭제할 필요는 없습니다. 같은 경로 파일을 덮어씁니다. ZIP 자체를 GitHub에 올리는 방식은 적용되지 않습니다. 이 파일은 코드 저장소용이며 **학생 데이터 저장소에는 올리지 않습니다.**

수정 가능한 원본과 검사 코드를 포함한 전체 대시보드는 `myDashBoard2_quizpop_updated.zip`입니다. 작은 수정 ZIP에는 실행에 필요한 퀴즈 폴더만 담았습니다. npm 명령은 Streamlit 배포에 필요하지 않습니다.

## 학생 데이터 저장 위치

학생 퀴즈의 생성·재개·저장은 **`jsku-sm/class-dashboard-data`에 연결된 기존 GitHub 저장 백엔드**를 사용합니다. 로컬 모드 또는 다른 저장소에서는 학생 퀴즈를 진행하지 않고 연결 안내를 표시합니다. 교사의 체험 기록은 학생 기록과 분리된 접속 세션에만 유지됩니다.

학생별 `game_profiles`의 기존 `state_json` 안에 `quiz_pop`을 저장하며, 기존 아바타·함수퀴즈·12종 게임 데이터는 보존합니다. 기존의 학생별 파일 경로와 암호화 자료함 복사 동작을 유지합니다. 저장 변경은 기존 대기열에서 모아 GitHub에 반영합니다. 화면 아래 `퀴즈 기록 GitHub 저장 확인` 버튼으로 대기 여부를 확인할 수 있습니다.

기존 Secrets에 아래 값이 맞게 들어 있으면 그대로 사용합니다. 이미 있는 구역을 중복 추가하지 말고 값을 확인하세요. **기존 토큰과 암호화키는 변경하지 않습니다.**

```toml
[app]
storage = "github"

[github]
repo = "jsku-sm/class-dashboard-data"
branch = "main"
# token과 암호화키는 현재 운영 설정을 그대로 유지
```

AI 키를 찾지 못했다는 안내가 나오면 Streamlit Settings → Secrets의 기존 `[quiz_ai]` 구역을 수정하거나, 없는 경우만 추가합니다.

```toml
[quiz_ai]
api_key = "본인의 OpenAI API 키"
model = "gpt-6-luna"
enabled = true
```

별도 설정이 없다면 키를 찾는 순서는 `[quiz_ai]` → `[openai]` → 최상위 Secrets → 서버 환경변수 → `[school_record_ai]` → `[snorkl]`입니다. 다른 AI 제공업체의 `base_url`로 설정된 키는 공식 OpenAI 주소로 재전송하지 않습니다.

## 확인 결과

- Python 검사 63개 통과: 생성 요청과 응답, 중복 요청 방지, 설정 재사용, 오류 안내, 학생 계정·학급 잠금·기록 유지, 저장소 제한, 메뉴 연결.
- 기존 JavaScript 검사 39개 통과.
- 실제 화면 코드의 DOM 검사 3가지 통과: 직접 클릭 → 요청 → 문항 표시, API 키 누락 안내, 성취기준 누락 안내. 모의 서버 응답을 사용했습니다.
- Vite 배포 빌드 완료. 기존 게임·로그인 코드 변경 없음.
- 실제 브라우저 시각 검사, 유료 AI 호출, 운영 데이터 저장소에 대한 쓰기는 수행하지 않았습니다. 연결된 GitHub 도구에서 비공개 데이터 저장소를 읽을 권한이 없어 실제 커밋 여부는 배포 앱에서 확인해야 합니다.

개발 검사: `python -m pytest -q tests/test_quiz_pop_component.py tests/test_quiz_pop.py tests/test_tools_menu.py tests/test_review_menu.py`; `quiz_pop/source`에서 `npm ci`, `npm test`, `npm run test:dashboard`, `npm run build`.
