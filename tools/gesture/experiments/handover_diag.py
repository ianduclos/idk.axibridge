"""handover (round 13, II-b): diagnostic render — the line coloured by stage (how many features are B's)."""
import sys
sys.path.insert(0, "tools/gesture")
import numpy as np
from PIL import Image, ImageDraw
from gesture import kit
from gesture.kit.core import PAPER

# Flexoki 600 accents (axibridge/static/css/flexoki.css): stage 0 black, then red, orange, green, blue
STAGE_COL = [(0x10, 0x0F, 0x0F), (0xAF, 0x30, 0x29), (0xBC, 0x52, 0x15), (0x66, 0x80, 0x0B), (0x20, 0x5E, 0xA6)]


def stage_image(sheet, px_per_mm=4.0, pen=0.35, ss=2, chan="stage", label=None):
    W, H = sheet.frame
    k = px_per_mm * ss
    im = Image.new("RGB", (int(W * k), int(H * k)), PAPER)
    dr = ImageDraw.Draw(im)
    for m in sheet.marks:
        st = m.channels[chan].astype(int)
        q = m.points * k
        cut = np.r_[0, np.nonzero(np.diff(st))[0] + 1, len(st)]
        for a, b in zip(cut[:-1], cut[1:]):
            seg = q[max(a - 1, 0):b]
            if len(seg) >= 2:
                dr.line([tuple(v) for v in seg], fill=STAGE_COL[min(st[a], 4)], width=max(int(pen * k), 1),
                        joint="curve")
    im = im.resize((im.width // ss, im.height // ss), Image.Resampling.LANCZOS)
    if label:
        from gesture.kit.core import _font
        full = Image.new("RGB", (im.width, im.height + 30), PAPER)
        full.paste(im, (0, 0))
        ImageDraw.Draw(full).text((8, im.height + 6), label, fill=(0x10, 0x0F, 0x0F), font=_font(16))
        return full
    return im


if __name__ == "__main__":
    import json
    rec = json.loads(open(sys.argv[1]).read())
    sh = kit.run(rec)
    stage_image(sh, label=rec.get("label")).save(sys.argv[2], quality=85)
