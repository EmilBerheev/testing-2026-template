"use strict";

/* Главная страница: каталог, расчёт стоимости, оформление заказа. */

const quantities = new Map(); // book_id -> количество, сохраняется при поиске

function bookRow(book) {
  const row = document.createElement("tr");
  row.dataset.testid = "book-row";
  row.dataset.bookId = String(book.id);

  const title = document.createElement("th");
  title.scope = "row";
  title.innerHTML = '<span class="book-title"></span><span class="book-author"></span>';
  title.querySelector(".book-title").textContent = book.title;
  title.querySelector(".book-author").textContent = book.author;

  const price = document.createElement("td");
  price.className = "num";
  price.textContent = rub(book.price);

  const stock = document.createElement("td");
  stock.className = "num";
  stock.dataset.testid = `stock-${book.id}`;
  stock.textContent = String(book.stock);

  const qtyCell = document.createElement("td");
  qtyCell.className = "num";
  const qty = document.createElement("input");
  qty.type = "number";
  qty.min = "0";
  qty.step = "1";
  qty.inputMode = "numeric";
  qty.value = String(quantities.get(book.id) ?? 0);
  qty.dataset.testid = `qty-${book.id}`;
  qty.setAttribute("aria-label", `Количество: ${book.title}`);
  qty.addEventListener("input", () => {
    const value = Number.parseInt(qty.value, 10);
    if (Number.isNaN(value) || value <= 0) quantities.delete(book.id);
    else quantities.set(book.id, value);
  });
  qtyCell.append(qty);

  row.append(title, price, stock, qtyCell);
  return row;
}

async function loadBooks(query = "") {
  const path = query ? `/api/books?q=${encodeURIComponent(query)}` : "/api/books";
  const { ok, data } = await callApi(path);
  const body = document.querySelector("#books");
  body.replaceChildren();
  if (!ok) return;
  for (const book of data) body.append(bookRow(book));
  document.querySelector("#empty").hidden = data.length > 0;
}

async function loadVariant() {
  const { ok, data } = await callApi("/api/variant");
  if (ok) document.querySelector('[data-testid="variant"]').textContent = `Вариант ${data.variant}`;
}

function requestBody() {
  const form = document.querySelector("#order-form");
  const promo = form.promo.value.trim();
  return {
    items: [...quantities].map(([book_id, qty]) => ({ book_id, qty })),
    loyalty: form.loyalty.value,
    promo_code: promo || null,
    delivery: form.delivery.value,
  };
}

function renderSummary(quote) {
  const set = (id, text) => {
    document.querySelector(`[data-testid="${id}"]`).textContent = text;
  };
  set("items-count", `${quote.items_count} шт.`);
  set("subtotal", rub(quote.subtotal));
  set("discount-percent", `${quote.discount_percent} %`);
  set("discount", rub(quote.discount));
  set("delivery-cost", quote.delivery_cost === 0 ? "бесплатно" : rub(quote.delivery_cost));
  set("total", rub(quote.total));
  document.querySelector("#summary").hidden = false;
}

async function submit(path, extra = {}) {
  const errorBox = document.querySelector("#error");
  hideError(errorBox);
  const body = { ...requestBody(), ...extra };
  if (body.items.length === 0) {
    showError(errorBox, "Выберите хотя бы одну книгу");
    return null;
  }
  const { ok, data } = await callApi(path, { method: "POST", body: JSON.stringify(body) });
  if (!ok) {
    showError(errorBox, data.detail);
    return null;
  }
  return data;
}

document.addEventListener("DOMContentLoaded", () => {
  loadVariant();
  loadBooks();

  let timer;
  document.querySelector("#search").addEventListener("input", (event) => {
    clearTimeout(timer);
    timer = setTimeout(() => loadBooks(event.target.value.trim()), 250);
  });

  document.querySelector("#quote-button").addEventListener("click", async () => {
    const quote = await submit("/api/quote");
    if (quote) renderSummary(quote);
  });

  document.querySelector("#order-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const order = await submit("/api/orders", {
      customer: { name: form.name.value.trim(), email: form.email.value.trim() },
    });
    if (order) window.location.assign(`/order?id=${order.id}`);
  });
});
