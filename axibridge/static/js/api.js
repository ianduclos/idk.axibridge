// Thin API client + SSE subscription. All server errors are normalised to
// thrown Error(detail) so panels can toast them uniformly.

async function req(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

export const api = {
  get: (url) => req("GET", url),
  post: (url, body) => req("POST", url, body),
  put: (url, body) => req("PUT", url, body),
  patch: (url, body) => req("PATCH", url, body),
  del: (url) => req("DELETE", url),
  upload: async (url, formData) => {
    const res = await fetch(url, { method: "POST", body: formData });
    if (!res.ok) {
      let detail = res.statusText;
      try { detail = (await res.json()).detail || detail; } catch {}
      throw new Error(detail);
    }
    return res.json();
  },
};

// SSE: EventSource auto-reconnects; onReconnect lets main.js re-hydrate
// from /api/state after a dropped connection (e.g. laptop slept).
export function subscribe(onEvent, onReconnect) {
  let dropped = false;
  const es = new EventSource("/api/events");
  es.onmessage = (e) => onEvent(JSON.parse(e.data));
  es.onerror = () => { dropped = true; };
  es.onopen = () => { if (dropped) { dropped = false; onReconnect(); } };
  return es;
}
