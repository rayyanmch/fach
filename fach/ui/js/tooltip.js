// Hover-Karten für Statistik (Semester-Takt, Speicher …). Inhalt wird erst beim Zeigen gebaut.
import { h } from "./dom.js";

let current = null;
let anchor = null;
let timer = 0;

// Verschwindet das Element (Seite neu gezeichnet), gibt es kein mouseleave – also selbst nachsehen.
function watch() {
  if (!current) return;
  if (!anchor?.isConnected) { hideTip(); return; }
  requestAnimationFrame(watch);
}

function place(tip, anchor) {
  const r = anchor.getBoundingClientRect();
  const w = tip.offsetWidth;
  const ht = tip.offsetHeight;
  let top = r.top - ht - 8;
  if (top < 44) top = r.bottom + 8;
  const left = Math.max(8, Math.min(r.left + r.width / 2 - w / 2, innerWidth - w - 8));
  tip.style.top = `${top}px`;
  tip.style.left = `${left}px`;
}

export function hideTip() {
  clearTimeout(timer);
  current?.remove();
  current = null;
  anchor = null;
}

export function tip(el, build, delay = 120) {
  el.addEventListener("mouseenter", () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      hideTip();
      if (!el.isConnected) return;
      const content = build();
      if (!content) return;
      current = h("div", { class: "tip", role: "tooltip" }, content);
      anchor = el;
      document.body.append(current);
      place(current, el);
      requestAnimationFrame(watch);
    }, delay);
  });
  el.addEventListener("mouseleave", hideTip);
  return el;
}

addEventListener("scroll", hideTip, true);
addEventListener("blur", hideTip);
