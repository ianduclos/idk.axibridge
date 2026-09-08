# Ribbon stress sweep

Baseline commit: `6617aed`. Final run included the working-tree loop fixture tangent/density correction. Run with `node stress-check.cjs`; the parent process enforces a fixed 240-second timeout.

The sweep exercises all six study fixtures plus short, repeated-point, multi-corner zigzag, reversed, and near-180-degree paths. It uses 156 deliberately interleaved configurations spanning widths 5/24/90, wavelengths 45/180/240, seeds 0/7/43, steps 1/10/32, all three side relations, and a bounded masked subset in both passage orders. This is broad coverage without a Cartesian explosion.

Each configuration checks for exceptions, input mutation, malformed or non-finite coordinates. Every unmasked strand must retain the source endpoints exactly. A sampled subset is regenerated and compared byte for byte. Masked runs may split or fully hide strands, so endpoint preservation is intentionally not asserted there. The sweep does not require globally crossing-free hairpins; that is outside the prototype's stated boundary.

Final result: all 156 configurations passed in 14.0 seconds of measured generation time (15.3 seconds wall time). This covered 52 masked configurations, 15 byte-for-byte determinism reruns, and 1,445,115 generated strand points.

The slowest case was the reversed zigzag at width 90, wavelength 240, seed 43, 32 steps, independent sides, mask off: 1.75 seconds. Its forward counterpart took 1.57 seconds. The largest masked result was the reversed near-180 path at width 5, wavelength 180, seed 43, 32 steps, mirrored sides, forward mask order: 254 visible fragments. This is a complexity boundary rather than a correctness failure, but it is the clearest case to watch if fragment count becomes operationally important.

No crash, non-finite coordinate, endpoint, determinism, or purity failure was found. The result makes no claim that tight hairpins are globally crossing-free.
