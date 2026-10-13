"""Classroom management for the login-free Streamlit dashboard."""
from datetime import datetime, timezone, timedelta
import re
import uuid

from .storage import AppError

CLASSES = [f"{number}반" for number in range(1, 8)]
DASHBOARD_CLASSES = [f"1-{number}" for number in range(1, 8)]
COLORS = ["#e44768", "#d881e6", "#f5c64f", "#6284ee", "#55b98a", "#f18e4c", "#8b70dc"]
KST = timezone(timedelta(hours=9))


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


class CourseManager:
    def __init__(self, store):
        self.store = store

    def list_courses(self):
        courses = self.store.read().get("courses", {})
        return sorted(courses.values(), key=lambda course: course["updated"], reverse=True)

    def get(self, course_id):
        return self.store.read().get("courses", {}).get(course_id)

    def create(self, title, color, classes):
        values = self._validate(title, color, classes)
        course_id = uuid.uuid4().hex
        timestamp = now()
        course = {"id": course_id, **values, "created": timestamp, "updated": timestamp}

        def change(state):
            state.setdefault("courses", {})[course_id] = course

        self.store.transaction(change)
        return course_id

    def update(self, course_id, title, color, classes):
        values = self._validate(title, color, classes)

        def change(state):
            course = state.setdefault("courses", {}).get(course_id)
            if not course:
                raise AppError("수업을 찾을 수 없습니다.")
            course.update(values)
            course["updated"] = now()

        self.store.transaction(change)

    def delete(self, course_id):
        def change(state):
            if course_id not in state.setdefault("courses", {}):
                raise AppError("수업을 찾을 수 없습니다.")
            del state["courses"][course_id]

        self.store.transaction(change)

    def archive(self, course_id):
        archive = getattr(self.store, "save_course_archive", None)
        if archive is None:
            raise AppError("GitHub 보관은 THINK_MODE = \"github\"일 때 사용할 수 있습니다.")
        course = self.get(course_id)
        if not course:
            raise AppError("수업을 찾을 수 없습니다.")
        archive(course, now())
        self.delete(course_id)

    def list_archives(self):
        list_archives = getattr(self.store, "list_course_archives", None)
        if list_archives is None:
            raise AppError("GitHub 보관 파일을 불러오려면 THINK_MODE = \"github\"로 설정하세요.")
        return list_archives()

    def restore(self, archive_id):
        load_archive = getattr(self.store, "get_course_archive", None)
        if load_archive is None:
            raise AppError("GitHub 보관 파일을 불러오려면 THINK_MODE = \"github\"로 설정하세요.")
        course = load_archive(archive_id)["course"]
        values = self._validate(course.get("title"), course.get("color"), course.get("classes"))
        course_id = course.get("id")
        if not isinstance(course_id, str) or not re.fullmatch(r"[a-f0-9]{32}", course_id):
            raise AppError("보관 파일의 수업 식별자가 올바르지 않습니다.")

        def change(state):
            courses = state.setdefault("courses", {})
            if course_id in courses:
                raise AppError("같은 이름의 수업이 이미 진행 중입니다. 기존 수업을 삭제한 뒤 다시 시도하세요.")
            courses[course_id] = {
                "id": course_id,
                **values,
                "created": course.get("created", now()),
                "updated": course.get("updated", now()),
            }

        self.store.transaction(change)

    @staticmethod
    def _validate(title, color, classes):
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
            raise AppError("수업 이름을 1~120자로 입력하세요.")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise AppError("수업 색상을 확인하세요.")
        if not isinstance(classes, (list, tuple)) or not classes:
            raise AppError("참여할 수 있는 대상을 하나 이상 선택하세요.")
        if any(value not in CLASSES + DASHBOARD_CLASSES for value in classes) or len(set(classes)) != len(classes):
            raise AppError("참여할 수 있는 대상은 1반~7반 또는 1-1~1-7에서 선택하세요.")
        return {"title": title.strip(), "color": color.lower(), "classes": list(classes)}
