// Übersicht: Probleme (nur wenn es welche gibt), Kennzahlen, der Semester-Takt und der Eingang neuer Dateien.
import { api } from "../api.js";
import { button, h, icon, iconButton, mount, plate, toast } from "../dom.js";
import { bytes, clock, dayLabel, daysUntil, inDays, plural, shortDay, when } from "../format.js";
import { courseById, modules, refreshExams, refreshFeed, refreshState, refreshTimeline, store, subscribe } from "../store.js";
import { tip } from "../tooltip.js";
import { startSync } from "./shell.js";
import { taktCard } from "./takt.js";

export function mountHome(el) {
  let frame = 0;
  const render = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => mount(el, h("div", { class: "page" },
      header(), banners(), stats(), taktCard({ onPick: pick }), feedSection())));
  };
  const pick = (module) => {
    store.ui.filter = module;
    render();
    refreshFeed().catch(() => {});
  };
  const off = subscribe((what) => { if (what !== "runs" && what !== "update") render(); });
  render();
  Promise.all([refreshFeed(), refreshTimeline(), refreshExams()]).catch((e) => toast(e.message, "alert"));
  return () => { off(); cancelAnimationFrame(frame); };
}

function header() {
  const t = store.timeline;
  const recent = store.state.new_7d;
  const unopened = store.state.courses.reduce((n, c) => n + (c.enabled ? c.unopened : 0), 0);
  let title = "Übersicht";
  if (t) title = t.current_week && !t.estimated ? `${t.current_week}. Vorlesungswoche` : t.semester;
  const meta = [t?.semester !== title ? t?.semester : null,
    recent ? `${plural(recent, "neue Datei", "neue Dateien")} in 7 Tagen` : "Diese Woche noch nichts Neues",
    unopened ? `${unopened} ungeöffnet` : null].filter(Boolean).join(" · ");
  return h("header", { class: "page-head" }, h("div", {}, h("h1", {}, title), h("p", { class: "meta" }, meta)));
}

// --- Kennzahlen -------------------------------------------------------------

function stats() {
  const t = store.timeline;
  const storage = t?.storage;
  const enabled = new Set(store.state.courses.filter((c) => c.enabled).map((c) => c.id));
  const files = t ? t.courses.filter((c) => enabled.has(c.id)).reduce((n, c) => n + c.total, 0) : null;
  const week = t && t.today_index >= 0 ? t.courses.filter((c) => enabled.has(c.id)).reduce((n, c) => n + (c.counts[t.today_index] || 0), 0) : 0;

  const filesStat = h("div", { class: "kpi" },
    h("span", { class: "label" }, "Dateien"),
    h("span", { class: "figure" }, files === null ? "–" : files.toLocaleString("de-DE")),
    h("span", { class: "sub" }, week ? `${week} in dieser Vorlesungswoche hochgeladen` : `in ${modules({ enabledOnly: true }).length} Modulen`));

  const storageStat = h("div", { class: "kpi" },
    h("span", { class: "label" }, "Speicher"),
    h("span", { class: "figure" }, storage ? bytes(storage.bytes) : "–"),
    h("span", { class: "sub" }, storage?.free ? `noch ${bytes(storage.free)} frei auf dem Laufwerk` : "im Uni-Ordner"));
  if (t) tip(storageStat, () => storageTip(t));

  return h("section", { class: "card stats", "aria-label": "Kennzahlen" }, filesStat, storageStat, examStat());
}

function storageTip(t) {
  const byId = new Map(t.courses.map((c) => [c.id, c]));
  const mods = modules({ enabledOnly: true })
    .map((m) => ({ m, size: m.courses.reduce((n, c) => n + (byId.get(c.id)?.bytes || 0), 0) }))
    .sort((a, b) => b.size - a.size).slice(0, 4);
  return [h("div", { class: "tip-head" }, "Größte Module"),
    h("ul", { class: "tip-list" }, mods.map(({ m, size }) => h("li", {}, `${m.label} · ${bytes(size)}`)))];
}

