"""Ownership checks for the authenticated dashboard's native Snorkl courses.

Unowned legacy records stay assigned to the original configured dashboard
teacher; reading never migrates or rewrites them.
"""
from .courses import CourseManager
from .storage import AppError


def legacy_teacher_id():
    import streamlit as st
    try:
        return str(st.secrets.get("app", {}).get("teacher_id", "teacher")).strip()
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return "teacher"


def owns_course(user, course):
    if not course or user.get("role") != "teacher":
        return False
    owner = course.get("owner_id") or course.get("creator") or legacy_teacher_id()
    return user.get("id") == owner or user.get("id") in course.get("shared_teachers", [])


class OwnedCourseManager(CourseManager):
    def __init__(self, store, user):
        super().__init__(store)
        self.user = user

    def _check(self, course):
        if not owns_course(self.user, course):
            raise AppError("이 소노클 수업을 관리할 권한이 없습니다.")
        return course

    def list_courses(self):
        return [c for c in super().list_courses() if owns_course(self.user, c)]

    def get(self, course_id):
        course = super().get(course_id)
        return self._check(course) if course else None

    def create(self, title, color, classes):
        if self.user.get("role") != "teacher":
            raise AppError("교사만 수업을 만들 수 있습니다.")
        import uuid
        from .courses import now
        course_id, timestamp = uuid.uuid4().hex, now()
        course = dict(id=course_id, **self._validate(title, color, classes),
                      created=timestamp, updated=timestamp, owner_id=self.user["id"])
        self.store.transaction(lambda state: state.setdefault("courses", {}).__setitem__(course_id, course))
        return course_id

    def update(self, course_id, title, color, classes):
        self._check(super().get(course_id))
        return super().update(course_id, title, color, classes)

    def delete(self, course_id):
        self._check(super().get(course_id))
        return super().delete(course_id)

    def list_archives(self):
        return [a for a in super().list_archives() if owns_course(self.user, a.get("course"))]

    def restore(self, archive_id):
        import re
        course = self._check(self.store.get_course_archive(archive_id).get("course"))
        values = self._validate(course.get("title"), course.get("color"), course.get("classes"))
        if not re.fullmatch(r"[a-f0-9]{32}", str(course.get("id", ""))):
            raise AppError("보관 파일의 수업 식별자를 확인하세요.")
        def preserve(state):
            courses = state.setdefault("courses", {})
            if course["id"] in courses:
                raise AppError("같은 수업이 이미 있습니다. 기존 수업을 확인하세요.")
            courses[course["id"]] = dict(course, **values,
                                        owner_id=course.get("owner_id") or course.get("creator") or legacy_teacher_id())
        self.store.transaction(preserve)
