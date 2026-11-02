"""ЛР2. Тест-дизайн и тестовая документация."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal
from typing import Any

import yaml

from grader.common import bug_reports, report_section
from grader.context import Context, GitHubUnavailable, PytestRun, describe
from grader.core import Lab, Outcome, fail, ok, partial, skip
from grader.textutil import code_blocks, find_section, numbers, strip_comments, tables

lab = Lab("lab2", "ЛР2. Тест-дизайн и тестовая документация")

CASES_FILE = "docs/test-cases.yaml"
TECHNIQUES = {"EP", "BVA", "DT", "ST", "EG", "UC", "PW"}
REQUIRED_TECHNIQUES = ("EP", "BVA", "DT", "ST")
PRIORITIES = {"high", "medium", "low"}
STATUSES = ("NEW", "PAID", "SHIPPED", "DELIVERED", "CANCELLED", "RETURNED")
ISSUE_REF = re.compile(r"#(\d+)|/issues/(\d+)")


def _requirements(ctx: Context) -> set[str]:
    return set(re.findall(r"\*\*(R-\d{2})\.", ctx.read("docs/requirements.md") or ""))


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _case_problems(case: Any, known_reqs: set[str]) -> list[str]:
    if not isinstance(case, dict):
        return ["элемент списка — не словарь"]
    problems = []
    if not re.fullmatch(r"TC-\d{3,}", str(case.get("id", ""))):
        problems.append("id вида TC-001")
    if not str(case.get("title") or "").strip():
        problems.append("пустой title")
    if str(case.get("technique", "")).upper() not in TECHNIQUES:
        problems.append("technique: EP, BVA, DT, ST или EG")
    reqs = [str(r) for r in _as_list(case.get("requirement")) if r]
    if not reqs or any(r not in known_reqs for r in reqs):
        problems.append("requirement: R-01…R-16 из docs/requirements.md")
    if str(case.get("priority", "")).lower() not in PRIORITIES:
        problems.append("priority: high, medium или low")
    steps = case.get("steps")
    if not isinstance(steps, list) or not steps or not all(str(s).strip() for s in steps):
        problems.append("steps — непустой список шагов")
    expected = case.get("expected")
    if not expected or (isinstance(expected, list) and not all(expected)):
        problems.append("пустой expected")
    return problems


def load_cases(ctx: Context) -> tuple[list[dict[str, Any]], list[str], str]:
    """(корректные кейсы, описания проблем, фатальная проблема)."""
    data, problem = ctx.load_yaml(CASES_FILE)
    if problem:
        return [], [], problem
    if not data:
        return [], [], f"{CASES_FILE} пуст — добавьте тест-кейсы списком YAML"
    if not isinstance(data, list):
        return [], [], f"{CASES_FILE}: на верхнем уровне должен быть список кейсов"
    known = _requirements(ctx)
    valid: list[dict[str, Any]] = []
    problems: list[str] = []
    ids = Counter(str(c.get("id")) for c in data if isinstance(c, dict))
    for index, case in enumerate(data, start=1):
        issues = _case_problems(case, known)
        if isinstance(case, dict) and ids[str(case.get("id"))] > 1:
            issues.append("id повторяется")
        if issues:
            name = case.get("id", f"№{index}") if isinstance(case, dict) else f"№{index}"
            problems.append(f"{name}: {', '.join(issues)}")
        else:
            valid.append(case)
    return valid, problems, ""


@lab.check("cases_format", "Тест-кейсы в docs/test-cases.yaml по формату", 4)
def check_cases_format(ctx: Context) -> Outcome:
    valid, problems, fatal = load_cases(ctx)
    if fatal:
        return fail(fatal)
    if not problems:
        return ok()
    share = len(valid) / (len(valid) + len(problems))
    hint = "исправьте кейсы — " + "; ".join(problems[:4])
    if len(problems) > 4:
        hint += f" и ещё {len(problems) - 4}"
    return partial(2, hint) if share >= 0.8 else fail(hint)


@lab.check("cases_count", "Не меньше 20 тест-кейсов", 6)
def check_cases_count(ctx: Context) -> Outcome:
    valid, _, fatal = load_cases(ctx)
    if fatal:
        return fail(fatal)
    if len(valid) >= 20:
        return ok()
    hint = f"корректных кейсов {len(valid)}, нужно не меньше 20"
    return partial(3, hint) if len(valid) >= 10 else fail(hint)


@lab.check("techniques", "Четыре техники: EP, BVA, DT, ST — по 3+ кейса", 8)
def check_techniques(ctx: Context) -> Outcome:
    valid, _, fatal = load_cases(ctx)
    if fatal:
        return fail(fatal)
    counts = Counter(str(c["technique"]).upper() for c in valid)
    short = [f"{t}: {counts[t]}" for t in REQUIRED_TECHNIQUES if counts[t] < 3]
    score = 2 * (len(REQUIRED_TECHNIQUES) - len(short))
    if not short:
        return ok()
    return partial(score, "нужно по 3 кейса на технику, сейчас " + ", ".join(short))


def _bva_numbers(cases: list[dict[str, Any]]) -> set[Decimal]:
    found: set[Decimal] = set()
    for case in cases:
        if str(case["technique"]).upper() != "BVA":
            continue
        parts = {k: v for k, v in case.items() if k not in {"id", "requirement"}}
        found |= numbers(yaml.safe_dump(parts, allow_unicode=True))
    return found


def _near(value: int) -> set[Decimal]:
    base = Decimal(value)
    return {base - 1, base + 1, base - Decimal("0.01"), base + Decimal("0.01")}


@lab.check("variant_values", "В граничных кейсах — числа вашего варианта", 6)
def check_variant_values(ctx: Context) -> Outcome:
    if not ctx.variant_ok or ctx.params is None:
        return fail("сначала укажите номер варианта в variant.toml")
    valid, _, fatal = load_cases(ctx)
    if fatal:
        return fail(fatal)
    p = ctx.params
    found = _bva_numbers(valid)
    score, hints = 0, []
    if {Decimal(p["max_qty"]), Decimal(p["max_qty"] + 1)} <= found:
        score += 2
    else:
        hints.append(f"граница количества: {p['max_qty']} и {p['max_qty'] + 1} (MAX_QTY)")
    free = p["free_delivery_from"]
    if Decimal(free) in found and _near(free) & found:
        score += 2
    else:
        hints.append(f"порог бесплатной доставки {free} ₽ и значение рядом с ним")
    others = [
        Decimal(p["promo_min"]) in found and bool(_near(p["promo_min"]) & found),
        {Decimal(p["bulk_qty"]), Decimal(p["bulk_qty"] - 1)} <= found,
        {Decimal(p["max_items"]), Decimal(p["max_items"] + 1)} <= found,
    ]
    if any(others):
        score += 2
    else:
        hints.append(
            f"ещё одна граница: PROMO_MIN = {p['promo_min']}, BULK_QTY = {p['bulk_qty']} "
            f"или MAX_ITEMS = {p['max_items']} вместе с соседним значением"
        )
    if score == 6:
        return ok()
    return partial(score, "в кейсах BVA не нашлось чисел — " + "; ".join(hints))


@lab.check("design_doc", "docs/test-design.md: классы, таблица решений, диаграмма", 6)
def check_design_doc(ctx: Context) -> Outcome:
    text = ctx.read("docs/test-design.md")
    if text is None:
        return fail("нет файла docs/test-design.md — верните его из шаблона")
    score, hints = 0, []
    ep = find_section(text, r"Классы эквивалентности") or ""
    if any(len(t) - 1 >= 5 for t in tables(ep)):
        score += 2
    else:
        hints.append("в разделе «Классы эквивалентности» нужна таблица от 5 строк")
    dt = find_section(text, r"Таблица решений") or ""
    if any(max(len(t) - 1, len(t[0]) - 1) >= 6 for t in tables(dt)):
        score += 2
    else:
        hints.append("в разделе «Таблица решений» нужна таблица от 6 правил")
    st = strip_comments(find_section(text, r"Диаграмма состояний") or "")
    diagram = next((b for b in code_blocks(st, "mermaid") if "stateDiagram" in b), "")
    missing = [s for s in STATUSES if s not in diagram]
    if diagram and not missing:
        score += 2
    elif diagram:
        hints.append("на диаграмме нет статусов: " + ", ".join(missing))
    else:
        hints.append("в разделе «Диаграмма состояний» нужен блок ```mermaid со stateDiagram-v2")
    return ok() if score == 6 else partial(score, "; ".join(hints))


@lab.check("checklist", "Чек-лист от 15 пунктов с результатами", 4)
def check_checklist(ctx: Context) -> Outcome:
    text = ctx.read("docs/checklist.md")
    if text is None:
        return fail("нет файла docs/checklist.md — верните его из шаблона")
    results = ("пройдено", "не пройдено", "заблокировано", "pass", "fail", "blocked")
    done = 0
    for table in tables(text):
        for row in table[1:]:
            if len(row) >= 2 and row[1] and row[-1].lower().startswith(results):
                done += 1
    if done >= 15:
        return ok()
    hint = f"пунктов с результатом {done}, нужно не меньше 15 (результат — последний столбец)"
    return partial(2, hint) if done >= 8 else fail(hint)


def _tc_ids(item: dict[str, Any]) -> list[str]:
    ids = []
    for mark in item["markers"]:
        if mark["name"] == "tc":
            ids += [str(a) for a in mark["args"]]
    return ids


@lab.check("traceability", "Автотесты связаны с тест-кейсами (@pytest.mark.tc)", 6)
def check_traceability(ctx: Context) -> Outcome:
    valid, _, fatal = load_cases(ctx)
    if fatal:
        return fail(fatal)
    run = ctx.pytest("nonui")
    if run.problem:
        return fail(run.problem)
    known = {str(c["id"]) for c in valid}
    linked: set[str] = set()
    unknown: set[str] = set()
    for item in run.items:
        if not PytestRun.green(item):
            continue
        for tc in _tc_ids(item):
            (linked if tc in known else unknown).add(tc)
    hint = f"зелёные автотесты ссылаются на {len(linked)} тест-кейс(ов), нужно 15"
    if unknown:
        hint += "; нет в docs/test-cases.yaml: " + ", ".join(sorted(unknown)[:5])
    if len(linked) >= 15:
        return ok(hint if unknown else "")
    return partial(3, hint) if len(linked) >= 8 else fail(hint)


@lab.check("parametrize", "Параметризованные тесты, весь набор зелёный", 6)
def check_parametrize(ctx: Context) -> Outcome:
    run = ctx.pytest("nonui")
    if run.problem:
        return fail(run.problem)
    problem = run.collect_problem()
    if problem:
        return fail(problem)
    broken = PytestRun.broken(run.items)
    if broken:
        return fail(f"падают тесты: {describe(broken)} — набор должен быть зелёным")
    groups: dict[tuple[str, str], int] = defaultdict(int)
    for item in run.items:
        if item["parametrized"]:
            groups[(item["path"], item["function"])] += 1
    rich = [k for k, n in groups.items() if n >= 3]
    if len(rich) >= 3:
        return ok()
    hint = f"функций с @pytest.mark.parametrize на 3+ набора: {len(rich)}, нужно 3"
    return partial(3, hint) if rich else fail(hint)


@lab.check("hypothesis", "Property-based тест на Hypothesis", 4)
def check_hypothesis(ctx: Context) -> Outcome:
    run = ctx.pytest("nonui")
    if run.problem:
        return fail(run.problem)
    tests = [i for i in run.items if i["hypothesis"]]
    if any(PytestRun.green(i) for i in tests):
        return ok()
    if tests:
        return fail(f"тесты с @given не проходят: {describe(tests)}")
    return fail("нет ни одного теста с @given из hypothesis")


def _xfail_info(item: dict[str, Any]) -> tuple[bool, str] | None:
    for mark in item["markers"]:
        if mark["name"] == "xfail":
            strict = mark["kwargs"].get("strict", item["xfail_strict_default"])
            reason = str(mark["kwargs"].get("reason") or item.get("xfail_reason") or "")
            return bool(strict), reason
    return None


def linked_xfails(run: PytestRun) -> tuple[list[dict[str, Any]], list[str]]:
    good, hints = [], []
    for item in run.items:
        info = _xfail_info(item)
        if info is None:
            continue
        strict, reason = info
        if not strict:
            hints.append(f"{item['nodeid']}: нужен strict=True")
        elif not ISSUE_REF.search(reason):
            hints.append(f"{item['nodeid']}: в reason нет ссылки на issue (#N)")
        elif item["outcome"] == "xfailed":
            good.append(item)
    return good, hints


@lab.check("xfail_issues", "Тесты на дефекты: xfail(strict) со ссылкой на issue", 4)
def check_xfail_issues(ctx: Context) -> Outcome:
    run = ctx.pytest("nonui")
    if run.problem:
        return fail(run.problem)
    good, hints = linked_xfails(run)
    if len(good) >= 3:
        return ok()
    hint = f"тестов xfail(strict) со ссылкой на issue: {len(good)}, нужно 3"
    if hints:
        hint += "; " + "; ".join(hints[:3])
    return partial(2, hint) if good else fail(hint)


@lab.check("bug_issues", "Не меньше 3 баг-репортов в Issues", 4)
def check_bug_issues(ctx: Context) -> Outcome:
    try:
        reports = bug_reports(ctx)
    except GitHubUnavailable as exc:
        return skip(str(exc))
    numbers_ = {int(i["number"]) for i in ctx.issues()}
    good, _ = linked_xfails(ctx.pytest("nonui"))
    refs = set()
    for item in good:
        for a, b in ISSUE_REF.findall(item.get("xfail_reason") or ""):
            refs.add(int(a or b))
    dangling = sorted(refs - numbers_)
    hint = f"баг-репортов по форме: {len(reports)}, нужно 3"
    if dangling:
        hint += "; xfail ссылается на несуществующие issues: " + ", ".join(
            f"#{n}" for n in dangling
        )
    if len(reports) >= 3 and not dangling:
        return ok()
    if len(reports) >= 3:
        return partial(3, hint)
    return partial(2, hint) if reports else fail(hint)


@lab.check("report", "Раздел ЛР2 в README.md", 2)
def check_report(ctx: Context) -> Outcome:
    return report_section(
        ctx, 2, ["Тест-дизайн", "Найденные дефекты", "Что автоматизировано", "Выводы"], 2
    )
