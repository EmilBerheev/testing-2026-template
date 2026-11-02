"use strict";

/* Общие функции для страниц «Книжной лавки». */

const FIELD_NAMES = {
  name: "Имя: от 2 до 50 символов",
  email: "Электронная почта: адрес вида name@example.ru",
  qty: "Количество: целое число не меньше 1",
  items: "Выберите хотя бы одну книгу",
  promo_code: "Промокод: не длиннее 32 символов",
};

function rub(value) {
  return value.toFixed(2).replace(".", ",") + " ₽";
}

function errorText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((err) => {
        if (err.type === "business_rule") return err.msg;
        const field = [...err.loc].reverse().find((part) => part in FIELD_NAMES);
        return field ? FIELD_NAMES[field] : err.msg;
      })
      .join(". ");
  }
  return "Не удалось выполнить запрос";
}

async function callApi(path, options = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...options };
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    return { ok: false, status: 0, data: { detail: "Сервер недоступен" } };
  }
  const text = await response.text();
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: `Сервер ответил ${response.status}` };
  }
  if (!response.ok && (!data || !data.detail)) {
    data = { detail: `Сервер ответил ${response.status}` };
  }
  return { ok: response.ok, status: response.status, data };
}

function showError(box, detail) {
  box.textContent = errorText(detail);
  box.hidden = false;
}

function hideError(box) {
  box.textContent = "";
  box.hidden = true;
}
