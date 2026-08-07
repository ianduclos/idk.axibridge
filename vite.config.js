// Build config for the frontend. The SOURCE stays exactly where it has always
// been (`axibridge/static/`) — this slice's whole claim is that nothing moved
// except the build — and the bundle lands beside it in `axibridge/static_dist/`.
//
// The server picks between the two by one rule, written down in app.py: it
// serves the built output when it exists, and the source when it does not.
// That fallback is what keeps a machine with no Node toolchain (the Pi)
// working exactly as it did before there was a build step.
//
// `npm run dev` is the edit-reload loop: Vite serves the source with HMR and
// proxies /api (including the SSE stream) to a real axibridge on 2942.
import { defineConfig } from "vite";

export default defineConfig({
  root: "axibridge/static",
  base: "/",
  build: {
    // outside `root`, so Vite needs telling it may empty it
    outDir: "../static_dist",
    emptyOutDir: true,
    sourcemap: true,
    // the app is served from a fixed origin by our own FastAPI; no CDN, no
    // legacy targets — this is what the browsers on Ian's bench support
    target: "es2022",
  },
  server: {
    proxy: {
      // SSE included: it is plain HTTP under /api, so it needs no special
      // casing — but it must NOT be buffered, hence ws:false and no rewrite
      "/api": {
        target: "http://127.0.0.1:2942",
        changeOrigin: false,
      },
    },
  },
});
