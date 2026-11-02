"""ЛР1. Инфраструктура тестирования и первые тесты."""

from __future__ import annotations

import re

from grader.common import (
    FORM_FIELDS,
    REQUIRED_IDS,
    bug_reports,
    form_fields,
    header_filled,
    load_form,
    report_section,
)
from grader.context import Context, GitHubUnavailable, PytestRun, describe
from grader.core import Lab, Outcome, fail, ok, partial, skip
from grader.textutil import strip_comments

lab = Lab("lab1", "ЛР1. Инфраструктура тестирования и первые тесты")


@lab.check("variant", "Номер варианта указан", 4)
def check_variant(ctx: Context) -> Outcome:
    if ctx.variant_ok:
        return ok()
    return fail(ctx.variant_problem + ". Впишите номер варианта от преподавателя в variant.toml")


@lab.check("unit_tests", "Не меньше 10 модульных тестов, все проходят", 12)
def check_unit_tests(ctx: Context) -> Outcome:
    run = ctx.pytest("unit")
    if run.problem:
        return fail(run.problem)
    problem = run.collect_problem("tests/unit")
    if problem:
        return fail(problem)
    tests = run.under("tests/unit/")
    broken = PytestRun.broken(tests)
    if broken:
        return fail(
            f"падают {len(broken)} тест(ов): {describe(broken)}. Если падение из-за дефекта "
            "приложения, отметьте тест xfail со ссылкой на issue"
        )
    count = len(tests)
    if count >= 10:
        return ok()
    if count >= 5:
        return partial(6, f"в tests/unit {count} тестов, нужно не меньше 10")
    return fail(f"в tests/unit {count} тест(ов), нужно не меньше 10 — для функций pricing.py")


@lab.check("coverage", "Покрытие pricing.py не ниже 80 %", 12)
def check_coverage(ctx: Context) -> Outcome:
    run = ctx.pytest("unit")
    if run.problem:
        return fail(run.problem)
    percent = run.coverage_of("bookshop/pricing.py")
    if percent is None:
        return fail("покрытие не измерилось: проверьте, что pytest-cov установлен (uv sync)")
    measured = f"модульные тесты покрывают pricing.py на {percent:.0f} % (строки и ветки)"
    if percent >= 80:
        return ok(measured)
    if percent >= 60:
        return partial(6, measured + ", нужно 80 %")
    return fail(
        measured + ", нужно 80 %. Смотрите непокрытые строки: "
        "uv run pytest tests/unit --cov=bookshop.pricing --cov-branch --cov-report=term-missing"
    )


def _triggers(workflow: dict) -> object:
    # PyYAML читает ключ on: как True (YAML 1.1)
    return workflow.get("on", workflow.get(True))


def _has_push(triggers: object) -> bool:
    if isinstance(triggers, str):
        return triggers == "push"
    if isinstance(triggers, list):
        return "push" in triggers
    if isinstance(triggers, dict):
        return "push" in triggers
    return False


def _steps(workflow: dict) -> list[dict]:
    steps = []
    for job in workflow.get("jobs", {}).values():
        if isinstance(job, dict):
            steps += [s for s in job.get("steps", []) or [] if isinstance(s, dict)]
    return steps


@lab.check("ci_workflow", "Workflow CI запускает тесты на push", 8)
def check_ci_workflow(ctx: Context) -> Outcome:
    workflow, _, problem = ctx.workflow()
    if workflow is None:
        return fail(problem + ". Создайте его по образцу из задания ЛР1")
    score, hints = 2, []
    if _has_push(_triggers(workflow)):
        score += 2
    else:
        hints.append("добавьте запуск на push (on: push)")
    steps = _steps(workflow)
    if any(str(s.get("uses", "")).startswith("astral-sh/setup-uv") for s in steps):
        score += 2
    else:
        hints.append("установите uv шагом astral-sh/setup-uv")
    if any("pytest" in str(s.get("run", "")) for s in steps):
        score += 2
    else:
        hints.append("добавьте шаг run: uv run pytest")
    return ok() if score == 8 else partial(score, "; ".join(hints))


@lab.check("issue_form", "Форма баг-репорта в .github/ISSUE_TEMPLATE", 10)
def check_issue_form(ctx: Context) -> Outcome:
    form, problem = load_form(ctx)
    if form is None:
        return fail(problem + ". Создайте форму по образцу из задания ЛР1")
    fields = form_fields(form)
    score, hints = 2, []
    for field_id, types in FORM_FIELDS.items():
        element = fields.get(field_id)
        if element is None:
            hints.append(f"нет поля с id: {field_id}")
        elif element.get("type") not in types:
            hints.append(f"поле {field_id} должно быть типа {' или '.join(sorted(types))}")
        elif (
            element.get("type") == "dropdown"
            and len((element.get("attributes") or {}).get("options") or []) < 3
        ):
            hints.append(f"в списке {field_id} нужно не меньше 3 вариантов")
        else:
            score += 1
    labels = form.get("labels") or []
    if isinstance(labels, str):
        labels = [part.strip() for part in labels.split(",")]
    if "bug" in labels:
        score += 1
    else:
        hints.append("добавьте labels: [bug]")
    not_required = [
        fid
        for fid in REQUIRED_IDS
        if fid in fields and not (fields[fid].get("validations") or {}).get("required")
    ]
    if not not_required and all(fid in fields for fid in REQUIRED_IDS):
        score += 1
    else:
        hints.append(
            "сделайте обязательными (validations: required: true) поля "
            + ", ".join(not_required or REQUIRED_IDS)
        )
    return ok() if score == 10 else partial(score, "; ".join(hints))


@lab.check("bug_issue", "Баг-репорт заведён в Issues по форме", 4)
def check_bug_issue(ctx: Context) -> Outcome:
    try:
        reports = bug_reports(ctx)
    except GitHubUnavailable as exc:
        return skip(str(exc))
    if reports:
        return ok(f"найдено баг-репортов: {len(reports)}")
    return fail(
        "нет ни одного issue, созданного по форме, с заполненными серьёзностью, "
        "приоритетом, шагами, ожидаемым и фактическим результатом"
    )


@lab.check("ai_usage", "Журнал AI_USAGE.md заполнен", 4)
def check_ai_usage(ctx: Context) -> Outcome:
    text = ctx.read("AI_USAGE.md")
    if text is None:
        return fail("нет файла AI_USAGE.md — верните его из шаблона")
    clean = strip_comments(text)
    if re.search(r"^\s*Итог:\s*ИИ не использовал", clean, re.M):
        return ok()
    rows = []
    for line in clean.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.strip().startswith("|") and len(cells) >= 5:
            if all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                continue
            rows.append(cells)
    filled = [r for r in rows[1:] if all(c for c in r[:5])]
    if filled:
        return ok()
    return fail(
        "заполните хотя бы одну строку таблицы (все 5 столбцов) "
        "или напишите отдельной строкой «Итог: ИИ не использовался»"
    )


@lab.check("report", "Раздел ЛР1 в README.md", 6)
def check_report(ctx: Context) -> Outcome:
    missing = header_filled(ctx)
    section = report_section(ctx, 1, ["Что сделано", "Покрытие", "Найденные дефекты", "Выводы"], 4)
    score = (0 if missing else 2) + (4 if section.points is None else section.points)
    hints = []
    if missing:
        hints.append("заполните в шапке README: " + ", ".join(missing))
    if section.hint:
        hints.append(section.hint)
    return ok() if score == 6 else partial(score, "; ".join(hints))
