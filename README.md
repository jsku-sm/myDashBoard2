# 📐 구쌤의 수학 교실 — 수업용 대시보드

Streamlit으로 만든 수업용 웹앱입니다.
**코드**는 공개 저장소에, **학생 데이터와 업로드 파일**은 별도의 **비공개 깃허브 저장소**에 자동으로 저장됩니다.
구글이나 Supabase 같은 다른 서비스는 필요 없습니다.

```
[공개] class-dashboard        ← 이 코드 (Streamlit Cloud가 여기서 앱을 실행)
[비공개] class-dashboard-data ← 앱이 데이터를 자동 저장 (학생 정보 보호)
```

## 폴더 구성

코드 저장소의 **맨 위(root)** 에 아래 파일들이 바로 보이도록 올려 주세요.

```
.streamlit/config.toml           테마, 업로드 크기 제한(10MB)
.streamlit/secrets.toml.example  비밀 설정 예시
views/                           메뉴별 화면
.gitignore
assets/profile.png               '선생님 소개' 프로필 사진
app.py  auth.py  config.py  realtime.py  storage.py  ui.py
profile_data.py                  '선생님 소개' 화면의 글 내용
requirements.txt  students_template.csv  README.md
```

> 💡 `.streamlit`, `.gitignore`는 이름이 점(.)으로 시작하는 숨김 항목이라 빠뜨리기 쉽습니다.
> - 윈도우: 탐색기에서 **보기 → 숨긴 항목**을 켜세요.
> - 맥: Finder에서 `Command + Shift + .`을 누르세요.

---

## 1단계. 데이터용 비공개 저장소 만들기

1. 깃허브 오른쪽 위의 **+ → New repository**를 누릅니다.
2. Repository name에 `class-dashboard-data`를 입력합니다.
3. **Private**을 꼭 선택합니다.
   - 공개 저장소면 앱이 학생 정보 보호를 위해 실행을 멈춥니다.
4. **Create repository**를 누릅니다.
   - 빈 저장소여도 괜찮습니다. 앱이 처음 실행될 때 자동으로 준비합니다.

## 2단계. 토큰 만들기 (앱이 데이터 저장소에 쓸 수 있는 열쇠)

1. 깃허브 오른쪽 위 프로필 사진을 누르고 **Settings**로 들어갑니다.
2. 왼쪽 맨 아래 **Developer settings → Personal access tokens → Fine-grained tokens**로 이동합니다.
3. **Generate new token**을 누르고 아래와 같이 설정합니다.

   | 항목 | 설정 |
   |---|---|
   | Token name | `class-dashboard` |
   | Expiration | 원하는 기간 (예: 1년. 만료되면 새로 만들어 교체) |
   | Repository access | **Only select repositories** → `class-dashboard-data`만 선택 |
   | Permissions → Repository permissions → **Contents** | **Read and write** |

4. **Generate token**을 누르고 `github_pat_...`로 시작하는 토큰을 복사해 둡니다.
   - 이 화면을 벗어나면 다시 볼 수 없습니다.

> ⚠️ 토큰은 비밀번호와 같습니다. 코드나 README에 적지 말고 **Streamlit Secrets에만** 넣으세요.

## 3단계. 코드 저장소 만들고 올리기

1. 새 저장소 `class-dashboard`를 만듭니다. 공개(Public)여도 괜찮습니다.
2. 이 폴더의 **내용물**을 저장소 root에 올립니다.

## 4단계. Streamlit Cloud에 배포

