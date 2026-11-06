// Klausuren: Termine aus den eigenen Unterlagen, pro Modul einen wählen, eigene ergänzen.
// Ehrlich zur Quelle: Jeder gefundene Termin zeigt Datei und Seite; verbindlich bleiben KLIPS und die Lehrenden.
import { api } from "../api.js";
import { button, h, icon, iconButton, mount, plate, spinner, toast } from "../dom.js";
import { daysUntil, inDays, isoDate, longDay, plural, shortDay } from "../format.js";
import { courseById, refreshExams, refreshTimeline, store, subscribe } from "../store.js";
import { tip } from "../tooltip.js";

export function mountExams(el) {
  const ui = { adding: null, showDismissed: new Set() };
  let frame = 0;
  const render = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (el.contains(document.activeElement) && document.activeElement.matches("input")) return;
      mount(el, page(ui, render));
    });
  };
  const off = subscribe((what) => { if (what === "exams" || what === "state" || what === "timeline") render(); });
  render();
  refreshExams().catch((e) => toast(e.message, "alert"));
  if (!store.timeline) refreshTimeline().catch(() => {});
  return () => { off(); cancelAnimationFrame(frame); };
}

const timeText = (e) => (e.start ? `${e.start}${e.end ? `–${e.end}` : ""}` : "Uhrzeit offen");

async function act(path, body, message) {
  try {
    await api.post(path, body);
    await refreshExams();
    if (message) toast(message);
  } catch (e) { toast(e.message, "alert"); }
}

function page(ui, render) {
  const data = store.exams;
  const s = store.state;
  const head = h("header", { class: "page-head" },
    h("div", {}, h("h1", {}, "Klausuren"),
      h("p", { class: "meta" }, data ? `${store.timeline?.semester || ""}${store.timeline ? " · " : ""}gefunden in deinen Vorlesungsunterlagen` : "")),
    h("div", { class: "actions" },
      h("button", { class: "btn btn-quiet", disabled: data?.scan.running, onclick: () => act("/api/exams/rescan", { full: true }, "Unterlagen werden neu durchsucht") },
        data?.scan.running ? spinner() : icon("refresh"), "Neu durchsuchen"),
      h("button", { class: "btn", disabled: !data?.modules.some((m) => m.chosen), onclick: exportIcs, title: "Gewählte Termine als Kalenderdatei" },
        icon("calendar"), "In Kalender übernehmen")));

  const note = h("p", { class: "exam-note" }, icon("fileText"),
    h("span", {}, "Fach liest die Termine aus den Unterlagen deiner Kurse, meist aus den Orga-Folien der ersten Vorlesung. ",
      "Das ist eine Hilfe, keine amtliche Quelle – verbindlich sind KLIPS und die Ankündigungen der Lehrenden. ",
      "Über „Quelle“ öffnest du die Datei, in der der Termin steht."));

  if (!data) return h("div", { class: "page" }, head, note, h("div", { class: "card skeleton", style: { height: "200px" } }));

  const scan = data.scan.running
    ? h("div", { class: "card", style: { padding: "12px 16px", marginBottom: "16px" } },
      h("div", { class: "inline", style: { gap: "8px", fontSize: "13px" } }, spinner(),
        `Durchsuche Unterlagen · ${data.scan.done} von ${data.scan.total}`),
      h("div", { class: "progress", style: { marginTop: "10px" } }, h("i", { style: { transform: `scaleX(${data.scan.total ? data.scan.done / data.scan.total : 0})` } })))
    : null;

  const withExams = data.modules.filter((m) => m.exams.some((e) => e.status !== "dismissed" || ui.showDismissed.has(m.module)));
  const without = data.modules.filter((m) => !withExams.includes(m));

  return h("div", { class: "page" }, head, note, scan,
    withExams.length ? periodCard(data) : null,
    withExams.map((m) => moduleCard(m, ui, render)),
    without.length ? h("section", { class: "section" },
      h("div", { class: "section-head" }, h("h2", {}, "Ohne gefundenen Termin"),
        h("span", { class: "muted", style: { fontSize: "13px" } }, s.last_ok ? "Steht der Termin woanders, trag ihn selbst ein" : "Erscheint nach dem ersten Abgleich")),
      h("div", { class: "card" }, without.map((m) => h("div", {},
        h("div", { class: "exam-empty-row" }, plate(m.label), h("span", { class: "truncate", style: { flex: 1 } }, m.title),
          button("Termin eintragen", { kind: "quiet", size: "sm", icon: "plus", onClick: () => { ui.adding = m.module; render(); } })),
        ui.adding === m.module ? addForm(m, ui, render) : null)))) : null);
}

// --- Zeitstrahl ---------------------------------------------------------------

