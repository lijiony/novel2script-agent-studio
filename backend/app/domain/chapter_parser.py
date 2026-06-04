import re
from app.domain.schemas import Chapter


CHAPTER_HEADING = re.compile(
    r"(?m)^(?P<title>\s*(?:第\s*[一二三四五六七八九十百千万\d]+\s*[章节回幕]|Chapter\s+\d+|CHAPTER\s+\d+)[^\n]*)$"
)


class ChapterParseError(ValueError):
    pass


def parse_chapters(text: str, *, max_chars: int) -> list[Chapter]:
    clean_text = text.replace("\r\n", "\n").strip()
    if not clean_text:
        raise ChapterParseError("Input text is empty.")
    if len(clean_text) > max_chars:
        raise ChapterParseError(f"Input is too long. Limit is {max_chars} characters.")

    matches = list(CHAPTER_HEADING.finditer(clean_text))
    if len(matches) < 3:
        raise ChapterParseError("At least 3 chapter headings are required.")

    chapters: list[Chapter] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(clean_text)
        title = match.group("title").strip()
        chapter_text = clean_text[start:end].strip()
        if not chapter_text:
            raise ChapterParseError(f"Chapter '{title}' has no body text.")
        chapters.append(
            Chapter(
                index=idx + 1,
                title=title,
                text=chapter_text,
                char_count=len(chapter_text),
            )
        )

    return chapters
