// Rahmen: Sidebar mit Navigation, Update-Hinweis und dem Abgleich-Status unten. Der Status
// aktualisiert sich live (SSE), ohne die Seite daneben neu zu zeichnen.
import { api } from "../api.js";
import { h, icon, mount, plate, spinner, toast } from "../dom.js";
import { bytes, eta, plural, upcoming, when } from "../format.js";
import { courseById, refreshState, store } from "../store.js";

export const ROUTES = [
  { id: "uebersicht", label: "Übersicht", icon: "inbox" },
  { id: "kurse", label: "Kurse", icon: "book" },
  { id: "dateien", label: "Dateien", icon: "folder" },
  { id: "klausuren", label: "Klausuren", icon: "calendar" },
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

function navCounts() {
  const s = store.state;
  const unopened = s.courses.reduce((n, c) => n + (c.enabled ? c.unopened : 0), 0);
  const modules = new Set(s.courses.filter((c) => c.enabled).map((c) => c.module)).size;
  return { uebersicht: unopened, kurse: modules };
}

export function renderShell(root, active) {
  const s = store.state;
  const counts = navCounts();
  const syncBox = h("div", { class: "sync-box", "aria-live": "polite" });
  const main = h("main", { class: "main" });

  const sidebar = h("aside", { class: "sidebar" },
    h("div", { class: "brand" }, brandMark(), h("span", { class: "brand-name" }, "Fach")),
    h("div", { class: "account mono truncate", title: s.username }, `${s.uni.name} · ${s.username}`),
    h("nav", { class: "nav", "aria-label": "Bereiche" },
      ROUTES.map((r, i) => h("a", {
        href: `#/${r.id}`, "aria-current": r.id === active ? "page" : null, title: `${r.label} (${i + 1})`, dataset: { route: r.id },
      }, icon(r.icon), r.label,
      counts[r.id] ? h("span", { class: `count ${r.id === "uebersicht" ? "new" : ""}` }, counts[r.id]) : null))),
    h("div", { style: { marginTop: "auto" } }, h("div", { class: "update-slot" }), syncBox),
  );
  mount(root, h("div", { class: "app" }, sidebar, main));
  updateSyncBox(syncBox);
  updatePill();
  return { main, syncBox };
}

export function refreshNavCounts() {
  const counts = navCounts();
  document.querySelectorAll(".nav a").forEach((a) => {
    const id = a.dataset.route;
    let badge = a.querySelector(".count");
    if (!counts[id]) { badge?.remove(); return; }
    if (!badge) { badge = h("span", { class: `count ${id === "uebersicht" ? "new" : ""}` }); a.append(badge); }
    badge.textContent = counts[id];
  });
}

// Update lädt / wird installiert: kleiner Hinweis über dem Abgleich-Status
export function updatePill() {
  const slot = document.querySelector(".update-slot");
  const u = store.update;
  if (!slot) return;
  if (!u || !["downloading", "ready", "installing"].includes(u.status)) { slot.replaceChildren(); return; }
  const text = u.status === "installing" ? "Update wird installiert, Fach startet neu"
    : u.status === "ready" ? `Update ${u.latest} bereit`
      : `Update ${u.latest} lädt · ${Math.round((u.progress || 0) * 100)} %`;
  mount(slot, h("div", { class: "update-pill" }, u.status === "ready" ? icon("check", 14) : spinner(14), text));
}

export function updateSyncBox(box = document.querySelector(".sync-box")) {
  if (!box || !store.state) return;
  const s = store.state;
  const p = s.sync;

  if (p.running) {
    const course = courseById(p.course_id);
    const pct = Math.round((p.fraction || 0) * 100);
    const indeterminate = p.phase === "network";
    const bar = h("div", { class: `progress ${indeterminate ? "indeterminate" : ""}` },
      h("i", { style: indeterminate ? {} : { transform: `scaleX(${(p.fraction || 0).toFixed(3)})` } }));
    const details = [p.downloads ? plural(p.downloads, "Datei", "Dateien") : null, p.bytes ? bytes(p.bytes) : null].filter(Boolean).join(" · ");
    mount(box,
      h("div", { class: "sync-head" }, spinner(), indeterminate ? "Verbinde mit ILIAS" : "Gleicht ab",
        indeterminate ? null : h("span", { class: "sync-pct" }, `${pct} %`)),
      bar,
      h("div", { class: "sync-meta" }, h("span", {}, indeterminate ? "" : eta(p.eta)), h("span", { class: "mono" }, details)),
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
    toast(run.added ? `${plural(run.added, "neue Datei", "neue Dateien")} aus ILIAS` : run.message || "Alles aktuell, nichts Neues");
  } else if (run.status !== "cancelled") {
    toast(run.message || "Abgleich fehlgeschlagen", "alert");
  }
  refreshState();
}
