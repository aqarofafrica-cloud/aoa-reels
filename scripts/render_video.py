#!/usr/bin/env python3
"""AQAR OF AFRICA - edit a real walkthrough video from a Claude montage plan.

Usage: render_video.py --src in.mp4 --plan plan.json --out final.mp4 --preview preview.mp4
                       [--music track.mp3] [--logo logo.png]

Plan (times in seconds of the ORIGINAL video):
{
  "trim_start": 0, "trim_end": 0,
  "captions": [{"start": 0.5, "end": 3.0, "text": "..."}],
  "effects":  [{"type": "title|dimensions|sun|sea|zoom|highlight|badge|whoosh",
                "start": 5.0, "end": 8.0, "text": "..."}]
}
Everything is drawn with FFmpeg + libass (Arabic shaping via HarfBuzz/FriBidi).
"""
import argparse, json, os, subprocess, tempfile, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_reel import end_card, brand_badge, badge_overlay  # same end card as the photo reels

W, H, FPS = 1080, 1920, 30
END = 3.5
FONT = "DejaVu Sans"
GOLD = "&H004BB0E8&"     # ASS colours are &HAABBGGRR
NAVY = "&H0020120C&"
WHITE = "&H00FFFFFF&"
BLACK = "&H00000000&"


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stderr.write(p.stderr[-4000:])
        raise RuntimeError("ffmpeg failed: " + " ".join(cmd[:6]))
    return p.stdout


def probe(src):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
               "-of", "json", src])
    j = json.loads(out)
    dur = float(j["format"]["duration"])
    vs = [s for s in j["streams"] if s.get("codec_type") == "video"]
    has_a = any(s.get("codec_type") == "audio" for s in j["streams"])
    return dur, (vs[0]["width"], vs[0]["height"]) if vs else (W, H), has_a


def num(x, d=0.0):
    try:
        return float(x)
    except Exception:
        return d


