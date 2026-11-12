"""Canonical menu CSV paths. Logical table names stay stable for every reader."""
import hashlib
import re

FOLDERS = {'observations': 'observations', 'points': 'points', 'records': 'school_records'}
MENU_TABLES = frozenset(FOLDERS)


def student_path(table, row):
    key = hashlib.sha256(str(row.get('student_id', '')).encode('utf-8')).hexdigest()
    return f'data/{FOLDERS[table]}/{key}.csv'


def partition_table(path):
    for table, folder in FOLDERS.items():
        if re.fullmatch(r'data/' + folder + r'/[a-f0-9]{64}\.csv', path):
            return table
    return None


def merge_partitions(table, legacy, partitions):
    """A complete per-student snapshot wins even when it has zero rows.

    Legacy CSVs stay untouched as backups. Never union their rows into an
    existing partition: a removed observation/point must not reappear.
    """
    result = {}
    for row in legacy:
        if student_path(table, row) not in partitions:
            result[(row.get('student_id', ''), row['id'])] = row
    for path, rows in partitions.items():
        for row in rows:
            if student_path(table, row) != path:
                raise ValueError('학생별 저장 경로와 기록의 학번이 일치하지 않습니다. 원본을 보존하고 저장소를 확인하세요.')
            result[(row.get('student_id', ''), row['id'])] = row
    return list(result.values())