function periodCard(data) {
  const marks = [];
  for (const m of data.modules) {
    if (m.chosen) marks.push({ m, e: m.chosen, chosen: true });
    else for (const e of m.exams) if (e.status === "candidate") marks.push({ m, e, chosen: false });
  }
  if (!marks.length) return null;
  const dates = marks.map((x) => isoDate(x.e.date).getTime());
  const today = new Date(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()).getTime();
  let from = Math.min(...dates) - 3 * 86400000;
  let to = Math.max(...dates) + 3 * 86400000;
  if (today < from && from - today < 21 * 86400000) from = today - 86400000;
  if (to - from < 21 * 86400000) to = from + 21 * 86400000;
  const pos = (t) => `${((t - from) / (to - from)) * 100}%`;

  const chosen = marks.filter((x) => x.chosen);
  const byDay = new Map();
  for (const x of chosen) byDay.set(x.e.date, [...(byDay.get(x.e.date) || []), x]);
  const clashes = [...byDay.entries()].filter(([, xs]) => xs.length > 1);

  const track = h("div", { class: "period-track" }, h("div", { class: "period-line" }));
  // Wochenstriche (montags)
  const d = new Date(from);
  d.setDate(d.getDate() + ((8 - d.getDay()) % 7));
  for (; d.getTime() <= to; d.setDate(d.getDate() + 7)) {
    track.append(h("div", { class: "period-tick", style: { left: pos(d.getTime()) } },
      h("span", {}, `${d.getDate()}.${d.getMonth() + 1}.`)));
  }
  if (today >= from && today <= to) track.append(h("div", { class: "period-today", style: { left: pos(today) } }, h("span", {}, "heute")));
  // Kürzel stapeln, wenn Termine nah beieinander liegen (nicht nur am selben Tag)
  const placed = [];
  const MIN_GAP = 0.055;
  for (const x of [...marks].sort((a, b) => Number(b.chosen) - Number(a.chosen) || a.e.date.localeCompare(b.e.date))) {
    const at = (isoDate(x.e.date).getTime() - from) / (to - from);
    let level = 0;
    while (placed.some((p) => p.level === level && Math.abs(p.at - at) < MIN_GAP)) level++;
    placed.push({ at, level });
    const clash = x.chosen && (byDay.get(x.e.date) || []).length > 1;
    const p = plate(x.m.label);
    p.style.bottom = `${18 + level * 26}px`;
    const mark = h("div", { class: `period-mark ${x.chosen ? "chosen" : "alt"} ${clash ? "clash" : ""}`, style: { left: pos(isoDate(x.e.date).getTime()) } }, level < 3 ? p : null);
    tip(mark, () => [h("div", { class: "tip-head" }, x.chosen ? "Gewählt" : "Möglicher Termin"),
      h("div", { class: "tip-main" }, x.m.title), h("div", {}, `${longDay(x.e.date)} · ${timeText(x.e)}`),
      x.e.room ? h("div", {}, x.e.room) : null]);
    track.append(mark);
  }

  const first = chosen.filter((x) => daysUntil(x.e.date) >= 0).sort((a, b) => a.e.date.localeCompare(b.e.date))[0];
  const undecided = data.modules.filter((m) => !m.chosen && m.exams.some((e) => e.status === "candidate")).length;
  return h("section", { class: "card period", "aria-label": "Prüfungszeitraum" },
    h("div", { class: "period-head" },
      h("span", { class: "big" }, first ? `Erste Klausur ${inDays(daysUntil(first.e.date))}` : "Wähle pro Modul einen Termin"),
      h("span", { class: "muted" }, [first ? `${first.m.title}, ${shortDay(first.e.date)}` : null,
        undecided ? `${plural(undecided, "Modul", "Module")} noch ohne Wahl` : null].filter(Boolean).join(" · "))),
    track,
    clashes.map(([day, xs]) => h("div", { class: "clash-note" }, icon("alert", 14),
      `Am ${shortDay(day)} liegen ${xs.map((x) => x.m.label).join(" und ")} am selben Tag.`)));
}

// --- Module ---------------------------------------------------------------------

function moduleCard(m, ui, render) {
  const visible = m.exams.filter((e) => e.status !== "dismissed" || ui.showDismissed.has(m.module));
  const hidden = m.exams.filter((e) => e.status === "dismissed").length;
  return h("section", { class: "card exam-module" },
    h("div", { class: "exam-module-head" }, plate(m.label), h("span", { class: "title truncate" }, m.title),
      h("span", { class: "chosen-text" }, m.chosen ? ["Du schreibst am ", h("b", {}, shortDay(m.chosen.date))] : "Noch kein Termin gewählt")),
    visible.map((e) => optionRow(m, e)),
    ui.adding === m.module ? addForm(m, ui, render) : h("div", { class: "exam-foot" },
      button("Eigenen Termin", { kind: "quiet", size: "sm", icon: "plus", onClick: () => { ui.adding = m.module; render(); } }),
      hidden ? h("button", { class: "link-btn", style: { fontSize: "13px", color: "var(--muted)", fontWeight: 400 },
        onclick: () => { ui.showDismissed.has(m.module) ? ui.showDismissed.delete(m.module) : ui.showDismissed.add(m.module); render(); } },
      ui.showDismissed.has(m.module) ? "Ausgeblendete verbergen" : `${hidden} ausgeblendet – zeigen`) : null));
}

