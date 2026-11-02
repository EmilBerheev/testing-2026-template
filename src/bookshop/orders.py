"""Заказы и их жизненный цикл (R-13, R-14)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from bookshop import pricing
from bookshop.catalog import Book, Catalog, OutOfStock
from bookshop.variants import Params


class Status(StrEnum):
    NEW = "NEW"
    PAID = "PAID"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURNED = "RETURNED"


FINAL_STATUSES = frozenset({Status.CANCELLED, Status.RETURNED})


class OrderNotFound(LookupError):
    def __init__(self, order_id: int):
        super().__init__(f"Заказ {order_id} не найден")
        self.order_id = order_id


class BookNotFound(LookupError):
    def __init__(self, book_id: int):
        super().__init__(f"Книга {book_id} не найдена")
        self.book_id = book_id


class InvalidTransition(Exception):
    def __init__(self, status: Status, action: str):
        super().__init__(f"Действие «{action}» недоступно для заказа в статусе {status}")
        self.status = status
        self.action = action


@dataclass(frozen=True)
class Customer:
    name: str
    email: str


@dataclass(frozen=True)
class OrderLine:
    book_id: int
    title: str
    price: Decimal
    qty: int

    @property
    def total(self) -> Decimal:
        return pricing.money(self.price * self.qty)


@dataclass
class Order:
    id: int
    customer: Customer
    loyalty: str
    delivery: str
    promo_code: str | None
    lines: list[OrderLine]
    quote: pricing.Quote
    status: Status = Status.NEW
    history: list[Status] = field(default_factory=lambda: [Status.NEW])


@dataclass(frozen=True)
class ItemRequest:
    book_id: int
    qty: int


class Shop:
    """Каталог + заказы. Один экземпляр на приложение."""

    def __init__(self, params: Params):
        self.params = params
        self.catalog = Catalog()
        self.orders: dict[int, Order] = {}
        self._next_id = 1

    def reset(self) -> None:
        self.catalog.reset()
        self.orders.clear()
        self._next_id = 1

    # --- расчёт и создание -------------------------------------------------

    def _lines(self, items: Sequence[ItemRequest]) -> list[OrderLine]:
        lines = []
        for item in items:
            book = self.catalog.books[item.book_id]
            lines.append(OrderLine(book.id, book.title, book.price, item.qty))
        return lines

    def quote(
        self,
        items: Sequence[ItemRequest],
        *,
        loyalty: str = "none",
        promo_code: str | None = None,
        delivery: str = "pickup",
    ) -> tuple[list[OrderLine], pricing.Quote]:
        lines = self._lines(items)
        result = pricing.calculate(
            [pricing.Line(line.book_id, line.price, line.qty) for line in lines],
            self.params,
            loyalty=loyalty,
            promo_code=promo_code,
            delivery=delivery,
        )
        for line in lines:
            book = self.catalog.books[line.book_id]
            if line.qty > book.stock:
                raise OutOfStock(book, line.qty)
        return lines, result

    def create(
        self,
        customer: Customer,
        items: Sequence[ItemRequest],
        *,
        loyalty: str = "none",
        promo_code: str | None = None,
        delivery: str = "pickup",
    ) -> Order:
        lines, result = self.quote(items, loyalty=loyalty, promo_code=promo_code, delivery=delivery)
        for line in lines:
            self.catalog.take(line.book_id, line.qty)
        order = Order(
            id=self._next_id,
            customer=customer,
            loyalty=loyalty,
            delivery=delivery,
            promo_code=pricing.normalize_promo(promo_code),
            lines=lines,
            quote=result,
        )
        self.orders[order.id] = order
        self._next_id += 1
        return order

    # --- чтение -------------------------------------------------------------

    def book(self, book_id: int) -> Book:
        found = self.catalog.find(book_id)
        if found is None:
            raise BookNotFound(book_id)
        return found

    def get(self, order_id: int) -> Order:
        try:
            return self.orders[order_id]
        except KeyError:
            raise OrderNotFound(order_id) from None

    def list(self, status: Status | None = None) -> list[Order]:
        orders = sorted(self.orders.values(), key=lambda o: o.id)
        if status is not None:
            orders = [o for o in orders if o.status is status]
        return orders

    # --- переходы состояний ------------------------------------------------

    def _move(self, order: Order, target: Status) -> Order:
        order.status = target
        order.history.append(target)
        return order

    def _release_stock(self, order: Order) -> None:
        for line in order.lines:
            self.catalog.put_back(line.book_id, line.qty)

    def pay(self, order_id: int) -> Order:
        order = self.get(order_id)
        if order.status is not Status.NEW:
            raise InvalidTransition(order.status, "оплатить")
        return self._move(order, Status.PAID)

    def ship(self, order_id: int) -> Order:
        order = self.get(order_id)
        if order.status is not Status.PAID:
            raise InvalidTransition(order.status, "отправить")
        return self._move(order, Status.SHIPPED)

    def deliver(self, order_id: int) -> Order:
        order = self.get(order_id)
        if order.status is not Status.SHIPPED:
            raise InvalidTransition(order.status, "доставить")
        return self._move(order, Status.DELIVERED)

    def cancel(self, order_id: int) -> Order:
        order = self.get(order_id)
        if order.status in FINAL_STATUSES or order.status is Status.DELIVERED:
            raise InvalidTransition(order.status, "отменить")
        if order.status is Status.NEW:
            self._release_stock(order)
        return self._move(order, Status.CANCELLED)

    def return_order(self, order_id: int) -> Order:
        order = self.get(order_id)
        if order.status is not Status.DELIVERED:
            raise InvalidTransition(order.status, "вернуть")
        self._release_stock(order)
        return self._move(order, Status.RETURNED)
