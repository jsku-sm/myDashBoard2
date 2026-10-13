"""Offline 2022 curriculum selectors for high-school mathematics.

Source: Ministry of Education Notice 2022-33, mathematics curriculum appendix 8.
The bundled data contains every achievement standard in its 15 high-school
common, general, career and interdisciplinary subjects. Unit names follow the
official curriculum's areas; equation objects use readable plain notation.
"""
import json
from pathlib import Path
from types import MappingProxyType

from .storage import AppError


_document = json.loads(Path(__file__).with_name("curriculum_2022_math.json").read_text(encoding="utf-8"))
CURRICULUM_YEAR = _document["year"]
SOURCE_TITLE = _document["source_title"]
SOURCE_URL = _document["source_url"]
_SUBJECTS = MappingProxyType({
    subject: MappingProxyType({
        unit: tuple((standard["code"], standard["text"]) for standard in standards)
        for unit, standards in units.items()
    })
    for subject, units in _document["subjects"].items()
})
del _document


def subject_names():
    """Return subjects in curriculum order, with common subjects first."""
    return list(_SUBJECTS)


def unit_names(subject):
    """Return official curriculum areas for a subject, or none if unknown."""
    if not isinstance(subject, str):
        return []
    return list(_SUBJECTS.get(subject, {}))


def standards_for(subject, unit):
    """Return independent code/text records; callers cannot mutate the source."""
    if not isinstance(subject, str) or not isinstance(unit, str):
        return []
    return [{"code": code, "text": text}
            for code, text in _SUBJECTS.get(subject, {}).get(unit, ())]


def _selected_standards(subject, unit, standard_codes):
    if not isinstance(subject, str) or subject not in _SUBJECTS:
        raise AppError("2022 개정 교육과정의 과목을 선택하세요.")
    if not isinstance(unit, str) or unit not in _SUBJECTS[subject]:
        raise AppError("선택한 과목의 단원을 선택하세요.")
    if not isinstance(standard_codes, (list, tuple)) or not 1 <= len(standard_codes) <= 8:
        raise AppError("성취기준을 1~8개 선택하세요.")
    if any(not isinstance(code, str) for code in standard_codes):
        raise AppError("성취기준 코드를 확인하세요.")
    selected = set(standard_codes)
    if len(selected) != len(standard_codes):
        raise AppError("같은 성취기준을 중복 선택할 수 없습니다.")
    standards = _SUBJECTS[subject][unit]
    if not selected.issubset({code for code, _ in standards}):
        raise AppError("선택한 과목과 단원에 속한 성취기준을 선택하세요.")
    return [(code, text) for code, text in standards if code in selected]


def selection_metadata(subject, unit, standard_codes):
    """Validate and return a storage-ready selection in official code order."""
    standards = _selected_standards(subject, unit, standard_codes)
    return {
        "year": CURRICULUM_YEAR,
        "subject": subject,
        "unit": unit,
        "standard_codes": [code for code, _ in standards],
        "source_url": SOURCE_URL,
    }


def criteria_text(subject, unit, standard_codes):
    """Return the selected official standards as individual rubric criteria."""
    return [f"[{code}] {text}"
            for code, text in _selected_standards(subject, unit, standard_codes)]


def validate_selection(metadata):
    """Normalize persisted metadata without trusting its year or source URL."""
    if not isinstance(metadata, dict) or type(metadata.get("year")) is not int or metadata["year"] != CURRICULUM_YEAR:
        raise AppError("2022 개정 교육과정 선택 정보를 확인하세요.")
    return selection_metadata(metadata.get("subject"), metadata.get("unit"), metadata.get("standard_codes"))