function optionRow(m, e) {
  const days = daysUntil(e.date);
  const isChosen = e.status === "chosen";
  const dismissed = e.status === "dismissed";
  const src = e.sources[0];
  const course = src ? courseById(src.course_id) : null;
  const choose = () => {
    if (dismissed) return act("/api/exams/restore", { ids: e.ids });
    return isChosen ? act("/api/exams/choose", { module: m.module, ids: [] }) : act("/api/exams/choose", { ids: e.ids });
  };
  return h("div", { class: `exam-opt ${isChosen ? "chosen" : ""}`, role: "radio", "aria-checked": isChosen ? "true" : "false", tabindex: 0,
    onclick: choose, onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); choose(); } } },
  h("span", { class: "radio" }),
  h("span", { class: `when ${days < 0 ? "past" : ""}` }, shortDay(e.date), h("small", {}, inDays(days))),
  h("span", { class: "time" }, timeText(e)),
  h("span", { class: "what" },
    h("span", { class: "kind" }, e.kind), e.room ? ` · ${e.room}` : "", dismissed ? " · ausgeblendet" : "",
    e.origin === "manual"
      ? h("span", { class: "src" }, e.note ? `Eigener Termin · ${e.note}` : "Eigener Termin")
      : src ? h("span", { class: "src", title: src.snippet },
        "Quelle: ", h("button", { onclick: (ev) => { ev.stopPropagation(); act("/api/exams/source", { id: src.id }); } },
          `${src.file.split("/").pop()}${src.page ? `, S. ${src.page}` : ""}`), course ? ` · ${course.role || course.display_title}` : "") : null),
  e.origin === "manual"
    ? iconButton("trash", "Eigenen Termin löschen", (ev) => { ev.stopPropagation(); deleteManual(e); })
    : dismissed ? h("span") : iconButton("x", "Ist kein Klausurtermin – ausblenden", (ev) => { ev.stopPropagation(); act("/api/exams/dismiss", { ids: e.ids }); }));
}

async function deleteManual(e) {
  try { for (const id of e.ids) await api.del(`/api/exams/${id}`); await refreshExams(); } catch (err) { toast(err.message, "alert"); }
}

function addForm(m, ui, render) {
  const date = h("input", { class: "input sm", type: "date", "aria-label": "Datum" });
  const start = h("input", { class: "input sm", type: "time", "aria-label": "Beginn" });
  const end = h("input", { class: "input sm", type: "time", "aria-label": "Ende" });
  const room = h("input", { class: "input sm", type: "text", placeholder: "Raum oder Notiz", "aria-label": "Raum" });
  const close = () => { ui.adding = null; document.activeElement?.blur(); render(); };
  const save = async (ev) => {
    ev.preventDefault();
    if (!date.value) { toast("Bitte ein Datum wählen", "alert"); return; }
    try {
      await api.post("/api/exams", { module: m.module, date: date.value, start: start.value, end: end.value, room: room.value });
      ui.adding = null;
      document.activeElement?.blur();
      await refreshExams();
      toast("Termin eingetragen und gewählt");
    } catch (err) { toast(err.message, "alert"); }
  };
  setTimeout(() => date.focus(), 0);
  return h("form", { class: "exam-add", onsubmit: save, onkeydown: (ev) => { if (ev.key === "Escape") close(); } },
    h("label", { class: "field" }, h("span", {}, "Datum"), date),
    h("label", { class: "field" }, h("span", {}, "Beginn"), start),
    h("label", { class: "field" }, h("span", {}, "Ende"), end),
    h("label", { class: "field" }, h("span", {}, "Raum"), room),
    h("div", { class: "inline", style: { gap: "4px" } }, button("Speichern", { kind: "primary", size: "sm", type: "submit" }),
      button("Abbrechen", { kind: "quiet", size: "sm", onClick: close })));
}

async function exportIcs() {
  try {
    const res = await api.post("/api/exams/ics");
    toast(`Kalenderdatei geöffnet: ${res.path.split(/[\\/]/).pop()}`, "calendar");
  } catch (e) { toast(e.message, "alert"); }
}
