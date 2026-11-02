"""Общие фикстуры. Их можно использовать в любом тесте, импортировать не нужно.

params       — параметры вашего варианта (bookshop.variants.Params)
shop         — «магазин» без HTTP: каталог + заказы (bookshop.orders.Shop)
app, client  — свежее FastAPI-приложение и HTTP-клиент на httpx (TestClient) для API-тестов
live_server  — настоящий сервер на свободном порту (для Playwright, Schemathesis, httpx.Client)
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from bookshop.api import create_app
from bookshop.orders import Shop
from bookshop.variants import Params, load_params


@pytest.fixture(scope="session")
def params() -> Params:
    return load_params()


@pytest.fixture
def shop(params: Params) -> Shop:
    return Shop(params)


@pytest.fixture
def app(params: Params) -> FastAPI:
    return create_app(params)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: ошибка сервера приходит как ответ 500, а не исключение
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@dataclass
class LiveServer:
    url: str
    app: FastAPI

    def reset(self) -> None:
        """Вернуть каталог и заказы в исходное состояние."""
        self.app.state.shop.reset()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def live_server(params: Params) -> Iterator[LiveServer]:
    app = create_app(params)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Сервер не запустился за 10 секунд")
        time.sleep(0.05)
    yield LiveServer(f"http://127.0.0.1:{port}", app)
    server.should_exit = True
    thread.join(timeout=5)
