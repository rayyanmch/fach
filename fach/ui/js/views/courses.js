// Kurse: Module (Vorlesung + Übung gehören zusammen), was abgeglichen wird, wohin, wie viel Platz.
import { api } from "../api.js";
import { button, confirmDialog, h, icon, iconButton, menu, mount, plate, spinner, toast, toggle } from "../dom.js";
import { bytes, plural, prettyPath, when } from "../format.js";
import { modules, refreshState, refreshTimeline, store, subscribe } from "../store.js";

export function mountCourses(el) {
  const ui = { editing: null, plate: null, found: null, searching: false, linkOpen: false, linkBusy: false, linkError: "", groups: [] };
  let frame = 0;
  const render = () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (el.contains(document.activeElement) && document.activeElement.matches("input[type=text]")) return; // nicht beim Tippen neu zeichnen
      mount(el, page(ui, render));
    });
  };
  const loadGroups = async () => { try { ui.groups = await api.get("/api/courses/groups"); render(); } catch {} };
  const off = subscribe((what) => {
    if (what === "state" || what === "timeline") render();
    if (what === "state") loadGroups();
  });
  render();
  refreshTimeline().catch(() => {});
  loadGroups();
  return () => { off(); cancelAnimationFrame(frame); };
}

function statsFor(courses) {
  const byId = new Map((store.timeline?.courses || []).map((c) => [c.id, c]));
  let total = 0, size = 0, last = 0;
  for (const c of courses) {
    const t = byId.get(c.id);
    if (!t) continue;
    total += t.total; size += t.bytes; last = Math.max(last, t.last || 0);
  }
  return { total, size, last, known: byId.size > 0 };
}

function page(ui, render) {
  const s = store.state;
  const mods = modules();
  const active = mods.filter((m) => m.enabled);
  const all = statsFor(s.courses.filter((c) => c.enabled));

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
        h("p", { class: "meta" }, [plural(active.length, "Modul", "Module"), all.known ? bytes(all.size) : null,
          `in ${prettyPath(s.target_dir)}`].filter(Boolean).join(" · "))),
      h("div", { class: "actions" },
        h("button", { class: "btn btn-quiet", onclick: () => { ui.linkOpen = !ui.linkOpen; render(); } }, icon("link"), "Per Link"),
        h("button", { class: "btn", onclick: search, disabled: ui.searching }, ui.searching ? spinner() : icon("search"),
          ui.searching ? "Suche in ILIAS" : "Neue Kurse suchen"))),
    ui.groups.map((g) => groupCard(g, ui, render)),
    ui.linkOpen ? linkPanel(ui, render) : null,
    ui.found?.length ? foundPanel(ui, render) : null,
    mods.length
      ? [h("div", { class: "course-head" }, h("span"), h("span"), h("span", {}, "Modul"), h("span", {}, "Dateien"),
        h("span", {}, "Größe"), h("span", {}, "Letzte Datei"), h("span")),
      h("div", { class: "card course-list" }, mods.map((m) => moduleRows(m, ui, render)))]
      : h("div", { class: "card empty" }, h("h3", {}, "Noch keine Kurse"), h("p", {}, "Suche in ILIAS nach deinen Kursen.")),
    storageSection(mods),
  );
}

// --- Vorschlag: Vorlesung + Übung zusammenlegen --------------------------------

function groupCard(g, ui, render) {
  const decide = async (apply) => {
    try {
      await api.post("/api/courses/groups", { key: g.key, apply });
      ui.groups = ui.groups.filter((x) => x.key !== g.key);
      await Promise.all([refreshState(), refreshTimeline()]);
      if (apply) toast(`In „${g.module}“ zusammengelegt`);
    } catch (e) { toast(e.message, "alert"); }
    render();
  };
  return h("section", { class: "card group-card" },
    h("div", { class: "inline", style: { justifyContent: "space-between" } },
      h("div", {}, h("h2", {}, `${g.module}: ${g.members.length} Kurse, ein Modul`),
        h("p", { class: "muted", style: { fontSize: "13px", marginTop: "2px" } },
          "Diese Kurse gehören zusammen. Fach legt sie in einen gemeinsamen Ordner – Dateien und Notizen ziehen mit um.")),
      plate(g.label)),
    h("div", { class: "moves" }, g.members.map((m) => h("div", { class: "move" },
      h("span", { class: "truncate" }, m.from), icon("chevronRight", 14), h("span", { class: "to truncate" }, m.to)))),
    h("div", { class: "inline" }, button("Zusammenlegen", { kind: "primary", size: "sm", onClick: () => decide(true) }),
      button("Getrennt lassen", { kind: "quiet", size: "sm", onClick: () => decide(false) })));
}

