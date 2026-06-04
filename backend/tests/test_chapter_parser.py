import pytest

from app.domain.chapter_parser import ChapterParseError, parse_chapters


def test_parse_three_chapters():
    text = """第一章 开始
内容一

第二章 继续
内容二

第三章 结束
内容三
"""
    chapters = parse_chapters(text, max_chars=1000)
    assert len(chapters) == 3
    assert chapters[0].title == "第一章 开始"
    assert chapters[2].index == 3


def test_reject_less_than_three_chapters():
    with pytest.raises(ChapterParseError):
        parse_chapters("第一章 开始\n内容\n第二章 结束\n内容", max_chars=1000)


def test_reject_too_long_input():
    with pytest.raises(ChapterParseError):
        parse_chapters("第一章 开始\n" + "x" * 20, max_chars=10)
