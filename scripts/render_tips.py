#!/usr/bin/env python3
"""AQAR OF AFRICA - advice content (tips) from one Claude plan.

Usage: render_tips.py --plan plan.json --out DIR [--logo logo.png] [--music track.mp3]
Plan: {"title": "...", "subtitle": "...", "tips": [{"heading": "...", "body": "..."}], "cta": "..."}
Outputs in DIR: c01.png.. (carousel 1080x1350), s01.png.. (story 1080x1920), reel.mp4 (9:16, <= 30 s)
"""
import argparse, json, os, subprocess, tempfile
from PIL import Image, ImageDraw, ImageFont

NAVY, NAVY2 = (12, 18, 32), (22, 32, 54)
GOLD, WHITE, SOFT = (232, 176, 75), (255, 255, 255), (190, 200, 215)
PHONE = "+212 660 96 66 20"
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
LAYOUT = ImageFont.Layout.RAQM


def font(path, size):
    return ImageFont.truetype(path, size, layout_engine=LAYOUT)


def is_rtl(s):
    return any("\u0600" <= ch <= "\u06ff" for ch in s)


def wrap(text, f, maxw):
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if f.getlength(t, direction="rtl" if is_rtl(t) else "ltr") <= maxw or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def fit(text, path, size, maxw, maxlines, minsize=30):
    while size >= minsize:
        f = font(path, size)
        ls = wrap(text, f, maxw)
        if len(ls) <= maxlines:
            return f, ls
        size -= 4
    f = font(path, minsize)
    return f, wrap(text, f, maxw)[:maxlines]


def center_lines(d, lines, f, y, W, fill, gap=1.35):
    size = f.size
    for ln in lines:
        d.text((W / 2, y), ln, font=f, fill=fill, anchor="ma", direction="rtl" if is_rtl(ln) else "ltr")
        y += int(size * gap)
    return y


def frame(W, H):
    im = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(im)
    for i in range(H):  # soft vertical gradient
        t = i / H
        c = tuple(int(NAVY[k] * (1 - t) + NAVY2[k] * t) for k in range(3))
        d.line([(0, i), (W, i)], fill=c)
    d.rectangle([0, 0, W, 14], fill=GOLD)
    return im, d


def brand(d, W, H, page=None):
    d.text((W / 2, H - 70), "AQAR OF AFRICA", font=font(FB, 34), fill=GOLD, anchor="ma")
    if page:
        d.text((60, H - 70), page, font=font(FR, 30), fill=SOFT, anchor="la")


def cover(plan, W, H, story):
    im, d = frame(W, H)
    d.text((W / 2, 90 if not story else 150), "نصائح عقارية", font=font(FB, 40), fill=GOLD, anchor="ma", direction="rtl")
    f, ls = fit(plan.get("title", ""), FB, 96, W - 160, 4, 56)
    y0 = int(H * 0.30)
    y = center_lines(d, ls, f, y0, W, WHITE, 1.3)
    if plan.get("subtitle"):
        fs, ls2 = fit(plan["subtitle"], FR, 46, W - 200, 3, 32)
        center_lines(d, ls2, fs, y + 40, W, SOFT)
    n = len(plan.get("tips") or [])
    badge = f"{n}"
    cy = int(H * 0.73)
    d.ellipse([W / 2 - 80, cy - 80, W / 2 + 80, cy + 80], outline=GOLD, width=6)
    d.text((W / 2, cy), badge, font=font(FB, 96), fill=GOLD, anchor="mm")
    hint = "اسحب باش تشوف" if not story else "تابع معانا"
    d.text((W / 2, cy + 120), hint, font=font(FR, 36), fill=SOFT, anchor="ma", direction="rtl")
    brand(d, W, H)
    return im


