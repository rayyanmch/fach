// Einrichtung in drei Schritten plus erster Abgleich. Ziel: auch ohne Technikwissen in zwei Minuten fertig.
//   1 Anmelden  →  2 Kurse  →  3 Ablage & Zeitplan  →  erster Abgleich (live)
import { api } from "../api.js";
import { button, h, icon, mount, plate, spinner, toast, toggle } from "../dom.js";
import { plural, prettyPath } from "../format.js";
import { refreshState, store } from "../store.js";
import { brandMark } from "./shell.js";
import { createShelf } from "./shelf.js";

const PREVIEW = ["BWL", "ISM", "SWT", "MA1", "VIS", "STA", "", "WINF", "VWL"];
const PREVIEW_COUNTS = [9, 5, 14, 7, undefined, 4, undefined, 3, 6];

const ob = {
  step: 1, username: "", password: "", error: "", busy: false,
  courses: [], target: "", schedule: { enabled: true, times: ["07:00"] },
  linkOpen: false, linkError: "", editing: null,
  live: { done: {}, finished: null },
};
let shelf = null;
let root = null;

export function mountOnboarding(el) {
  root = el;
  const s = store.state;
  // Jede Einrichtung beginnt vorn – auch nach „Abmelden“ in derselben Sitzung.
  Object.assign(ob, { step: 1, error: "", busy: false, courses: [], linkOpen: false, linkError: "", editing: null,
    live: { done: {}, finished: null } });
  ob.username = ob.username || s.username || "";
  ob.target = s.target_dir;
  shelf = createShelf();
  render();
  return () => { root = null; };
}

export function onboardingActive() {
  return root !== null;
}

function render() {
  if (!root) return;
  const focusId = document.activeElement?.id;
  const visual = h("aside", { class: "ob-visual" },
    h("div", { class: "brand" }, brandMark(), h("span", { class: "brand-name" }, "Fach")),
    h("div", { class: "shelf-wrap" }, shelf.svg),
    h("p", { class: "caption" }, caption()));
  updateShelf();
  const body = [null, stepLogin, stepCourses, stepPlace, stepLive][ob.step]();
  mount(root, h("div", { class: "onboarding" }, visual,
    h("div", { class: "ob-main" }, h("div", { class: "ob-inner" }, steps(), body))));
  if (focusId) document.getElementById(focusId)?.focus();
}

function caption() {
  if (ob.step === 1) return "Ein Fach pro Kurs, wie die Postfächer am Lehrstuhl. Fach legt jeden Morgen ab, was in ILIAS neu ist.";
  if (ob.step === 4 && ob.live.finished) return `Jedes Fach ist ein Ordner in ${prettyPath(ob.target || store.state.target_dir)}.`;
  if (ob.step === 4) return "Die Fächer füllen sich, Kurs für Kurs.";
  return "Jeder ausgewählte Kurs bekommt sein eigenes Fach.";
}

function selected() {
  return ob.courses.filter((c) => c.selected);
}

function updateShelf() {
  if (ob.step === 1) {
    shelf.setLabels(PREVIEW);
    shelf.setFilled(PREVIEW_COUNTS, 2);
    return;
  }
  const sel = ob.step === 4 && !ob.courses.length ? store.state.courses.filter((c) => c.enabled) : selected();
  shelf.setLabels(sel.map((c) => c.label));
  shelf.setFilled(sel.map((c) => ob.live.done[c.id]), -1);
}

function steps() {
  const names = ["Anmelden", "Kurse", "Ablage"];
  return h("div", { class: "steps", "aria-label": "Fortschritt" },
    names.map((n, i) => h("span", { class: i + 1 === ob.step ? "on" : i + 1 < ob.step ? "done" : "" }, `${i + 1} ${n}`)));
}

