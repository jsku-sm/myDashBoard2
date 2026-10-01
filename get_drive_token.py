"""개인 지메일 드라이브용 refresh_token 발급 도우미 (내 컴퓨터에서 한 번만 실행)

준비: 구글 클라우드 콘솔 > API 및 서비스 > 사용자 인증 정보 > 'OAuth 클라이언트 ID'(데스크톱 앱) 생성 후
      JSON 을 내려받아 이 파일과 같은 폴더에 client_secret.json 으로 저장하세요.
실행: pip install google-auth-oauthlib
      python get_drive_token.py
결과로 나온 세 값을 secrets 의 [gdrive_oauth] 에 붙여 넣으면 됩니다.
"""
import json

from google_auth_oauthlib.flow import InstalledAppFlow

flow = InstalledAppFlow.from_client_secrets_file(
    "client_secret.json", scopes=["https://www.googleapis.com/auth/drive.file"])
creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
info = json.load(open("client_secret.json"))
info = info.get("installed") or info.get("web")
print("\n[gdrive_oauth]")
print(f'client_id = "{info["client_id"]}"')
print(f'client_secret = "{info["client_secret"]}"')
print(f'refresh_token = "{creds.refresh_token}"')
