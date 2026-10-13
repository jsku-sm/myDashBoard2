"""Official high-school curriculum coverage and saved selection integrity."""
import pytest

from think_app import curriculum
from think_app.storage import AppError


EXPECTED_COUNTS = {
    "공통수학1": [3, 11, 3, 2],
    "공통수학2": [7, 8, 5],
    "대수": [8, 3, 7],
    "미적분Ⅰ": [4, 10, 6],
    "확률과 통계": [3, 6, 7],
    "미적분Ⅱ": [5, 11, 7],
    "기하": [4, 5, 5],
    "경제 수학": [5, 6, 3, 4],
    "인공지능 수학": [3, 3, 3, 4, 2],
    "직무 수학": [3, 5, 5, 5],
    "수학과 문화": [4, 4, 4, 4],
    "실용 통계": [3, 4, 4, 2],
    "수학과제 탐구": [2, 4, 4],
    "기본수학1": [3, 9, 3, 2],
    "기본수학2": [7, 5, 5],
}


def test_official_subjects_have_complete_standards_without_explanatory_paragraphs():
    assert curriculum.subject_names() == list(EXPECTED_COUNTS)
    codes = []
    for subject, counts in EXPECTED_COUNTS.items():
        records = [curriculum.standards_for(subject, unit) for unit in curriculum.unit_names(subject)]
        assert [len(group) for group in records] == counts
        for group in records:
            codes.extend(standard["code"] for standard in group)
            assert all(standard["text"] and "(수식)" not in standard["text"] for standard in group)
    assert len(codes) == len(set(codes)) == 254
    assert curriculum.unit_names("공통수학1") == ["다항식", "방정식과 부등식", "경우의 수", "행렬"]
    assert curriculum.unit_names("공통수학2") == ["도형의 방정식", "집합과 명제", "함수와 그래프"]


def test_mathematical_equation_objects_are_kept_in_plain_text():
    functions = {item["code"]: item["text"] for item in curriculum.standards_for("공통수학2", "함수와 그래프")}
    assert "y=(ax+b)/(cx+d)" in functions["10공수2-03-04"]
    assert "y=√(ax+b)+c" in functions["10공수2-03-05"]
    sequence = {item["code"]: item["text"] for item in curriculum.standards_for("대수", "수열")}
    assert sequence["12대수03-04"].startswith("∑의 뜻과 성질")
    assert "제n항" in sequence["12대수03-02"]


def test_selection_preserves_criterion_text_and_returns_canonical_metadata():
    selected = ["10공수1-01-03", "10공수1-01-01"]
    metadata = curriculum.selection_metadata("공통수학1", "다항식", selected)
    assert metadata == {
        "year": 2022, "subject": "공통수학1", "unit": "다항식",
        "standard_codes": ["10공수1-01-01", "10공수1-01-03"],
        "source_url": curriculum.SOURCE_URL,
    }
    assert curriculum.criteria_text("공통수학1", "다항식", selected) == [
        "[10공수1-01-01] 다항식의 사칙연산의 원리를 설명하고, 그 계산을 할 수 있다.",
        "[10공수1-01-03] 다항식의 인수분해를 할 수 있다.",
    ]
    assert curriculum.validate_selection({**metadata, "source_url": "https://unknown.example"}) == metadata


@pytest.mark.parametrize("subject, unit, codes", [
    ("2015 수학", "다항식", ["10공수1-01-01"]),
    ("공통수학1", "없는 단원", ["10공수1-01-01"]),
    ("공통수학1", "다항식", ["10공수2-01-01"]),
    ("공통수학1", "다항식", ["10공수1-02-01"]),
    ("공통수학1", "다항식", []),
    ("공통수학1", "다항식", ["10공수1-01-01"] * 2),
    ("공통수학1", "다항식", "10공수1-01-01"),
    ("공통수학1", "다항식", [None]),
    ("공통수학1", "방정식과 부등식", [f"10공수1-02-{number:02}" for number in range(1, 10)]),
])
def test_invalid_or_cross_unit_codes_cannot_be_saved(subject, unit, codes):
    with pytest.raises(AppError):
        curriculum.selection_metadata(subject, unit, codes)


@pytest.mark.parametrize("metadata", [None, [], {}, {"year": "2022"}, {"year": 2022.0}, {"year": 2015}])
def test_metadata_rejects_wrong_curriculum_version(metadata):
    with pytest.raises(AppError):
        curriculum.validate_selection(metadata)


def test_ui_reads_cannot_mutate_official_dataset_and_unknown_reads_are_empty():
    first = curriculum.standards_for("공통수학1", "다항식")
    first[0]["text"] = "변경됨"
    first.append({"code": "wrong", "text": "잘못된 기준"})
    assert len(curriculum.standards_for("공통수학1", "다항식")) == 3
    assert curriculum.standards_for("공통수학1", "다항식")[0]["text"].startswith("다항식의 사칙연산")
    assert curriculum.unit_names(None) == []
    assert curriculum.standards_for([], "다항식") == []
    assert curriculum.standards_for("없는 과목", "다항식") == []
