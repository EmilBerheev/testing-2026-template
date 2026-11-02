"""Каталог книг и склад. Данные живут в памяти процесса."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal


@dataclass
class Book:
    id: int
    title: str
    author: str
    price: Decimal
    stock: int


INITIAL_BOOKS: tuple[Book, ...] = (
    Book(1, "Мастер и Маргарита", "Михаил Булгаков", Decimal("549.50"), 20),
    Book(2, "Преступление и наказание", "Фёдор Достоевский", Decimal("399.90"), 15),
    Book(3, "Чистый код", "Роберт Мартин", Decimal("1290.00"), 10),
    Book(4, "Тестирование Dot Com", "Роман Савин", Decimal("750.00"), 8),
    Book(5, "Искусство тестирования программ", "Гленфорд Майерс", Decimal("1000.00"), 12),
    Book(6, "Пикник на обочине", "Аркадий и Борис Стругацкие", Decimal("250.00"), 30),
    Book(7, "Совершенный код", "Стив Макконнелл", Decimal("1890.00"), 5),
    Book(8, "Евгений Онегин", "Александр Пушкин", Decimal("500.00"), 25),
)


class OutOfStock(Exception):
    def __init__(self, book: Book, requested: int):
        super().__init__(f"«{book.title}»: на складе {book.stock} шт., запрошено {requested}")
        self.book = book
        self.requested = requested


class Catalog:
    def __init__(self, books: tuple[Book, ...] = INITIAL_BOOKS):
        self._initial = books
        self.books: dict[int, Book] = {}
        self.reset()

    def reset(self) -> None:
        self.books = {book.id: replace(book) for book in self._initial}

    def all(self) -> list[Book]:
        return sorted(self.books.values(), key=lambda b: b.id)

    def find(self, book_id: int) -> Book | None:
        return self.books.get(book_id)

    def search(self, query: str) -> list[Book]:
        needle = query.strip().casefold()
        return [
            b for b in self.all() if needle in b.title.casefold() or needle in b.author.casefold()
        ]

    def take(self, book_id: int, qty: int) -> None:
        book = self.books[book_id]
        if qty > book.stock:
            raise OutOfStock(book, qty)
        book.stock -= qty

    def put_back(self, book_id: int, qty: int) -> None:
        self.books[book_id].stock += qty
