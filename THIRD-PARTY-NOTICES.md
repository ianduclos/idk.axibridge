# Third-party notices

Vendored assets shipped inside this repo, with the notices their licences
require. Code dependencies are declared in `pyproject.toml` and are not
vendored — this file covers things copied into the tree.

## Lucide icons — ISC

The canvas toolbar's tool icons (`axibridge/static/index.html`: select, draw,
pen, commit) are Lucide icon path data, inlined as SVG. Inlined rather than
loaded as a sprite or font on purpose: the frontend has no build step, and an
inline `<svg>` inherits `currentColor`, so the toolbar's inverted active state
themes for free. Stroke width and joins are overridden in `style.css`
(`.tool-icon`) — the paths themselves are unmodified.

Icons used: `mouse-pointer-2`, `pencil`, `pen-tool`, `check`.

```
ISC License

Copyright (c) 2026 Lucide Icons and Contributors

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

`check` is among the Lucide icons derived from the Feather project, which is
MIT-licensed:

```
The MIT License (MIT)

Copyright (c) 2013-present Cole Bemis

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## CamBam stick fonts — freeware

The ten TrueType engraving fonts in `axibridge/fonts/stick/`
(`1CamBam_Stick_0.ttf` … `1CAMBam_Stick_9.ttf`) are the CamBam "stick"
(single-line) fonts bundled with the CamBam CAD/CAM application by Andy
Payne / Hexagon. They are distributed as freeware; CamBam's documentation
states they may be used and shared freely. They are vendored here (rather
than referenced from a user font folder) so the text generator works
identically on every machine, including the Pi.

