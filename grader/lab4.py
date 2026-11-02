"""ЛР4. CI и нефункциональные проверки."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from grader.common import report_section
from grader.context import Context, PytestRun
from grader.core import Lab, Outcome, fail, ok, partial
from grader.textutil import find_section, numbers, strip_comments, table_rows, words

lab = Lab("lab4", "ЛР4. CI и нефункциональные проверки")

STAGES = ("lint", "unit", "api", "e2e")
CHAIN = (("unit", "lint"), ("api", "unit"), ("e2e", "api"))


def _needs(job: dict[str, Any]) -> list[str]:
    needs = job.get("needs") or []
    return [needs] if isinstance(needs, str) else list(needs)


def _job_steps(job: Any) -> list[dict[str, Any]]:
    if not isinstance(job, dict):
        return []
    return [s for s in job.get("steps") or [] if isinstance(s, dict)]


def _runs(job: Any) -> str:
    return "\n".join(str(s.get("run", "")) for s in _job_steps(job))


def _uses(job: Any) -> list[str]:
    return [str(s.get("uses", "")) for s in _job_steps(job)]


def _all_steps(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return [s for job in workflow["jobs"].values() for s in _job_steps(job)]


@lab.check("ci_stages", "Стадии lint → unit → api → e2e в ci.yml", 8)
def check_ci_stages(ctx: Context) -> Outcome:
    workflow, _, problem = ctx.workflow()
    if workflow is None:
        return fail(problem)
    jobs = workflow["jobs"]
    present = [s for s in STAGES if isinstance(jobs.get(s), dict)]
    score = len(present)
    hints = []
    if len(present) < len(STAGES):
        hints.append("нет jobs: " + ", ".join(s for s in STAGES if s not in present))
    edges = [(job, dep) for job, dep in CHAIN if job in present and dep in _needs(jobs[job])]
    score += {0: 0, 1: 1, 2: 2, 3: 4}[len(edges)]
    if len(edges) < len(CHAIN):
        missing = [f"{job}: needs {dep}" for job, dep in CHAIN if (job, dep) not in edges]
        hints.append("свяжите стадии — " + ", ".join(missing))
    return ok() if score == 8 else partial(score, "; ".join(hints))


@lab.check("ci_commands", "Каждая стадия запускает свои проверки", 6)
def check_ci_commands(ctx: Context) -> Outcome:
    workflow, _, problem = ctx.workflow()
    if workflow is None:
        return fail(problem)
    jobs = workflow["jobs"]
    rules = [
        ("lint", lambda r: "ruff check" in r, "lint: uv run ruff check ."),
        ("unit", lambda r: "pytest" in r and "tests/unit" in r, "unit: uv run pytest tests/unit"),
        ("api", lambda r: "pytest" in r and "tests/api" in r, "api: uv run pytest tests/api"),
        ("e2e", lambda r: "playwright install" in r, "e2e: uv run playwright install --with-deps"),
        ("e2e", lambda r: "pytest" in r and "tests/ui" in r, "e2e: uv run pytest tests/ui"),
    ]
    score, hints = 0, []
    for job, rule, hint in rules:
        if rule(_runs(jobs.get(job))):
            score += 1
        else:
            hints.append(hint)
    if all(any(u.startswith("astral-sh/setup-uv") for u in _uses(jobs.get(s))) for s in STAGES):
        score += 1
    else:
        hints.append("во всех стадиях установите uv (astral-sh/setup-uv)")
    return ok() if score == 6 else partial(score, "добавьте шаги — " + "; ".join(hints))


@lab.check("ruff", "ruff check без замечаний, правила B и PT включены", 6)
def check_ruff(ctx: Context) -> Outcome:
    lint = ctx.pyproject().get("tool", {}).get("ruff", {}).get("lint", {})
    rules = set(lint.get("select", [])) | set(lint.get("extend-select", []))
    score, hints = 0, []
    if {"B", "PT"} <= rules or "ALL" in rules:
        score += 3
    else:
        hints.append('добавьте в [tool.ruff.lint] select правила "B" и "PT"')
    result = ctx.run_command(
        [sys.executable, "-m", "ruff", "check", ".", "--output-format", "concise"]
    )
    if result.returncode == 0:
        score += 3
    else:
        issues = [ln for ln in result.stdout.splitlines() if re.match(r"^\S+:\d+:\d+:", ln)]
        detail = issues[0] if issues else (result.stderr.strip().splitlines() or [""])[-1]
        hints.append(f"ruff нашёл замечаний: {len(issues)} (первое: {detail})")
    return ok() if score == 6 else partial(score, "; ".join(hints))


@lab.check("coverage_gate", "Порог покрытия 80 % в CI, покрытие его проходит", 10)
def check_coverage_gate(ctx: Context) -> Outcome:
    _, text, _ = ctx.workflow()
    gates = [int(m) for m in re.findall(r"--cov-fail-under[= ](\d+)", text)]
    report_cfg = ctx.pyproject().get("tool", {}).get("coverage", {}).get("report", {})
    if isinstance(report_cfg.get("fail_under"), int | float):
        gates.append(int(report_cfg["fail_under"]))
    score, hints = 0, []
    if gates and max(gates) >= 80:
        score += 4
    else:
        hints.append("задайте порог: --cov-fail-under=80 в ci.yml или fail_under = 80 в pyproject")
    run = ctx.pytest("nonui")
    total = run.coverage_total()
    if run.problem or total is None:
        hints.append(run.problem or "покрытие не измерилось")
    elif total >= 80:
        score += 6
    else:
        hints.append(f"тесты tests/unit + tests/api покрывают bookshop на {total:.0f} %, нужно 80")
        if total >= 70:
            score += 3
    return ok() if score == 10 else partial(score, "; ".join(hints))


@lab.check("mutation", "Мутационное тестирование: mutmut в CI и отчёт", 8)
def check_mutation(ctx: Context) -> Outcome:
    score, hints = 0, []
    cfg = ctx.pyproject().get("tool", {}).get("mutmut", {})
    if cfg.get("source_paths") or cfg.get("paths_to_mutate"):
        score += 2
    else:
        hints.append("добавьте в pyproject.toml раздел [tool.mutmut] с source_paths")
    workflow, _, _ = ctx.workflow()
    if workflow and any("mutmut run" in str(s.get("run", "")) for s in _all_steps(workflow)):
        score += 2
    else:
        hints.append("добавьте в ci.yml job с шагом uv run mutmut run")
    text = ctx.read("docs/mutation-report.md")
    if text is None:
        hints.append("нет docs/mutation-report.md")
    else:
        summary = find_section(text, r"^Итог") or ""
        filled = [r for r in table_rows(summary) if len(r) >= 2 and numbers(r[-1])]
        if len(filled) >= 4:
            score += 2
        else:
            hints.append("заполните числами таблицу «Итог» в docs/mutation-report.md")
        survivors = strip_comments(find_section(text, r"выживш") or "")
        items = re.findall(r"^\s*(?:[-*]|\d+[.)]|###)\s+\S", survivors, re.M)
        if len(items) >= 3 and words(survivors) >= 60:
            score += 2
        else:
            hints.append("разберите не меньше 3 выживших мутантов (список или ###, от 60 слов)")
    return ok() if score == 8 else partial(score, "; ".join(hints))


def _k6_scripts(ctx: Context) -> list[Path]:
    folder = ctx.path("load")
    if not folder.is_dir():
        return []
    return [p for p in sorted(folder.rglob("*.js")) if "k6/http" in p.read_text(encoding="utf-8")]


@lab.check("k6", "Сценарий k6 с порогами и проверками", 6)
def check_k6(ctx: Context) -> Outcome:
    scripts = _k6_scripts(ctx)
    if not scripts:
        return fail("в папке load нет сценария k6 (*.js с import из k6/http)")
    script = scripts[0]
    text = script.read_text(encoding="utf-8")
    score, hints = 0, []
    if "thresholds" in text and "http_req_duration" in text and "http_req_failed" in text:
        score += 2
    else:
        hints.append("в options.thresholds нужны http_req_duration и http_req_failed")
    if re.search(r"\bcheck\s*\(", text):
        score += 1
    else:
        hints.append("проверяйте ответы через check()")
    if "__ENV.BASE_URL" in text:
        score += 1
    else:
        hints.append("берите адрес из __ENV.BASE_URL")
    k6 = ctx.tool("k6")
    rel = script.relative_to(ctx.root).as_posix()
    if k6 is None:
        hint = "; ".join(hints) or f"{rel}: k6 inspect выполнится в Actions"
        return partial(score, hint, skipped=2)
    result = ctx.run_command([k6, "inspect", rel], timeout=120)
    try:
        options = json.loads(result.stdout)
    except json.JSONDecodeError:
        options = None
    thresholds = (options or {}).get("thresholds") or {}
    if result.returncode == 0 and "http_req_duration" in thresholds:
        score += 2
    else:
        error = (result.stderr.strip().splitlines() or ["нет порогов в итоговых options"])[-1]
        hints.append(f"k6 inspect {rel}: {error}")
    return ok() if score == 6 else partial(score, "; ".join(hints))


@lab.check("k6_ci", "k6 запускается в CI (grafana/setup-k6-action)", 4)
def check_k6_ci(ctx: Context) -> Outcome:
    workflow, _, problem = ctx.workflow()
    if workflow is None:
        return fail(problem)
    steps = _all_steps(workflow)
    score, hints = 0, []
    if any(str(s.get("uses", "")).startswith("grafana/setup-k6-action") for s in steps):
        score += 2
    else:
        hints.append("установите k6 шагом grafana/setup-k6-action@v1")
    if any(str(s.get("uses", "")).startswith("grafana/run-k6-action") for s in steps) or any(
        "k6 run" in str(s.get("run", "")) for s in steps
    ):
        score += 2
    else:
        hints.append("запустите сценарий: grafana/run-k6-action@v1 или run: k6 run load/…")
    return ok() if score == 4 else partial(score, "; ".join(hints))


@lab.check("allure", "Отчёт Allure Report 3 собирается в CI", 8)
def check_allure(ctx: Context) -> Outcome:
    workflow, text, problem = ctx.workflow()
    if workflow is None:
        return fail(problem)
    steps = _all_steps(workflow)
    score, hints = 0, []
    if "--alluredir" in text:
        score += 3
    else:
        hints.append("запускайте pytest с --alluredir=allure-results")
    runs = "\n".join(str(s.get("run", "")) for s in steps)
    legacy = "allure-commandline" in runs or re.search(r"allure@2\b", runs)
    if re.search(r"allure(@3[\w.]*)?\s+(generate|run|awesome)", runs) and not legacy:
        score += 3
    else:
        hints.append("соберите отчёт Allure 3: npx allure generate allure-results")
    uploads = [s for s in steps if str(s.get("uses", "")).startswith("actions/upload-artifact")]
    if any("allure-report" in str((s.get("with") or {}).get("path", "")) for s in uploads):
        score += 2
    else:
        hints.append("выложите allure-report через actions/upload-artifact")
    return ok() if score == 8 else partial(score, "; ".join(hints))


@lab.check("report", "Раздел ЛР4 в README.md", 4)
def check_report(ctx: Context) -> Outcome:
    return report_section(ctx, 4, ["Пайплайн", "Мутационное тестирование", "Нагрузка", "Выводы"], 4)


@lab.check("a11y_bonus", "Бонус: проверка доступности axe-core", 5, bonus=True)
def check_a11y_bonus(ctx: Context) -> Outcome:
    run = ctx.pytest("ui")
    if run.problem:
        return fail(run.problem)
    tests = [
        i
        for i in run.under("tests/ui/")
        if "axe_playwright_python" in i["imports"] or any(m["name"] == "a11y" for m in i["markers"])
    ]
    green = [i for i in tests if PytestRun.green(i)]
    if green:
        return ok()
    if tests:
        return fail("тесты доступности не проходят — найденное нарушение оформите issue и xfail")
    return fail("необязательно: добавьте UI-тест с axe-core (axe-playwright-python)")
