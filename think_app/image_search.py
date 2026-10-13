"""Build a Google Images link for the student's keyword."""
from urllib.parse import urlencode

from .storage import AppError


def google_images_url(query):
    if not isinstance(query, str) or not query.strip():
        raise AppError("이미지 검색어를 입력하세요.")
    query = query.strip()
    if len(query) > 2000:
        raise AppError("이미지 검색어는 2,000자 이내로 입력하세요.")
    return "https://www.google.com/search?" + urlencode({"udm": "2", "q": query})
