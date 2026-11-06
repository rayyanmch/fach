// Das Regal im Onboarding: Postfächer wie am Lehrstuhl, eines pro Kurs, beschriftet mit dem Kürzel.
// Beim ersten Abgleich füllen sich die Fächer mit Papierstapeln – so hoch, wie Dateien ankamen.
// Dieselbe Bildsprache wie im Semester-Takt: ein Strich = ein Blatt.

const NS = "http://www.w3.org/2000/svg";
const W = 400, H = 360, PAD = 18, GAP = 12, COLS = 3, ROWS = 3;
const CW = (W - 2 * 20 - 2 * PAD - (COLS - 1) * GAP) / COLS;
const CH = (H - 2 * 20 - 2 * PAD - (ROWS - 1) * GAP) / ROWS;

function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
}

function stack(g, x, y, w, n, marker) {
  // Stapel liegender Blätter, von vorne gesehen: Kanten als feine Linien
  const lines = Math.max(2, Math.min(12, Math.round(Math.sqrt(n) * 2.4)));
  const sw = w * 0.72;
  const sx = x + (w - sw) / 2;
  const top = y - lines * 3 - 2;
  el("rect", { x: sx, y: top, width: sw, height: lines * 3 + 2, rx: 1.5, fill: "var(--sheet)", stroke: "var(--sheet-line)", "stroke-width": 1 }, g);
  for (let i = 1; i < lines; i++) {
    el("line", { x1: sx + 1, x2: sx + sw - 1, y1: top + i * 3 + 1, y2: top + i * 3 + 1, stroke: "var(--sheet-line)", "stroke-width": 1 }, g);
  }
  // oberstes Blatt, leicht verrutscht
  const sheet = el("g", { transform: `rotate(-3 ${sx + sw / 2} ${top})` }, g);
  el("rect", { x: sx + 4, y: top - 3, width: sw - 2, height: 3, rx: 1, fill: "var(--sheet)", stroke: "var(--sheet-line)", "stroke-width": 1 }, sheet);
  if (marker) {
    // Textmarker auf dem obersten Blatt: neu, noch nicht geöffnet
    el("rect", { x: sx + sw * 0.2, y: top - 4, width: sw * 0.45, height: 5, rx: 1, fill: "var(--marker)" }, sheet);
  }
}

export function createShelf() {
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "shelf", role: "img", "aria-label": "Regal mit einem Fach pro Kurs" });
  el("rect", { x: 20, y: 20, width: W - 40, height: H - 40, rx: 12, fill: "var(--shelf)", stroke: "var(--shelf-edge)", "stroke-width": 1 }, svg);
  const cells = [];
  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const x = 20 + PAD + c * (CW + GAP);
      const y = 20 + PAD + r * (CH + GAP);
      const g = el("g", {}, svg);
      el("rect", { x, y, width: CW, height: CH, rx: 6, fill: "var(--shelf-hole)" }, g);
      // Schatten der oberen Kante – Tiefe ohne Effekte
      el("rect", { x, y, width: CW, height: 6, rx: 3, fill: "rgba(0,0,0,0.05)" }, g);
      const fill = el("g", { class: "hole-fill" }, g);
      fill.style.transition = "opacity 360ms cubic-bezier(0.22,1,0.36,1), transform 360ms cubic-bezier(0.22,1,0.36,1)";
      const plateG = el("g", {}, g);
      el("rect", { x: x + CW / 2 - 24, y: y + CH - 20, width: 48, height: 15, rx: 3, fill: "var(--panel)", stroke: "var(--line-strong)", "stroke-width": 1 }, plateG);
      const text = el("text", { x: x + CW / 2, y: y + CH - 9.5, "text-anchor": "middle", "font-family": "IBM Plex Mono, monospace", "font-size": 9, "font-weight": 500, fill: "var(--text-2)" }, plateG);
      cells.push({ g, fill, plateG, text, x, y });
    }
  }

  const api = {
    svg,
    // labels: Kürzel der Kurse (max. 9; ab 10 wird das letzte Fach zu „+n“)
    setLabels(labels) {
      let shown = labels.slice(0, 9);
      if (labels.length > 9) shown = [...labels.slice(0, 8), `+${labels.length - 8}`];
      cells.forEach((cell, i) => {
        const label = shown[i];
        cell.plateG.style.opacity = label ? 1 : 0;
        cell.text.textContent = label || "";
      });
    },
    // counts: Zahl der Dateien pro Fach (Index wie labels); undefined = noch leer
    setFilled(counts, markerIndex = -1) {
      cells.forEach((cell, i) => {
        const n = counts[i];
        const key = n === undefined ? "" : `${n}:${i === markerIndex}`;
        if (cell.fill.dataset.key === key) return;
        cell.fill.dataset.key = key;
        cell.fill.replaceChildren();
        if (n === undefined) {
          cell.g.classList.remove("filled");
          return;
        }
        stack(cell.fill, cell.x, cell.y + CH - 26, CW, Math.max(n, 1), i === markerIndex);
        requestAnimationFrame(() => cell.g.classList.add("filled"));
      });
    },
  };
  return api;
}
