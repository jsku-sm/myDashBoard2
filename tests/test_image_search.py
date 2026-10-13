from urllib.parse import parse_qs, urlsplit

import pytest

from think_app.image_search import google_images_url
from think_app.storage import AppError


def test_google_images_link_encodes_keyword_as_a_single_query_parameter():
    query = "포물선 그래프 & x=2 #그림 ?"
    parts = urlsplit(google_images_url("  " + query + "  "))
    assert parts.scheme == "https" and parts.netloc == "www.google.com"
    assert parts.path == "/search" and not parts.fragment
    assert parse_qs(parts.query) == {"udm": ["2"], "q": [query]}


@pytest.mark.parametrize("query", [None, "", " "])
def test_google_images_link_requires_keyword(query):
    with pytest.raises(AppError, match="검색어를 입력"):
        google_images_url(query)


def test_google_images_link_limits_query_length():
    assert parse_qs(urlsplit(google_images_url("가" * 2000)).query)["q"] == ["가" * 2000]
    with pytest.raises(AppError, match="2,000자"):
        google_images_url("가" * 2001)