// --- Modul- und Kurszeilen ------------------------------------------------------

async function saveCourses(items) {
  try {
    await api.put("/api/courses", { courses: items });
    await Promise.all([refreshState(), refreshTimeline()]);
    return true;
  } catch (e) { toast(e.message, "alert"); return false; }
}

function plateEditor(m, ui, render) {
  if (ui.plate !== m.module) {
    return h("button", { class: "plate-btn", title: "Kürzel ändern", onclick: () => { ui.plate = m.module; render(); } }, plate(m.label));
  }
  const input = h("input", { class: "plate-input", type: "text", value: m.label, maxlength: 5, "aria-label": "Kürzel" });
  let done = false;
  const save = async () => {
    if (done) return;
    done = true;
    const label = input.value.trim().toUpperCase();
    ui.plate = null;
    input.blur();
    if (label && label !== m.label) await saveCourses(m.courses.map((c) => ({ id: c.id, label })));
    render();
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") save(); if (e.key === "Escape") { done = true; ui.plate = null; input.blur(); render(); } });
  input.addEventListener("blur", save);
  setTimeout(() => { input.focus(); input.select(); }, 0);
  return input;
}

function moduleRows(m, ui, render) {
  const st = statsFor(m.courses);
  const openFolder = (course) => api.post("/api/open", { course_id: course.id }).catch((e) => toast(e.message, "alert"));
  if (!m.grouped) return courseRow(m.courses[0], m, ui, render, { single: true });

  const moduleMenu = (e) => menu(e.currentTarget, [
    { label: "Modulordner umbenennen", icon: "pencil", onClick: () => { ui.editing = `module:${m.module}`; render(); } },
    { label: "Kürzel ändern", icon: "pencil", onClick: () => { ui.plate = m.module; render(); } },
  ]);
  const head = h("div", { class: "course module-row" },
    h("span"),
    plateEditor(m, ui, render),
    h("div", { class: "truncate" },
      h("div", { class: "title truncate" }, m.module),
      h("div", { class: "folder truncate" }, icon("folder", 14), `${m.courses.length} Kurse`),
      ui.editing === `module:${m.module}` ? moduleRename(m, ui, render) : null),
    h("div", { class: "stat mono" }, st.known && st.total ? st.total : "–"),
    h("div", { class: "stat mono" }, st.known && st.total ? bytes(st.size) : "–"),
    h("div", { class: "stat last mono" }, st.last ? when(st.last * 1000) : "–"),
    h("div", { class: "tools" }, iconButton("folderOpen", "Modulordner öffnen", () => openFolder(m.courses[0]).then(() => {})),
      iconButton("more", "Mehr", moduleMenu)));
  return [head, m.courses.map((c) => courseRow(c, m, ui, render, { single: false }))];
}

function moduleRename(m, ui, render) {
  const input = h("input", { class: "input sm", type: "text", value: m.module, "aria-label": "Modulordner" });
  const done = async () => {
    const name = input.value.trim();
    ui.editing = null;
    input.blur();
    if (name && name !== m.module) {
      const ok = await saveCourses(m.courses.map((c) => ({ id: c.id, folder: c.role ? `${name}/${c.role}` : name })));
      if (ok) toast("Ordner umbenannt");
    }
    render();
  };
  setTimeout(() => { input.focus(); input.select(); }, 0);
  return h("form", { class: "course-edit", style: { gridTemplateColumns: "1fr auto" }, onsubmit: (e) => { e.preventDefault(); done(); },
    onkeydown: (e) => { if (e.key === "Escape") { ui.editing = null; input.blur(); render(); } } },
  input, button("Speichern", { kind: "primary", size: "sm", type: "submit" }));
}

function courseRow(c, m, ui, render, { single }) {
  const st = statsFor([c]);
  const openFolder = () => api.post("/api/open", { course_id: c.id }).catch((e) => toast(e.message, "alert"));
  const remove = async () => {
    const ok = await confirmDialog({ title: `${c.display_title} nicht mehr abgleichen?`, text: "Die Dateien bleiben in deinem Ordner.",
      ok: "Nicht mehr abgleichen", danger: true });
    if (!ok) return;
    try { await api.del(`/api/courses/${encodeURIComponent(c.id)}`); await refreshState(); toast("Kurs entfernt"); }
    catch (e) { toast(e.message, "alert"); }
  };
  const editing = ui.editing === c.id;
  return h("div", { class: `course ${c.enabled ? "" : "off"} ${single ? "" : "sub-course"}` },
    toggle(c.enabled, (on) => saveCourses([{ id: c.id, enabled: on }]), `${c.display_title} abgleichen`),
    single ? plateEditor(m, ui, render) : h("span"),
    h("div", { class: "truncate" },
      single
        ? h("div", { class: "title truncate", title: c.title }, c.display_title)
        : h("div", { class: "truncate", title: c.title }, h("span", { class: "role" }, c.role || "Kurs"),
          h("span", { class: "muted", style: { marginLeft: "8px", fontSize: "13px" } }, c.display_title)),
      single ? h("div", { class: "folder truncate" }, icon("folder", 14), c.folder, c.semester ? h("span", {}, `· ${c.semester}`) : null) : null,
      editing ? folderForm(c, ui, render) : null),
    h("div", { class: "stat mono" }, st.known && st.total ? st.total : "–"),
    h("div", { class: "stat mono" }, st.known && st.total ? bytes(st.size) : "–"),
    h("div", { class: "stat last mono" }, st.last ? when(st.last * 1000) : "–"),
    h("div", { class: "tools" },
      iconButton("folderOpen", "Ordner öffnen", openFolder),
      iconButton("more", "Mehr", (e) => menu(e.currentTarget, [
        { label: "Ordner ändern", icon: "pencil", onClick: () => { ui.editing = c.id; render(); } },
        ...(single ? [{ label: "Kürzel ändern", icon: "pencil", onClick: () => { ui.plate = m.module; render(); } }] : []),
        { label: "Nicht mehr abgleichen", icon: "trash", danger: true, onClick: remove },
      ]))),
  );
}

function folderForm(c, ui, render) {
  const folder = h("input", { class: "input sm", type: "text", value: c.folder, "aria-label": "Ordner" });
  const done = async () => {
    const ok = await saveCourses([{ id: c.id, folder: folder.value.trim() }]);
    ui.editing = null; folder.blur(); render();
    if (ok) toast("Ordner geändert");
  };
  const cancel = () => { ui.editing = null; folder.blur(); render(); };
  setTimeout(() => folder.focus(), 0);
  return h("form", { class: "course-edit", style: { gridTemplateColumns: "1fr auto" }, onsubmit: (e) => { e.preventDefault(); done(); },
    onkeydown: (e) => { if (e.key === "Escape") cancel(); } },
  h("label", { class: "field" }, h("span", {}, "Ordner im Uni-Ordner (Unterordner mit /)"), folder),
  h("div", { class: "inline", style: { gap: "4px" } }, button("Speichern", { kind: "primary", size: "sm", type: "submit" }),
    button("Abbrechen", { kind: "quiet", size: "sm", onClick: cancel })));
}

// --- Speicher -----------------------------------------------------------------

function storageSection(mods) {
  const t = store.timeline;
  if (!t) return null;
  const rows = mods.map((m) => ({ m, ...statsFor(m.courses) })).filter((r) => r.size > 0).sort((a, b) => b.size - a.size);
  if (!rows.length) return null;
  const max = rows[0].size;
  const total = rows.reduce((n, r) => n + r.size, 0);
  return h("section", { class: "section" },
    h("div", { class: "section-head" }, h("h2", {}, "Speicher"), h("span", { class: "mono" }, bytes(total))),
    h("div", { class: "card" },
      h("div", { class: "bars" }, rows.map((r) => h("div", { class: "bar-row" },
        plate(r.m.label),
        h("div", { class: "name" }, h("span", { class: "truncate" }, r.m.title),
          h("div", { class: "track" }, h("i", { style: { width: `${Math.max(2, (r.size / max) * 100)}%` } }))),
        h("span", { class: "mono", style: { textAlign: "right", color: "var(--text-2)" } }, bytes(r.size))))),
      t.storage.free ? h("div", { class: "bar-foot" },
        `Auf dem Laufwerk sind noch ${bytes(t.storage.free)} von ${bytes(t.storage.capacity)} frei.`) : null));
}

// --- Neue Kurse ---------------------------------------------------------------

function foundPanel(ui, render) {
  const chosen = new Set(ui.found.filter((c) => c.selected).map((c) => c.id));
  const add = async () => {
    const items = ui.found.filter((c) => chosen.has(c.id)).map((c) => ({ ...c, enabled: true }));
    if (!items.length) return;
    if (await saveCourses(items)) {
      ui.found = null;
      toast(`${plural(items.length, "Kurs", "Kurse")} hinzugefügt – beim nächsten Abgleich dabei`);
    }
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
        h("span", { class: "sem mono" }, c.folder));
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
      else if (await saveCourses([{ ...course, enabled: true }])) {
        toast(`${course.display_title} hinzugefügt`);
        ui.linkOpen = false;
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
