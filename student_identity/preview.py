"""Inventory a local DATA repository snapshot. No live writes or decryption."""
import csv
import hashlib
import io
from pathlib import Path
from .registry import prepare_legacy, IdentityError

ROOTS = ('data', 'files', 'goodteacher', 'students', 'think-learning-v1', 'student-vault-v1')


def preview_snapshot(snapshot, academic_year):
    root = Path(snapshot).resolve()
    source = root / 'data/users.csv'
    if not source.is_file() or source.is_symlink():
        raise IdentityError('데이터 저장소 사본의 data/users.csv가 필요합니다.')
    raw = source.read_bytes()
    users = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    registry = prepare_legacy(users, academic_year)
    known = {s['legacy_storage_id'] for s in registry['students'].values()}
    inventory, orphans, json_columns, encrypted = [], set(), set(), 0
    for directory in ROOTS:
        base = root / directory
        if base.is_symlink():
            raise IdentityError('연결된 폴더 대신 실제 파일로 된 사본을 사용하세요.')
        if not base.exists():
            continue
        for path in sorted(base.rglob('*')):
            if path.is_symlink():
                raise IdentityError('사본에 심볼릭 링크가 있습니다. 원본은 변경하지 않았습니다.')
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            if path.name == '.encryption.key':
                # Record its presence without reading or copying secret material.
                inventory.append(dict(path=relative, kind='key_file_not_read'))
                continue
            content = path.read_bytes()
            entry = dict(path=relative, bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
            if path.suffix == '.enc':
                encrypted += 1
                entry['inspection'] = 'encrypted_content_not_inspected'
            if path.suffix == '.csv':
                reader = csv.DictReader(io.StringIO(content.decode('utf-8-sig')))
                rows = list(reader)
                entry['rows'] = len(rows)
                for row in rows:
                    sid = (row.get('student_id') or '').strip()
                    if sid and sid not in known:
                        orphans.add(sid)
                json_columns.update(relative + ':' + col for col in (reader.fieldnames or []) if col.endswith('_json'))
            inventory.append(entry)
    blockers = ['운영 데이터 이전과 로그인 연결은 별도 승인 후 구현·적용해야 합니다.']
    if not known:
        blockers.append('학생 명단이 비어 있습니다.')
    if orphans:
        blockers.append('현재 명단에 없는 학생 ID의 기록이 있습니다. 삭제하지 말고 대응 관계를 확인하세요.')
    if encrypted:
        blockers.append('암호화 자료의 내부 학생 연결과 첨부·이력을 아직 검증하지 않았습니다.')
    if json_columns:
        blockers.append('JSON 안의 참여 대상·응답·수업 회원 연결을 추가 검증해야 합니다.')
    return dict(schema=1, mode='read_only_preview', academic_year=academic_year, can_apply=False,
                registry=registry, inventory=inventory, orphan_student_ids=sorted(orphans),
                embedded_json_columns=sorted(json_columns), encrypted_file_count=encrypted,
                blockers=blockers, original_files_changed=False)
