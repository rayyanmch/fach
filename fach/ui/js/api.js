// Verbindung zum lokalen Fach-Server. Der Token kommt einmalig über die Adresse (#t=…)
// und lebt danach nur im sessionStorage dieses Fensters.

const KEY = "fach-token";

function readToken() {
  const m = location.hash.match(/[#&]t=([^&]+)/);
  if (m) {
    const t = decodeURIComponent(m[1]);
    try { sessionStorage.setItem(KEY, t); } catch {}
    history.replaceState(null, "", location.pathname + location.search);
    return t;
  }
  try { return sessionStorage.getItem(KEY) || ""; } catch { return ""; }
}

const token = readToken();

export class ApiError extends Error {
  constructor(status, code, message) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { "X-Fach-Token": token, ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "network", "Fach antwortet nicht. Läuft die App noch?");
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, data?.error || "error", data?.message || "Das hat nicht geklappt.");
  return data;
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b = {}) => request("POST", p, b),
  put: (p, b = {}) => request("PUT", p, b),
  del: (p) => request("DELETE", p),
  hasToken: () => Boolean(token),
};

// Server-Sent Events mit automatischem Wiederverbinden (macht EventSource selbst).
export function listen(onEvent, onStatus) {
  const es = new EventSource(`/api/events?token=${encodeURIComponent(token)}`);
  es.onmessage = (e) => {
    try { onEvent(JSON.parse(e.data)); } catch {}
  };
  es.onopen = () => onStatus?.(true);
  es.onerror = () => onStatus?.(false);
  return () => es.close();
}
