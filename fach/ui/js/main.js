// Start, Routing, Live-Ereignisse und Tastenkürzel.
import { api, listen } from "./api.js";
import { h, mount, toast } from "./dom.js";
import { refreshFeed, refreshRuns, refreshState, refreshTimeline, store, subscribe } from "./store.js";
import { mountCourses } from "./views/courses.js";
import { mountHome } from "./views/home.js";
import { mountOnboarding, onboardingActive, onboardingEvent } from "./views/onboarding.js";
import { mountSettings } from "./views/settings.js";
import { renderShell, ROUTES, runToast, startSync, updateSyncBox } from "./views/shell.js";

const root = document.getElementById("root");
const PAGES = { uebersicht: mountHome, kurse: mountCourses, einstellungen: mountSettings };
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
  cleanup?.();
  current = key;
  const { main } = renderShell(root, id);
  cleanup = PAGES[id](main);
  main.focus?.();
}

// Sidebar-Zähler und Status ändern sich, ohne dass die Seite neu gezeichnet wird.
function refreshChrome() {
  if (!current?.startsWith("page:")) return;
  const s = store.state;
  const unopened = s.courses.reduce((n, c) => n + (c.enabled ? c.unopened : 0), 0);
  const counts = { uebersicht: unopened, kurse: s.courses.filter((c) => c.enabled).length };
  document.querySelectorAll(".nav a").forEach((a, i) => {
    const id = ROUTES[i].id;
    let badge = a.querySelector(".count");
    if (!counts[id]) { badge?.remove(); return; }
    if (!badge) { badge = h("span", { class: `count ${id === "uebersicht" ? "new" : ""}` }); a.append(badge); }
    badge.textContent = counts[id];
  });
  updateSyncBox();
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
  } else if (ev.type === "changed") {
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
  window.addEventListener("hashchange", route);
  listen(onEvent, (ok) => {
    if (ok && !store.ui.connected) refreshState().then(route);
    store.ui.connected = ok;
  });
  // Zustandsänderungen → Routing und Sidebar nachziehen
  subscribe((what) => {
    if (what !== "state") return;
    route();
    refreshChrome();
    watchExternal();
  });
  route();
  watchExternal();
}

window.addEventListener("unhandledrejection", (e) => {
  if (e.reason?.message) toast(e.reason.message, "alert");
});

boot();
