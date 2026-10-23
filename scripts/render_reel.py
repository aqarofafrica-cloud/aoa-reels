#!/usr/bin/env python3
"""AQAR OF AFRICA - reel montage from property photos.
Usage: render_reel.py --out reel.mp4 --music track.mp3 [--logo logo.png] img1 img2 ...
Output: 1080x1920 H.264/AAC, ~3.2s per photo, slow zoom, crossfade, end card."""
import argparse, subprocess, os, tempfile, json
from PIL import Image, ImageDraw, ImageFont, ImageFilter

W, H, FPS = 1080, 1920, 30
PER = 3.2          # seconds per photo
XF = 0.6           # crossfade seconds
END = 3.0          # end card seconds
PHONE = "+212 660 96 66 20"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_R = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def frame_from_photo(src, dst):
    """Fit photo on a 9:16 canvas: blurred cover background + sharp contained photo."""
    im = Image.open(src).convert("RGB")
    bg = im.copy()
    s = max(W / bg.width, H / bg.height)
    bg = bg.resize((int(bg.width * s) + 1, int(bg.height * s) + 1))
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    bg = bg.filter(ImageFilter.GaussianBlur(40))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.35)
    s2 = min(W / im.width, H * 0.82 / im.height)
    fg = im.resize((int(im.width * s2), int(im.height * s2)), Image.LANCZOS)
    bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
    # 2x size gives room for a smooth zoom without pixel jitter
    bg.resize((W * 2, H * 2), Image.LANCZOS).save(dst, quality=92)

def end_card(dst, logo=None):
    c = Image.new("RGB", (W, H), (12, 18, 32))
    d = ImageDraw.Draw(c)
    y = 560
    if logo and os.path.exists(logo):
        lg = Image.open(logo).convert("RGBA")
        s = 520 / max(lg.width, lg.height)
        lg = lg.resize((int(lg.width * s), int(lg.height * s)), Image.LANCZOS)
        plate = Image.new("RGBA", (lg.width + 80, lg.height + 80), (255, 255, 255, 255))
        plate.paste(lg, (40, 40), lg)
        c.paste(plate, ((W - plate.width) // 2, 380), plate)
        y = 380 + plate.height + 70
    def ctext(txt, font, yy, fill):
        bw = d.textlength(txt, font=font)
        d.text(((W - bw) / 2, yy), txt, font=font, fill=fill)
    ctext("AQAR OF AFRICA", ImageFont.truetype(FONT_B, 78), y, (255, 255, 255))
    ctext("Martil - Tetouan - Nord du Maroc", ImageFont.truetype(FONT_R, 40), y + 110, (190, 200, 215))
    ctext("WhatsApp / Tel", ImageFont.truetype(FONT_R, 46), y + 260, (37, 211, 102))
    ctext(PHONE, ImageFont.truetype(FONT_B, 92), y + 330, (255, 255, 255))
    c.save(dst, quality=95)

BADGE_W, BADGE_M = 170, 36   # brand watermark: width and margin (px, top-right corner)


def brand_badge(logo, dst, width=BADGE_W):
    """AQAR OF AFRICA logo on a white rounded plate, kept on screen during the whole video (visual identity)."""
    if not logo or not os.path.exists(logo):
        return None
    lg = Image.open(logo).convert("RGBA")
    pad = int(width * 0.08)
    s = (width - 2 * pad) / lg.width
    lg = lg.resize((int(lg.width * s), int(lg.height * s)), Image.LANCZOS)
    h = lg.height + 2 * pad
    plate = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    ImageDraw.Draw(plate).rounded_rectangle([0, 0, width - 1, h - 1], radius=int(width * 0.12), fill=(255, 255, 255, 235))
    plate.alpha_composite(lg, (pad, pad))
    plate.save(dst)
    return dst


def badge_overlay(src_label, idx, until, out_label):
    """ffmpeg filter: put the badge (input #idx) top-right until `until` seconds (the end card has its own big logo)."""
    return (f"[{src_label}][{idx}:v]overlay=x=W-w-{BADGE_M}:y={BADGE_M}:enable='lt(t,{until:.2f})'[{out_label}]")


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--music")
    ap.add_argument("--logo")
    ap.add_argument("images", nargs="+")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp()
    clips = []
    frames = int(PER * FPS)
    for i, src in enumerate(a.images[:10]):
        f = os.path.join(tmp, f"f{i}.jpg"); frame_from_photo(src, f)
        clip = os.path.join(tmp, f"c{i}.mp4")
        zin = i % 2 == 0   # alternate zoom in / zoom out
        z = "min(1+0.0009*on,1.08)" if zin else "max(1.08-0.0009*on,1)"
        run(["ffmpeg", "-y", "-loop", "1", "-i", f, "-vf",
             f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p",
             "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", clip])
        clips.append((clip, PER))
    ec = os.path.join(tmp, "end.jpg"); end_card(ec, a.logo)
    ecl = os.path.join(tmp, "end.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", ec, "-t", str(END), "-r", str(FPS), "-vf", "format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", ecl])
    clips.append((ecl, END))
    # crossfade chain
    inputs, filt, off, last = [], [], 0.0, "0:v"
    for c, _ in clips: inputs += ["-i", c]
    for i in range(1, len(clips)):
        off += clips[i - 1][1] - XF
        out = f"v{i}"
        filt.append(f"[{last}][{i}:v]xfade=transition=fade:duration={XF}:offset={off:.2f}[{out}]")
        last = out
    total = off + clips[-1][1]
    badge = brand_badge(a.logo, os.path.join(tmp, "badge.png"))
    if badge:
        inputs += ["-i", badge]
        filt.append(badge_overlay(last, len(clips), off, "vb"))
        last = "vb"
    video = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filt), "-map", f"[{last}]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS), video])
    if a.music:
        run(["ffmpeg", "-y", "-i", video, "-stream_loop", "-1", "-i", a.music, "-t", f"{total:.2f}",
             "-af", f"afade=t=in:d=1,afade=t=out:st={total-2:.2f}:d=2,volume=0.8",
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
             "-movflags", "+faststart", a.out])
    else:
        run(["ffmpeg", "-y", "-i", video, "-c", "copy", "-movflags", "+faststart", a.out])
    print(json.dumps({"out": a.out, "seconds": round(total, 1), "photos": len(clips) - 1}))

if __name__ == "__main__":
    main()
