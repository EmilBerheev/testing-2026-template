"""Разбор Markdown и текста: разделы, таблицы, числа, слова."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
WORD_RE = re.compile(r"[^\W\d_]{2,}")
NUMBER_RE = re.compile(r"(?<![\w.])-?\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|-?\d+(?:[.,]\d+)?")


def strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def words(text: str) -> int:
    return len(WORD_RE.findall(strip_comments(text)))


def sections(text: str, level: int = 2) -> dict[str, str]:
    """Заголовок уровня level → текст до следующего заголовка того же или более высокого уровня."""
    result: dict[str, str] = {}
    current: str | None = None
    buffer: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        match = None if in_code else re.match(r"^(#{1,6})\s+(.*?)\s*#*\s*$", line)
        if match and len(match.group(1)) <= level:
            if current is not None:
                result[current] = "\n".join(buffer)
            current = match.group(2).strip() if len(match.group(1)) == level else None
            buffer = []
        elif current is not None:
            buffer.append(line)
    if current is not None:
        result[current] = "\n".join(buffer)
    return result


def find_section(text: str, pattern: str, level: int = 2) -> str | None:
    regex = re.compile(pattern, re.I)
    for title, body in sections(text, level).items():
        if regex.search(title):
            return body
    return None


def table_rows(text: str) -> list[list[str]]:
    """Строки всех Markdown-таблиц без заголовка и разделителя."""
    return [row for table in tables(text) for row in table[1:]]


def tables(text: str) -> list[list[list[str]]]:
    """Все таблицы целиком: список таблиц, таблица — список строк (с заголовком)."""
    found: list[list[list[str]]] = []
    block: list[list[str]] = []
    for line in [*strip_comments(text).splitlines(), ""]:
        stripped = line.strip()
        if stripped.startswith("|"):
            block.append([c.strip() for c in stripped.strip("|").split("|")])
            continue
        if len(block) >= 2 and all(re.fullmatch(r":?-{2,}:?", c) for c in block[1] if c):
            found.append([block[0], *block[2:]])
        block = []
    return found


def numbers(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    for raw in NUMBER_RE.findall(text):
        cleaned = re.sub(r"[   ]", "", raw).replace(",", ".")
        try:
            values.add(Decimal(cleaned))
        except InvalidOperation:
            continue
    return values


def code_blocks(text: str, language: str) -> list[str]:
    pattern = re.compile(rf"```{language}\s*\n(.*?)```", re.S)
    return pattern.findall(strip_comments(text))
