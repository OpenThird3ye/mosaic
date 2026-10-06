#!/usr/bin/env python3
"""
4K 30fps Video Test Signal Generator — with live display window
No OpenCV required. Uses: pillow, numpy, imageio-ffmpeg, tkinter (built-in)

Install:
    pip install pillow numpy imageio-ffmpeg

Usage:
    python generate_test_signal.py                  # display only
    python generate_test_signal.py --save           # display + save MP4
    python generate_test_signal.py --save --crf 18 --duration 30
    python generate_test_signal.py --no-display --save  # headless encode only

Press  Q  or close the window to quit.
"""

import argparse
import time
import tkinter as tk
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageTk
import imageio_ffmpeg

# ── Configuration ─────────────────────────────────────────────────────────────
SOURCE_W  = 3840   # native resolution of the signal
SOURCE_H  = 2160
FPS       = 30
DURATION_S = 10
OUTPUT    = "test_signal_4k_30fps.mp4"

# Display window – scale down so it fits on screen (change to 1.0 for full 4K)
DISPLAY_SCALE = 0.35   # ~1344×756 preview window

# ── SMPTE 75% colour bars (RGB) ───────────────────────────────────────────────
SMPTE_BARS = [
    (191, 191, 191),  # White 75%
    (191, 191,   0),  # Yellow
    (  0, 191, 191),  # Cyan
    (  0, 191,   0),  # Green
    (191,   0, 191),  # Magenta
    (191,   0,   0),  # Red
    (  0,   0, 191),  # Blue
    (  0,   0,   0),  # Black
]

# ── Static base frame (rendered once) ────────────────────────────────────────

def make_base(W, H):
    arr = np.zeros((H, W, 3), dtype=np.uint8)
    n, bw = len(SMPTE_BARS), W // len(SMPTE_BARS)

    y0, y1 = 0, int(H * 0.55)
    for i, c in enumerate(SMPTE_BARS):
        arr[y0:y1, i*bw : (i*bw+bw if i<n-1 else W)] = c

    y0, y1 = y1, y1 + int(H * 0.08)
    ramp = np.linspace(0, 255, W, dtype=np.uint8)
    arr[y0:y1] = np.stack([ramp, ramp, ramp], axis=-1)[np.newaxis]

    y0, y1 = y1, y1 + int(H * 0.08)
    steps, sw = 11, W // 11
    for i in range(steps):
        v = int(round(i * 255 / (steps - 1)))
        arr[y0:y1, i*sw : (i*sw+sw if i<steps-1 else W)] = (v, v, v)

    y0, y1 = y1, y1 + int(H * 0.06)
    segs, psw = [0, 4, 8, 16, 0, 0, 0, 0], W // 8
    for i, v in enumerate(segs):
        arr[y0:y1, i*psw : (i*psw+psw if i<7 else W)] = (v, v, v)

    img = Image.fromarray(arr, "RGB")
    drw = ImageDraw.Draw(img)
    for pct, col in [(0.90, (80,80,80)), (0.80, (130,130,130))]:
        mx, my = int(W*(1-pct)/2), int(H*(1-pct)/2)
        drw.rectangle([mx, my, W-mx, H-my], outline=col, width=max(2, int(4*W/SOURCE_W)))
    cx, cy = W//2, H//2
    lw = max(2, int(4*W/SOURCE_W))
    drw.line([(cx-100,cy),(cx+100,cy)], fill=(210,210,210), width=lw)
    drw.line([(cx,cy-100),(cx,cy+100)], fill=(210,210,210), width=lw)
    drw.ellipse([cx-70,cy-70,cx+70,cy+70], outline=(210,210,210), width=lw)

    return np.array(img, dtype=np.uint8)


