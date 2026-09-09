// Thin API client + SSE subscription. All server errors are normalised to
// thrown Error(detail) so panels can toast them uniformly.

async function req(method, url, body, requestOpts = {}) {
  const opts = { method, headers: {}, signal: requestOpts.signal };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch {}
    const payload = typeof detail === "object" && detail ? detail : null;
    const error = new Error(payload?.message || detail);
    error.code = payload?.code;
    error.status = res.status;
    throw error;
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("json") ? res.json() : res.text();
}

export const api = {
  get: (url, opts) => req("GET", url, undefined, opts),
  post: (url, body, opts) => req("POST", url, body, opts),
  put: (url, body, opts) => req("PUT", url, body, opts),
  patch: (url, body, opts) => req("PATCH", url, body, opts),
  del: (url, opts) => req("DELETE", url, undefined, opts),
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
