// Zentraler Zustand der Oberfläche. Der Server ist die Quelle der Wahrheit;
// hier liegt nur die letzte Antwort plus ein wenig reiner UI-Zustand.
import { api } from "./api.js";

const listeners = new Set();

export const store = {
  state: null,        // /api/state
  feed: null,         // /api/feed
  timeline: null,     // /api/timeline
  runs: null,         // /api/runs
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
  const q = store.ui.filter ? `?course=${encodeURIComponent(store.ui.filter)}` : "";
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
