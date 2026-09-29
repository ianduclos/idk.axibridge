# Territory bench (29 September 2026)

The meander prototype (Version 10) ported into axibridge as a bench: Generate → Territory → Bench. See `docs/MODULES.md` "Client-engine benches".

The screenshots come from a temporary test server with the simulator:
- `bench-1440.png`, `bench-1280.png`, `bench-1100.png`: seed 13 with the Version 10 max recipe pasted in;
- `bench-1280-compose.png`: the kept layer in Compose. The bed shows in portrait because of that config; the rotation is display-only.

What was verified on screen: engine parity with the prototype, the built and the source-only frontends, Keep → layer, Resume, locks, Back and paste. Nothing was plotted.

A Sonnet usability pass led to:
- the pinned seed header with a shadow;
- the shorter "Surprise" label and the lock hint;
- the labelled seed strip with the current seed highlighted;
- key hints in the bottom bar.

Skipped from that pass:
- hiding the host's "Stop plot" (shared host chrome);
- collapsing the dial notes, which were kept for clarity.
