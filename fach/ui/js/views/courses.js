// Kurse: was abgeglichen wird, wohin, und neue Kurse aus ILIAS dazuholen.
import { api } from "../api.js";
import { button, h, icon, iconButton, menu, mount, plate, spinner, toast, toggle } from "../dom.js";
import { plural, prettyPath, when } from "../format.js";
import { refreshState, refreshTimeline, store, subscribe } from "../store.js";

export function mountCourses(el) {
  const ui = { editing: null, found: null, searching: false, linkOpen: false, linkBusy: false, linkError: "" };
  let frame = 0;
  const render = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (el.contains(document.activeElement) && document.activeElement.matches("input[type=text]")) return; // nicht beim Tippen neu zeichnen
      mount(el, page(ui, render));
    });
  };
  const off = subscribe((what) => { if (what === "state" || what === "timeline") render(); });
  render();
  refreshTimeline().catch(() => {});
  return () => { off(); cancelAnimationFrame(frame); };
}

function page(ui, render) {
  const s = store.state;
  const stats = new Map((store.timeline?.courses || []).map((c) => [c.id, c]));
  const active = s.courses.filter((c) => c.enabled);
  const totalFiles = [...stats.values()].reduce((n, c) => n + c.total, 0);

  const search = async () => {
    ui.searching = true; render();
    try {
      const res = await api.post("/api/discover");
      const fresh = res.courses.filter((c) => !c.known);
      ui.found = fresh;
      if (!fresh.length) toast("Keine neuen Kurse in ILIAS gefunden");
    } catch (e) { toast(e.message, "alert"); }
    ui.searching = false; render();
  };

  return h("div", { class: "page" },
    h("header", { class: "page-head" },
      h("div", {}, h("h1", {}, "Kurse"),
        h("p", { class: "meta" }, `${plural(active.length, "Kurs", "Kurse")} · ${plural(totalFiles, "Datei", "Dateien")} in ${prettyPath(s.target_dir)}`)),
      h("div", { class: "actions" },
        h("button", { class: "btn btn-quiet", onclick: () => { ui.linkOpen = !ui.linkOpen; render(); } }, icon("link"), "Per Link"),
        h("button", { class: "btn", onclick: search, disabled: ui.searching }, ui.searching ? spinner() : icon("search"),
          ui.searching ? "Suche in ILIAS" : "Neue Kurse suchen"))),
    ui.linkOpen ? linkPanel(ui, render) : null,
    ui.found?.length ? foundPanel(ui, render) : null,
    s.courses.length
      ? h("div", { class: "card course-list" }, s.courses.map((c) => courseRow(c, stats.get(c.id), ui, render)))
      : h("div", { class: "card empty" }, h("h3", {}, "Noch keine Kurse"), h("p", {}, "Suche in ILIAS nach deinen Kursen.")),
  );
}

function courseRow(c, stat, ui, render) {
  const save = async (patch) => {
    try {
      await api.put("/api/courses", { courses: [{ id: c.id, ...patch }] });
      await refreshState();
    } catch (e) { toast(e.message, "alert"); }
  };
  const openFolder = () => api.post("/api/open", { course_id: c.id }).catch((e) => toast(e.message, "alert"));
  const remove = async () => {
    if (!confirm(`${c.display_title} nicht mehr abgleichen?\n\nDie Dateien bleiben in deinem Ordner.`)) return;
    try { await api.del(`/api/courses/${encodeURIComponent(c.id)}`); await refreshState(); toast("Kurs entfernt"); }
    catch (e) { toast(e.message, "alert"); }
  };

  const editing = ui.editing === c.id;
  const row = h("div", { class: `course ${c.enabled ? "" : "off"}` },
    toggle(c.enabled, (on) => save({ enabled: on }), `${c.display_title} abgleichen`),
    plate(c.label),
    h("div", { class: "truncate" },
      h("div", { class: "title truncate", title: c.title }, c.display_title),
      h("div", { class: "folder truncate" }, icon("folder", 14), c.folder, c.semester ? h("span", {}, `· ${c.semester}`) : null),
      editing ? editForm(c, ui, render, save) : null),
    h("div", { class: "stat mono" }, stat ? stat.total : "–", h("small", {}, "Dateien")),
    h("div", { class: "stat last mono" }, stat?.last ? when(stat.last * 1000) : "–", h("small", {}, "letzte Datei")),
    h("div", { class: "tools" },
      iconButton("folderOpen", "Ordner öffnen", openFolder),
      iconButton("more", "Mehr", (e) => menu(e.currentTarget, [
        { label: "Ordner und Kürzel ändern", icon: "pencil", onClick: () => { ui.editing = c.id; render(); } },
        { label: "Nicht mehr abgleichen", icon: "trash", danger: true, onClick: remove },
      ]))),
  );
  return row;
}