// ---------- 1 Anmelden ----------
function stepLogin() {
  const s = store.state;
  const user = h("input", { id: "ob-user", class: "input", type: "text", autocomplete: "username", value: ob.username,
    placeholder: s.uni.username_hint, autocapitalize: "off", spellcheck: "false", "aria-invalid": ob.error ? "true" : null });
  const pass = h("input", { id: "ob-pass", class: "input", type: "password", autocomplete: "current-password", value: ob.password,
    "aria-invalid": ob.error ? "true" : null });
  user.addEventListener("input", () => { ob.username = user.value; });
  pass.addEventListener("input", () => { ob.password = pass.value; });
  const submit = async (e) => {
    e.preventDefault();
    if (ob.busy) return;
    ob.error = ""; ob.busy = true; render();
    try {
      const res = await api.post("/api/login", { username: ob.username.trim(), password: ob.password });
      ob.courses = res.courses;
      ob.password = "";
      ob.step = 2;
    } catch (err) {
      ob.error = err.message;
    }
    ob.busy = false;
    render();
    if (ob.error) { const el = document.getElementById("ob-pass"); el?.focus(); el?.select(); }
  };
  setTimeout(() => (ob.username ? pass : user).focus(), 0);
  return h("div", {},
    h("h1", { class: "ob-title" }, "Deine Unterlagen aus ILIAS, jeden Morgen auf deinem Rechner"),
    h("p", { class: "ob-lead" }, "Melde dich einmal an. Fach sucht deine Kurse, legt pro Kurs einen Ordner an und holt Neues automatisch."),
    h("form", { class: "ob-form", onsubmit: submit },
      h("label", { class: "field" }, h("span", {}, "Uni-Kennung"), user, h("span", { class: "help" }, s.uni.username_help)),
      h("label", { class: "field" }, h("span", {}, "Passwort"), pass),
      ob.error ? h("div", { class: "form-error", role: "alert" }, icon("alert"), ob.error) : null,
      h("div", { class: "ob-actions" },
        h("button", { class: "btn btn-primary btn-lg", type: "submit", disabled: ob.busy },
          ob.busy ? spinner() : null, ob.busy ? "Suche deine Kurse" : "Anmelden und Kurse suchen"))),
    h("div", { class: "trust" }, icon("lock"),
      h("p", {}, `Dein Passwort bleibt auf diesem Rechner, in ${s.app.password_store}. Fach spricht nur mit ${s.uni.host} – keine eigenen Server, keine Statistik.`)),
    s.app.demo ? h("p", { class: "muted", style: { marginTop: "12px", fontSize: "13px" } },
      "Demo-Modus: jede Kennung funktioniert. Mit dem Passwort „falsch“ siehst du den Fehlerfall.") : null);
}

// ---------- 2 Kurse ----------
function stepCourses() {
  const groups = [
    ["Dieses Semester", ob.courses.filter((c) => c.current)],
    ["Ohne Semesterangabe", ob.courses.filter((c) => !c.current && !c.semester)],
    ["Frühere Semester", ob.courses.filter((c) => !c.current && c.semester)],
  ].filter(([, list]) => list.length);
  const n = selected().length;

  const list = h("div", { class: "pick-list" }, groups.map(([label, items]) => [
    groups.length > 1 ? h("div", { class: "pick-group" }, label) : null,
    items.map(pickRow),
  ]));

  return h("div", {},
    h("h1", { class: "ob-title" }, "Welche Kurse sollen mit?"),
    h("p", { class: "ob-lead" }, ob.courses.length
      ? `${plural(ob.courses.length, "Kurs", "Kurse")} in ILIAS gefunden. Aus diesem Semester ist alles ausgewählt; Ordnernamen kannst du anklicken und ändern.`
      : "In ILIAS stehen gerade keine Kurse in „Meine Kurse und Gruppen“. Füge einen per Link hinzu."),
    h("div", { class: "ob-form" },
      ob.courses.length ? list : null,
      linkAdd(),
      h("div", { class: "ob-actions" },
        button("Zurück", { kind: "quiet", onClick: () => { ob.step = 1; render(); } }),
        h("span", { class: "spacer" }),
        h("span", { class: "muted" }, n ? plural(n, "Kurs", "Kurse") : "Keiner ausgewählt"),
        button("Weiter", { kind: "primary", size: "lg", disabled: !n, onClick: () => { ob.step = 3; render(); } }))));
}

