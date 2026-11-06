// Semester-Takt: pro Modul eine Zeile, pro Vorlesungswoche ein Stapel – ein Strich je Datei,
// nach Upload-Datum. Ab sechs Dateien steht die Zahl über einem gekappten Stapel.
// Die aktuelle Woche trägt die Tinte, alles andere bleibt neutral. Hover zeigt, was genau kam.
import { h, plate } from "../dom.js";
import { bytes, month, plural, WEEKDAYS_LONG, when } from "../format.js";
import { modules, store } from "../store.js";
import { tip } from "../tooltip.js";

const MAX_LINES = 5;
const CAPPED_LINES = 3;
const ROW = 40;

const dm = (iso) => `${Number(iso.slice(8, 10))}.${Number(iso.slice(5, 7))}.`;

function aggregate(mod, byId, weeks) {
  const agg = { counts: Array(weeks).fill(0), bytes: Array(weeks).fill(0), names: Array.from({ length: weeks }, () => []),
    split: Array.from({ length: weeks }, () => []), total: 0, size: 0, last: 0, weekdays: Array(7).fill(0), types: {}, before: 0 };
  for (const c of mod.courses) {
    const t = byId.get(c.id);
    if (!t) continue;
    t.counts.forEach((n, i) => {
      agg.counts[i] += n;
      agg.bytes[i] += t.bytes_by_week[i];
      agg.names[i].push(...t.names[i]);
      if (n && mod.grouped) agg.split[i].push(`${c.role || "Kurs"} ${n}`);
    });
    agg.total += t.total;
    agg.size += t.bytes;
    agg.before += t.before;
    agg.last = Math.max(agg.last, t.last || 0);
    t.weekdays.forEach((n, i) => { agg.weekdays[i] += n; });
    for (const [k, v] of Object.entries(t.types)) agg.types[k] = (agg.types[k] || 0) + v;
  }
  return agg;
}

function rhythm(weekdays) {
  const total = weekdays.reduce((a, b) => a + b, 0);
  if (total < 5) return null;
  const max = Math.max(...weekdays);
  const day = weekdays.indexOf(max);
  return max / total >= 0.35 ? `Lädt meist ${WEEKDAYS_LONG[day]} hoch` : "Lädt an wechselnden Tagen hoch";
}

function cellTip(t, i, agg) {
  const n = agg.counts[i];
  if (!n) return null;
  const start = t.week_starts[i];
  const end = new Date(start);
  end.setDate(end.getDate() + 6);
  const endIso = `${end.getFullYear()}-${String(end.getMonth() + 1).padStart(2, "0")}-${String(end.getDate()).padStart(2, "0")}`;
  const names = agg.names[i];
  const lectureWeek = i + 1;
  return [
    h("div", { class: "tip-head" }, `Woche ${lectureWeek} · ${dm(start)} – ${dm(endIso)}`),
    h("div", { class: "tip-main" }, `${plural(n, "Datei", "Dateien")} · ${bytes(agg.bytes[i])}`),
    agg.split[i].length ? h("div", { class: "tip-split" }, agg.split[i].join(" · ")) : null,
    h("ul", { class: "tip-list" }, names.slice(0, 4).map((x) => h("li", {}, x))),
    n > 4 ? h("div", { class: "tip-more" }, `und ${n - Math.min(4, names.length)} weitere`) : null,
  ];
}

function moduleTip(mod, agg) {
  const types = Object.entries(agg.types).map(([k, v]) => `${v} ${k.toUpperCase()}`).join(" · ");
  return [
    h("div", { class: "tip-head" }, mod.grouped ? mod.courses.map((c) => c.role || c.display_title).join(" + ") : "Modul"),
    h("div", { class: "tip-main" }, mod.title),
    h("div", {}, `${plural(agg.total, "Datei", "Dateien")} · ${bytes(agg.size)}`),
    agg.last ? h("div", {}, `Letzter Upload ${when(agg.last * 1000)}`) : null,
    rhythm(agg.weekdays) ? h("div", {}, rhythm(agg.weekdays)) : null,
    types ? h("div", { class: "tip-split" }, types) : null,
  ];
}

