"use strict";

/* Страница заказа: статус, состав, действия по жизненному циклу. */

const STATUS_TEXT = {
  NEW: "Новый",
  PAID: "Оплачен",
  SHIPPED: "Передан в доставку",
  DELIVERED: "Доставлен",
  CANCELLED: "Отменён",
  RETURNED: "Возвращён",
};

const ALLOWED = {
  NEW: ["pay", "cancel"],
  PAID: ["ship", "cancel"],
  SHIPPED: ["deliver"],
  DELIVERED: ["return"],
  CANCELLED: [],
  RETURNED: [],
};

const orderId = new URLSearchParams(window.location.search).get("id");

function renderStatus(status) {
  const badge = document.querySelector('[data-testid="order-status"]');
  badge.textContent = STATUS_TEXT[status] ?? status;
  badge.dataset.status = status;
}

function renderActions(status) {
  for (const button of document.querySelectorAll("[data-action]")) {
    button.hidden = !ALLOWED[status].includes(button.dataset.action);
  }
}

function renderHistory(history) {
  const list = document.querySelector('[data-testid="history"]');
  list.replaceChildren(
    ...history.map((status) => {
      const item = document.createElement("li");
      item.textContent = STATUS_TEXT[status] ?? status;
      return item;
    }),
  );
  document.querySelector("#history-card").hidden = false;
}

function renderLines(order) {
  const body = document.querySelector("#lines");
  body.replaceChildren(
    ...order.lines.map((line) => {
      const row = document.createElement("tr");
      for (const [text, numeric] of [
        [line.title, false],
        [rub(line.price), true],
        [String(line.qty), true],
        [rub(line.line_total), true],
      ]) {
        const cell = document.createElement("td");
        cell.textContent = text;
        if (numeric) cell.className = "num";
        row.append(cell);
      }
      return row;
    }),
  );
  const set = (id, text) => {
    document.querySelector(`#lines-card [data-testid="${id}"]`).textContent = text;
  };
  set("subtotal", rub(order.subtotal));
  set("discount", `${rub(order.discount)} (${order.discount_percent} %)`);
  set("delivery-cost", order.delivery_cost === 0 ? "бесплатно" : rub(order.delivery_cost));
  set("total", rub(order.total));
  document.querySelector("#lines-card").hidden = false;
}

function render(order) {
  document.querySelector('[data-testid="order-id"]').textContent = String(order.id);
  document.querySelector('[data-testid="customer"]').textContent =
    `${order.customer.name}, ${order.customer.email}`;
  renderStatus(order.status);
  renderActions(order.status);
  renderLines(order);
  renderHistory(order.history);
  document.querySelector("#order").hidden = false;
}

async function perform(action) {
  const errorBox = document.querySelector("#error");
  hideError(errorBox);
  const { ok, data } = await callApi(`/api/orders/${orderId}/${action}`, { method: "POST" });
  if (!ok) {
    showError(errorBox, data.detail);
    return null;
  }
  return data;
}

document.addEventListener("DOMContentLoaded", async () => {
  const errorBox = document.querySelector("#error");
  if (!orderId) {
    showError(errorBox, "Не указан номер заказа");
    return;
  }
  const { ok, data } = await callApi(`/api/orders/${encodeURIComponent(orderId)}`);
  if (!ok) {
    showError(errorBox, data.detail);
    return;
  }
  render(data);

  for (const action of ["pay", "ship", "deliver", "return"]) {
    document.querySelector(`[data-action="${action}"]`).addEventListener("click", async () => {
      const order = await perform(action);
      if (order) render(order);
    });
  }

  document.querySelector('[data-action="cancel"]').addEventListener("click", async () => {
    if (!window.confirm("Отменить заказ? Вернуть его будет нельзя.")) return;
    const order = await perform("cancel");
    if (order) {
      renderActions(order.status);
      renderHistory(order.history);
    }
  });
});
