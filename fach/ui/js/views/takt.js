// Semester-Takt: pro Kurs eine Zeile, pro Vorlesungswoche ein Stapel – ein Strich je Datei,
// nach Upload-Datum. Die aktuelle Woche trägt die Tinte, alles andere bleibt neutral.
import { h, plate } from "../dom.js";
import { month, plural } from "../format.js";
import { store } from "../store.js";

const MAX_LINES = 6;

export function taktCard({ onPick }) {
  const t = store.timeline;
  const s = store.state;
  const card = h("section", { class: "card takt", "aria-label": "Semester-Takt" });
  if (!t) {
    card.append(h("div", { class: "takt-head" }, h("h2", {}, "Semester-Takt")),
      h("div", { class: "skeleton", style: { height: "180px" } }));
    return card;
  }
  const rows = t.courses.map((r) => ({ ...r, course: s.courses.find((c) => c.id === r.id) })).filter((r) => r.course);
  const weeks = t.week_starts.length;
  const totalFiles = rows.reduce((n, r) => n + r.total, 0);
  const nowIdx = t.today_index >= 0 && t.today_index < weeks ? t.today_index : -1;

  card.append(h("div", { class: "takt-head" },
    h("h2", {}, "Semester-Takt"),
    h("span", { class: "muted" }, totalFiles
      ? `${plural(totalFiles, "Datei", "Dateien")}, jeder Strich nach Upload-Woche`
      : "Füllt sich mit dem ersten Abgleich")));

  if (!rows.length) {
    card.append(h("p", { class: "takt-empty" }, "Noch keine Kurse ausgewählt."));
    return card;
  }

  const left = h("div", {});
  const mid = h("div", { style: { position: "relative" } });
  const right = h("div", {});
  if (nowIdx >= 0) {
    mid.append(h("div", { class: "takt-now", style: {
      left: `calc(${(nowIdx / weeks) * 100}% + 2px)`, width: `calc(${100 / weeks}% - 4px)`,
    } }));
  }

  for (const r of rows) {
    const active = store.ui.filter === r.id;
    left.append(h("div", { class: `takt-row ${active ? "active" : ""}` },
      h("button", { class: "takt-course", title: `${r.course.display_title} – nur diesen Kurs zeigen`,
        onclick: () => onPick(active ? null : r.id), style: { height: "36px", width: "100%" } },
      plate(r.course.label), h("span", { class: "truncate" }, r.course.display_title))));

    const grid = h("div", { class: "takt-weeks", style: { gridTemplateColumns: `repeat(${weeks}, 1fr)` } });
    r.counts.forEach((n, i) => {
      const cell = h("div", { class: `takt-cell ${i === nowIdx ? "now" : ""}`,
        title: n ? `Woche ab ${t.week_starts[i].slice(8, 10)}.${t.week_starts[i].slice(5, 7)}.: ${plural(n, "Datei", "Dateien")}` : null });
      for (let k = 0; k < Math.min(n, MAX_LINES); k++) cell.append(h("i"));
      if (n > MAX_LINES) cell.append(h("span", { class: "more" }, `+${n - MAX_LINES}`));
      grid.append(cell);
    });
    mid.append(grid);
    right.append(h("div", { class: "takt-total mono", style: { height: "36px", display: "flex", alignItems: "center" },
      title: r.before ? `${r.before} davon vor Vorlesungsbeginn` : null }, r.total || "–"));
  }

  // Achse: Monatsnamen, die aktuelle Woche als „jetzt“
  const axis = h("div", { class: "takt-axis" });
  let prevMonth = null;
  t.week_starts.forEach((iso, i) => {
    const m = iso.slice(5, 7);
    const nearNow = nowIdx >= 0 && Math.abs(i - nowIdx) <= 1;
    if (m !== prevMonth && !nearNow) {
      axis.append(h("span", { style: { left: `${(i / weeks) * 100}%` } }, month(iso)));
    }
    prevMonth = m;
  });
  if (nowIdx >= 0) {
    axis.append(h("span", { class: "now-label", style: { left: `${((nowIdx + 0.5) / weeks) * 100}%`, transform: "translateX(-50%)" } },
      t.current_week ? `Woche ${t.current_week}` : "jetzt"));
  }
  mid.append(axis);

  card.append(h("div", { class: "takt-grid" }, left, mid, right));
  return card;
}
