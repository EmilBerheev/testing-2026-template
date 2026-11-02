"""Модель результатов, реестр проверок и вывод таблиц."""

from __future__ import annotations

import json
import os
import textwrap
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from grader.context import Context

STATUS_TEXT = {
    "pass": "пройдено",
    "partial": "частично",
    "fail": "не пройдено",
    "skip": "пропущено (только в CI)",
    "ci": "пройдено, остальное — в CI",
    "error": "ошибка автопроверки",
}
STATUS_ICON = {"pass": "✅", "partial": "⚠️", "fail": "❌", "skip": "⏭️", "ci": "☑️", "error": "💥"}


@dataclass
class Outcome:
    """Что вернула проверка. points=None — полный балл."""

    points: int | None = None
    hint: str = ""
    skipped: int = 0  # баллы, которые можно проверить только в CI
    status: str | None = None


def ok(hint: str = "") -> Outcome:
    return Outcome(points=None, hint=hint)


def partial(points: int, hint: str, skipped: int = 0) -> Outcome:
    return Outcome(points=points, hint=hint, skipped=skipped)


def fail(hint: str) -> Outcome:
    return Outcome(points=0, hint=hint)


def skip(hint: str) -> Outcome:
    return Outcome(points=0, hint=hint, status="skip")


@dataclass
class Result:
    id: str
    title: str
    max: int
    points: int = 0
    skipped: int = 0
    status: str = "fail"
    hint: str = ""


@dataclass
class Check:
    id: str
    title: str
    max: int
    func: Callable[[Context], Outcome]
    bonus: bool = False


@dataclass
class Lab:
    key: str
    title: str
    checks: list[Check] = field(default_factory=list)

    def check(
        self, check_id: str, title: str, points: int, *, bonus: bool = False
    ) -> Callable[[Callable[[Context], Outcome]], Callable[[Context], Outcome]]:
        def register(func: Callable[[Context], Outcome]) -> Callable[[Context], Outcome]:
            self.checks.append(Check(f"{self.key}.{check_id}", title, points, func, bonus))
            return func

        return register

    def run(self, ctx: Context) -> LabResult:
        results: list[Result] = []
        bonus: list[Result] = []
        crashed = False
        for check in self.checks:
            result = Result(check.id, check.title, check.max)
            try:
                outcome = check.func(ctx)
            except Exception as exc:  # ошибка самого грейдера: показываем и идём дальше
                crashed = True
                result.status = "error"
                result.hint = f"{type(exc).__name__}: {exc}"
                ctx.errors.append(f"{check.id}\n{traceback.format_exc()}")
            else:
                _apply(result, outcome)
            (bonus if check.bonus else results).append(result)
        return LabResult(self.key, self.title, results, bonus, crashed, ctx.tag_info(self.key))


def _apply(result: Result, outcome: Outcome) -> None:
    result.hint = outcome.hint
    if outcome.status == "skip":
        result.points = 0
        result.skipped = result.max
        result.status = "skip"
        return
    points = result.max if outcome.points is None else max(0, min(outcome.points, result.max))
    result.points = points
    result.skipped = min(outcome.skipped, result.max - points)
    if points == result.max:
        result.status = "pass"
    elif points + result.skipped == result.max and result.skipped:
        result.status = "skip" if points == 0 else "ci"
    elif points > 0:
        result.status = "partial"
    else:
        result.status = "fail"


@dataclass
class LabResult:
    key: str
    title: str
    results: list[Result]
    bonus: list[Result]
    crashed: bool
    tag: str

    @property
    def score(self) -> int:
        return sum(r.points for r in self.results)

    @property
    def max(self) -> int:
        return sum(r.max for r in self.results)

    @property
    def skipped(self) -> int:
        return sum(r.skipped for r in self.results)

    @property
    def bonus_score(self) -> int:
        return sum(r.points for r in self.bonus)


# --- вывод ------------------------------------------------------------------


def render_console(lab: LabResult, variant: str) -> str:
    width = 106
    lines = ["", f"{lab.title} — {variant}", "─" * width]
    for r in [*lab.results, *lab.bonus]:
        score = f"{r.points}/{r.max}" + (" бонус" if r in lab.bonus else "")
        head = f" {r.id:<20} {r.title:<54} {score:>9}  {STATUS_TEXT[r.status]}"
        lines.append(head)
        if r.hint and r.status != "pass":
            for chunk in textwrap.wrap(r.hint, width=width - 8):
                lines.append(f"       → {chunk}")
    lines.append("─" * width)
    total = f" Итого {lab.title.split('.')[0]}: {lab.score}/{lab.max}"
    if lab.skipped:
        total += f" (ещё {lab.skipped} балл(ов) проверяются только в CI)"
    if lab.bonus:
        total += f"; бонус: +{lab.bonus_score}"
    lines.append(total)
    lines.append(f" {lab.tag}")
    return "\n".join(lines)


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(labs: list[LabResult], variant: str) -> str:
    out = [f"# Автопроверка — {variant}", ""]
    out.append("| Работа | Баллы (авто) | Только в CI |")
    out.append("|---|---|---|")
    for lab in labs:
        out.append(f"| {lab.title} | **{lab.score} / {lab.max}** | {lab.skipped or ''} |")
    for lab in labs:
        out += ["", f"## {lab.title} — {lab.score} / {lab.max}", "", f"_{lab.tag}_", ""]
        out.append("| Проверка | Баллы | Статус | Что исправить |")
        out.append("|---|---|---|---|")
        for r in [*lab.results, *lab.bonus]:
            hint = "" if r.status == "pass" else _md(r.hint)
            name = f"`{r.id}` {_md(r.title)}" + (" (бонус)" if r in lab.bonus else "")
            status = f"{STATUS_ICON[r.status]} {STATUS_TEXT[r.status]}"
            out.append(f"| {name} | {r.points} / {r.max} | {status} | {hint} |")
    out.append("")
    out.append(
        "Автоматическая часть — 60 баллов из 100, остальные 40 ставит преподаватель на защите."
    )
    return "\n".join(out) + "\n"


def write_outputs(ctx: Context, labs: list[LabResult]) -> None:
    variant = ctx.variant_label()
    for lab in labs:
        print(render_console(lab, variant))
    if ctx.integrity_warning:
        print(f"\n ВНИМАНИЕ: {ctx.integrity_warning}")
    data = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "commit": os.environ.get("GITHUB_SHA", ctx.git_head()),
        "variant": ctx.variant,
        "integrity_warning": ctx.integrity_warning,
        "labs": {
            lab.key: {
                "title": lab.title,
                "score": lab.score,
                "max": lab.max,
                "skipped": lab.skipped,
                "bonus": lab.bonus_score,
                "tag": lab.tag,
                "checks": [asdict(r) for r in lab.results],
                "bonus_checks": [asdict(r) for r in lab.bonus],
            }
            for lab in labs
        },
    }
    (ctx.root / "grade.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        markdown = render_markdown(labs, variant)
        if ctx.integrity_warning:
            markdown += f"\n> **Внимание:** {ctx.integrity_warning}\n"
        with Path(summary).open("a", encoding="utf-8") as fh:
            fh.write(markdown)
    print(f"\n Результат записан в {ctx.root / 'grade.json'}")
