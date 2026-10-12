// Thin API client + SSE subscription. All server errors are normalised to
// thrown Error(detail) so panels can toast them uniformly.

// Per-tab identity for live sync: the server echoes it as a project event's
// `origin`, so a tab can skip changes it made itself. Deliberately NOT
// the Web Crypto UUID helper — that only exists in secure contexts, and the app is
// also opened over plain http from other machines on the LAN.
export const CLIENT_ID = `tab-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

// Mutating requests this tab has in flight. Live sync waits for them to
// settle before refetching, so an external refresh never interleaves with
// this tab's own edit sequence.
let mutationsInFlight = 0;
const idleListeners = new Set();
export const mutationsPending = () => mutationsInFlight;
export function onMutationsIdle(fn) { idleListeners.add(fn); }
function settle(mutating) {
  if (mutating && --mutationsInFlight === 0) idleListeners.forEach((fn) => fn());
}

async function req(method, url, body, requestOpts = {}) {
  const opts = { method, headers: { "X-Axb-Client": CLIENT_ID }, signal: requestOpts.signal };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const mutating = method !== "GET";
  if (mutating) mutationsInFlight++;
  try {
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
  } finally {
    settle(mutating);
  }
}

export const api = {
  get: (url, opts) => req("GET", url, undefined, opts),
  post: (url, body, opts) => req("POST", url, body, opts),
  put: (url, body, opts) => req("PUT", url, body, opts),
  patch: (url, body, opts) => req("PATCH", url, body, opts),
  del: (url, opts) => req("DELETE", url, undefined, opts),
  upload: async (url, formData) => {
    mutationsInFlight++;
    try {
      const res = await fetch(url, { method: "POST", body: formData,
                                     headers: { "X-Axb-Client": CLIENT_ID } });
      if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch {}
        throw new Error(detail);
      }
      return res.json();
    } finally {
      settle(true);
    }
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
