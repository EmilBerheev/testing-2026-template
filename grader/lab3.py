"""ЛР3. Функциональное тестирование API и UI."""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from grader.common import report_section
from grader.context import Context, PytestRun, describe
from grader.core import Lab, Outcome, fail, ok, partial

lab = Lab("lab3", "ЛР3. Функциональное тестирование API и UI")

SEMANTIC = {
    "get_by_role",
    "get_by_label",
    "get_by_test_id",
    "get_by_text",
    "get_by_placeholder",
    "get_by_alt_text",
    "get_by_title",
}
DIRECT = SEMANTIC | {
    "locator",
    "click",
    "fill",
    "type",
    "press",
    "check",
    "uncheck",
    "select_option",
    "dblclick",
    "hover",
    "query_selector",
    "query_selector_all",
    "wait_for_selector",
    "text_content",
    "inner_text",
    "is_visible",
}
NOT_REQUIRED_ROUTES = {"POST /api/admin/reset"}


def api_items(ctx: Context) -> tuple[list[dict[str, Any]], str]:
    run = ctx.pytest("nonui")
    if run.problem:
        return [], run.problem
    problem = run.collect_problem("tests/api")
    if problem:
        return [], problem
    return [i for i in run.under("tests/api/") if not i["schemathesis"]], ""


@lab.check("api_tests", "Не меньше 15 API-тестов, все проходят", 10)
def check_api_tests(ctx: Context) -> Outcome:
    tests, problem = api_items(ctx)
    if problem:
        return fail(problem)
    broken = PytestRun.broken(tests)
    if broken:
        return fail(f"падают API-тесты: {describe(broken)}")
    if len(tests) >= 15:
        return ok()
    hint = f"API-тестов в tests/api: {len(tests)}, нужно не меньше 15"
    return partial(5, hint) if len(tests) >= 8 else fail(hint)


@lab.check("api_negative", "Негативные API-тесты (@pytest.mark.negative)", 6)
def check_api_negative(ctx: Context) -> Outcome:
    tests, problem = api_items(ctx)
    if problem:
        return fail(problem)
    negative = [t for t in tests if any(m["name"] == "negative" for m in t["markers"])]
    if len(negative) >= 6:
        return ok()
    hint = f"негативных API-тестов: {len(negative)}, нужно 6 (маркер @pytest.mark.negative)"
    return partial(3, hint) if len(negative) >= 3 else fail(hint)


def required_routes() -> set[str]:
    from bookshop.api import create_app
    from bookshop.variants import load_params

    schema = create_app(load_params(0)).openapi()
    routes = set()
    for path, operations in schema["paths"].items():
        for method in operations:
            routes.add(f"{method.upper()} {path}")
    return routes - NOT_REQUIRED_ROUTES


@lab.check("api_endpoints", "API-тесты вызывают все эндпоинты", 4)
def check_api_endpoints(ctx: Context) -> Outcome:
    tests, problem = api_items(ctx)
    if problem:
        return fail(problem)
    run = ctx.pytest("nonui")
    hit: set[str] = set()
    for item in tests:
        hit |= set(run.routes.get(item["nodeid"], []))
    try:
        required = required_routes()
    except Exception as exc:  # приложение не импортируется — покажут тесты
        return fail(f"не удалось получить список эндпоинтов: {exc}")
    missing = sorted(required - hit)
    share = 1 - len(missing) / len(required)
    if not missing:
        return ok()
    hint = "не вызваны: " + ", ".join(missing[:6]) + (" …" if len(missing) > 6 else "")
    return partial(2, hint) if share >= 0.75 else fail(hint)


@lab.check("schemathesis", "Контрактные тесты Schemathesis по OpenAPI", 8)
def check_schemathesis(ctx: Context) -> Outcome:
    run = ctx.pytest("nonui")
    if run.problem:
        return fail(run.problem)
    items = [i for i in run.under("tests/api/") if i["schemathesis"]]
    if not items:
        return fail("в tests/api нет тестов, построенных Schemathesis (schema.parametrize())")
    broken = PytestRun.broken(items)
    green = [i for i in items if PytestRun.green(i)]
    if not broken and green:
        return ok()
    if broken:
        return partial(
            3,
            f"падают контрактные тесты: {describe(broken)}. Найденный дефект оформите issue и "
            "закрепите отдельным API-тестом с xfail, а в контрактном тесте отключите проверку "
            "или ограничьте данные (см. задание ЛР3)",
        )
    return fail("контрактные тесты не выполнились (все пропущены)")


