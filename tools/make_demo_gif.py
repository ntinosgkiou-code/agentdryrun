"""Re-creates docs/assets/demo.gif from the REAL output of `python -m agentdryrun demo`.

Optional developer tool (needs Pillow: pip install pillow). Nothing in the verifier or the shadow report needs it.
The text in the GIF is whatever the command printed when you ran this script; only the typing speed is staged.

    python tools/make_demo_gif.py
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "assets", "demo.gif")
COMMAND = "python -m agentdryrun demo"

FONT_DIRS = ["C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/System/Library/Fonts", "/Library/Fonts"]
REGULAR = ["consola.ttf", "DejaVuSansMono.ttf", "Menlo.ttc"]
BOLD = ["consolab.ttf", "DejaVuSansMono-Bold.ttf", "Menlo.ttc"]

BG, FG, DIM = (13, 17, 23), (201, 209, 217), (125, 133, 144)
GREEN, RED, BLUE = (63, 185, 80), (248, 81, 73), (88, 166, 255)
W, PAD, LH, SIZE = 1060, 28, 23, 16


def load_font(names):
    for d in FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return ImageFont.truetype(p, SIZE)
    sys.exit("no monospace font found; edit FONT_DIRS in tools/make_demo_gif.py")


def real_output():
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONPATH=ROOT)
    with tempfile.TemporaryDirectory() as d:
        p = subprocess.run([sys.executable, "-m", "agentdryrun", "demo"], cwd=d, env=env, capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            sys.exit("the demo did not finish as expected:\n" + p.stdout + p.stderr)
        return p.stdout.rstrip("\n").splitlines()


def style(line):
    if line.startswith("RESULT: VERIFIED") or line.startswith("As expected"):
        return GREEN, True
    if line.startswith("RESULT: FAILED") or line.startswith("PROBLEM"):
        return RED, line.startswith("RESULT")
    if line.startswith("["):
        return BLUE, True
    if line.startswith("agentdryrun demo"):
        return DIM, False
    return FG, False


def main():
    reg, bold = load_font(REGULAR), load_font(BOLD)
    lines = real_output()
    rows = len(lines) + 3
    H = PAD * 2 + 20 + rows * LH

    def frame(typed, shown):
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
            d.ellipse((PAD + i * 22, 14, PAD + i * 22 + 12, 26), fill=c)
        y = 20 + PAD
        d.text((PAD, y), "$ ", font=reg, fill=GREEN)
        d.text((PAD + 20, y), COMMAND[:typed], font=reg, fill=FG)
        y += LH * 2
        for ln in lines[:shown]:
            col, b = style(ln)
            d.text((PAD, y), ln, font=bold if b else reg, fill=col)
            y += LH
        return im

    frames, durs = [], []
    for n in range(0, len(COMMAND) + 1, 3):
        frames.append(frame(n, 0)); durs.append(60)
    frames.append(frame(len(COMMAND), 0)); durs.append(500)
    for k in range(1, len(lines) + 1):
        ln = lines[k - 1]
        frames.append(frame(len(COMMAND), k))
        durs.append(1000 if ln.startswith("RESULT") else 450 if ln.startswith("[") else 110)
    durs[-1] = 5000

    pal = frames[-1].quantize(colors=64, method=Image.Quantize.MEDIANCUT)
    frames = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durs, loop=0, optimize=True, disposal=1)
    print(f"wrote {OUT}  ({os.path.getsize(OUT) // 1024} KB, {len(frames)} frames, {W}x{H})")


if __name__ == "__main__":
    main()
