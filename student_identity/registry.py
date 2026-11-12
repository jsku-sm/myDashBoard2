"""Pure identity and yearly-enrolment rules for a separately approved migration.

No storage, Streamlit, credentials or network access. Returned objects are drafts;
using this module does not activate a new login or rewrite any learning record.
"""
from copy import deepcopy
import uuid


class IdentityError(ValueError):
    pass


def _year(value):
    if type(value) is not int or not 2000 <= value <= 2099:
        raise IdentityError('학년도를 2000~2099 사이의 정수로 지정하세요.')
    return value


def _number(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        raise IdentityError('학번을 문자열로 지정하세요. 앞자리 0을 유지해야 합니다.')
    return value.strip()


def validate(registry):
    if registry.get('schema') != 1 or registry.get('activation') != 'preview_only':
        raise IdentityError('검토용 학생 식별자 자료가 아닙니다.')
    students, enrolments = registry.get('students'), registry.get('enrolments')
    if not isinstance(students, dict) or not isinstance(enrolments, list):
        raise IdentityError('학생 대응표 형식을 확인하세요.')
    if any(not isinstance(s, dict) for s in students.values()):
        raise IdentityError('학생 대응표의 항목 형식을 확인하세요.')
    legacy = [s.get('legacy_storage_id') for s in students.values() if s.get('legacy_storage_id')]
    if len(legacy) != len(set(legacy)):
        raise IdentityError('하나의 기존 계정이 여러 학생에게 연결되어 있습니다.')
    bindings, memberships = set(), set()
    for e in enrolments:
        if not isinstance(e, dict):
            raise IdentityError('재학 정보의 항목 형식을 확인하세요.')
        year, number = _year(e.get('academic_year')), _number(e.get('school_number'))
        if e.get('student_uid') not in students or e.get('status') not in ('active', 'archived'):
            raise IdentityError('재학 정보의 학생 연결을 확인하세요.')
        binding, membership = (year, number), (year, e['student_uid'])
        if binding in bindings or membership in memberships:
            raise IdentityError('같은 학년도의 학번 또는 학생 연결이 중복되어 있습니다.')
        bindings.add(binding); memberships.add(membership)
    return registry


def prepare_legacy(users, academic_year):
    """Deterministic draft UIDs; retain legacy IDs as aliases, never rewrite them."""
    _year(academic_year)
    result = dict(schema=1, activation='preview_only', legacy_academic_year=academic_year,
                  students={}, enrolments=[], unchanged_teacher_ids=[])
    seen = set()
    for user in users:
        sid = _number(user.get('id'))
        if sid in seen:
            raise IdentityError('기존 명단의 계정 ID가 중복되어 있습니다.')
        seen.add(sid)
        if user.get('role') == 'teacher':
            result['unchanged_teacher_ids'].append(sid)
            continue
        if user.get('role') != 'student':
            raise IdentityError('기존 계정의 역할을 확인하세요.')
        uid = 'stu_' + uuid.uuid5(uuid.NAMESPACE_URL,
            f'goodmath:jsku-sm/class-dashboard-data:legacy:{academic_year}:{sid}').hex
        result['students'][uid] = dict(legacy_storage_id=sid, name=str(user.get('name', '')))
        result['enrolments'].append(dict(student_uid=uid, academic_year=academic_year,
            school_number=sid, class_name=str(user.get('class', '')), status='active'))
    return validate(result)


def resolve_student(registry, academic_year, school_number):
    """Exact year+number only. A previous-year account is never a fallback."""
    validate(registry)
    year, number = _year(academic_year), _number(school_number)
    found = next((e for e in registry['enrolments'] if e['academic_year'] == year
                  and e['school_number'] == number and e['status'] == 'active'), None)
    if found is None:
        raise IdentityError('해당 학년도에 등록된 학생이 아닙니다.')
    return found['student_uid']


def enrol_student(registry, academic_year, school_number, class_name, *, student_uid=None, name=''):
    """New entrant gets a new UID; promotion explicitly reuses the person's UID."""
    validate(registry)
    year, number = _year(academic_year), _number(school_number)
    if number in registry.get('unchanged_teacher_ids', []):
        raise IdentityError('교사 계정 ID를 학생 학번으로 사용할 수 없습니다.')
    if any(e['academic_year'] == year and e['school_number'] == number for e in registry['enrolments']):
        raise IdentityError('이미 사용한 학년도·학번입니다. 다른 사람에게 재배정하지 않습니다.')
    result = deepcopy(registry)
    if student_uid is None:
        student_uid = 'stu_' + uuid.uuid4().hex
        result['students'][student_uid] = dict(legacy_storage_id=None, name=str(name))
    elif student_uid not in result['students']:
        raise IdentityError('진급 연결할 기존 학생이 없습니다.')
    result['enrolments'].append(dict(student_uid=student_uid, academic_year=year,
        school_number=number, class_name=str(class_name), status='active'))
    validate(result)
    return result, student_uid
