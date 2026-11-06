// Einstellungen: Zeitplan, Speicherort, Mitteilungen, Konto, Verlauf, Über.
import { api } from "../api.js";
import { button, h, mount, toast, toggle } from "../dom.js";
import { DAYS, duration, upcoming, when } from "../format.js";
import { refreshRuns, refreshState, store, subscribe } from "../store.js";

const STATUS = { ok: "Erfolgreich", partial: "Teilweise", error: "Fehler", offline: "Offline", auth: "Anmeldung", cancelled: "Abgebrochen", running: "Läuft" };
const TRIGGER = { auto: "automatisch", manual: "von Hand", onboarding: "Einrichtung" };

export function mountSettings(el) {
  let frame = 0;
  const render = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (el.contains(document.activeElement) && document.activeElement.matches("input[type=text], input[type=time]")) return;
      mount(el, page());
    });
  };
  const off = subscribe(render);
  render();
  refreshRuns().catch(() => {});
  return () => { off(); cancelAnimationFrame(frame); };
}

async function save(patch, message) {
  try {
    store.state = await api.put("/api/settings", patch);
    await refreshState();
    if (message) toast(message);
  } catch (e) {
    toast(e.message, "alert");
    refreshState();
  }
}

function setting(title, text, ...controls) {
  return h("section", { class: "setting" },
    h("div", { class: "label" }, h("h3", {}, title), text ? h("p", {}, text) : null),
    h("div", { class: "controls" }, controls));
}

function page() {
  const s = store.state;
  return h("div", { class: "page" },
    h("header", { class: "page-head" }, h("div", {}, h("h1", {}, "Einstellungen"),
      h("p", { class: "meta" }, `Fach ${s.app.version}${s.app.demo ? " · Demo-Modus" : ""}`))),
    h("div", { class: "settings" },
      scheduleSetting(s), folderSetting(s), notifySetting(s), videoSetting(s), accountSetting(s), historySetting(), aboutSetting(s)));
}

function scheduleSetting(s) {
  const sch = s.schedule;
  const days = h("div", { class: "days", role: "group", "aria-label": "Wochentage" },
    DAYS.map((d, i) => h("button", {
      class: "day", "aria-pressed": sch.days.includes(i) ? "true" : "false", disabled: !sch.enabled,
      onclick: () => {
        const next = sch.days.includes(i) ? sch.days.filter((x) => x !== i) : [...sch.days, i];
        if (!next.length) { toast("Mindestens ein Tag", "alert"); return; }
        save({ schedule: { days: next } });
      },
    }, d)));
  const time = h("input", { class: "input sm time-input", type: "time", value: sch.times[0] || "07:00", disabled: !sch.enabled, "aria-label": "Uhrzeit" });
  time.addEventListener("change", () => { if (time.value) save({ schedule: { times: [time.value, ...sch.times.slice(1)] } }, "Zeitplan gespeichert"); });
  const status = !sch.enabled ? null
    : s.schedule_error ? h("div", { class: "status-line" }, h("span", { class: "dot bad" }), "Nicht eingerichtet: ", s.schedule_error)
    : h("div", { class: "status-line" }, h("span", { class: "dot ok" }),
      `Nächster Abgleich ${upcoming(s.next_run)}${sch.spread_min ? `, mit bis zu ${sch.spread_min} Minuten Versatz` : ""}`);
  return setting("Automatisch abgleichen",
    "Läuft auch, wenn Fach geschlossen ist. War der Rechner aus, holt Fach den Abgleich beim nächsten Start nach.",
    h("div", { class: "inline" }, toggle(sch.enabled, (on) => save({ schedule: { enabled: on } }, on ? "Automatik an" : "Automatik aus"), "Automatisch abgleichen"),
      h("span", { class: "secondary" }, sch.enabled ? "An" : "Aus")),
    h("div", { class: "inline" }, days, h("span", { class: "muted" }, "um"), time),
    status);
}