function examStat() {
  const ex = store.exams;
  const chosen = (ex?.modules || []).map((m) => ({ m, e: m.chosen })).filter(({ e }) => e && daysUntil(e.date) >= 0)
    .sort((a, b) => a.e.date.localeCompare(b.e.date));
  const go = () => { location.hash = "#/klausuren"; };
  if (chosen.length) {
    const { m, e } = chosen[0];
    const d = daysUntil(e.date);
    return h("div", { class: "kpi" },
      h("span", { class: "label" }, "Nächste Klausur"),
      h("span", { class: "figure" }, inDays(d)),
      h("span", { class: "sub inline", style: { gap: "8px" } }, plate(m.label), `${shortDay(e.date)}${e.start ? ` · ${e.start}` : ""}`,
        chosen.length > 1 ? h("button", { class: "link-btn", onclick: go }, `+${chosen.length - 1} weitere`) : null));
  }
  const candidates = (ex?.modules || []).reduce((n, m) => n + m.exams.filter((e) => e.status === "candidate").length, 0);
  return h("div", { class: "kpi" },
    h("span", { class: "label" }, "Klausuren"),
    h("span", { class: "figure" }, candidates ? candidates : "–", candidates ? h("small", {}, "Termine gefunden") : null),
    h("span", { class: "sub" }, h("button", { class: "link-btn", onclick: go }, candidates ? "Termine auswählen" : "Termine ansehen")));
}

// --- Probleme ---------------------------------------------------------------

function banners() {
  const s = store.state;
  const out = [];
  const last = s.last_run;
  if (!s.has_password) {
    out.push(banner("bad", "lock", "Anmeldung nötig",
      `Auf diesem Rechner ist kein Passwort für ${s.username} gespeichert. Melde dich neu an – Kurse und Ordner bleiben erhalten.`,
      button("Neu anmelden", { onClick: relogin })));
  } else if (last?.status === "auth") {
    out.push(banner("bad", "lock", "ILIAS hat die Anmeldung abgelehnt",
      "Hast du dein Uni-Passwort geändert? Melde dich neu an – Kurse und Ordner bleiben erhalten.",
      button("Neu anmelden", { onClick: relogin })));
  }
  if (!s.target_exists && s.onboarded && last) {
    out.push(banner("bad", "folder", "Uni-Ordner nicht gefunden",
      `${s.target_dir} gibt es nicht mehr. Wähle in den Einstellungen einen neuen Ort.`,
      button("Einstellungen", { onClick: () => { location.hash = "#/einstellungen"; } })));
  }
  if (s.schedule_error) {
    out.push(banner("warn", "clock", "Automatischer Abgleich ließ sich nicht einrichten", s.schedule_error,
      button("Erneut versuchen", { onClick: async () => { store.state = await api.post("/api/schedule/repair"); refreshState(); } })));
  }
  if (last && (last.status === "partial" || last.status === "error")) {
    const failed = (last.details?.courses || []).filter((c) => c.errors?.length);
    const names = failed.map((c) => courseById(c.id)?.display_title).filter(Boolean);
    out.push(banner("warn", "alert", last.message,
      names.length ? `Betroffen: ${names.join(", ")}. Oft ist ein Kurs in ILIAS vorübergehend gesperrt – der nächste Abgleich versucht es erneut.` : "Details stehen im Verlauf unter Einstellungen.",
      button("Erneut versuchen", { onClick: startSync })));
  }
  if (last?.status === "offline" && (!s.last_ok || Date.now() / 1000 - s.last_ok.ended > 2 * 86400)) {
    out.push(banner("warn", "wifiOff", "ILIAS seit über zwei Tagen nicht erreicht",
      "Prüfe deine Verbindung. Wenn ILIAS gewartet wird, holt Fach alles automatisch nach.",
      button("Erneut versuchen", { onClick: startSync })));
  }
  return out.length ? h("div", { class: "stack", style: { marginBottom: "24px" } }, out) : null;
}

function banner(kind, ic, title, text, action) {
  return h("div", { class: `banner ${kind}`, role: kind === "bad" ? "alert" : "status" },
    icon(ic, 18), h("div", { class: "text" }, h("b", {}, title), h("p", {}, text)), action);
}

async function relogin() {
  await api.post("/api/logout");
  await refreshState();
}