def ass_time(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def esc(s):
    return str(s).replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def build_ass(plan, offset, length, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},68,{WHITE},{WHITE},{BLACK},&H96000000&,1,0,0,0,100,100,0,0,1,5,2,2,70,70,300,1
Style: Title,{FONT},96,{WHITE},{WHITE},{NAVY},&H64000000&,1,0,0,0,100,100,0,0,1,7,3,8,60,60,250,1
Style: Dim,{FONT},92,{GOLD},{GOLD},{NAVY},&H64000000&,1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Badge,{FONT},58,{NAVY},{NAVY},{GOLD},&H00000000&,1,0,0,0,100,100,0,0,3,18,0,7,60,60,170,1
Style: Draw,{FONT},20,{GOLD},{GOLD},{NAVY},&H00000000&,0,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []

    def add(layer, a, b, style, text):
        a, b = a - offset, b - offset
        if b <= 0 or a >= length:
            return
        ev.append(f"Dialogue: {layer},{ass_time(max(0, a))},{ass_time(min(length, b))},{style},,0,0,0,,{text}")

    for c in plan.get("captions") or []:
        a, b = num(c.get("start")), num(c.get("end"))
        if b > a and esc(c.get("text")):
            add(1, a, b, "Cap", r"{\fad(120,80)}" + esc(c["text"]))

    for e in plan.get("effects") or []:
        t = str(e.get("type", "")).lower()
        a = num(e.get("start")); b = max(num(e.get("end")), a + 1.5)
        txt = esc(e.get("text", ""))
        if t == "title" and txt:
            add(3, a, b, "Title", r"{\fad(150,200)\move(-300,250,540,250,0,350)\an8}" + txt)
        elif t == "dimensions":
            # animated double arrows (width + depth) and the measure label
            hx = r"m 0 0 l 760 0 l 760 10 l 0 10" + " m -10 5 l 30 -25 l 30 35 m 770 5 l 730 -25 l 730 35"
            add(2, a, b, "Draw", r"{\an7\pos(160,1240)\p1\bord3\fscx0\t(0,450,\fscx100)\fad(0,250)}" + hx + r"{\p0}")
            vx = r"m 0 0 l 10 0 l 10 520 l 0 520" + " m 5 -10 l -25 30 l 35 30 m 5 530 l -25 490 l 35 490"
            add(2, a + 0.25, b, "Draw", r"{\an7\pos(960,650)\p1\bord3\fscy0\t(0,450,\fscy100)\fad(0,250)}" + vx + r"{\p0}")
            if txt:
                add(4, a + 0.35, b, "Dim", r"{\an5\pos(540,1150)\fscx130\fscy130\t(0,300,\fscx100\fscy100)\fad(100,250)}" + txt)
        elif t == "sun":
            glow = r"m 0 0 b 0 -140 280 -140 280 0 b 280 140 0 140 0 0"
            add(2, a, b, "Draw", r"{\an7\pos(760,180)\p1\bord0\blur35\1c&H66CCFF&\alpha&H70&\fad(500,600)"
                                 r"\t(0,1500,\alpha&H40&)\move(780,160,700,230)}" + glow + r"{\p0}")
            if txt:
                add(3, a + 0.3, b, "Badge", r"{\fad(200,200)}" + txt)
        elif t == "sea":
            wave = ("m 0 0 b 90 -40 180 -40 270 0 b 360 40 450 40 540 0 b 630 -40 720 -40 810 0 "
                    "b 900 40 990 40 1080 0 b 1170 -40 1260 -40 1350 0 l 1350 14 b 1260 -26 1170 -26 1080 14 "
                    "b 990 54 900 54 810 14 b 720 -26 630 -26 540 14 b 450 54 360 54 270 14 b 180 -26 90 -26 0 14")
            for k, y in enumerate((1720, 1775, 1830)):
                add(2, a + 0.15 * k, b, "Draw",
                    r"{\an7\p1\bord0\blur2\1c&HE0B040&\alpha&H50&\fad(400,400)" +
                    f"\\move({-150 - 90 * k},{y},{-420 + 60 * k},{y})" + "}" + wave + r"{\p0}")
            if txt:
                add(3, a + 0.3, b, "Badge", r"{\fad(200,200)}" + txt)
        elif t in ("highlight", "badge") and txt:
            add(3, a, b, "Badge", r"{\fad(150,200)\fscx70\fscy70\t(0,250,\fscx105\fscy105)\t(250,400,\fscx100\fscy100)}" + txt)
    open(path, "w", encoding="utf-8").write(head + "\n".join(ev) + "\n")
    return len(ev)


def zoom_expr(plan, offset):
    terms = []
    for e in plan.get("effects") or []:
        if str(e.get("type", "")).lower() == "zoom":
            a = num(e.get("start")) - offset; b = max(num(e.get("end")) - offset, a + 1.0)
            terms.append(f"0.16*clip(min((t-{a:.2f})/0.5\\,({b:.2f}-t)/0.5)\\,0\\,1)")
    return "1+" + "+".join(terms) if terms else None


def colour_filters(plan, offset):
    f = []
    for e in plan.get("effects") or []:
        t = str(e.get("type", "")).lower()
        a = num(e.get("start")) - offset; b = max(num(e.get("end")) - offset, a + 1.5)
        if t == "sun":
            f.append(f"eq=brightness=0.05:saturation=1.25:enable='between(t,{a:.2f},{b:.2f})'")
            f.append(f"colorbalance=rm=0.06:bm=-0.05:enable='between(t,{a:.2f},{b:.2f})'")
        elif t == "sea":
            f.append(f"eq=saturation=1.2:enable='between(t,{a:.2f},{b:.2f})'")
            f.append(f"colorbalance=bm=0.05:rm=-0.03:enable='between(t,{a:.2f},{b:.2f})'")
    return f


def sfx_file(kind, d, path):
    if kind == "whoosh":
        src, af = f"anoisesrc=color=pink:d={d}:a=0.5", f"highpass=f=500,lowpass=f=4500,afade=t=in:d={d*0.55:.2f},afade=t=out:st={d*0.55:.2f}:d={d*0.45:.2f},volume=0.55"
    elif kind == "ding":
        src = f"sine=f=1318:d={d}"
        af = f"afade=t=out:st=0.03:d={d-0.03:.2f}:curve=exp,volume=0.35"
    elif kind == "waves":
        src = f"anoisesrc=color=brown:d={d}:a=0.6"
        af = f"lowpass=f=900,tremolo=f=0.18:d=0.8,afade=t=in:d=1,afade=t=out:st={max(0.5, d-1.2):.2f}:d=1.2,volume=0.9"
    else:  # shimmer (sun)
        src = f"sine=f=880:d={d}"
        af = f"tremolo=f=6:d=0.4,afade=t=in:d=0.8,afade=t=out:st={max(0.3, d-1):.2f}:d=1,volume=0.07"
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", src, "-af", af, "-ar", "48000", "-ac", "2", path])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", required=True)
    ap.add_argument("--music")
    ap.add_argument("--logo")
    a = ap.parse_args()
    plan = json.load(open(a.plan, encoding="utf-8"))
    tmp = tempfile.mkdtemp()
    dur, (iw, ih), has_a = probe(a.src)
    ts = min(max(0.0, num(plan.get("trim_start"))), max(0.0, dur - 3))
    te = min(max(0.0, num(plan.get("trim_end"))), max(0.0, dur - ts - 3))
    length = dur - ts - te

    # 1) picture: 9:16 cover (or blurred background for landscape), zooms, colour moods, overlays
    ass = os.path.join(tmp, "fx.ass")
    n_ev = build_ass(plan, ts, length, ass)
    portrait = ih / iw >= 1.6
    z = zoom_expr(plan, ts)
    chain = []
    if portrait:
        chain.append(f"[0:v]trim=start={ts:.3f}:duration={length:.3f},setpts=PTS-STARTPTS,"
                     f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1[base]")
    else:
        chain.append(f"[0:v]trim=start={ts:.3f}:duration={length:.3f},setpts=PTS-STARTPTS,split[s1][s2]")
        chain.append(f"[s1]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,eq=brightness=-0.12[bg]")
        chain.append(f"[s2]scale={W}:-2:force_original_aspect_ratio=decrease[fg]")
        chain.append("[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[base]")
    cur = "base"
    if z:
        chain.append(f"[{cur}]scale=w='trunc({W}*({z})/2)*2':h='trunc({H}*({z})/2)*2':eval=frame,"
                     f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2[zm]")
        cur = "zm"
    col = colour_filters(plan, ts)
    fonts = "/usr/share/fonts/truetype/noto"
    badge = brand_badge(a.logo, os.path.join(tmp, "badge.png"))
    chain.append(f"[{cur}]" + ",".join(col + [f"ass={ass}", f"fps={FPS}"]) + ("[v0]" if badge else ",format=yuv420p[v]"))
    if badge:
        chain.append(badge_overlay("v0", 1, length + 1, "v1") + ";[v1]format=yuv420p[v]")
    body = os.path.join(tmp, "body.mp4")
    run(["ffmpeg", "-y", "-i", a.src, *(["-i", badge] if badge else []), "-filter_complex", ";".join(chain), "-map", "[v]", "-an",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-r", str(FPS), body])

    # 2) end card (same as photo reels) + concat
    ec = os.path.join(tmp, "end.jpg"); end_card(ec, a.logo)
    ecl = os.path.join(tmp, "end.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", ec, "-t", str(END), "-r", str(FPS),
         "-vf", "format=yuv420p,fade=t=in:d=0.4", "-c:v", "libx264", "-preset", "medium", "-crf", "20", ecl])
    video = os.path.join(tmp, "video.mp4")
    run(["ffmpeg", "-y", "-i", body, "-i", ecl, "-filter_complex", "[0:v][1:v]concat=n=2:v=1:a=0[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", video])
    total = length + END

    # 3) sound: voice (cleaned) + effects, music ducked under the voice
    ins, parts, k = [], [], 0
    if has_a:
        ins += ["-ss", f"{ts:.3f}", "-t", f"{length:.3f}", "-i", a.src]
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,highpass=f=80,"
                     f"dynaudnorm=f=150:g=15,volume=1.6,apad=whole_dur={total:.2f}[voice]")
    else:
        ins += ["-f", "lavfi", "-t", f"{total:.2f}", "-i", "anullsrc=r=48000:cl=stereo"]
        parts.append(f"[{k}:a]anull[voice]")
    k += 1
    sfx = []
    for e in plan.get("effects") or []:
        t = str(e.get("type", "")).lower()
        st = num(e.get("start")) - ts
        en = max(num(e.get("end")) - ts, st + 1.5)
        if st < 0 or st >= length:
            continue
        kind = {"title": "whoosh", "whoosh": "whoosh", "dimensions": "ding", "highlight": "ding",
                "badge": "ding", "sea": "waves", "sun": "shimmer"}.get(t)
        if not kind:
            continue
        d = {"whoosh": 0.7, "ding": 1.2}.get(kind, min(max(en - st, 2.0), 8.0))
        f = os.path.join(tmp, f"sfx{len(sfx)}.wav"); sfx_file(kind, d, f)
        ins += ["-i", f]
        ms = int(st * 1000)
        parts.append(f"[{k}:a]adelay={ms}|{ms}[x{len(sfx)}]")
        sfx.append(f"[x{len(sfx)}]"); k += 1
    voice_mix = "voice"
    if sfx:
        parts.append(f"[voice]{''.join(sfx)}amix=inputs={1 + len(sfx)}:normalize=0:duration=first[vm]")
        voice_mix = "vm"
    if a.music:
        ins += ["-stream_loop", "-1", "-i", a.music]
        parts.append(f"[{voice_mix}]asplit[vo][key]")
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.2f},volume=0.22,"
                     f"afade=t=in:d=1,afade=t=out:st={total-2:.2f}:d=2[mus]")
        parts.append("[mus][key]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[duck]")
        parts.append(f"[vo][duck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    else:
        parts.append(f"[{voice_mix}]alimiter=limit=0.95[aout]")
    audio = os.path.join(tmp, "audio.m4a")
    run(["ffmpeg", "-y", *ins, "-filter_complex", ";".join(parts), "-map", "[aout]", "-t", f"{total:.2f}",
         "-c:a", "aac", "-b:a", "160k", audio])

    # 4) final (for publishing) + light preview (for WhatsApp, < 15 MB)
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
         "-shortest", "-movflags", "+faststart", a.out])
    vbr = int(max(250, min(1100, (14 * 8 * 1024) / total - 100)))
    run(["ffmpeg", "-y", "-i", a.out, "-vf", "scale=720:1280", "-c:v", "libx264", "-preset", "veryfast",
         "-b:v", f"{vbr}k", "-maxrate", f"{vbr}k", "-bufsize", f"{vbr*2}k", "-c:a", "aac", "-b:a", "96k",
         "-movflags", "+faststart", a.preview])
    print(json.dumps({"out": a.out, "preview": a.preview, "seconds": round(total, 1), "overlays": n_ev,
                      "sfx": len(sfx), "portrait": portrait,
                      "preview_mb": round(os.path.getsize(a.preview) / 1048576, 2),
                      "final_mb": round(os.path.getsize(a.out) / 1048576, 2)}))


if __name__ == "__main__":
    main()
