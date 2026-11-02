"""HTTP API и веб-интерфейс «Книжной лавки».

Запуск: uv run bookshop  →  http://127.0.0.1:8000 (интерфейс), /docs (Swagger UI),
/openapi.json (схема OpenAPI).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from bookshop import __version__
from bookshop.catalog import Book, OutOfStock
from bookshop.orders import (
    BookNotFound,
    Customer,
    InvalidTransition,
    ItemRequest,
    Order,
    OrderLine,
    OrderNotFound,
    Shop,
    Status,
)
from bookshop.pricing import Quote, RuleViolation
from bookshop.schemas import (
    BookOut,
    ErrorOut,
    HealthOut,
    OrderIn,
    OrderOut,
    QuoteIn,
    QuoteOut,
    VariantOut,
)
from bookshop.variants import Params, load_params

STATIC_DIR = Path(__file__).parent / "static"

NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorOut, "description": "Не найдено"}}
CONFLICT: dict[int | str, dict[str, Any]] = {
    409: {"model": ErrorOut, "description": "Конфликт: склад или статус заказа"}
}
BAD_BODY: dict[int | str, dict[str, Any]] = {
    400: {"model": ErrorOut, "description": "Тело запроса не разобрано как JSON"}
}


def _book_out(book: Book) -> BookOut:
    return BookOut(
        id=book.id, title=book.title, author=book.author, price=float(book.price), stock=book.stock
    )


def _quote_fields(lines: list[OrderLine], quote: Quote) -> dict[str, Any]:
    return {
        "lines": [
            {
                "book_id": line.book_id,
                "title": line.title,
                "price": float(line.price),
                "qty": line.qty,
                "line_total": float(line.total),
            }
            for line in lines
        ],
        "items_count": quote.items_count,
        "subtotal": float(quote.subtotal),
        "discount_percent": quote.discount_percent,
        "discount": float(quote.discount),
        "goods_total": float(quote.goods_total),
        "delivery_cost": float(quote.delivery_cost),
        "total": float(quote.total),
        "promo_applied": quote.promo_applied,
    }


def _order_out(order: Order) -> OrderOut:
    return OrderOut(
        id=order.id,
        status=order.status,
        customer={"name": order.customer.name, "email": order.customer.email},
        loyalty=order.loyalty,
        delivery=order.delivery,
        promo_code=order.promo_code,
        history=list(order.history),
        **_quote_fields(order.lines, order.quote),
    )


def _items(body: QuoteIn) -> list[ItemRequest]:
    return [ItemRequest(item.book_id, item.qty) for item in body.items]


def create_app(params: Params | None = None) -> FastAPI:
    """Создаёт приложение с чистым состоянием. В тестах — новое на каждый тест."""
    params = params or load_params()
    app = FastAPI(
        title="Книжная лавка",
        version=__version__,
        description=(
            "Учебное приложение курса «Тестирование ПО». "
            f"Вариант {params.variant}. Требования — docs/requirements.md."
        ),
    )
    shop = Shop(params)
    app.state.shop = shop

    @app.exception_handler(RuleViolation)
    async def rule_violation(_: Request, exc: RuleViolation) -> JSONResponse:
        detail = [{"loc": ["body", exc.field], "msg": exc.message, "type": "business_rule"}]
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.exception_handler(OutOfStock)
    async def out_of_stock(_: Request, exc: OutOfStock) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidTransition)
    async def invalid_transition(_: Request, exc: InvalidTransition) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(OrderNotFound)
    @app.exception_handler(BookNotFound)
    async def not_found(_: Request, exc: LookupError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # --- служебное -----------------------------------------------------------

    @app.get("/api/health", tags=["service"], summary="Проверка, что сервис жив")
    def health() -> HealthOut:
        return HealthOut(status="ok")

    @app.get("/api/variant", tags=["service"], summary="Параметры правил текущего варианта")
    def variant() -> VariantOut:
        return VariantOut(**params.as_dict())

    @app.post(
        "/api/admin/reset",
        status_code=204,
        tags=["service"],
        summary="Вернуть каталог и заказы в исходное состояние (для тестов)",
    )
    def reset() -> Response:
        shop.reset()
        return Response(status_code=204)

    # --- каталог -------------------------------------------------------------

    @app.get("/api/books", tags=["catalog"], summary="Список книг, поиск по названию и автору")
    def list_books(
        q: Annotated[str | None, Query(max_length=100, description="Строка поиска")] = None,
    ) -> list[BookOut]:
        books = shop.catalog.search(q) if q else shop.catalog.all()
        return [_book_out(b) for b in books]

    @app.get("/api/books/{book_id}", tags=["catalog"], summary="Одна книга", responses=NOT_FOUND)
    def get_book(book_id: int) -> BookOut:
        return _book_out(shop.book(book_id))

    # --- расчёт и заказы -------------------------------------------------------

    @app.post(
        "/api/quote",
        tags=["orders"],
        summary="Рассчитать стоимость без оформления заказа",
        responses={**BAD_BODY, **NOT_FOUND, **CONFLICT},
    )
    def quote(body: QuoteIn) -> QuoteOut:
        lines, result = shop.quote(
            _items(body), loyalty=body.loyalty, promo_code=body.promo_code, delivery=body.delivery
        )
        return QuoteOut(**_quote_fields(lines, result))

    @app.post(
        "/api/orders",
        status_code=201,
        tags=["orders"],
        summary="Оформить заказ",
        responses={**BAD_BODY, **NOT_FOUND, **CONFLICT},
    )
    def create_order(body: OrderIn) -> OrderOut:
        order = shop.create(
            Customer(body.customer.name, body.customer.email),
            _items(body),
            loyalty=body.loyalty,
            promo_code=body.promo_code,
            delivery=body.delivery,
        )
        return _order_out(order)

    @app.get("/api/orders", tags=["orders"], summary="Список заказов")
    def list_orders(status: Status | None = None) -> list[OrderOut]:
        return [_order_out(o) for o in shop.list(status)]

    @app.get("/api/orders/{order_id}", tags=["orders"], summary="Один заказ", responses=NOT_FOUND)
    def get_order(order_id: int) -> OrderOut:
        return _order_out(shop.get(order_id))

    transitions = {
        "pay": (shop.pay, "Оплатить заказ (NEW → PAID)"),
        "ship": (shop.ship, "Передать в доставку (PAID → SHIPPED)"),
        "deliver": (shop.deliver, "Отметить доставку (SHIPPED → DELIVERED)"),
        "cancel": (shop.cancel, "Отменить заказ (NEW или PAID → CANCELLED)"),
        "return": (shop.return_order, "Оформить возврат (DELIVERED → RETURNED)"),
    }

    def make_endpoint(handler: Callable[[int], Order]) -> Callable[[int], OrderOut]:
        def endpoint(order_id: int) -> OrderOut:
            return _order_out(handler(order_id))

        return endpoint

    for action, (handler, summary) in transitions.items():
        app.add_api_route(
            f"/api/orders/{{order_id}}/{action}",
            make_endpoint(handler),
            methods=["POST"],
            tags=["orders"],
            summary=summary,
            name=f"{action}_order",
            operation_id=f"{action}_order",
            responses={**NOT_FOUND, **CONFLICT},
        )

    # --- веб-интерфейс -------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/order", include_in_schema=False)
    def order_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "order.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
