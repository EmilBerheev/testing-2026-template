"""Точка входа: uv run python -m grader lab1 | lab2 | lab3 | lab4 | all."""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        prog="python -m grader", description="Автопроверка лабораторных «Тестирование ПО»"
    )
    parser.add_argument("labs", nargs="*", default=["all"], help="lab1 … lab4 или all")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="корень репозитория")
    args = parser.parse_args(argv)

    from grader import lab1, lab2, lab3, lab4
    from grader.context import Context
    from grader.core import write_outputs

    registry = {lab.key: lab for lab in (lab1.lab, lab2.lab, lab3.lab, lab4.lab)}
    wanted = list(registry) if "all" in args.labs else args.labs
    unknown = [name for name in wanted if name not in registry]
    if unknown:
        parser.error(f"неизвестные работы: {', '.join(unknown)}; есть {', '.join(registry)}, all")

    root = args.root.resolve()
    sys.path.insert(0, str(root))
    ctx = Context(root)
    print(f"Автопроверка: {', '.join(wanted)} — {ctx.variant_label()}", flush=True)
    results = [registry[name].run(ctx) for name in wanted]
    write_outputs(ctx, results)
    if ctx.errors:
        print("\n Внутренние ошибки автопроверки (сообщите преподавателю):", file=sys.stderr)
        for error in ctx.errors:
            print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        sys.exit(1)