function pickRow(c) {
  const box = h("input", { type: "checkbox", class: "check", "aria-label": c.display_title });
  box.checked = c.selected;
  box.addEventListener("change", () => { c.selected = box.checked; render(); });
  let folder;
  if (ob.editing === c.id) {
    const input = h("input", { id: `f-${c.id}`, class: "input sm", type: "text", value: c.folder, "aria-label": "Ordnername" });
    const done = () => { const v = input.value.trim(); if (v) c.folder = v; ob.editing = null; render(); };
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); done(); } if (e.key === "Escape") { ob.editing = null; render(); } });
    input.addEventListener("blur", done);
    input.addEventListener("click", (e) => e.preventDefault());
    setTimeout(() => { input.focus(); input.select(); }, 0);
    folder = h("div", { class: "f" }, input);
  } else {
    folder = h("div", { class: "f" }, icon("folder", 14),
      h("button", { class: "link-btn", style: { color: "inherit", fontWeight: 400 }, title: "Ordnernamen ändern",
        onclick: (e) => { e.preventDefault(); ob.editing = c.id; render(); } }, c.folder));
  }
  return h("label", { class: `pick ${c.selected ? "" : "dim"}` }, box, plate(c.label),
    h("div", { class: "truncate" }, h("div", { class: "t truncate", title: c.title }, c.display_title), folder),
    h("span", { class: "sem mono" }, c.current ? "" : c.semester || ""));
}

function linkAdd() {
  if (!ob.linkOpen) {
    return h("div", {}, h("button", { class: "link-btn", onclick: () => { ob.linkOpen = true; render(); } }, "Kurs fehlt? Link einfügen"));
  }
  const input = h("input", { id: "ob-link", class: "input", type: "text", placeholder: "Adresse des Kurses aus dem Browser" });
  const add = async (e) => {
    e.preventDefault();
    ob.linkError = "";
    try {
      const { course } = await api.post("/api/courses/resolve", { url: input.value });
      const existing = ob.courses.find((c) => c.id === course.id);
      if (existing) existing.selected = true;
      else ob.courses.push({ ...course, selected: true, current: true });
      ob.linkOpen = false;
    } catch (err) { ob.linkError = err.message; }
    render();
  };
  setTimeout(() => input.focus(), 0);
  return h("form", { class: "stack", onsubmit: add },
    h("div", { class: "inline", style: { flexWrap: "nowrap" } }, input, button("Hinzufügen", { type: "submit" })),
    ob.linkError ? h("div", { class: "form-error" }, icon("alert"), ob.linkError) : null);
}

// ---------- 3 Ablage & Zeitplan ----------
function stepPlace() {
  const s = store.state;
  const sel = selected();
  const sep = ob.target.includes("\\") ? "\\" : "/";
  const rootName = ob.target.split(/[\\/]/).filter(Boolean).pop() || ob.target;
  const lines = sel.slice(0, 5).map((c, i) => `${i === Math.min(sel.length, 5) - 1 && sel.length <= 5 ? "└─" : "├─"} ${c.folder}`);
  if (sel.length > 5) lines.push(`└─ … ${sel.length - 5} weitere`);
  const tree = h("div", { class: "tree" }, h("span", { class: "root" }, `${rootName}${sep}`), "\n", lines.join("\n"));

  const choose = async () => {
    if (s.app.can_choose_folder) {
      const res = await api.post("/api/folder/choose", { start: ob.target }).catch((e) => { toast(e.message, "alert"); return null; });
      if (res?.path) { ob.target = res.path; render(); }
    }
  };
  const pathField = s.app.can_choose_folder
    ? h("div", { class: "inline", style: { flexWrap: "nowrap" } },
      h("div", { class: "path truncate", style: { flex: 1 }, title: ob.target }, prettyPath(ob.target)),
      button("Ändern", { icon: "folder", onClick: choose }))
    : (() => {
      const input = h("input", { id: "ob-target", class: "input mono", type: "text", value: ob.target });
      input.addEventListener("change", () => { ob.target = input.value.trim(); render(); });
      return input;
    })();

  const time = h("input", { class: "input sm time-input", type: "time", value: ob.schedule.times[0], disabled: !ob.schedule.enabled, "aria-label": "Uhrzeit" });
  time.addEventListener("change", () => { if (time.value) ob.schedule.times = [time.value]; });

  const finish = async () => {
    ob.busy = true; ob.error = ""; render();
    try {
      await api.post("/api/setup", {
        target_dir: ob.target,
        courses: ob.courses.map((c) => ({ id: c.id, title: c.title, folder: c.folder, label: c.label, semester: c.semester, enabled: c.selected })),
        schedule: { enabled: ob.schedule.enabled, times: ob.schedule.times },
      });
      ob.step = 4;
      ob.live = { done: {}, finished: null };
      await refreshState();
    } catch (err) { ob.error = err.message; }
    ob.busy = false;
    render();
  };

  return h("div", {},
    h("h1", { class: "ob-title" }, "Wohin mit den Unterlagen?"),
    h("p", { class: "ob-lead" }, "Pro Kurs ein Ordner. Eigene Notizen und markierte PDFs darin überschreibt Fach nie."),
    h("div", { class: "ob-form" },
      h("div", { class: "field" }, h("span", {}, "Uni-Ordner"), pathField),
      tree,
      h("div", { class: "field", style: { marginTop: "8px" } }, h("span", {}, "Automatisch"),
        h("div", { class: "inline" },
          toggle(ob.schedule.enabled, (on) => { ob.schedule.enabled = on; render(); }, "Jeden Tag automatisch abgleichen"),
          h("span", {}, "Jeden Tag um"), time),
        h("span", { class: "help" }, "Auch wenn Fach geschlossen ist. War der Rechner aus, wird es beim nächsten Start nachgeholt.")),
      ob.error ? h("div", { class: "form-error", role: "alert" }, icon("alert"), ob.error) : null,
      h("div", { class: "ob-actions" },
        button("Zurück", { kind: "quiet", onClick: () => { ob.step = 2; render(); } }),
        h("span", { class: "spacer" }),
        h("button", { class: "btn btn-primary btn-lg", disabled: ob.busy || !ob.target, onclick: finish },
          ob.busy ? spinner() : null, "Fertig, Unterlagen holen"))));
}