function editForm(c, ui, render, save) {
  const folder = h("input", { class: "input sm", type: "text", value: c.folder, "aria-label": "Ordnername" });
  const label = h("input", { class: "input sm mono", type: "text", value: c.label, maxlength: 5, "aria-label": "Kürzel" });
  const done = async () => {
    await save({ folder: folder.value.trim(), label: label.value.trim() });
    ui.editing = null; document.activeElement?.blur(); render();
  };
  const cancel = () => { ui.editing = null; document.activeElement?.blur(); render(); };
  setTimeout(() => folder.focus(), 0);
  return h("form", { class: "course-edit", onsubmit: (e) => { e.preventDefault(); done(); }, onkeydown: (e) => { if (e.key === "Escape") cancel(); } },
    h("label", { class: "field" }, h("span", {}, "Ordner"), folder),
    h("label", { class: "field" }, h("span", {}, "Kürzel"), label),
    h("div", { class: "inline", style: { gap: "4px" } }, button("Speichern", { kind: "primary", size: "sm", type: "submit" }),
      button("Abbrechen", { kind: "quiet", size: "sm", onClick: cancel })));
}

function foundPanel(ui, render) {
  const chosen = new Set(ui.found.filter((c) => c.selected).map((c) => c.id));
  const add = async () => {
    const items = ui.found.filter((c) => chosen.has(c.id)).map((c) => ({ ...c, enabled: true }));
    if (!items.length) return;
    try {
      await api.put("/api/courses", { courses: items });
      ui.found = null;
      await refreshState();
      toast(`${plural(items.length, "Kurs", "Kurse")} hinzugefügt – beim nächsten Abgleich dabei`);
    } catch (e) { toast(e.message, "alert"); }
    render();
  };
  return h("section", { class: "card found", style: { marginBottom: "16px" } },
    h("div", { class: "found-head" }, h("h2", {}, `${plural(ui.found.length, "Kurs", "Kurse")} in ILIAS, die noch fehlen`),
      h("span", { class: "spacer", style: { flex: 1 } }),
      iconButton("x", "Schließen", () => { ui.found = null; render(); })),
    h("div", {}, ui.found.map((c) => {
      const box = h("input", { type: "checkbox", class: "check" });
      box.checked = chosen.has(c.id);
      box.addEventListener("change", () => (box.checked ? chosen.add(c.id) : chosen.delete(c.id)));
      return h("label", { class: "found-item" }, box, plate(c.label), h("span", { class: "truncate" }, c.display_title),
        h("span", { class: "sem mono" }, c.semester || ""));
    })),
    h("div", {}, button("Ausgewählte hinzufügen", { kind: "primary", size: "sm", onClick: add })));
}

function linkPanel(ui, render) {
  const input = h("input", { class: "input", type: "text", placeholder: "https://www.ilias.uni-koeln.de/ilias/goto.php/crs/…", "aria-label": "Kurs-Link" });
  const submit = async (e) => {
    e.preventDefault();
    ui.linkBusy = true; ui.linkError = "";
    try {
      const { course } = await api.post("/api/courses/resolve", { url: input.value });
      if (course.known) { toast("Den Kurs gleichst du schon ab"); }
      else {
        await api.put("/api/courses", { courses: [{ ...course, enabled: true }] });
        toast(`${course.display_title} hinzugefügt`);
        ui.linkOpen = false;
        await refreshState();
      }
    } catch (err) { ui.linkError = err.message; }
    ui.linkBusy = false;
    input.blur(); render();
  };
  setTimeout(() => input.focus(), 0);
  return h("form", { class: "card found", style: { marginBottom: "16px" }, onsubmit: submit },
    h("div", {}, h("h2", {}, "Kurs per Link hinzufügen"),
      h("p", { class: "muted", style: { fontSize: "13px", marginTop: "4px" } },
        "Öffne den Kurs in ILIAS und kopiere die Adresse aus der Adresszeile.")),
    h("div", { class: "inline", style: { flexWrap: "nowrap" } }, input,
      button(ui.linkBusy ? "Prüfe" : "Hinzufügen", { kind: "primary", type: "submit", disabled: ui.linkBusy })),
    ui.linkError ? h("div", { class: "form-error" }, icon("alert"), ui.linkError) : null);
}
