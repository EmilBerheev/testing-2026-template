"""Командная строка: uv run bookshop [serve|variant] [--host H] [--port P]."""

from __future__ import annotations

import argparse
import sys

from bookshop.variants import LABELS, load_params


def show_variant() -> None:
    params = load_params()
    print(f"Вариант {params.variant}")
    if params.variant == 0:
        print("(демонстрационный: впишите свой номер в variant.toml)")
    for key, label in LABELS.items():
        print(f"  {label:<48} {getattr(params, key)}")


def serve(host: str, port: int) -> None:
    import uvicorn

    from bookshop.api import create_app

    params = load_params()
    print(f"Книжная лавка, вариант {params.variant}: http://{host}:{port}")
    uvicorn.run(create_app(params), host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="bookshop", description="Книжная лавка")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve", "variant"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.command == "variant":
        show_variant()
    else:
        serve(args.host, args.port)


if __name__ == "__main__":
    main()
