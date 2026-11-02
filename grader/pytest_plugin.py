"""Плагин pytest для автопроверки.

Подключается только грейдером (`-p grader.pytest_plugin`) и пишет в JSON-файл из переменной
GRADER_PYTEST_REPORT сведения о каждом тесте: файл, маркеры, фикстуры, параметризацию,
признаки Hypothesis и Schemathesis, итог прогона и вызванные эндпоинты API.
На поведение тестов плагин не влияет.
"""

from __future__ import annotations

import json
import os
import types
from pathlib import Path
from typing import Any

import pytest

_items: dict[str, dict[str, Any]] = {}
_collect_errors: list[dict[str, str]] = []
_routes: dict[str, set[str]] = {}
_current: dict[str, str | None] = {"nodeid": None}


def _safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return repr(value)


def _install_route_hook() -> None:
    """Запоминает, какие маршруты FastAPI вызывал каждый тест."""
    try:
        from fastapi.routing import APIRoute
    except ImportError:
        return
    original = APIRoute.handle
    if getattr(original, "_grader_hook", False):
        return

    async def handle(self, scope, receive, send):  # noqa: ANN001, ANN202
        nodeid = _current["nodeid"]
        if nodeid is not None:
            _routes.setdefault(nodeid, set()).add(f"{scope.get('method', '')} {self.path}")
        await original(self, scope, receive, send)

    handle._grader_hook = True  # type: ignore[attr-defined]
    APIRoute.handle = handle  # type: ignore[method-assign]


def _imported_packages(module: types.ModuleType | None) -> set[str]:
    names: set[str] = set()
    if module is None:
        return names
    for value in vars(module).values():
        if isinstance(value, types.ModuleType):
            names.add(value.__name__.split(".")[0])
        else:
            owner = getattr(value, "__module__", None)
            if isinstance(owner, str) and owner:
                names.add(owner.split(".")[0])
    return names


def _is_schemathesis(item: pytest.Item) -> bool:
    if "schemathesis" in type(item).__module__:
        return True
    obj = getattr(item, "obj", None)
    if obj is None:
        return False
    if any(name.startswith("_schemathesis") for name in dir(obj)):
        return True
    return "case" in getattr(item, "fixturenames", ()) and "schemathesis" in _imported_packages(
        getattr(item, "module", None)
    )


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def pytest_configure(config: pytest.Config) -> None:
    _install_route_hook()


def pytest_collectreport(report: pytest.CollectReport) -> None:
    if report.failed:
        _collect_errors.append({"nodeid": report.nodeid, "message": str(report.longrepr)[-1500:]})


def pytest_collection_modifyitems(
    session: pytest.Session, config: pytest.Config, items: list[pytest.Item]
) -> None:
    strict_default = bool(config.getini("xfail_strict"))
    for item in items:
        obj = getattr(item, "obj", None)
        module = getattr(item, "module", None)
        _items[item.nodeid] = {
            "nodeid": item.nodeid,
            "path": _relative(Path(item.path), config.rootpath),
            "name": item.name,
            "function": getattr(item, "originalname", None) or item.name,
            "markers": [
                {
                    "name": mark.name,
                    "args": [_safe(a) for a in mark.args],
                    "kwargs": {k: _safe(v) for k, v in mark.kwargs.items()},
                }
                for mark in item.iter_markers()
            ],
            "fixtures": list(getattr(item, "fixturenames", [])),
            "parametrized": getattr(item, "callspec", None) is not None,
            "hypothesis": bool(getattr(obj, "is_hypothesis_test", False)),
            "schemathesis": _is_schemathesis(item),
            "imports": sorted(_imported_packages(module)),
            "xfail_strict_default": strict_default,
            "outcome": "not-run",
            "message": "",
        }


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):  # noqa: ANN201
    _current["nodeid"] = item.nodeid
    try:
        return (yield)
    finally:
        _current["nodeid"] = None


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    info = _items.get(report.nodeid)
    if info is None:
        return
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
        if hasattr(report, "wasxfail"):
            outcome = "xfailed" if report.skipped else "xpassed"
            info["xfail_reason"] = report.wasxfail
        elif report.failed:
            outcome = "failed" if report.when == "call" else "error"
        elif report.skipped:
            outcome = "skipped"
        else:
            outcome = "passed"
        info["outcome"] = outcome
        if report.failed or report.skipped:
            info["message"] = str(report.longrepr)[-1500:]
    elif report.when == "teardown" and report.failed and info["outcome"] == "passed":
        info["outcome"] = "error"
        info["message"] = str(report.longrepr)[-1500:]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    target = os.environ.get("GRADER_PYTEST_REPORT")
    if not target:
        return
    data = {
        "exitstatus": int(exitstatus),
        "items": list(_items.values()),
        "collect_errors": _collect_errors,
        "routes": {nodeid: sorted(routes) for nodeid, routes in _routes.items()},
    }
    Path(target).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
