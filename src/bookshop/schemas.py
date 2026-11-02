"""Модели запросов и ответов HTTP API (из них FastAPI строит OpenAPI-схему)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from bookshop.orders import Status

Loyalty = Literal["none", "silver", "gold"]
Delivery = Literal["pickup", "courier"]


class ErrorOut(BaseModel):
    detail: str = Field(description="Что пошло не так")


class HealthOut(BaseModel):
    status: Literal["ok"]


class VariantOut(BaseModel):
    variant: int
    max_items: int
    max_qty: int
    silver_pct: int
    gold_pct: int
    bulk_qty: int
    bulk_pct: int
    promo_code: str
    promo_pct: int
    promo_min: int
    max_discount_pct: int
    free_delivery_from: int
    delivery_fee: int


class BookOut(BaseModel):
    id: int
    title: str
    author: str
    price: float = Field(description="Цена за экземпляр, ₽")
    stock: int = Field(description="Остаток на складе, шт.")


class ItemIn(BaseModel):
    book_id: int = Field(ge=1, description="Идентификатор книги из каталога")
    qty: int = Field(ge=1, description="Количество экземпляров, от 1 до MAX_QTY")


class QuoteIn(BaseModel):
    items: list[ItemIn] = Field(min_length=1, description="Позиции заказа")
    loyalty: Loyalty = Field(default="none", description="Уровень карты лояльности")
    promo_code: str | None = Field(default=None, max_length=32, description="Промокод")
    delivery: Delivery = Field(default="pickup", description="Способ получения")


class CustomerIn(BaseModel):
    name: str = Field(min_length=2, max_length=50, description="Имя покупателя")
    email: str = Field(
        max_length=100,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Электронная почта",
    )


class OrderIn(QuoteIn):
    customer: CustomerIn


class LineOut(BaseModel):
    book_id: int
    title: str
    price: float
    qty: int
    line_total: float


class QuoteOut(BaseModel):
    lines: list[LineOut]
    items_count: int = Field(description="Всего экземпляров")
    subtotal: float = Field(description="Сумма без скидок, ₽")
    discount_percent: int = Field(description="Итоговая скидка, %")
    discount: float = Field(description="Скидка, ₽")
    goods_total: float = Field(description="Сумма товаров после скидки, ₽")
    delivery_cost: float = Field(description="Доставка, ₽")
    total: float = Field(description="К оплате, ₽")
    promo_applied: bool


class CustomerOut(BaseModel):
    name: str
    email: str


class OrderOut(QuoteOut):
    id: int
    status: Status
    customer: CustomerOut
    loyalty: Loyalty
    delivery: Delivery
    promo_code: str | None
    history: list[Status] = Field(description="Статусы заказа по порядку")