// ---------- 4 Erster Abgleich ----------
function stepLive() {
  const s = store.state;
  const p = s.sync;
  const courses = s.courses.filter((c) => c.enabled);
  const fin = ob.live.finished;
  const total = Object.values(ob.live.done).reduce((a, b) => a + b, 0);

  const rows = courses.map((c, i) => {
    const done = ob.live.done[c.id];
    const active = p.running && p.course_id === c.id;
    const state = done !== undefined ? icon("check") : active ? spinner() : h("span", { class: "dot", style: { opacity: 0.4 } });
    return h("div", { class: `live ${active ? "active" : ""} ${done !== undefined ? "done" : ""}` },
      plate(c.label),
      h("div", { class: "truncate" }, h("div", { class: "t truncate" }, c.display_title),
        active && p.current ? h("div", { class: "mono muted truncate", style: { fontSize: "11px" } }, p.current.split("/").pop()) : null),
      h("div", { class: "inline", style: { justifyContent: "flex-end", flexWrap: "nowrap", gap: "8px" } },
        h("span", { class: "n mono" }, done !== undefined ? done : ""), h("span", { class: "state" }, state)));
  });

  const frac = p.running && p.course_total ? (p.course_index - 1 + 0.5) / p.course_total : fin ? 1 : 0;
  const okish = fin && (fin.status === "ok" || fin.status === "partial");
  return h("div", {},
    h("h1", { class: "ob-title" }, fin ? (okish ? "Alles abgelegt" : "Das hat nicht ganz geklappt") : "Hole deine Unterlagen"),
    h("p", { class: "ob-lead" }, fin
      ? okish ? `${plural(total, "Datei", "Dateien")} aus ${plural(Object.keys(ob.live.done).length, "Kurs", "Kursen")}. ${fin.status === "partial" ? "Ein paar Kurse hatten Probleme – sie werden beim nächsten Abgleich erneut versucht." : "Ab jetzt landet hier nur noch, was neu ist."}`
        : fin.message
      : "Der erste Abgleich dauert ein paar Minuten, danach geht es schnell. Du kannst das Fenster offen lassen."),
    h("div", { class: "progress", style: { marginTop: "24px" } }, h("i", { style: { transform: `scaleX(${frac})` } })),
    h("div", { class: "live-list" }, rows),
    fin ? h("div", { class: "ob-actions", style: { marginTop: "24px" } },
      button("Ordner öffnen", { icon: "folderOpen", onClick: () => api.post("/api/open", { target: "root" }).catch((e) => toast(e.message, "alert")) }),
      h("span", { class: "spacer" }),
      button("Zur Übersicht", { kind: "primary", size: "lg", onClick: () => { root = null; location.hash = "#/uebersicht"; window.dispatchEvent(new HashChangeEvent("hashchange")); } }))
      : null);
}

// ---------- Live-Ereignisse vom Server ----------
export function onboardingEvent(ev) {
  if (!root || ob.step !== 4) return;
  if (ev.type === "course_done") ob.live.done[ev.course_id] = ev.added;
  if (ev.type === "run_done") ob.live.finished = ev.run;
  render();
}
