"""Пример модульного теста. Свои тесты для pricing пишите рядом (ЛР1)."""

from decimal import Decimal

from bookshop.pricing import Line


def test_line_total_multiplies_price_by_quantity():
    line = Line(book_id=1, price=Decimal("250.00"), qty=3)

    assert line.total == Decimal("750.00")
