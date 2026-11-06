// DOM-Hilfen. Texte werden immer als Text gesetzt, nie als HTML – Dateinamen kommen aus ILIAS
// und sind damit fremde Daten.
import { icon } from "./icons.js";

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, String(v));
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function mount(el, ...children) {
  el.replaceChildren();
  append(el, children);
  return el;
}

export { icon };

export const plate = (label) => h("span", { class: "plate", title: label }, label || "–");

export function button(label, { kind = "", icon: ic, onClick, disabled, type = "button", title, size = "" } = {}) {
  return h("button", { class: `btn ${kind ? `btn-${kind}` : ""} ${size ? `btn-${size}` : ""}`.trim(), type, disabled, title, onclick: onClick },
    ic ? icon(ic) : null, label);
}

export function iconButton(name, title, onClick) {
  return h("button", { class: "icon-btn", type: "button", title, "aria-label": title, onclick: onClick }, icon(name));
}

export function toggle(checked, onChange, label) {
  const input = h("input", { type: "checkbox", role: "switch", "aria-label": label });
  input.checked = Boolean(checked);
  input.addEventListener("change", () => onChange(input.checked));
  return h("label", { class: "switch" }, input, h("span"));
}

export function toast(text, ic = "check") {
  const box = document.getElementById("toasts");
  const t = h("div", { class: "toast", role: "status" }, icon(ic), text);
  box.append(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 240); }, 3200);
}

let openMenu = null;
export function menu(anchor, items) {
  closeMenu();
  const r = anchor.getBoundingClientRect();
  const m = h("div", { class: "menu", role: "menu" },
    items.map((it) => h("button", { role: "menuitem", class: it.danger ? "danger" : "", onclick: () => { closeMenu(); it.onClick(); } },
      it.icon ? icon(it.icon) : null, it.label)));
  document.body.append(m);
  const w = m.offsetWidth;
  m.style.top = `${Math.min(r.bottom + 4, innerHeight - m.offsetHeight - 8)}px`;
  m.style.left = `${Math.max(8, Math.min(r.right - w, innerWidth - w - 8))}px`;
  openMenu = m;
  setTimeout(() => document.addEventListener("pointerdown", onOutside), 0);
}
function onOutside(e) { if (openMenu && !openMenu.contains(e.target)) closeMenu(); }
export function closeMenu() {
  openMenu?.remove();
  openMenu = null;
  document.removeEventListener("pointerdown", onOutside);
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });

export const spinner = (size = 16) => { const s = icon("loader", size); s.classList.add("spin"); return s; };
