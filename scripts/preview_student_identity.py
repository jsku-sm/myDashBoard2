"""Read-only identity preview. There is deliberately no apply/migrate command."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from student_identity.preview import preview_snapshot


def main():
    parser = argparse.ArgumentParser(description='학생 식별 전환 검토용. 기존 파일을 변경하지 않습니다.')
    parser.add_argument('--snapshot', required=True, type=Path, help='비공개 데이터 저장소의 로컬 사본')
    parser.add_argument('--year', required=True, type=int, help='확인된 기존 자료 학년도: 2026')
    parser.add_argument('--output', required=True, type=Path, help='사본 밖의 새 JSON 파일')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(args.snapshot.resolve()):
        parser.error('출력은 원본 사본 폴더 밖에 지정하세요.')
    try:
        plan = preview_snapshot(args.snapshot, args.year)
        with output.open('x', encoding='utf-8') as f:
            json.dump(plan, f, ensure_ascii=False, indent=2)
            f.write('\n')
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
    print('검토용 대응표를 작성했습니다. 원본 변경 없음 · 운영 적용 불가 · 별도 검증과 승인 필요')


if __name__ == '__main__':
    main()
