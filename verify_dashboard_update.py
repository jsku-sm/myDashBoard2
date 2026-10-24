"""Check the uploaded files using only Python's standard library. No network/Secrets."""
from __future__ import annotations
import hashlib
import json
import sys
from pathlib import Path


def main(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parent
    manifest = root / "FINAL5_CHANGE_MANIFEST.json"
    if not manifest.is_file():
        print("확인표가 없습니다. 이번 수정 ZIP의 내용을 app.py와 같은 위치에 올려 주세요.")
        return 1
    data = json.loads(manifest.read_text(encoding="utf-8"))
    errors=[]
    for entry in data["changes"]:
        path=root/entry["path"]
        if not path.is_file(): errors.append(entry["path"]+" : 파일 없음")
        elif hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
            errors.append(entry["path"]+" : 배포한 수정본과 내용이 다름 (직접 수정 여부 확인)")
    print(data["version"])
    if errors:
        print("\n".join(errors))
        print("Secrets·학생 데이터는 이 검사에서 읽거나 변경하지 않습니다.")
        return 1
    print(f"수정 파일 {len(data['changes'])}개 일치")
    print("app.py와 streamlit_app.py 모두 같은 새 로그인/생기부 화면으로 연결됩니다.")
    print("파일 검사 완료이며, 원격 GitHub·OpenAI·실제 Streamlit 실행 검증은 별도입니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
