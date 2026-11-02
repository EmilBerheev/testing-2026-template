"""Расчёт стоимости заказа.

Модуль ничего не знает про HTTP и хранение: на вход — строки заказа и параметры
варианта, на выход — суммы. Его удобно проверять модульными тестами (ЛР1).
Требования к расчёту — в docs/requirements.md, разделы R-02, R-03, R-06…R-12.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from bookshop.variants import Params

KOPECK = Decimal("0.01")
ZERO = Decimal("0.00")
LOYALTY_LEVELS = ("none", "silver", "gold")
DELIVERY_METHODS = ("pickup", "courier")


class RuleViolation(ValueError):
    """Нарушено бизнес-правило. field — поле запроса, к которому относится ошибка."""

    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True)
class Line:
    """Строка заказа: книга, цена за экземпляр и количество."""

    book_id: int
    price: Decimal
    qty: int

    @property
    def total(self) -> Decimal:
        return money(self.price * self.qty)


@dataclass(frozen=True)
class Quote:
    """Результат расчёта. Все суммы — в рублях с копейками."""

    items_count: int
    subtotal: Decimal
    discount_percent: int
    discount: Decimal
    goods_total: Decimal
    delivery_cost: Decimal
    total: Decimal
    promo_applied: bool


def money(value: Decimal | int | str) -> Decimal:
    """Округляет сумму до копейки по математическим правилам."""
    return Decimal(value).quantize(KOPECK, rounding=ROUND_HALF_UP)


def check_lines(lines: Sequence[tuple[int, int]], params: Params) -> None:
    """Проверяет позиции заказа: (book_id, qty). R-02, R-03."""
    if not lines:
        raise RuleViolation("items", "В заказе должна быть хотя бы одна позиция")
    if len(lines) > params.max_items:
        raise RuleViolation(
            "items", f"В заказе может быть не больше {params.max_items} разных книг"
        )
    seen: set[int] = set()
    for book_id, qty in lines:
        if book_id in seen:
            raise RuleViolation("items", f"Книга {book_id} указана в заказе дважды")
        seen.add(book_id)
        if qty not in range(1, params.max_qty):
            raise RuleViolation(
                "qty", f"Количество одной книги — от 1 до {params.max_qty} экземпляров"
            )


def subtotal(lines: Iterable[Line]) -> Decimal:
    return money(sum((line.total for line in lines), ZERO))


def items_count(lines: Iterable[Line]) -> int:
    return sum(line.qty for line in lines)


def normalize_promo(code: str | None) -> str | None:
    if code is None:
        return None
    code = code.strip()
    return code or None


def promo_applies(code: str | None, amount: Decimal, params: Params) -> bool:
    """True, если промокод указан и действует. Неверный промокод — ошибка. R-08."""
    code = normalize_promo(code)
    if code is None:
        return False
    if code != params.promo_code:
        raise RuleViolation("promo_code", "Такого промокода нет")
    if amount < params.promo_min:
        raise RuleViolation("promo_code", f"Промокод действует для заказов от {params.promo_min} ₽")
    return True


def loyalty_percent(level: str, params: Params) -> int:
    """Скидка по карте лояльности. R-06."""
    match level:
        case "none":
            return 0
        case "silver":
            return params.silver_pct
        case "gold":
            return params.gold_pct
    raise RuleViolation("loyalty", f"Неизвестный уровень карты: {level}")


def bulk_percent(count: int, params: Params) -> int:
    """Оптовая скидка по общему числу экземпляров. R-07."""
    return params.bulk_pct if count >= params.bulk_qty else 0


def discount_percent(level: str, count: int, promo: bool, params: Params) -> int:
    """Итоговый процент скидки. R-09."""
    percent = loyalty_percent(level, params) + bulk_percent(count, params)
    percent = min(percent, params.max_discount_pct)
    if promo:
        percent += params.promo_pct
    return percent


def discount_amount(amount: Decimal, percent: int) -> Decimal:
    """Сумма скидки в рублях. R-10."""
    return (amount * percent / 100).quantize(KOPECK, rounding=ROUND_DOWN)


def delivery_cost(goods_total: Decimal, method: str, params: Params) -> Decimal:
    """Стоимость доставки. R-11."""
    if method == "pickup":
        return ZERO
    if method != "courier":
        raise RuleViolation("delivery", f"Неизвестный способ доставки: {method}")
    if goods_total > params.free_delivery_from:
        return ZERO
    return money(params.delivery_fee)


def calculate(
    lines: Sequence[Line],
    params: Params,
    *,
    loyalty: str = "none",
    promo_code: str | None = None,
    delivery: str = "pickup",
) -> Quote:
    """Полный расчёт заказа. R-02…R-12."""
    check_lines([(line.book_id, line.qty) for line in lines], params)
    base = subtotal(lines)
    count = items_count(lines)
    promo = promo_applies(promo_code, base, params)
    percent = discount_percent(loyalty, count, promo, params)
    discount = discount_amount(base, percent)
    goods_total = base - discount
    shipping = delivery_cost(goods_total, delivery, params)
    return Quote(
        items_count=count,
        subtotal=base,
        discount_percent=percent,
        discount=discount,
        goods_total=goods_total,
        delivery_cost=shipping,
        total=goods_total + shipping,
        promo_applied=promo,
    )
