"""Общее состояние прогона: вариант, файлы репозитория, прогоны pytest, GitHub API."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from grader import variants_ref

PYTEST_RUNS: dict[str, tuple[list[str], bool, int]] = {
    # ключ: (аргументы pytest, мерить покрытие, таймаут в секундах)
    "unit": (["tests/unit"], True, 600),
    "nonui": (["tests", "--ignore=tests/ui"], True, 1200),
    "ui": (["tests/ui"], False, 1200),
}


class GitHubUnavailable(Exception):
    """GitHub API недоступен: нет токена (локальный запуск) или ошибка сети."""


@dataclass
class PytestRun:
    key: str
    items: list[dict[str, Any]] = field(default_factory=list)
    collect_errors: list[dict[str, str]] = field(default_factory=list)
    routes: dict[str, list[str]] = field(default_factory=dict)
    coverage: dict[str, Any] | None = None
    exitstatus: int | None = None
    problem: str = ""  # почему прогон не удался целиком

    def under(self, prefix: str) -> list[dict[str, Any]]:
        return [i for i in self.items if i["path"].startswith(prefix)]

    @staticmethod
    def broken(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [i for i in items if i["outcome"] in {"failed", "error", "xpassed"}]

    @staticmethod
    def green(item: dict[str, Any]) -> bool:
        return item["outcome"] in {"passed", "xfailed"}

    def collect_problem(self, prefix: str = "") -> str:
        errors = [e for e in self.collect_errors if e["nodeid"].startswith(prefix)]
        if not errors:
            return ""
        first = errors[0]
        last_line = [ln for ln in first["message"].splitlines() if ln.strip()][-1:]
        detail = last_line[0].strip() if last_line else ""
        return f"ошибка при сборе тестов в {first['nodeid'] or 'tests'}: {detail}"

    def coverage_of(self, suffix: str) -> float | None:
        if not self.coverage:
            return None
        for name, data in self.coverage.get("files", {}).items():
            if name.replace("\\", "/").endswith(suffix):
                return float(data["summary"]["percent_covered"])
        return 0.0

    def coverage_total(self) -> float | None:
        if not self.coverage:
            return None
        return float(self.coverage["totals"]["percent_covered"])


def describe(items: list[dict[str, Any]], limit: int = 3) -> str:
    names = [i["nodeid"] for i in items[:limit]]
    more = f" и ещё {len(items) - limit}" if len(items) > limit else ""
    return ", ".join(names) + more


class Context:
    def __init__(self, root: Path):
        self.root = root
        self.workdir = root / ".grader"
        self.workdir.mkdir(exist_ok=True)
        self.errors: list[str] = []
        self.variant: int | None = None
        self.variant_problem = ""
        self.params: dict[str, Any] | None = None
        self.integrity_warning = ""
        self._runs: dict[str, PytestRun] = {}
        self._issues: list[dict[str, Any]] | None = None
        self._read_variant()
        self._check_integrity()

    # --- вариант ---------------------------------------------------------

    def _read_variant(self) -> None:
        path = self.root / "variant.toml"
        if not path.is_file():
            self.variant_problem = "нет файла variant.toml в корне репозитория"
            return
        try:
            value = tomllib.loads(path.read_text(encoding="utf-8")).get("variant")
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
            self.variant_problem = f"variant.toml не читается: {exc}"
            return
        if not isinstance(value, int) or variants_ref.params(value) is None:
            self.variant_problem = f"в variant.toml указано variant = {value!r}, а нужен номер 1–20"
            return
        self.variant = value
        self.params = variants_ref.params(value)
        if value == 0:
            self.variant_problem = "в variant.toml стоит демонстрационный вариант 0"

    def _check_integrity(self) -> None:
        try:
            from bookshop import variants as app_variants
        except Exception as exc:  # приложение сломано — это покажут тесты
            self.integrity_warning = f"не удалось импортировать bookshop.variants: {exc}"
            return
        for number in range(0, 21):
            expected = variants_ref.params(number)
            actual = app_variants.VARIANTS.get(number)
            if actual is None or actual.as_dict() != expected:
                self.integrity_warning = (
                    f"таблица вариантов в src/bookshop/variants.py изменена (вариант {number}). "
                    "Автопроверка берёт границы из эталонной таблицы, преподаватель увидит это."
                )
                return

    def variant_label(self) -> str:
        if self.variant is None or self.variant == 0:
            return "вариант не указан"
        return f"вариант {self.variant}"

    @property
    def variant_ok(self) -> bool:
        return self.variant is not None and self.variant > 0

    # --- файлы -----------------------------------------------------------

    def path(self, relative: str) -> Path:
        return self.root / relative

    def read(self, relative: str) -> str | None:
        path = self.path(relative)
        if not path.is_file():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def first_existing(self, *candidates: str) -> str | None:
        for candidate in candidates:
            if self.path(candidate).is_file():
                return candidate
        return None

    def load_yaml(self, relative: str) -> tuple[Any, str]:
        text = self.read(relative)
        if text is None:
            return None, f"нет файла {relative}"
        try:
            return yaml.safe_load(text), ""
        except yaml.YAMLError as exc:
            return None, f"{relative}: ошибка YAML — {str(exc).splitlines()[0]}"

    def workflow(self) -> tuple[dict[str, Any] | None, str, str]:
        """Файл .github/workflows/ci.yml: (данные, текст, проблема)."""
        rel = self.first_existing(".github/workflows/ci.yml", ".github/workflows/ci.yaml")
        if rel is None:
            return None, "", "нет файла .github/workflows/ci.yml"
        data, problem = self.load_yaml(rel)
        if problem:
            return None, "", problem
        if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
            return None, "", f"{rel}: нет раздела jobs"
        return data, self.read(rel) or "", ""

    def pyproject(self) -> dict[str, Any]:
        try:
            return tomllib.loads(self.read("pyproject.toml") or "")
        except tomllib.TOMLDecodeError:
            return {}

    # --- pytest ----------------------------------------------------------

    def pytest(self, key: str) -> PytestRun:
        if key not in self._runs:
            self._runs[key] = self._run_pytest(key)
        return self._runs[key]

    def _run_pytest(self, key: str) -> PytestRun:
        args, with_coverage, timeout = PYTEST_RUNS[key]
        run = PytestRun(key)
        report = self.workdir / f"pytest-{key}.json"
        coverage_file = self.workdir / f"coverage-{key}.json"
        for stale in (report, coverage_file):
            stale.unlink(missing_ok=True)
        if not self.path(args[0]).exists():
            run.problem = f"нет папки {args[0]}"
            return run
        command = [sys.executable, "-m", "pytest", *args, "-p", "grader.pytest_plugin"]
        command += ["-o", "addopts=", "-p", "no:cacheprovider", "-q", "--tb=short", "-rN"]
        if with_coverage:
            command += ["--cov=bookshop", "--cov-branch", f"--cov-report=json:{coverage_file}"]
        env = {**os.environ, "GRADER_PYTEST_REPORT": str(report), "PYTHONUTF8": "1"}
        if self.variant is not None:
            env["BOOKSHOP_VARIANT"] = str(self.variant)
        print(f" … pytest {' '.join(args)}", flush=True)
        try:
            completed = subprocess.run(
                command,
                cwd=self.root,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            run.problem = f"pytest {' '.join(args)} не уложился в {timeout} с — тесты зависли?"
            return run
        run.exitstatus = completed.returncode
        if report.is_file():
            data = json.loads(report.read_text(encoding="utf-8"))
            run.items = data["items"]
            run.collect_errors = data["collect_errors"]
            run.routes = data["routes"]
        else:
            tail = (completed.stdout + completed.stderr).strip().splitlines()[-5:]
            run.problem = "pytest не запустился: " + " | ".join(tail)
        output = (completed.stdout + completed.stderr).strip().splitlines()
        if run.exitstatus == 3 or (run.exitstatus == 2 and not run.collect_errors):
            internal = [ln for ln in output if "INTERNALERROR" in ln][-1:]
            run.problem = f"pytest аварийно завершился (код {run.exitstatus}): " + (
                internal[0].strip() if internal else " | ".join(output[-3:])
            )
        elif run.exitstatus == 4:
            run.problem = "pytest не принял параметры запуска: " + " | ".join(output[-3:])
        if with_coverage and coverage_file.is_file():
            run.coverage = json.loads(coverage_file.read_text(encoding="utf-8"))
        (self.workdir / f"pytest-{key}.log").write_text(
            completed.stdout + completed.stderr, encoding="utf-8"
        )
        return run

    # --- инструменты -----------------------------------------------------

    def tool(self, name: str) -> str | None:
        return shutil.which(name)

    def run_command(self, command: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
        return subprocess.run(
            command,
            cwd=self.root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            env={**os.environ, "PYTHONUTF8": "1"},
        )

    # --- git и GitHub ----------------------------------------------------

    def git_head(self) -> str:
        try:
            result = self.run_command(["git", "rev-parse", "HEAD"], timeout=30)
        except (OSError, subprocess.SubprocessError):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    def tag_info(self, lab_key: str) -> str:
        tag = f"lab-{lab_key.removeprefix('lab')}"
        try:
            result = self.run_command(
                ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"],
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return f"Тег {tag}: git недоступен"
        if result.returncode != 0 or not result.stdout.strip():
            return (
                f"Тег {tag} не найден: работа считается сданной, когда на коммите стоит тег {tag}"
            )
        return f"Тег {tag} стоит на коммите {result.stdout.strip()[:7]}"

    def issues(self) -> list[dict[str, Any]]:
        if self._issues is not None:
            return self._issues
        token = os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPOSITORY")
        if not token or not repo:
            raise GitHubUnavailable("нужен GitHub API (GITHUB_TOKEN), проверяется в Actions")
        api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
        issues: list[dict[str, Any]] = []
        for page in range(1, 6):
            request = urllib.request.Request(
                f"{api}/repos/{repo}/issues?state=all&per_page=100&page={page}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "testing-course-grader",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    batch = json.loads(response.read().decode("utf-8"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise GitHubUnavailable(f"GitHub API не ответил: {exc}") from exc
            issues += [i for i in batch if "pull_request" not in i]
            if len(batch) < 100:
                break
        self._issues = issues
        return issues
