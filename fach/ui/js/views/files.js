// Dateien: ein Explorer für den Uni-Ordner. Doppelklick öffnet mit dem Standardprogramm (PDF → dein
// PDF-Programm), Rechtsklick bietet Öffnen mit, Kopieren, Umbenennen, Papierkorb. Ziehen gibt Dateien als
// Kopie an andere Programme – z. B. eine Vorlesung in einen KI-Chat im Browser.
import { api } from "../api.js";
import { confirmDialog, h, icon, menuAt, mount, toast } from "../dom.js";
import { bytes, plural, when } from "../format.js";
import { store } from "../store.js";

const collator = new Intl.Collator("de", { numeric: true, sensitivity: "base" });

export function mountFiles(el) {
  const st = {
    path: store.ui.filesPath || "", data: null, error: "", sel: new Set(), anchor: null, renaming: null,
    sort: { key: "name", dir: 1 }, q: "", results: null,
  };
  let alive = true;

  const load = async (path = st.path) => {
    try {
      const data = await api.get(`/api/files?path=${encodeURIComponent(path)}`);
      if (!alive) return;
      st.data = data; st.path = data.path; st.error = ""; store.ui.filesPath = data.path;
      st.sel = new Set([...st.sel].filter((r) => data.items.some((i) => i.rel === r)));
    } catch (e) {
      st.error = e.message;
      if (path) return load("");
    }
    render();
  };

  const items = () => {
    const list = st.results ?? st.data?.items ?? [];
    const { key, dir } = st.sort;
    return [...list].sort((a, b) => (st.results ? 0 : Number(b.dir) - Number(a.dir))
      || (key === "name" ? collator.compare(a.name, b.name) : (a[key] ?? 0) - (b[key] ?? 0)) * dir);
  };

  const go = (path) => { st.sel.clear(); st.anchor = null; st.q = ""; st.results = null; load(path); };
  const selected = () => items().filter((i) => st.sel.has(i.rel));

  // --- Aktionen -------------------------------------------------------------
  const open = async (item) => {
    if (item.dir) { go(item.rel); return; }
    try {
      const res = await api.post("/api/files/open", { rels: [item.rel] });
      if (res.revealed) toast("Programme öffnet Fach nicht direkt – im Ordner gezeigt", "alert");
      if (item.new) { item.new = false; render(); }
    } catch (e) { toast(e.message, "alert"); }
  };
  const post = (path, body, ok) => api.post(path, body).then((r) => { if (ok) toast(ok); return r; }).catch((e) => { toast(e.message, "alert"); return null; });
  const copy = (list) => post("/api/files/copy", { rels: list.map((i) => i.rel) },
    list.length === 1 ? "Kopiert – einfügen mit Strg V" : `${list.length} Dateien kopiert – einfügen mit Strg V`);
  const copyPath = async (item) => {
    const root = st.data?.root || "";
    const sep = root.includes("\\") ? "\\" : "/";
    try { await navigator.clipboard.writeText(`${root}${sep}${item.rel.split("/").join(sep)}`); toast("Pfad kopiert"); }
    catch { toast("Pfad konnte nicht kopiert werden", "alert"); }
  };
  const trash = async (list) => {
    if (!list.length) return;
    const one = list.length === 1;
    const ok = await confirmDialog({
      title: one ? `„${list[0].name}“ in den Papierkorb?` : `${list.length} Elemente in den Papierkorb?`,
      text: "Du kannst es aus dem Papierkorb zurückholen. Kommt die Datei aus ILIAS, lädt Fach sie danach nicht erneut herunter.",
      ok: "In den Papierkorb", danger: true });
    if (!ok) return;
    if (await post("/api/files/trash", { rels: list.map((i) => i.rel), keep_away: true }, one ? "In den Papierkorb verschoben" : `${list.length} Elemente im Papierkorb`)) {
      st.sel.clear(); load();
    }
  };
  const rename = async (item, name) => {
    st.renaming = null;
    if (!name || name === item.name) { render(); return; }
    const res = await post("/api/files/rename", { rel: item.rel, name });
    if (res) {
      toast("Umbenannt – Fach merkt sich den neuen Namen");
      st.sel = new Set([res.rel]);
      if (st.results) { st.q = ""; st.results = null; }
      load();
    } else render();
  };

  const contextMenu = (e, item) => {
    e.preventDefault();
    if (item && !st.sel.has(item.rel)) { st.sel = new Set([item.rel]); st.anchor = item.rel; render(); }
    const list = selected();
    if (!list.length) return;
    const single = list.length === 1 ? list[0] : null;
    const protectedItem = list.some((i) => i.protected);
    menuAt(e.clientX, e.clientY, [
      { label: single?.dir ? "Öffnen" : "Öffnen", icon: single?.dir ? "folderOpen" : "external", hint: "Enter", onClick: () => list.slice(0, 10).forEach(open) },
      { label: "Öffnen mit …", icon: "external", disabled: !single || single.dir, onClick: () => post("/api/files/open-with", { rel: single.rel }) },
      { label: (store.state?.app.platform || "").startsWith("macos") ? "Im Finder zeigen" : "Im Explorer zeigen", icon: "folder", onClick: () => post("/api/files/reveal", { rel: list[0].rel }) },
      "-",
      { label: "Kopieren", icon: "file", hint: "Strg C", onClick: () => copy(list) },
      { label: "Pfad kopieren", icon: "link", disabled: !single, onClick: () => copyPath(single) },
      "-",
      { label: "Umbenennen", icon: "pencil", hint: "F2", disabled: !single || protectedItem, onClick: () => { st.renaming = single.rel; render(); } },
      { label: "In den Papierkorb", icon: "trash", hint: "Entf", danger: true, disabled: protectedItem, onClick: () => trash(list) },
    ]);
  };

  // --- Auswahl ---------------------------------------------------------------
  const click = (e, item) => {
    if (e.shiftKey && st.anchor) {
      const list = items();
      const a = list.findIndex((i) => i.rel === st.anchor);
      const b = list.findIndex((i) => i.rel === item.rel);
      st.sel = new Set(list.slice(Math.min(a, b), Math.max(a, b) + 1).map((i) => i.rel));
    } else if (e.ctrlKey || e.metaKey) {
      st.sel.has(item.rel) ? st.sel.delete(item.rel) : st.sel.add(item.rel);
      st.anchor = item.rel;
    } else {
      st.sel = new Set([item.rel]);
      st.anchor = item.rel;
    }
    render();
  };

  // Ziehen nach außen: erst nach ein paar Pixeln Bewegung, dann übernimmt Windows (Kopie)
  let press = null;
  const onDown = (e, item) => {
    if (e.button !== 0 || st.renaming) return;
    press = { x: e.clientX, y: e.clientY, item, started: false };
  };
  const onMove = (e) => {
    if (!press || press.started || !(e.buttons & 1)) return;
    if (Math.abs(e.clientX - press.x) + Math.abs(e.clientY - press.y) < 6) return;
    press.started = true;
    if (!st.data?.drag) return;
    if (!st.sel.has(press.item.rel)) { st.sel = new Set([press.item.rel]); render(); }
    api.post("/api/files/drag", { rels: selected().map((i) => i.rel) }).catch(() => {});
  };
  const onUp = () => { setTimeout(() => { press = null; }, 0); };

  const onKey = (e) => {
    if (!el.isConnected || e.target.matches("input") || document.querySelector(".dialog-backdrop, .menu")) return;
    const list = items();
    const idx = list.findIndex((i) => i.rel === st.anchor);
    const ctrl = e.ctrlKey || e.metaKey;
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = list[Math.max(0, Math.min(list.length - 1, idx + (e.key === "ArrowDown" ? 1 : -1)))];
      if (next) { st.sel = new Set([next.rel]); st.anchor = next.rel; render(); el.querySelector(".frow.sel")?.scrollIntoView({ block: "nearest" }); }
    } else if (e.key === "Enter" && selected().length) {
      e.preventDefault(); selected().slice(0, 10).forEach(open);
    } else if ((e.key === "Backspace" || (e.altKey && e.key === "ArrowUp")) && st.path) {
      e.preventDefault(); go(st.path.split("/").slice(0, -1).join("/"));
    } else if (e.key === "F2" && selected().length === 1) {
      e.preventDefault(); st.renaming = selected()[0].rel; render();
    } else if (e.key === "Delete" && selected().length) {
      e.preventDefault(); trash(selected());
    } else if (ctrl && e.key.toLowerCase() === "c" && selected().length) {
      e.preventDefault(); copy(selected());
    } else if (ctrl && e.key.toLowerCase() === "a") {
      e.preventDefault(); st.sel = new Set(list.map((i) => i.rel)); render();
    }
  };
  document.addEventListener("keydown", onKey);
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);

  // --- Suche --------------------------------------------------------------------
  let searchTimer = 0;
  const search = (q) => {
    st.q = q;
    clearTimeout(searchTimer);
    if (q.trim().length < 2) { st.results = null; render(); return; }
    searchTimer = setTimeout(async () => {
      try { st.results = (await api.get(`/api/files/search?q=${encodeURIComponent(q.trim())}`)).items; st.sel.clear(); render(); }
      catch (e) { toast(e.message, "alert"); }
    }, 220);
  };

  // --- Darstellung --------------------------------------------------------------
  function render() {
    if (!alive) return;
    const searchInput = h("input", { class: "input", type: "text", placeholder: "Im Uni-Ordner suchen", value: st.q, "aria-label": "Dateien suchen" });
    searchInput.addEventListener("input", () => search(searchInput.value));
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Escape") { searchInput.value = ""; search(""); searchInput.blur(); } });
    const hadFocus = document.activeElement?.closest?.(".files-search");

    const parts = st.path ? st.path.split("/") : [];
    const crumbs = h("nav", { class: "crumbs", "aria-label": "Pfad" },
      h("button", { onclick: () => go("") }, "Uni"),
      parts.map((p, i) => [h("span", { class: "sep" }, icon("chevronRight", 14)),
        h("button", { onclick: () => go(parts.slice(0, i + 1).join("/")) }, p)]));

    const list = items();
    const sortBtn = (key, label, right) => h("button", { class: right ? "r" : "", onclick: () => {
      st.sort = { key, dir: st.sort.key === key ? -st.sort.dir : (key === "name" ? 1 : -1) }; render();
    } }, label, st.sort.key === key ? (st.sort.dir === 1 ? " ↑" : " ↓") : "");

    const rows = list.map((item) => {
      const sel = st.sel.has(item.rel);
      let name;
      if (st.renaming === item.rel) {
        const input = h("input", { class: "input sm rename", type: "text", value: item.name, "aria-label": "Neuer Name" });
        let done = false;
        const finish = (save) => { if (done) return; done = true; save ? rename(item, input.value.trim()) : (st.renaming = null, render()); };
        input.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
        input.addEventListener("blur", () => finish(true));
        input.addEventListener("mousedown", (e) => e.stopPropagation());
        setTimeout(() => { input.focus(); const dot = item.dir ? -1 : item.name.lastIndexOf("."); input.setSelectionRange(0, dot > 0 ? dot : item.name.length); }, 0);
        name = input;
      } else {
        name = h("span", { class: "n" }, h("span", { class: item.new ? "marked" : "" }, item.name));
      }
      const ext = (item.ext || "").slice(0, 4);
      return h("div", {
        class: `frow ${sel ? "sel" : ""}`, role: "row", "aria-selected": sel ? "true" : "false",
        onmousedown: (e) => onDown(e, item),
        onclick: (e) => { if (press?.started) return; click(e, item); },
        ondblclick: () => open(item),
        oncontextmenu: (e) => contextMenu(e, item),
        title: item.risky ? "Programm – Fach zeigt es nur im Ordner, statt es zu starten" : null,
      },
      item.dir ? icon(item.protected ? "book" : "folder", 16) : h("span", { class: "ftype" }, ext || "–"),
      h("span", { class: "fname" }, name,
        item.dir && st.renaming !== item.rel ? h("span", { class: "parent" }, plural(item.items || 0, "Datei", "Dateien")) : null,
        st.results && item.parent ? h("span", { class: "parent" }, item.parent) : null),
      h("span", { class: "fmeta r" }, bytes(item.size)),
      h("span", { class: "fmeta r" }, when(item.mtime * 1000)));
    });

    const total = list.reduce((n, i) => n + (i.size || 0), 0);
    const sel = selected();
    const selSize = sel.reduce((n, i) => n + (i.size || 0), 0);
    const body = st.error && !st.data
      ? h("div", { class: "empty" }, h("h3", {}, "Ordner nicht erreichbar"), h("p", {}, st.error))
      : !st.data ? h("div", { class: "skeleton", style: { height: "200px", margin: "12px" } })
        : rows.length ? h("div", { class: "files-list", role: "rowgroup" }, rows)
          : h("div", { class: "empty" }, h("h3", {}, st.results ? "Nichts gefunden" : "Dieser Ordner ist leer"),
            h("p", {}, st.results ? "Gesucht wird in allen Dateinamen im Uni-Ordner." : ""));

    mount(el, h("div", { class: "page" },
      h("header", { class: "page-head" }, h("div", {}, h("h1", {}, "Dateien"),
        h("p", { class: "meta" }, st.data?.drag
          ? "Doppelklick öffnet mit deinem Standardprogramm. Ziehen kopiert Dateien in andere Programme."
          : "Doppelklick öffnet mit deinem Standardprogramm. Rechtsklick für mehr."))),
      h("div", { class: "files-bar" },
        st.results ? h("div", { class: "crumbs" }, h("span", { style: { fontWeight: 500 } }, `Suche nach „${st.q.trim()}“`)) : crumbs,
        h("div", { class: "files-search" }, icon("search", 16), searchInput)),
      h("div", { class: "card ftable", role: "grid", oncontextmenu: (e) => { if (e.target.closest(".frow")) return; e.preventDefault(); } },
        h("div", { class: "fhead", role: "row" }, h("span"), sortBtn("name", "Name"), sortBtn("size", "Größe", true), sortBtn("mtime", "Geändert", true)),
        body,
        h("div", { class: "files-foot" },
          h("span", {}, sel.length ? `${sel.length} ausgewählt${selSize ? ` · ${bytes(selSize)}` : ""}` : `${plural(list.length, "Element", "Elemente")}${total ? ` · ${bytes(total)}` : ""}`),
          h("span", {}, "Enter öffnen · F2 umbenennen · Entf Papierkorb · Strg C kopieren")))));
    if (hadFocus) { const i = el.querySelector(".files-search input"); i?.focus(); i?.setSelectionRange(i.value.length, i.value.length); }
  }

  render();
  load();
  return () => {
    alive = false;
    document.removeEventListener("keydown", onKey);
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
}
