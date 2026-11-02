"""Параметры бизнес-правил по вариантам.

Номер варианта выдаёт преподаватель. Приложение берёт его из переменной окружения
BOOKSHOP_VARIANT, а если её нет — из файла variant.toml в корне репозитория.
Вариант 0 — демонстрационный: на нём работает приложение «из коробки».

Посмотреть параметры своего варианта: uv run bookshop variant
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Params:
    """Параметры правил. Имена в верхнем регистре — как в docs/requirements.md."""

    variant: int
    max_items: int  # MAX_ITEMS — разных книг в заказе, не больше
    max_qty: int  # MAX_QTY — экземпляров одной книги, не больше
    silver_pct: int  # SILVER_PCT — скидка по серебряной карте, %
    gold_pct: int  # GOLD_PCT — скидка по золотой карте, %
    bulk_qty: int  # BULK_QTY — с какого числа экземпляров действует оптовая скидка
    bulk_pct: int  # BULK_PCT — оптовая скидка, %
    promo_code: str  # PROMO_CODE — промокод
    promo_pct: int  # PROMO_PCT — скидка по промокоду, %
    promo_min: int  # PROMO_MIN — минимальная сумма для промокода, ₽
    max_discount_pct: int  # MAX_DISCOUNT — потолок суммарной скидки, %
    free_delivery_from: int  # FREE_DELIVERY_FROM — бесплатная доставка от, ₽
    delivery_fee: int  # DELIVERY_FEE — стоимость курьерской доставки, ₽

    def as_dict(self) -> dict[str, int | str]:
        return asdict(self)


# variant: (MAX_ITEMS, MAX_QTY, SILVER_PCT, GOLD_PCT, BULK_QTY, BULK_PCT,
#           PROMO_CODE, PROMO_PCT, PROMO_MIN, MAX_DISCOUNT, FREE_DELIVERY_FROM, DELIVERY_FEE)
_TABLE: dict[int, tuple[int, int, int, int, int, int, str, int, int, int, int, int]] = {
    0: (5, 10, 5, 10, 10, 5, "READMORE", 15, 1500, 25, 3000, 299),
    1: (6, 10, 4, 9, 6, 8, "KNIGA", 15, 2000, 27, 2000, 199),
    2: (4, 7, 3, 9, 8, 6, "BOOKWORM", 12, 1500, 18, 2000, 390),
    3: (5, 9, 3, 8, 9, 6, "CHITAY", 10, 2000, 15, 3000, 290),
    4: (5, 6, 5, 9, 8, 10, "STRANICA", 10, 2000, 24, 2500, 199),
    5: (4, 8, 3, 9, 9, 7, "LISTAI", 10, 2500, 17, 4000, 349),
    6: (6, 7, 5, 9, 8, 6, "ZAKLADKA", 12, 1000, 20, 3000, 390),
    7: (4, 8, 4, 10, 9, 7, "POLKA", 12, 1500, 16, 3000, 199),
    8: (5, 5, 4, 7, 8, 8, "ABZAC", 15, 1000, 25, 3000, 290),
    9: (3, 6, 4, 9, 7, 5, "GLAVA", 12, 1000, 18, 4000, 199),
    10: (3, 5, 5, 8, 7, 10, "ROMAN", 15, 1000, 26, 3000, 199),
    11: (3, 6, 4, 8, 6, 8, "NOVELLA", 10, 2000, 18, 2500, 249),
    12: (6, 10, 3, 9, 5, 8, "SKAZKA", 10, 2500, 23, 3500, 299),
    13: (3, 10, 3, 10, 8, 7, "POEMA", 12, 1000, 15, 2500, 299),
    14: (6, 8, 3, 7, 8, 6, "ALMANAH", 15, 1500, 19, 4000, 299),
    15: (3, 5, 5, 8, 8, 10, "FOLIANT", 10, 2500, 19, 4000, 349),
    16: (3, 10, 3, 7, 7, 10, "PEREPLET", 10, 1000, 24, 3000, 349),
    17: (4, 10, 3, 8, 7, 7, "EXLIBRIS", 10, 2000, 13, 2000, 290),
    18: (4, 6, 4, 9, 9, 5, "PROLOG", 12, 2000, 15, 3500, 390),
    19: (3, 5, 5, 10, 7, 5, "EPILOG", 12, 1500, 23, 3500, 290),
    20: (4, 8, 5, 10, 9, 10, "SYUZHET", 10, 2000, 26, 3000, 349),
}

VARIANTS: dict[int, Params] = {n: Params(n, *row) for n, row in _TABLE.items()}

#: Подписи параметров для `bookshop variant` и для отчётов.
LABELS: dict[str, str] = {
    "max_items": "MAX_ITEMS — разных книг в заказе, не больше",
    "max_qty": "MAX_QTY — экземпляров одной книги, не больше",
    "silver_pct": "SILVER_PCT — скидка по серебряной карте, %",
    "gold_pct": "GOLD_PCT — скидка по золотой карте, %",
    "bulk_qty": "BULK_QTY — оптовая скидка от, экземпляров",
    "bulk_pct": "BULK_PCT — оптовая скидка, %",
    "promo_code": "PROMO_CODE — промокод",
    "promo_pct": "PROMO_PCT — скидка по промокоду, %",
    "promo_min": "PROMO_MIN — промокод действует от, ₽",
    "max_discount_pct": "MAX_DISCOUNT — потолок суммарной скидки, %",
    "free_delivery_from": "FREE_DELIVERY_FROM — бесплатная доставка от, ₽",
    "delivery_fee": "DELIVERY_FEE — курьерская доставка, ₽",
}


def _variant_file_candidates() -> list[Path]:
    here = Path.cwd().resolve()
    package_root = Path(__file__).resolve().parents[2]
    candidates = [here / "variant.toml", *(p / "variant.toml" for p in here.parents)]
    candidates.append(package_root / "variant.toml")
    return candidates


def read_variant_number() -> int:
    """Номер варианта: BOOKSHOP_VARIANT, затем variant.toml, иначе 0."""
    env = os.environ.get("BOOKSHOP_VARIANT", "").strip()
    if env:
        return int(env)
    for path in _variant_file_candidates():
        if path.is_file():
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            return int(data.get("variant", 0))
    return 0


def load_params(variant: int | None = None) -> Params:
    number = read_variant_number() if variant is None else variant
    try:
        return VARIANTS[number]
    except KeyError:
        known = f"{min(VARIANTS)}–{max(VARIANTS)}"
        raise ValueError(f"Варианта {number} нет, допустимые номера: {known}") from None
