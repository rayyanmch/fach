// Deutsche Formatierung: Zeiten, Daten, Mengen. Eine Stelle für alle Texte mit Zahlen.

const DAY = 86400000;
const weekday = new Intl.DateTimeFormat("de-DE", { weekday: "long" });
const dayMonth = new Intl.DateTimeFormat("de-DE", { day: "numeric", month: "long" });
const shortDate = new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit" });
const timeFmt = new Intl.DateTimeFormat("de-DE", { hour: "2-digit", minute: "2-digit" });
const monthShort = new Intl.DateTimeFormat("de-DE", { month: "short" });

const startOfDay = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

export function dayLabel(ts) {
  const d = new Date(ts);
  const diff = Math.round((startOfDay(new Date()) - startOfDay(d)) / DAY);
  if (diff === 0) return "Heute";
  if (diff === 1) return "Gestern";
  if (diff < 7) return weekday.format(d);
  return `${weekday.format(d)}, ${dayMonth.format(d)}`;
}

export const clock = (ts) => timeFmt.format(new Date(ts));
export const ddmm = (ts) => shortDate.format(new Date(ts));
export const month = (ts) => monthShort.format(new Date(ts)).replace(".", "");

// „vor 5 Min.“, „heute 07:12“, „gestern 07:12“, „Mo 07:12“, „02.11.“
export function when(ts) {
  if (!ts) return "noch nie";
  const d = new Date(ts);
  const mins = Math.round((Date.now() - ts) / 60000);
  if (mins < 1) return "gerade eben";
  if (mins < 60) return `vor ${mins} Min.`;
  const diff = Math.round((startOfDay(new Date()) - startOfDay(d)) / DAY);
  if (diff === 0) return `heute ${clock(ts)}`;
  if (diff === 1) return `gestern ${clock(ts)}`;
  if (diff < 7) return `${weekday.format(d).slice(0, 2)} ${clock(ts)}`;
  return ddmm(ts);
}

// Nächster Termin: „heute 18:00“, „morgen 07:00“, „Mo 07:00“
export function upcoming(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = Math.round((startOfDay(d) - startOfDay(new Date())) / DAY);
  if (diff === 0) return `heute ${clock(d)}`;
  if (diff === 1) return `morgen ${clock(d)}`;
  return `${weekday.format(d).slice(0, 2)} ${clock(d)}`;
}

export function plural(n, one, many) {
  return `${n.toLocaleString("de-DE")} ${n === 1 ? one : many}`;
}

export function duration(sec) {
  if (sec < 60) return `${Math.max(1, Math.round(sec))} s`;
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return s ? `${m} min ${s} s` : `${m} min`;
}

export function bytes(n) {
  if (n < 1024 * 1024) return `${Math.max(1, Math.round(n / 1024))} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toLocaleString("de-DE", { maximumFractionDigits: 0 })} MB`;
  return `${(n / 1024 ** 3).toLocaleString("de-DE", { maximumFractionDigits: 1 })} GB`;
}

// Pfad hübsch kürzen: /Users/x/Documents/Uni → ~/Documents/Uni, C:\Users\x\Documents\Uni → Dokumente\Uni
export function prettyPath(p) {
  if (!p) return "";
  return p
    .replace(/^[A-Za-z]:\\Users\\[^\\]+\\(OneDrive[^\\]*\\)?Documents/, "Dokumente")
    .replace(/^\/Users\/[^/]+\/Documents/, "Dokumente")
    .replace(/^\/Users\/[^/]+/, "~");
}

export const DAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];
