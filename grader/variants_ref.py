"""Эталонная таблица вариантов для автопроверки.

Копия таблицы из src/bookshop/variants.py. Грейдер берёт границы отсюда и сверяет с таблицей
приложения: если её поменяли, в отчёте появится предупреждение.
"""

from __future__ import annotations

FIELDS = (
    "max_items",
    "max_qty",
    "silver_pct",
    "gold_pct",
    "bulk_qty",
    "bulk_pct",
    "promo_code",
    "promo_pct",
    "promo_min",
    "max_discount_pct",
    "free_delivery_from",
    "delivery_fee",
)

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


def params(variant: int) -> dict[str, int | str] | None:
    row = _TABLE.get(variant)
    if row is None:
        return None
    return {"variant": variant, **dict(zip(FIELDS, row, strict=True))}
