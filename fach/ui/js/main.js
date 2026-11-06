// Start, Routing, Live-Ereignisse und Tastenkürzel.
import { api, listen } from "./api.js";
import { h, mount, toast } from "./dom.js";
import { refreshExams, refreshFeed, refreshRuns, refreshState, refreshTimeline, refreshUpdate, store, subscribe } from "./store.js";
import { mountTitlebar } from "./titlebar.js";
import { hideTip } from "./tooltip.js";
import { mountCourses } from "./views/courses.js";
import { mountExams } from "./views/exams.js";
import { mountFiles } from "./views/files.js";
import { mountHome } from "./views/home.js";
import { mountOnboarding, onboardingActive, onboardingEvent } from "./views/onboarding.js";
import { mountSettings } from "./views/settings.js";
import { refreshNavCounts, renderShell, ROUTES, runToast, startSync, updatePill, updateSyncBox } from "./views/shell.js";

const root = document.getElementById("root");
const PAGES = { uebersicht: mountHome, kurse: mountCourses, dateien: mountFiles, klausuren: mountExams, einstellungen: mountSettings };
let cleanup = null;
let current = null;

function routeId() {
  const id = location.hash.replace(/^#\/?/, "");
  return PAGES[id] ? id : "uebersicht";
}

function route() {
  const s = store.state;
  if (!s) return;
  if (!s.onboarded || onboardingActive()) {
    if (current !== "onboarding") {
      cleanup?.();
      current = "onboarding";
      cleanup = mountOnboarding(root);
    }
    return;
  }
  const id = routeId();
  const key = `page:${id}`;
  if (current === key) return;
  hideTip();
  cleanup?.();
  current = key;
  const { main } = renderShell(root, id);
  cleanup = PAGES[id](main);
}

function onEvent(ev) {
  const s = store.state;
  if (!s) return;
  if (ev.type === "sync") {
    s.sync = { ...ev.progress, external: false };
    updateSyncBox();
    onboardingEvent(ev);
  } else if (ev.type === "course_done") {
    onboardingEvent(ev);
    if (current === "page:uebersicht" || current === "page:kurse") refreshTimeline().catch(() => {});
  } else if (ev.type === "run_done") {
    onboardingEvent(ev);
    if (current?.startsWith("page:")) runToast(ev.run);
    refreshState().then(() => {
      if (current?.startsWith("page:")) {
        refreshFeed().catch(() => {});
        refreshTimeline().catch(() => {});
        refreshRuns().catch(() => {});
      }
    });
  } else if (ev.type === "update") {
    store.update = ev.update;
    updatePill();
    if (current === "page:einstellungen") refreshUpdate().catch(() => {});
  } else if (ev.type === "exams_scan") {
    if (store.exams) { store.exams.scan = ev.scan; if (current === "page:klausuren") refreshExams().catch(() => {}); }
  } else if (ev.type === "changed") {
    if (ev.what === "exams") { refreshExams().catch(() => {}); return; }
    refreshState().then(() => { if (ev.what === "feed") refreshFeed(); });
  }
}

let externalPoll = null;
function watchExternal() {
  // Läuft ein Abgleich aus der Aufgabenplanung (anderer Prozess), gibt es keine Live-Ereignisse – also nachfragen.
  clearInterval(externalPoll);
  if (store.state?.sync.external) {
    externalPoll = setInterval(async () => {
      const before = store.state.sync.external;
      await refreshState();
      if (before && !store.state.sync.external) {
        clearInterval(externalPoll);
        refreshFeed().catch(() => {});
        refreshTimeline().catch(() => {});
      }
    }, 4000);
  }
}

document.addEventListener("keydown", (e) => {
  const typing = e.target.matches?.("input, textarea, select");
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r") {
    e.preventDefault(); // kein Neuladen der Oberfläche
    if (store.state?.onboarded && !store.state.sync.running) startSync();
    return;
  }
  if (typing || e.ctrlKey || e.metaKey || e.altKey || !current?.startsWith("page:")) return;
  if (document.querySelector(".dialog-backdrop")) return;
  const idx = Number(e.key) - 1;
  if (ROUTES[idx]) location.hash = `#/${ROUTES[idx].id}`;
});

async function boot() {
  if (!api.hasToken()) {
    mount(root, h("div", { class: "empty", style: { marginTop: "20vh" } },
      h("h3", {}, "Bitte über die App öffnen"), h("p", {}, "Diese Seite gehört zur App Fach und funktioniert nur aus ihr heraus.")));
    return;
  }
  try {
    await refreshState();
  } catch (e) {
    mount(root, h("div", { class: "empty", style: { marginTop: "20vh" } }, h("h3", {}, "Fach antwortet nicht"), h("p", {}, e.message)));
    return;
  }
  mountTitlebar(Boolean(store.state.app.custom_chrome));
  window.addEventListener("hashchange", route);
  listen(onEvent, (ok) => {
    if (ok && !store.ui.connected) refreshState().then(route);
    store.ui.connected = ok;
  });
  // Zustandsänderungen → Routing und Sidebar nachziehen
  subscribe((what) => {
    if (what !== "state") return;
    route();
    if (current?.startsWith("page:")) { refreshNavCounts(); updateSyncBox(); }
    watchExternal();
  });
  route();
  watchExternal();
  refreshUpdate().then(updatePill).catch(() => {});
}

window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.message) toast(e.reason.message, "alert");
});

boot();
