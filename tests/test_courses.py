import base64
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

from think_app.courses import CourseManager
from think_app.storage import AppError, GitHubStore, MemoryStore


def test_course_lifecycle_and_validation():
    manager = CourseManager(MemoryStore())
    course_id = manager.create("수학 탐구", "#aabbcc", ["1반", "7반"])
    course = manager.get(course_id)
    assert course["title"] == "수학 탐구"
    assert course["classes"] == ["1반", "7반"]

    manager.update(course_id, "수학 탐구 2", "#112233", ["2반"])
    assert manager.get(course_id)["title"] == "수학 탐구 2"
    assert manager.get(course_id)["classes"] == ["2반"]

    with pytest.raises(AppError, match="1반~7반"):
        manager.update(course_id, "잘못된 대상", "#112233", ["8반"])
    with pytest.raises(AppError, match="하나 이상"):
        manager.create("대상 없음", "#112233", [])

    manager.delete(course_id)
    assert manager.list_courses() == []


def test_archive_requires_github_store():
    manager = CourseManager(MemoryStore())
    course_id = manager.create("보관할 수업", "#aabbcc", ["1반"])
    with pytest.raises(AppError, match="THINK_MODE"):
        manager.archive(course_id)
    assert manager.get(course_id)


class ArchiveGitHub:
    def __init__(self):
        self.headers = {}
        self.files = {}

    def request(self, method, url, timeout, **kwargs):
        if url.endswith("/contents/think-learning-v1/course-archives") and method == "GET":
            listing = [{"name": name.rsplit("/", 1)[-1]} for name in self.files if "/course-archives/" in name]
            return SimpleNamespace(status_code=200, json=lambda: listing)
        if "/contents/" in url and method == "GET":
            path = url.split("/contents/", 1)[1]
            if path not in self.files:
                return SimpleNamespace(status_code=404, json=lambda: {})
            raw = self.files[path]
            return SimpleNamespace(
                status_code=200,
                json=lambda: {
                    "content": base64.b64encode(raw).decode(),
                    "encoding": "base64",
                    "sha": "sha",
                },
            )
        if "/contents/" in url and method == "PUT":
            path = url.split("/contents/", 1)[1]
            self.files[path] = base64.b64decode(kwargs["json"]["content"])
            return SimpleNamespace(status_code=201, json=lambda: {})
        return SimpleNamespace(status_code=200, json=lambda: {"private": True})


def test_github_course_archive_round_trip_and_restore():
    key = Fernet.generate_key().decode()
    session = ArchiveGitHub()
    store = GitHubStore("owner/repo", "main", "token", key, session=session)
    manager = CourseManager(store)
    course_id = manager.create("보관과 복원", "#aabbcc", ["3반"])

    manager.archive(course_id)
    assert manager.get(course_id) is None
    archive_files = [path for path in session.files if "course-archives/" in path]
    assert len(archive_files) == 1
    assert "보관과 복원".encode("utf-8") not in session.files[archive_files[0]]

    archives = manager.list_archives()
    assert len(archives) == 1
    assert archives[0]["course"]["title"] == "보관과 복원"
    manager.restore(archives[0]["id"])
    restored = manager.get(course_id)
    assert restored["title"] == "보관과 복원"
    assert restored["classes"] == ["3반"]

    with pytest.raises(AppError, match="이미 진행 중"):
        manager.restore(archives[0]["id"])