// --- Eingang ------------------------------------------------------------------

function feedSection() {
  const feed = store.feed;
  const filter = store.ui.filter ? modules().find((m) => m.module === store.ui.filter) : null;
  const unopened = (feed || []).filter((f) => !f.opened && f.exists).length;
  const head = h("div", { class: "section-head" },
    h("h2", {}, "Neu"),
    unopened ? h("span", { class: "mono" }, `${unopened} ungeöffnet`) : null,
    h("span", { class: "spacer" }),
    filter ? h("button", { class: "filter-chip", onclick: () => { store.ui.filter = null; refreshFeed(); }, title: "Filter entfernen" },
      filter.label, icon("x", 14)) : null,
    unopened ? h("button", { class: "btn btn-sm btn-quiet", onclick: markAllSeen }, "Alle als gesehen markieren") : null,
  );
  if (!feed) return h("section", { class: "section" }, head, h("div", { class: "card skeleton", style: { height: "144px" } }));
  if (!feed.length) return h("section", { class: "section" }, head, emptyFeed(filter));

  const groups = new Map();
  for (const f of feed) {
    const key = dayLabel(f.at * 1000);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(f);
  }
  return h("section", { class: "section" }, head,
    [...groups].map(([label, items]) => h("div", { class: "day-group" },
      h("div", { class: "day-label" }, label),
      h("div", { class: "card rows" }, items.map(fileRow)))));
}

function fileRow(f) {
  const course = courseById(f.course_id);
  const nameEl = h("span", { class: `name ${!f.opened && f.exists ? "marked" : ""}` }, f.name);
  return h("div", {
    class: `row ${f.exists ? "" : "missing"}`, role: "button", tabindex: f.exists ? 0 : -1,
    title: f.exists ? `${f.name} öffnen` : "Nicht mehr im Ordner – verschoben oder gelöscht",
    onclick: () => f.exists && openFile(f), onkeydown: (e) => { if (e.key === "Enter" && f.exists) openFile(f); },
  },
  plate(course?.label),
  h("div", { class: "truncate" }, nameEl, f.kind === "changed" ? h("span", { class: "badge" }, "aktualisiert") : null,
    h("span", { class: "where truncate" }, [course?.folder, f.dir].filter(Boolean).join(" / "))),
  h("span", { class: "time mono" }, clock(f.at * 1000)),
  f.exists ? iconButton("folderOpen", "Im Ordner zeigen", (e) => { e.stopPropagation(); reveal(f); }) : h("span"));
}

async function openFile(f) {
  try {
    const res = await api.post("/api/open", { event_id: f.id });
    if (res.revealed) toast("Programme öffnet Fach nicht direkt – im Ordner gezeigt", "alert");
    if (!f.opened) {
      f.opened = true;
      const c = courseById(f.course_id);
      if (c && c.unopened > 0) c.unopened -= 1;
      refreshState();
    }
  } catch (e) {
    toast(e.message, "alert");
  }
}

async function reveal(f) {
  try { await api.post("/api/reveal", { event_id: f.id }); } catch (e) { toast(e.message, "alert"); }
}

async function markAllSeen() {
  await api.post("/api/feed/seen", { module: store.ui.filter });
  await Promise.all([refreshFeed(), refreshState()]);
}

function emptyFeed(filter) {
  const s = store.state;
  if (!s.last_ok) {
    return h("div", { class: "card empty" }, h("h3", {}, "Noch kein Abgleich"),
      h("p", {}, "Starte den ersten Abgleich – danach erscheinen neue Dateien hier."),
      h("div", { style: { marginTop: "16px" } }, button("Jetzt abgleichen", { kind: "primary", icon: "refresh", onClick: startSync })));
  }
  return h("div", { class: "card empty" },
    h("h3", {}, filter ? `Nichts Neues in ${filter.title}` : "Nichts Neues in den letzten drei Wochen"),
    h("p", {}, "Sobald in ILIAS etwas dazukommt, steht es hier – ", h("span", { class: "marked" }, "markiert"),
      ", bis du es öffnest. Zuletzt geprüft ", when(s.last_ok.ended * 1000).replace(/\.$/, ""), "."));
}
