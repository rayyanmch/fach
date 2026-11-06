// Eigene Titelleiste für das rahmenlose Windows-Fenster: Ziehen, Doppelklick = maximieren,
// Größe an den Kanten ändern, Minimieren/Maximieren/Schließen. Die eigentliche Arbeit macht Windows –
// wir melden nur, wo geklickt wurde (siehe fach/platform/windows_window.py).
import { api } from "./api.js";
import { h, toast } from "./dom.js";

const NS = "http://www.w3.org/2000/svg";
function glyph(d) {
  const svg = document.createElementNS(NS, "svg");
  svg.setAttribute("viewBox", "0 0 10 10");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1");
  svg.innerHTML = d;
  return svg;
}
const MIN = '<path d="M0 5h10"/>';
const MAX = '<rect x="0.5" y="0.5" width="9" height="9"/>';
const RESTORE = '<rect x="0.5" y="2.5" width="7" height="7"/><path d="M2.5 2.5V0.5h7v7h-2"/>';
const CLOSE = '<path d="M0.5 0.5l9 9M9.5 0.5l-9 9"/>';

let failedOnce = false;
async function windowAction(body) {
  try {
    const res = await api.post("/api/window", body);
    if (res.maximized !== undefined) document.body.classList.toggle("maximized", res.maximized);
    return res;
  } catch (e) {
    if (!failedOnce) {
      failedOnce = true;
      toast("Fenster reagiert nicht – in Einstellungen die Windows-Titelleiste einschalten", "alert");
    }
    return null;
  }
}

export function mountTitlebar(enabled) {
  document.querySelector(".titlebar")?.remove();
  document.querySelectorAll(".resize-edge").forEach((e) => e.remove());
  document.body.classList.toggle("chrome", enabled);
  if (!enabled) return;

  const maxBtn = h("button", { class: "tb-btn", title: "Maximieren", "aria-label": "Maximieren" }, glyph(MAX));
  const setMax = (on) => { maxBtn.replaceChildren(glyph(on ? RESTORE : MAX)); maxBtn.title = on ? "Verkleinern" : "Maximieren"; };
  const toggleMax = async () => { const r = await windowAction({ action: "maximize" }); if (r) setMax(r.maximized); };
  maxBtn.addEventListener("click", toggleMax);

  // Wie Tauri: Klickzähler am mousedown – das zweite Ereignis eines Doppelklicks maximiert, sonst ziehen.
  const drag = (el) => {
    el.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      if (e.detail === 2) toggleMax();
      else windowAction({ action: "drag" });
    });
    return el;
  };

  const bar = h("div", { class: "titlebar" },
    drag(h("div", { class: "tb-drag" })),
    drag(h("div", { class: "tb-drag tb-fill" })),
    h("div", { class: "tb-controls" },
      h("button", { class: "tb-btn", title: "Minimieren", "aria-label": "Minimieren", onclick: () => windowAction({ action: "minimize" }) }, glyph(MIN)),
      maxBtn,
      h("button", { class: "tb-btn close", title: "Schließen", "aria-label": "Schließen", onclick: () => windowAction({ action: "close" }) }, glyph(CLOSE))));
  document.body.append(bar);

  for (const edge of ["top", "bottom", "left", "right", "topleft", "topright", "bottomleft", "bottomright"]) {
    const el = h("div", { class: "resize-edge", dataset: { edge } });
    el.addEventListener("mousedown", (e) => { if (e.button === 0) windowAction({ action: "drag", edge }); });
    document.body.append(el);
  }
}
