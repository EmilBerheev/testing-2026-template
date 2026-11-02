"""Проверки, общие для нескольких лабораторных: форма баг-репорта, issues, отчёт в README."""

from __future__ import annotations

import re
from typing import Any

from grader.context import Context
from grader.core import Outcome, fail, ok, partial
from grader.textutil import find_section, sections, strip_comments, words

FORM_PATHS = (".github/ISSUE_TEMPLATE/bug_report.yml", ".github/ISSUE_TEMPLATE/bug_report.yaml")

# id поля формы → допустимые типы поля
FORM_FIELDS: dict[str, set[str]] = {
    "severity": {"dropdown"},
    "priority": {"dropdown"},
    "steps": {"textarea"},
    "expected": {"textarea"},
    "actual": {"textarea"},
    "environment": {"textarea", "input", "dropdown"},
}
REQUIRED_IDS = ("severity", "priority", "steps", "expected", "actual")
DEFAULT_LABELS = {
    "severity": "Серьёзность",
    "priority": "Приоритет",
    "steps": "Шаги воспроизведения",
    "expected": "Ожидаемый результат",
    "actual": "Фактический результат",
    "environment": "Окружение",
}
NO_RESPONSE = "_No response_"


def load_form(ctx: Context) -> tuple[dict[str, Any] | None, str]:
    rel = ctx.first_existing(*FORM_PATHS)
    if rel is None:
        return None, "нет файла .github/ISSUE_TEMPLATE/bug_report.yml"
    data, problem = ctx.load_yaml(rel)
    if problem:
        return None, problem
    if not isinstance(data, dict) or not isinstance(data.get("body"), list):
        return None, f"{rel}: у формы нет списка body"
    return data, ""


def form_fields(form: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    for element in form.get("body", []):
        if isinstance(element, dict) and isinstance(element.get("id"), str):
            fields[element["id"]] = element
    return fields


def form_labels(ctx: Context) -> dict[str, str]:
    """Подписи полей формы студента (по ним GitHub строит заголовки в теле issue)."""
    labels = dict(DEFAULT_LABELS)
    form, _ = load_form(ctx)
    if form:
        for field_id, element in form_fields(form).items():
            label = (element.get("attributes") or {}).get("label")
            if field_id in labels and isinstance(label, str) and label.strip():
                labels[field_id] = label.strip()
    return labels


def _section_value(body: str, label: str) -> str | None:
    pattern = re.compile(rf"^###\s+{re.escape(label)}\s*$(.*?)(?=^###\s|\Z)", re.M | re.S)
    match = pattern.search(body)
    if not match:
        return None
    return match.group(1).strip()


def bug_reports(ctx: Context) -> list[dict[str, Any]]:
    """Issues, созданные по форме баг-репорта и с заполненными ключевыми полями."""
    labels = form_labels(ctx)
    found = []
    for issue in ctx.issues():
        body = issue.get("body") or ""
        values = {key: _section_value(body, label) for key, label in labels.items()}
        filled = [k for k in REQUIRED_IDS if values[k] and values[k] != NO_RESPONSE]
        if len(filled) == len(REQUIRED_IDS):
            found.append(issue)
    return found


def report_section(ctx: Context, lab_no: int, subsections: list[str], points: int) -> Outcome:
    text = ctx.read("README.md")
    if text is None:
        return fail("нет README.md")
    body = find_section(text, rf"^ЛР\s*-?\s*{lab_no}\b")
    if body is None:
        return fail(f"в README.md нет раздела «## ЛР{lab_no}. …» — верните заголовок из шаблона")
    subs = sections(body, level=3)
    missing: list[str] = []
    filled = 0
    for name in subsections:
        content = next((v for k, v in subs.items() if k.lower().startswith(name.lower())), None)
        if content is not None and words(content) >= 15:
            filled += 1
        else:
            missing.append(name)
    total_words = words(body)
    score = round(points * filled / len(subsections))
    hints = []
    if missing:
        hints.append("заполните подразделы (от 15 слов): " + ", ".join(f"«{m}»" for m in missing))
    if total_words < 80:
        score = min(score, points // 2)
        hints.append(f"в разделе ЛР{lab_no} всего {total_words} слов, нужно от 80")
    if score == points:
        return ok()
    return partial(score, "; ".join(hints))


def header_filled(ctx: Context) -> list[str]:
    """Какие поля шапки отчёта (Студент, Группа) не заполнены."""
    text = strip_comments(ctx.read("README.md") or "")
    missing = []
    for field_name in ("Студент", "Группа"):
        match = re.search(rf"^\|\s*{field_name}\s*\|\s*(.*?)\s*\|", text, re.M)
        if not match or not match.group(1).strip():
            missing.append(field_name)
    return missing
