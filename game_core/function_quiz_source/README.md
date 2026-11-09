# 함수 개념퀴즈 원본 및 재생성

사용자가 제공한 `function-explorer-app-main.zip`의 개념퀴즈를 Streamlit 대시보드에 통합했습니다.

이 폴더의 `quiz-levels.js`, `quiz-generator.js`, `practice-random.js`는 첨부 앱의 동명 파일을 그대로 복사한 것입니다. `export-bank.mjs`는 단계·주제별 유일한 문항 변형을 추출하여 Python 서버에서 채점할 수 있는 JSON을 만듭니다.

프로젝트 루트에서 다음 명령으로 문제은행을 다시 만들 수 있습니다.

```sh
node game_core/function_quiz_source/export-bank.mjs
```

일반적인 Streamlit 실행에는 Node.js가 필요하지 않습니다. 이미 생성된 `game_core/function_quiz_bank.json`을 읽습니다. 정답이 포함된 문제은행을 브라우저 정적 파일 폴더로 옮기지 마세요.

`function_quiz_frontend/quiz-timer.js`는 원본을 그대로 사용하고, `quiz-math.js`는 KaTeX를 동봉된 브라우저 파일에서 읽도록 import 부분만 조정했습니다. 프런트엔드 화면 및 Streamlit 통신, 서버 채점, 기존 계정 저장 연동은 이번 통합을 위해 작성했습니다.

수식 렌더러 KaTeX 0.16.22와 글꼴은 기존 대시보드의 `review_core`에 동봉된 배포본을 복사했습니다. 라이선스는 `function_quiz_frontend/vendor/LICENSE`에 있습니다.