export function taktCard({ onPick }) {
  const t = store.timeline;
  const card = h("section", { class: "card takt", "aria-label": "Semester-Takt" });
  if (!t) {
    card.append(h("div", { class: "takt-head" }, h("h2", {}, "Semester-Takt")),
      h("div", { class: "skeleton", style: { height: "180px" } }));
    return card;
  }
  const byId = new Map(t.courses.map((c) => [c.id, c]));
  const weeks = t.week_starts.length;
  const mods = modules({ enabledOnly: true }).map((m) => ({ ...m, agg: aggregate(m, byId, weeks) }));
  const totalFiles = mods.reduce((n, m) => n + m.agg.total, 0);
  const nowIdx = t.today_index >= 0 && t.today_index < weeks ? t.today_index : -1;

  card.append(h("div", { class: "takt-head" },
    h("h2", {}, "Semester-Takt"),
    h("span", { class: "muted" }, totalFiles ? "Ein Strich je Datei, nach Upload-Woche" : "Füllt sich mit dem ersten Abgleich")));

  if (!mods.length) {
    card.append(h("p", { class: "takt-empty" }, "Noch keine Kurse ausgewählt."));
    return card;
  }

  const left = h("div", {});
  const mid = h("div", { style: { position: "relative" } });
  const right = h("div", {});
  if (nowIdx >= 0) {
    mid.append(h("div", { class: "takt-now", style: {
      left: `calc(${(nowIdx / weeks) * 100}% + 2px)`, width: `calc(${100 / weeks}% - 4px)`, top: "0",
    } }));
  }

  for (const m of mods) {
    const active = store.ui.filter === m.module;
    const label = h("button", { class: "takt-course", onclick: () => onPick(active ? null : m.module), style: { height: `${ROW}px`, width: "100%" } },
      plate(m.label), h("span", { class: "truncate" }, m.title));
    left.append(h("div", { class: `takt-row ${active ? "active" : ""}` }, tip(label, () => moduleTip(m, m.agg))));

    const grid = h("div", { class: "takt-weeks", style: { gridTemplateColumns: `repeat(${weeks}, 1fr)`, height: `${ROW}px` } });
    m.agg.counts.forEach((n, i) => {
      const cell = h("div", { class: `takt-cell ${i === nowIdx ? "now" : ""} ${n ? "has" : ""}` });
      const lines = n > MAX_LINES ? CAPPED_LINES : n;
      for (let k = 0; k < lines; k++) cell.append(h("i"));
      if (n > MAX_LINES) cell.append(h("span", { class: "count" }, n));
      if (n) tip(cell, () => cellTip(t, i, m.agg));
      grid.append(cell);
    });
    mid.append(grid);
    const total = h("div", { class: "takt-total mono", style: { height: `${ROW}px`, display: "flex", alignItems: "center" } }, m.agg.total || "–");
    if (m.agg.total) tip(total, () => [h("div", { class: "tip-main" }, bytes(m.agg.size)),
      m.agg.before ? h("div", {}, `${m.agg.before} davon vor Vorlesungsbeginn`) : null]);
    right.append(total);
  }

  // Achse: Monatsnamen; die aktuelle Woche mit Strich und Beschriftung unter der Markierung
  const axis = h("div", { class: "takt-axis" });
  let prevMonth = null;
  t.week_starts.forEach((iso, i) => {
    const m = iso.slice(5, 7);
    const nearNow = nowIdx >= 0 && Math.abs(i - nowIdx) <= 2;
    if (m !== prevMonth && !nearNow) axis.append(h("span", { style: { left: `${(i / weeks) * 100}%` } }, month(iso)));
    prevMonth = m;
  });
  if (nowIdx >= 0) {
    const center = `${((nowIdx + 0.5) / weeks) * 100}%`;
    axis.append(h("i", { class: "now-tick", style: { left: center } }));
    axis.append(h("span", { class: "now-label", style: { left: center, transform: "translateX(-50%)" } },
      t.current_week ? `Woche ${t.current_week}` : "jetzt"));
  }
  mid.append(axis);

  card.append(h("div", { class: "takt-grid" }, left, mid, right));
  return card;
}