1. [share.streamlit.io](https://share.streamlit.io)에 깃허브 계정으로 로그인합니다.
2. **Create app → Deploy a public app from GitHub**를 선택합니다.
   - Repository: `내아이디/class-dashboard`
   - Branch: `main`
   - Main file path: `app.py`
3. **Advanced settings → Secrets** 칸에 아래를 붙여 넣고 값을 바꿉니다.

```toml
[app]
storage = "github"
teacher_id = "teacher"
teacher_password = "처음-쓸-비밀번호"

[github]
token = "github_pat_복사한토큰"
repo = "내깃허브아이디/class-dashboard-data"
branch = "main"
```

4. **Deploy**를 누릅니다.

이미 배포한 앱이라면 **Manage app → ⋮ → Settings → Secrets**에서 수정한 뒤 **Reboot app**을 누르세요.

## 5단계. 처음 사용하기

1. 교사 아이디와 secrets에 적은 비밀번호로 로그인합니다.
2. **교사전용 → 학생 명단**에서 `students_template.csv` 양식대로 명단을 올립니다.
   - 엑셀(.xlsx)도 됩니다.
3. 학생은 학번으로 로그인합니다.
   - 처음 비밀번호도 학번입니다.
   - 첫 로그인 때 새 비밀번호로 바꿔야 들어갈 수 있습니다.

---

## 첫 화면에서 넘어가지 않을 때

| 화면에 보이는 것 | 해결 방법 |
|---|---|
| "설정을 확인해 주세요" + 토큰 오류 | 토큰을 다시 복사해 Secrets에 넣고 Reboot |
| "저장소를 찾을 수 없어요" | `repo` 값이 `아이디/저장소이름` 형식인지, 토큰에 그 저장소를 선택했는지 확인 |
| "공개(Public) 상태예요" | 데이터 저장소 **Settings → Danger Zone → Change visibility → Private** |
| "쓰기 권한이 없어요" | 토큰의 **Contents** 권한을 **Read and write**로 수정 |
| 로그인 화면에 "시험 모드" 경고 | Secrets에 `storage = "github"`가 빠졌어요 |
| 교사 로그인이 안 됨 | secrets의 `teacher_id` / `teacher_password` 확인. 교사 계정은 **처음 실행할 때 한 번만** 이 값으로 만들어지므로, 이미 만들어진 뒤에 secrets를 바꿔도 반영되지 않아요. 이 경우 데이터 저장소의 `data/users.csv`에서 교사 줄을 지우고 Reboot 하면 다시 만들어집니다 |

---

## 데이터는 어떻게 저장되나요?

- 앱이 켜질 때 데이터 저장소의 내용을 한 번 불러옵니다.
- 그 뒤 생긴 변경 사항은 **8초마다 모아서 커밋 1개**로 저장합니다.
  - 학생 30명이 동시에 저장해도 빠르고 서로 충돌하지 않습니다.
- 교사 사이드바에서 "모두 저장됨 / 저장 대기 n건"을 확인할 수 있습니다.
- **교사전용 → 설정 → 지금 바로 저장하기**로 즉시 저장할 수도 있습니다.

데이터 저장소 안의 모습:

```
data/users.csv                학생·교사 계정 (비밀번호는 암호화된 값만 저장)
data/emotions/2026-10.csv     감정 기록 (월별 파일)
data/logins/2026-10.csv       로그인 기록 (월별 파일)
data/submissions.csv          학급 게시판 결과물 + 자동 피드백
data/questions.csv            질문 게시판
data/materials.csv            평가계획·학습지 목록
data/observations.csv         관찰기록
data/points.csv               상점·벌점
data/records.csv              생기부 생성기에서 저장한 세특 (교사만)
data/sudanotes/10101.csv      수다노트 (학생별 파일: 날짜·시간·학번·이름·과목·질문1~5 답)
data/settings.csv             소개 문구, 링크, 피드백 문구 등
files/2026-10/...             업로드한 파일 원본
```

> **데이터 저장소의 파일을 깃허브에서 직접 고칠 때**
> 1. 먼저 앱을 Reboot 합니다. 앱은 켜질 때만 데이터를 불러오기 때문이에요.
> 2. 앱이 켜져 있는 동안 직접 고치면, 다음 자동 저장 때 앱의 내용으로 덮어써질 수 있습니다.

---

## (선택) 생기부 생성기에서 ChatGPT 쓰기

교사전용 → 📝 생기부 생성기는 학생의 **수다노트·관찰기록·질문 게시판 질문**을 모아 교과세특(300~400자) 초안을 만듭니다.

**방법 1. 버튼 한 번으로 초안 만들기 (OpenAI API, 유료)**
1. [platform.openai.com](https://platform.openai.com)에 로그인합니다.
2. **Billing**에서 결제 수단을 등록하고 소액을 충전합니다.
   - ChatGPT Plus 구독과는 **별개**예요. 구독 중이어도 API는 따로 결제해야 합니다.
3. **API keys → Create new secret key**를 눌러 `sk-...` 키를 복사합니다.
4. Streamlit Secrets에 아래를 추가하고 Reboot 합니다.
   ```toml
   [openai]
   api_key = "sk-..."
   model = "gpt-4o-mini"
   ```

**방법 2. 무료로 쓰기 (API 없이)**
- 학생별 작성 화면의 **📋 프롬프트 복사**를 누릅니다.
- 복사한 내용을 [chatgpt.com](https://chatgpt.com)에 붙여 넣고, 받은 결과를 다시 세특 칸에 붙여 넣으면 됩니다.

**개인정보 보호**
- AI에 보내는 자료에서 학생 이름은 '학생', 같은 반 친구 이름은 '친구'로 바뀝니다.
- 학번도 보내지 않습니다.
- 보내는 내용은 **📂 AI에 보내는 기초자료 보기**에서 미리 확인할 수 있어요.

**작성과 저장**
- 초안은 참고용입니다. **사실 확인과 최종 문장은 반드시 선생님이** 결정해 주세요.
- 글자 수와 나이스 바이트 수를 세어 주고, 아래 항목이 있으면 경고합니다.
  - 금지·주의 표현
  - 영문 표기
  - 다른 학생과 비슷한 문장
- 금지 표현과 문체 예시는 생성기의 **⚙️ 작성 규칙**에서 학교 지침에 맞게 고칠 수 있습니다.
- '한꺼번에 만들기'는 이미 저장된 세특을 **덮어쓰지 않습니다.**
- 저장한 세특은 학급별 CSV로 내려받아 나이스에 붙여 넣을 수 있습니다.

## 사용 안내

| 기능 | 위치 |
|---|---|
| 감정·접속 현황 (교사만) | 대시보드 |
| 학습지·평가계획 올리기 | 공통수학1·2 탭 |
| 학생 결과물 확인·한마디 | 공통수학 → 학급 게시판 |
| 질문 답변 | 공통수학 → 질문 게시판 |
| 화면 잠금/해제 | 교사전용 → 🔒 화면 잠금 (학급 선택 가능). 잠금 중이면 사이드바에 '모두 잠금 해제' 버튼이 생김 |
| 관찰기록·상벌점·생기부 생성기·명단·설정 | 교사전용 |
| 도구 링크 | 수업도구 화면의 ⚙️ 펼치기 |
| 수다노트 확인·CSV 내려받기 | 4. 수다노트 (교사로 들어가면 학급·날짜별 제출 현황과 학생별 모아 보기) |
| '선생님 소개' 내용·사진 | 코드 저장소의 `profile_data.py`, `assets/profile.png`를 깃허브에서 고치기 |
| 마. 앱 (by 구쌤) 목록 | 수업도구 → ⚙️ 링크 고치기 (`학습 주제|주소` 한 줄씩) |

## 알아 둘 점

**반응 속도**
- 학생 화면은 4초마다 상태를 확인합니다.
- 그래서 잠금, 폭죽, 벌점 안내가 몇 초 늦게 나타납니다.

**잠금 범위**
- 잠금은 **이 앱 안에서만** 적용됩니다.
- 학생이 따로 열어 둔 다른 사이트 탭은 잠그지 못합니다.

**접속 상태**
- 학생이 창을 닫으면 약 1분 30초 뒤 '미접속'으로 바뀝니다.

**앱이 재시작될 때**
- 잠금 상태와 '접속 중' 정보는 초기화됩니다(잠금 해제 상태).
- 기록 데이터는 깃허브에 남습니다.
- 다만 마지막 저장 후 몇 초 안에 생긴 변경은 사라질 수 있습니다.

**알림을 놓치는 경우**
- 학생이 접속하지 않았을 때 준 상벌점은 기록에는 남지만, 폭죽이나 안내 창은 뜨지 않을 수 있습니다.

**업로드와 새로고침**
- 업로드는 파일당 **10MB**까지입니다.
- 브라우저를 새로고침하면 다시 로그인해야 합니다.

**앱이 잠들었을 때**
- 며칠 동안 아무도 접속하지 않으면 앱이 잠들고, 깨우는 데 30초쯤 걸립니다.
- 수업 전에 한 번 열어 두세요.

## 내 컴퓨터에서 시험해 보기 (선택)

```bash
pip install -r requirements.txt
streamlit run app.py
```

- secrets가 없으면 `data/` 폴더에 저장되는 **시험 모드**로 실행됩니다.
- 교사 계정은 `teacher` / `teacher1234`입니다.
