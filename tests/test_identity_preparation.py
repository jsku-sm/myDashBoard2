import copy
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pytest
from student_identity.registry import prepare_legacy, resolve_student, enrol_student, validate, IdentityError
from student_identity.preview import preview_snapshot

USERS = [dict(id='teacher', role='teacher', pw_hash='private-hash'),
         dict(id='10101', role='student', name='가상학생', **{'class': '1-1'}, pw_hash='another-private-hash')]


def test_bootstrap_is_stable_non_mutating_and_keeps_teacher_and_legacy_ids():
    before = copy.deepcopy(USERS)
    r = prepare_legacy(USERS, 2026)
    uid = resolve_student(r, 2026, '10101')
    assert uid == resolve_student(prepare_legacy(USERS, 2026), 2026, '10101')
    assert r['students'][uid]['legacy_storage_id'] == '10101'
    assert r['unchanged_teacher_ids'] == ['teacher']
    assert 'private-hash' not in json.dumps(r) and USERS == before


def test_next_year_same_number_is_new_person_and_promotion_keeps_identity():
    first = prepare_legacy(USERS, 2026)
    original = resolve_student(first, 2026, '10101')
    with pytest.raises(IdentityError): resolve_student(first, 2027, '10101')
    second, new = enrol_student(first, 2027, '10101', '1-1', name='다른 가상학생')
    assert new != original and resolve_student(second, 2027, '10101') == new
    promoted, uid = enrol_student(second, 2027, '20101', '2-1', student_uid=original)
    assert uid == original == resolve_student(promoted, 2027, '20101')
    assert resolve_student(promoted, 2026, '10101') == original
    assert len(first['enrolments']) == 1


def test_no_same_year_reuse_even_after_archive_and_no_teacher_fallback():
    r = prepare_legacy(USERS, 2026)
    r['enrolments'][0]['status'] = 'archived'
    with pytest.raises(IdentityError): enrol_student(r, 2026, '10101', '1-1')
    with pytest.raises(IdentityError): resolve_student(r, 2026, '10101')
    with pytest.raises(IdentityError): resolve_student(r, 2026, 'teacher')
    with pytest.raises(IdentityError): resolve_student(r, 2026, 10101)
    assert resolve_student(prepare_legacy([dict(id='00101', role='student')], 2026), 2026, '00101')


def test_duplicate_students_and_year_binding_fail_closed():
    with pytest.raises(IdentityError): prepare_legacy(USERS + [USERS[1]], 2026)
    r = prepare_legacy(USERS, 2026); r['enrolments'].append(copy.deepcopy(r['enrolments'][0]))
    with pytest.raises(IdentityError): validate(r)


def snapshot(tmp_path):
    root = tmp_path / 'source'; (root / 'data').mkdir(parents=True)
    with (root / 'data/users.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'role', 'name', 'class', 'pw_hash'])
        w.writeheader(); w.writerows(USERS)
    (root / 'data/sudanotes.csv').write_text('id,student_id,q1\na,10101,가상 기록\nb,10999,미등록 학생의 가상 기록\n')
    (root / 'data/game_profiles.csv').write_text('id,student_id,state_json\ng,10101,{}\n')
    (root / 'think-learning-v1').mkdir()
    (root / 'think-learning-v1/state.enc').write_bytes(b'not-decrypted')
    (root / 'think-learning-v1/.encryption.key').write_bytes(b'must-never-copy-this-key')
    return root


def hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}


def test_preview_preserves_files_and_reports_orphans_and_uninspected_payloads(tmp_path):
    root = snapshot(tmp_path); before = hashes(root)
    p = preview_snapshot(root, 2026)
    assert p['orphan_student_ids'] == ['10999'] and p['can_apply'] is False
    assert p['encrypted_file_count'] == 1 and p['embedded_json_columns']
    assert 'must-never-copy-this-key' not in json.dumps(p)
    assert 'private-hash' not in json.dumps(p) and before == hashes(root)


def test_cli_cannot_apply_overwrite_or_write_into_snapshot(tmp_path):
    root = snapshot(tmp_path); before = hashes(root)
    script = Path(__file__).resolve().parents[1] / 'scripts/preview_student_identity.py'
    args = [sys.executable, str(script), '--snapshot', str(root), '--year', '2026', '--output']
    dest = tmp_path / 'plan.json'
    assert subprocess.run(args + [str(dest)], capture_output=True).returncode == 0
    plan = dest.read_bytes()
    assert subprocess.run(args + [str(dest)], capture_output=True).returncode != 0
    assert subprocess.run(args + [str(root / 'new.json')], capture_output=True).returncode != 0
    assert subprocess.run(args + [str(tmp_path / 'apply.json'), '--apply'], capture_output=True).returncode != 0
    assert hashes(root) == before and dest.read_bytes() == plan


def test_linked_snapshot_is_rejected(tmp_path):
    root = snapshot(tmp_path)
    (root / 'data/link.csv').symlink_to(tmp_path / 'unrelated')
    with pytest.raises(IdentityError): preview_snapshot(root, 2026)