def tip(plan, i, W, H, story, total):
    t = plan["tips"][i]
    im, d = frame(W, H)
    fh, lh = fit(t.get("heading", ""), FB, 76, W - 160, 3, 48)
    fb, lb = fit(t.get("body", ""), FR, 60 if story else 54, W - 160, 9 if story else 7, 34)
    block = 190 + 60 + int(len(lh) * fh.size * 1.25) + 75 + int(len(lb) * fb.size * 1.45)
    top_y = max(70, (H - 120 - block) // 2)
    cy = top_y + 95
    d.ellipse([W / 2 - 95, cy - 95, W / 2 + 95, cy + 95], fill=GOLD)
    d.text((W / 2, cy), str(i + 1), font=font(FB, 110), fill=NAVY, anchor="mm")
    y = center_lines(d, lh, fh, cy + 155, W, WHITE, 1.25)
    d.line([(W / 2 - 90, y + 25), (W / 2 + 90, y + 25)], fill=GOLD, width=5)
    center_lines(d, lb, fb, y + 75, W, SOFT, 1.45)
    brand(d, W, H, f"{i + 2}/{total}")
    return im


def outro(plan, W, H, logo):
    im, d = frame(W, H)
    y = int(H * 0.16)
    if logo and os.path.exists(logo):
        lg = Image.open(logo).convert("RGBA")
        s = 420 / max(lg.width, lg.height)
        lg = lg.resize((int(lg.width * s), int(lg.height * s)), Image.LANCZOS)
        plate = Image.new("RGBA", (lg.width + 60, lg.height + 60), (255, 255, 255, 255))
        plate.paste(lg, (30, 30), lg)
        im.paste(plate, ((W - plate.width) // 2, y), plate)
        y += plate.height + 60
    fc, lc = fit(plan.get("cta") or "عندك سؤال على العقار؟ تواصل معانا", FB, 60, W - 160, 3, 40)
    y = center_lines(d, lc, fc, y, W, WHITE, 1.3)
    d.text((W / 2, y + 50), "WhatsApp / Tel", font=font(FR, 42), fill=(37, 211, 102), anchor="ma")
    d.text((W / 2, y + 115), PHONE, font=font(FB, 84), fill=WHITE, anchor="ma", direction="ltr")
    d.text((W / 2, y + 240), "Martil - Tetouan - Nord du Maroc", font=font(FR, 36), fill=SOFT, anchor="ma")
    brand(d, W, H)
    return im


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        raise RuntimeError(p.stderr[-2000:])


def reel(stories, music, out):
    n = len(stories)
    tips_n = max(1, n - 2)
    per_tip = min(3.2, 23.0 / tips_n)
    durs = [3.0] + [per_tip] * tips_n + [3.0]
    tmp = tempfile.mkdtemp()
    clips = []
    for k, (img, du) in enumerate(zip(stories, durs)):
        c = os.path.join(tmp, f"k{k}.mp4")
        fr = int(du * 30)
        run(["ffmpeg", "-y", "-loop", "1", "-i", img, "-vf",
             f"scale=2160:3840,zoompan=z='min(1+0.0007*on,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:s=1080x1920:fps=30,format=yuv420p",
             "-frames:v", str(fr), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", c])
        clips.append(c)
    XF = 0.4
    ins, filt, off, last = [], [], 0.0, "0:v"
    for c in clips:
        ins += ["-i", c]
    for i in range(1, n):
        off += durs[i - 1] - XF
        filt.append(f"[{last}][{i}:v]xfade=transition=slideleft:duration={XF}:offset={off:.2f}[v{i}]")
        last = f"v{i}"
    total = off + durs[-1]
    vid = os.path.join(tmp, "v.mp4")
    run(["ffmpeg", "-y", *ins, "-filter_complex", ";".join(filt), "-map", f"[{last}]", "-c:v", "libx264",
         "-preset", "medium", "-crf", "21", "-pix_fmt", "yuv420p", "-r", "30", vid])
    if music:
        run(["ffmpeg", "-y", "-i", vid, "-stream_loop", "-1", "-i", music, "-t", f"{total:.2f}",
             "-af", f"afade=t=in:d=1,afade=t=out:st={total - 2:.2f}:d=2,volume=0.8", "-map", "0:v", "-map", "1:a",
             "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", out])
    else:
        run(["ffmpeg", "-y", "-i", vid, "-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=48000:cl=stereo",
             "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-shortest", "-movflags", "+faststart", out])
    return round(total, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--logo")
    ap.add_argument("--music")
    a = ap.parse_args()
    plan = json.load(open(a.plan, encoding="utf-8"))
    plan["tips"] = [t for t in (plan.get("tips") or []) if t.get("heading")][:8]
    if not plan["tips"]:
        raise RuntimeError("no tips in plan")
    os.makedirs(a.out, exist_ok=True)
    total = len(plan["tips"]) + 2
    car, sto = [], []
    for story, (W, H), pre, acc in ((False, (1080, 1350), "c", car), (True, (1080, 1920), "s", sto)):
        pages = [cover(plan, W, H, story)] + [tip(plan, i, W, H, story, total) for i in range(len(plan["tips"]))] \
                + [outro(plan, W, H, a.logo)]
        for k, im in enumerate(pages, 1):
            p = os.path.join(a.out, f"{pre}{k:02d}.png")
            im.save(p, optimize=True)
            acc.append(p)
    secs = reel(sto, a.music, os.path.join(a.out, "reel.mp4"))
    print(json.dumps({"carousel": [os.path.basename(p) for p in car], "stories": [os.path.basename(p) for p in sto],
                      "reel": "reel.mp4", "seconds": secs}))


if __name__ == "__main__":
    main()