function folderSetting(s) {
  const change = async () => {
    let path = null;
    if (s.app.can_choose_folder) {
      const res = await api.post("/api/folder/choose", { start: s.target_dir }).catch((e) => { toast(e.message, "alert"); return null; });
      path = res?.path;
    } else {
      path = prompt("Neuer Uni-Ordner (vollständiger Pfad):", s.target_dir);
    }
    if (path && path !== s.target_dir) save({ target_dir: path }, "Ordner geändert, Kursordner mitgenommen");
  };
  return setting("Speicherort", "Jeder Kurs bekommt hier einen eigenen Ordner. Beim Wechsel zieht Fach sie mit um.",
    h("div", { class: "path" }, s.target_dir),
    h("div", { class: "inline" },
      button("Ändern", { icon: "folder", size: "sm", onClick: change }),
      button("Öffnen", { kind: "quiet", size: "sm", icon: "folderOpen", onClick: () => api.post("/api/open", { target: "root" }).catch((e) => toast(e.message, "alert")) })));
}

function notifySetting(s) {
  const o = s.options;
  return setting("Mitteilungen", "Nur nach automatischen Abgleichen – wenn du in der App bist, siehst du es ja.",
    h("label", { class: "inline" }, toggle(o.notify_new, (v) => save({ options: { notify_new: v } }), "Neue Dateien"), "Neue Dateien"),
    h("label", { class: "inline" }, toggle(o.notify_error, (v) => save({ options: { notify_error: v } }), "Probleme"), "Probleme, die dich brauchen"));
}

function videoSetting(s) {
  return setting("Vorlesungsvideos", "Aufzeichnungen aus ILIAS mitladen. Kann viele Gigabyte belegen.",
    h("label", { class: "inline" }, toggle(s.options.videos, (v) => save({ options: { videos: v } }), "Videos mitladen"), "Videos mitladen"));
}

function accountSetting(s) {
  const logout = async () => {
    if (!confirm("Abmelden?\n\nDas Passwort wird von diesem Rechner gelöscht und der automatische Abgleich gestoppt. Deine Dateien und Kurse bleiben.")) return;
    await api.post("/api/logout");
    await refreshState();
  };
  return setting("Konto", `Dein Passwort liegt in ${s.app.password_store}, nicht in Fach. Fach spricht nur mit ${s.uni.host}.`,
    h("div", { class: "inline" }, h("span", { class: "mono" }, s.username), h("span", { class: "muted" }, s.uni.name)),
    h("div", {}, button("Abmelden", { kind: "danger", size: "sm", icon: "logout", onClick: logout })));
}

function historySetting() {
  const runs = store.runs;
  const table = !runs ? h("div", { class: "skeleton", style: { height: "120px" } })
    : !runs.length ? h("p", { class: "muted" }, "Noch keine Abgleiche.")
    : h("table", { class: "runs" }, h("tbody", {}, runs.slice(0, 10).map((r) => h("tr", {},
      h("td", { class: "mono" }, when(r.started * 1000)),
      h("td", {}, TRIGGER[r.trigger] || r.trigger),
      h("td", {}, h("span", { class: "inline", style: { gap: "8px", flexWrap: "nowrap" } },
        h("span", { class: `dot ${r.status === "ok" ? "ok" : r.status === "partial" || r.status === "offline" ? "warn" : r.status === "cancelled" ? "" : "bad"}` }),
        STATUS[r.status] || r.status)),
      h("td", { class: "secondary" }, r.message),
      h("td", { class: "num mono" }, r.ended ? duration(r.ended - r.started) : "")))));
  return setting("Verlauf", "Die letzten Abgleiche. Bei Problemen hilft die Protokolldatei weiter.",
    table,
    h("div", {}, button("Protokolle öffnen", { kind: "quiet", size: "sm", icon: "fileText", onClick: () => api.post("/api/open", { target: "logs" }).catch((e) => toast(e.message, "alert")) })));
}

function aboutSetting(s) {
  return setting("Über Fach", null,
    h("p", { class: "about" },
      "Ein inoffizielles Projekt von Studierenden – nicht von der Uni Köln oder dem RRZK. ",
      "Fach lädt nur, was du in ILIAS ohnehin sehen darfst, und verändert dort nichts. ",
      "Unter der Haube arbeitet PFERD (MIT-Lizenz). Schriften: Instrument Sans, IBM Plex Mono (OFL). Icons: Lucide (ISC)."),
    h("p", { class: "about mono" }, `Version ${s.app.version} · ${s.app.platform}`));
}
