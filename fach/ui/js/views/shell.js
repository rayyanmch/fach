// Rahmen: Sidebar mit Navigation und dem Abgleich-Status unten. Der Status aktualisiert sich
// live (SSE), ohne die Seite daneben neu zu zeichnen.
import { api } from "../api.js";
import { h, icon, mount, plate, spinner, toast } from "../dom.js";
import { plural, upcoming, when } from "../format.js";
import { courseById, refreshState, store } from "../store.js";

export const ROUTES = [
  { id: "uebersicht", label: "Übersicht", icon: "inbox" },
  { id: "kurse", label: "Kurse", icon: "book" },
  { id: "einstellungen", label: "Einstellungen", icon: "settings" },
];

export function brandMark(size = 20) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 20 20");
  svg.setAttribute("width", size);
  svg.setAttribute("height", size);
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("brand-mark");
  // Ein Fach mit einem Blatt darin
  svg.innerHTML = '<rect x="2.75" y="2.75" width="14.5" height="14.5" rx="3.5" fill="none" stroke="currentColor" stroke-width="1.5"/>'
    + '<path d="M2.75 12h14.5" stroke="currentColor" stroke-width="1.5"/>'
    + '<path d="M6.5 12V7.25a.75.75 0 0 1 .75-.75h5.5a.75.75 0 0 1 .75.75V12" fill="currentColor"/>';
  return svg;
}

export const isMac = () => (store.state?.app.platform || "").startsWith("macos");
export const syncKey = () => (isMac() ? "⌘R" : "Strg R");

export async function startSync() {
  try {
    await api.post("/api/sync");
  } catch (e) {
    toast(e.message, "alert");
  }
}

export function renderShell(root, active) {
  const s = store.state;
  const unopened = s.courses.reduce((n, c) => n + (c.enabled ? c.unopened : 0), 0);
  const counts = { uebersicht: unopened, kurse: s.courses.filter((c) => c.enabled).length };
  const syncBox = h("div", { class: "sync-box", "aria-live": "polite" });
  const main = h("main", { class: "main" });

  const sidebar = h("aside", { class: "sidebar" },
    h("div", { class: "brand" }, brandMark(), h("span", { class: "brand-name" }, "Fach")),
    h("div", { class: "account mono truncate", title: s.username }, `${s.uni.name} · ${s.username}`),
    h("nav", { class: "nav", "aria-label": "Bereiche" },
      ROUTES.map((r, i) => h("a", {
        href: `#/${r.id}`, "aria-current": r.id === active ? "page" : null, title: `${r.label} (${i + 1})`,
      }, icon(r.icon), r.label,
      counts[r.id] ? h("span", { class: `count ${r.id === "uebersicht" ? "new" : ""}` }, counts[r.id]) : null))),
    syncBox,
  );
  mount(root, h("div", { class: "app" }, sidebar, main));
  updateSyncBox(syncBox);
  return { main, syncBox };
}

export function updateSyncBox(box = document.querySelector(".sync-box")) {
  if (!box || !store.state) return;
  const s = store.state;
  const p = s.sync;

  if (p.running) {
    const course = courseById(p.course_id);
    const frac = p.course_total ? (p.course_index - 1 + 0.5) / p.course_total : 0;
    const bar = h("div", { class: `progress ${p.phase === "network" ? "indeterminate" : ""}` },
      h("i", { style: p.phase === "network" ? {} : { transform: `scaleX(${frac.toFixed(3)})` } }));
    mount(box,
      h("div", { class: "sync-head" }, spinner(), p.phase === "network" ? "Verbinde mit ILIAS" : "Gleicht ab",
        p.course_total ? h("span", { class: "mono muted", style: { marginLeft: "auto" } }, `${p.course_index}/${p.course_total}`) : null),
      bar,
      course ? h("div", { class: "inline", style: { gap: "8px", flexWrap: "nowrap" } }, plate(course.label),
        h("span", { class: "sync-file mono truncate", title: p.current }, p.current ? p.current.split("/").pop() : course.display_title)) : null,
      h("button", { class: "btn btn-sm btn-quiet", onclick: () => api.post("/api/sync/cancel") }, "Abbrechen"),
    );
    return;
  }
  if (p.external) {
    mount(box,
      h("div", { class: "sync-head" }, spinner(), "Gleicht im Hintergrund ab"),
      h("div", { class: "sync-sub" }, "Gestartet vom Zeitplan. Ergebnisse erscheinen gleich hier."));
    return;
  }

  const last = s.last_run;
  const lastOk = s.last_ok;
  let dot = "", head = "", sub = "";
  if (!last) {
    head = "Noch kein Abgleich";
    sub = s.next_run ? `Automatisch ab ${upcoming(s.next_run)}` : "";
  } else if (last.status === "ok" || last.status === "partial") {
    dot = last.status === "ok" ? "ok" : "warn";
    head = last.status === "ok" ? "Aktuell" : "Teilweise aktuell";
    sub = `Stand ${when(last.ended * 1000)}`;
  } else if (last.status === "offline") {
    dot = "warn"; head = "ILIAS nicht erreicht";
    sub = lastOk ? `Zuletzt aktuell ${when(lastOk.ended * 1000)}` : "Noch kein erfolgreicher Abgleich";
  } else if (last.status === "auth") {
    dot = "bad"; head = "Anmeldung nötig"; sub = last.message;
  } else if (last.status === "cancelled") {
    dot = ""; head = "Abgebrochen";
    sub = lastOk ? `Zuletzt aktuell ${when(lastOk.ended * 1000)}` : "";
  } else {
    dot = "bad"; head = "Fehler beim Abgleich"; sub = last.message;
  }
  const next = s.schedule.enabled && s.next_run ? `Nächster ${upcoming(s.next_run)}` : "Automatik aus";
  mount(box,
    h("div", { class: "sync-head" }, h("span", { class: `dot ${dot}` }), head),
    h("div", { class: "sync-sub" }, [sub, next].filter(Boolean).join(" · ")),
    h("button", { class: "btn btn-sm", onclick: startSync, title: `Jetzt abgleichen (${syncKey()})` },
      icon("refresh"), "Jetzt abgleichen", h("span", { class: "kbd" }, syncKey())),
  );
}

export function runToast(run) {
  if (run.status === "ok" || run.status === "partial") {
    toast(run.added ? `${plural(run.added, "neue Datei", "neue Dateien")} aus ILIAS` : "Alles aktuell, nichts Neues");
  } else if (run.status !== "cancelled") {
    toast(run.message || "Abgleich fehlgeschlagen", "alert");
  }
  refreshState();
}