def get_fonts(W):
    scale = W / SOURCE_W
    big_sz, med_sz = max(12, int(72*scale)), max(10, int(56*scale))
    candidates = [
        "C:/Windows/Fonts/courbd.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for path in candidates:
        try:
            return (ImageFont.truetype(path, big_sz),
                    ImageFont.truetype(path, med_sz))
        except (OSError, IOError):
            continue
    f = ImageFont.load_default()
    return f, f


def render_frame(base, frame_no, total, fonts, W, H):
    arr = base.copy()
    x = int((frame_no % FPS) / FPS * W)
    arr[:, max(0,x-3):min(W,x+4)] = (255, 255, 255)

    img = Image.fromarray(arr, "RGB")
    drw = ImageDraw.Draw(img)
    big, med = fonts
    pad = max(10, int(60 * W / SOURCE_W))

    drw.text((pad, pad),
             f"4K UHD  {SOURCE_W}\u00d7{SOURCE_H}  |  {FPS} fps  |  TEST SIGNAL",
             font=big, fill=(240,240,240))
    drw.text((pad, pad + int(90*W/SOURCE_W)),
             "1 kHz Reference Tone  |  \u221220 dBFS",
             font=med, fill=(200,200,200))

    elapsed = frame_no / FPS
    h_, rem = divmod(int(elapsed), 3600)
    m_, s_  = divmod(rem, 60)
    f_      = frame_no % FPS
    tc = f"TC  {h_:02d}:{m_:02d}:{s_:02d}:{f_:02d}    Frame {frame_no:06d}/{total:06d}"
    drw.text((pad, H - pad - int(80*W/SOURCE_W)), tc, font=big, fill=(220,220,220))

    return img   # return PIL Image


# ── Tkinter display loop ──────────────────────────────────────────────────────

class TestSignalApp:
    def __init__(self, root, args):
        self.root    = root
        self.args    = args
        self.running = True
        self.frame_no = 0

        DW = int(SOURCE_W * DISPLAY_SCALE)
        DH = int(SOURCE_H * DISPLAY_SCALE)

        root.title(f"Openthird3ye Video Test — {SOURCE_W}×{SOURCE_H} @ {FPS}fps")
        root.resizable(False, False)
        root.configure(bg="black")
        root.bind("<q>", lambda e: self.quit())
        root.bind("<Q>", lambda e: self.quit())
        root.protocol("WM_DELETE_WINDOW", self.quit)

        self.canvas = tk.Canvas(root, width=DW, height=DH,
                                bg="black", highlightthickness=0)
        self.canvas.pack()

        lbl = tk.Label(root,
                       text=f"Source: {SOURCE_W}×{SOURCE_H}  |  Display: {DW}×{DH}  "
                            f"|  {FPS} fps   [Press Q to quit]",
                       fg="#aaa", bg="black", font=("Courier", 11))
        lbl.pack(pady=(4, 6))

        # Build assets at display resolution
        print(f"Building base frame at display resolution ({DW}×{DH})…", flush=True)
        self.disp_base  = make_base(DW, DH)
        self.disp_fonts = get_fonts(DW)
        self.DW, self.DH = DW, DH

        # Build assets at source resolution if saving
        self.writer = None
        if args.save:
            total_src = args.duration * FPS
            print(f"Building base frame at source resolution ({SOURCE_W}×{SOURCE_H})…", flush=True)
            self.src_base  = make_base(SOURCE_W, SOURCE_H)
            self.src_fonts = get_fonts(SOURCE_W)
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            print(f"Opening encoder → {args.output}  (FFmpeg: {ffmpeg})")
            self.writer = imageio_ffmpeg.write_frames(
                args.output,
                size=(SOURCE_W, SOURCE_H),
                fps=FPS,
                codec="libx264",
                pix_fmt_in="rgb24",
                pix_fmt_out="yuv420p",
                output_params=["-crf", str(args.crf), "-preset", "fast"],
            )
            self.writer.send(None)

        self.total      = args.duration * FPS if args.save else 10**9
        self.t_start    = time.perf_counter()
        self.tk_img     = None

        # Kick off the loop
        self.root.after(0, self.next_frame)

    # ── frame tick ──────────────────────────────────────────────────────────
    def next_frame(self):
        if not self.running:
            return

        fn = self.frame_no

        # --- display frame (scaled resolution) ---
        disp_img = render_frame(self.disp_base, fn, self.total,
                                self.disp_fonts, self.DW, self.DH)
        self.tk_img = ImageTk.PhotoImage(disp_img)
        self.canvas.create_image(0, 0, anchor="nw", image=self.tk_img)

        # --- encode frame at full 4K resolution ---
        if self.writer:
            src_img = render_frame(self.src_base, fn, self.total,
                                   self.src_fonts, SOURCE_W, SOURCE_H)
            self.writer.send(src_img.tobytes())

        self.frame_no += 1

        # Stop saving after requested duration, but keep displaying
        if self.args.save and fn + 1 >= self.total:
            self.writer.close()
            self.writer = None
            print(f"\nSaved {self.total} frames → {self.args.output}")
            self.total = 10**9   # keep displaying indefinitely

        # Schedule next frame to maintain ~FPS
        elapsed   = time.perf_counter() - self.t_start
        ideal_ms  = int(self.frame_no * 1000 / FPS)
        actual_ms = int(elapsed * 1000)
        delay     = max(1, ideal_ms - actual_ms)
        self.root.after(delay, self.next_frame)

    def quit(self):
        self.running = False
        if self.writer:
            try:
                self.writer.close()
            except Exception:
                pass
        self.root.destroy()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global DISPLAY_SCALE

    parser = argparse.ArgumentParser(description="4K 30fps video test signal.")
    parser.add_argument("--save",       action="store_true",
                        help="Also encode and save an MP4 file")
    parser.add_argument("--output",     default=OUTPUT)
    parser.add_argument("--duration",   type=int, default=DURATION_S,
                        help=f"Seconds to save (default {DURATION_S}; display runs until closed)")
    parser.add_argument("--crf",        type=int, default=23,
                        help="H.264 CRF quality 0=lossless...51=worst (default 23)")
    parser.add_argument("--scale",      type=float, default=DISPLAY_SCALE,
                        help=f"Display window scale 0.0-1.0 (default {DISPLAY_SCALE})")
    args = parser.parse_args()

    DISPLAY_SCALE = args.scale

    root = tk.Tk()
    app  = TestSignalApp(root, args)
    root.mainloop()


if __name__ == "__main__":
    main()