def _hurl_stats(files: list[Path]) -> dict[str, int]:
    requests = with_status = asserts = templated = 0
    for file in files:
        current = False
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if re.match(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+\S+", stripped):
                requests += 1
                current = True
                if "{{" in stripped:
                    templated += 1
            elif current and re.match(r"^HTTP(/[\d.]+)?\s+\d{3}\b", stripped):
                with_status += 1
                current = False
            elif stripped == "[Asserts]":
                asserts += 1
    return {"requests": requests, "checked": with_status, "body": asserts, "templated": templated}


def _bruno_stats(root: Path) -> dict[str, int]:
    requests = checked = body = templated = 0
    for file in root.rglob("*"):
        if file.suffix not in {".bru", ".yml", ".yaml"} or "environments" in file.parts:
            continue
        if file.name in {"collection.bru", "folder.bru", "opencollection.yml", "folder.yml"}:
            continue
        text = file.read_text(encoding="utf-8", errors="replace")
        url = re.search(r"^\s*url:\s*(.+)$", text, re.M)
        if not url:
            continue
        requests += 1
        if "{{" in url.group(1):
            templated += 1
        has_assert = re.search(r"^\s*(assert|tests)\s*\{", text, re.M) or re.search(
            r"^\s*(assertions:|- type: tests|type: tests)", text, re.M
        )
        if has_assert:
            checked += 1
        if "res.body" in text or "res.getBody" in text:
            body += 1
    return {"requests": requests, "checked": checked, "body": body, "templated": templated}


@lab.check("collection", "Коллекция Hurl или Bruno с проверками", 8)
def check_collection(ctx: Context) -> Outcome:
    folder = ctx.path("api-collection")
    if not folder.is_dir():
        return fail("нет папки api-collection")
    hurl = sorted(folder.rglob("*.hurl"))
    is_bruno = (folder / "bruno.json").is_file() or (folder / "opencollection.yml").is_file()
    if hurl:
        stats, tool = _hurl_stats(hurl), "Hurl"
    elif is_bruno:
        stats, tool = _bruno_stats(folder), "Bruno"
    else:
        return fail("в api-collection нет ни файлов .hurl, ни коллекции Bruno")
    score, hints = 0, []
    if stats["checked"] >= 6:
        score += 4
    elif stats["checked"] >= 3:
        score += 2
        hints.append(f"запросов с проверкой ответа {stats['checked']}, нужно 6")
    else:
        hints.append(f"{tool}: запросов с проверкой ответа {stats['checked']}, нужно 6")
    if stats["body"] >= 3:
        score += 2
    else:
        hints.append("проверьте тело ответа хотя бы в 3 запросах ([Asserts] или res.body)")
    if stats["requests"] and stats["templated"] == stats["requests"]:
        score += 2
    else:
        hints.append("адрес сервера — только через переменную {{base_url}}")
    return ok() if score == 8 else partial(score, "; ".join(hints))


@lab.check("ui_tests", "Не меньше 5 UI-тестов Playwright, все проходят", 10)
def check_ui_tests(ctx: Context) -> Outcome:
    run = ctx.pytest("ui")
    if run.problem:
        return fail(run.problem)
    problem = run.collect_problem("tests/ui")
    if problem:
        return fail(problem)
    tests = [i for i in run.under("tests/ui/") if "page" in i["fixtures"]]
    broken = PytestRun.broken(tests)
    if any("Executable doesn't exist" in i["message"] for i in broken):
        return fail("не установлен браузер: выполните uv run playwright install chromium")
    if broken:
        return fail(f"падают UI-тесты: {describe(broken)}")
    if len(tests) >= 5:
        return ok()
    hint = f"UI-тестов с фикстурой page: {len(tests)}, нужно 5"
    return partial(5, hint) if len(tests) >= 3 else fail(hint)


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _page_calls(tree: ast.AST) -> list[str]:
    calls = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "page"
            and node.func.attr in DIRECT
        ):
            calls.append(node.func.attr)
    return calls


@lab.check("page_objects", "Page Object: тесты не обращаются к элементам напрямую", 6)
def check_page_objects(ctx: Context) -> Outcome:
    pages_dir = ctx.path("tests/ui/pages")
    classes = 0
    for file in sorted(pages_dir.glob("*.py")) if pages_dir.is_dir() else []:
        tree = _parse(file)
        for node in ast.walk(tree) if tree else []:
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                if any(m.name != "__init__" for m in methods):
                    classes += 1
    if classes < 2:
        return fail(f"в tests/ui/pages классов Page Object с методами: {classes}, нужно 2")
    direct: list[str] = []
    for file in sorted(ctx.path("tests/ui").glob("test_*.py")):
        tree = _parse(file)
        if tree:
            direct += [f"{file.name}: page.{c}()" for c in _page_calls(tree)]
    if not direct:
        return ok()
    hint = f"тесты обращаются к элементам мимо Page Object ({len(direct)}): " + ", ".join(
        direct[:3]
    )
    return partial(3, hint) if len(direct) <= 3 else fail(hint)


@lab.check("locators", "Устойчивые локаторы: роли, подписи, test id", 4)
def check_locators(ctx: Context) -> Outcome:
    pages_dir = ctx.path("tests/ui/pages")
    semantic = css = 0
    xpath: list[str] = []
    for file in sorted(pages_dir.glob("*.py")) if pages_dir.is_dir() else []:
        tree = _parse(file)
        for node in ast.walk(tree) if tree else []:
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                continue
            if node.func.attr in SEMANTIC:
                semantic += 1
            elif node.func.attr == "locator":
                css += 1
                arg = node.args[0] if node.args else None
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    value = arg.value.strip()
                    if value.startswith(("//", "(//", "xpath=")):
                        xpath.append(value)
    total = semantic + css
    if total == 0:
        return fail("в tests/ui/pages нет ни одного локатора")
    if xpath:
        return fail("уберите XPath из локаторов: " + ", ".join(xpath[:3]))
    share = semantic / total
    measured = f"get_by_role/label/test_id: {semantic} из {total} ({share:.0%})"
    if share >= 0.7:
        return ok(measured)
    return partial(2, measured + ", нужно от 70 %") if share >= 0.4 else fail(measured)


@lab.check("report", "Раздел ЛР3 в README.md", 4)
def check_report(ctx: Context) -> Outcome:
    return report_section(ctx, 3, ["API-тесты", "Контракт и Schemathesis", "UI-тесты", "Выводы"], 4)
