// Zentraler Zustand der Oberfläche. Der Server ist die Quelle der Wahrheit;
// hier liegt nur die letzte Antwort plus ein wenig reiner UI-Zustand.
import { api } from "./api.js";

const listeners = new Set();

export const store = {
  state: null,        // /api/state
  feed: null,         // /api/feed
  timeline: null,     // /api/timeline
  runs: null,         // /api/runs
  exams: null,        // /api/exams
  update: null,       // /api/update
  ui: { filter: null, connected: true },
};

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function notify(what = "all") {
  for (const fn of listeners) fn(what);
}

export async function refreshState() {
  store.state = await api.get("/api/state");
  notify("state");
  return store.state;
}

export async function refreshFeed() {
  const q = store.ui.filter ? `?module=${encodeURIComponent(store.ui.filter)}` : "";
  store.feed = await api.get(`/api/feed${q}`);
  notify("feed");
}

export async function refreshTimeline() {
  store.timeline = await api.get("/api/timeline");
  notify("timeline");
}

export async function refreshRuns() {
  store.runs = await api.get("/api/runs");
  notify("runs");
}

export const courseById = (id) => store.state?.courses.find((c) => c.id === id);

export async function refreshExams() {
  store.exams = await api.get("/api/exams");
  notify("exams");
}

export async function refreshUpdate() {
  store.update = await api.get("/api/update");
  notify("update");
}

// Module = erster Ordnerteil; Vorlesung + Übung eines Fachs sind ein Modul.
export function modules({ enabledOnly = false } = {}) {
  const map = new Map();
  for (const c of store.state?.courses || []) {
    if (enabledOnly && !c.enabled) continue;
    if (!map.has(c.module)) map.set(c.module, { module: c.module, label: c.label, courses: [] });
    map.get(c.module).courses.push(c);
  }
  for (const m of map.values()) {
    m.title = m.courses.length === 1 && !m.courses[0].role ? m.courses[0].display_title : m.module;
    m.grouped = m.courses.length > 1 || Boolean(m.courses[0].role);
    m.enabled = m.courses.some((c) => c.enabled);
  }
  return [...map.values()];
}
