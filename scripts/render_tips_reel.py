#!/usr/bin/env python3
"""AQAR OF AFRICA - advice reel with Darija voice-over (ElevenLabs), expressive stock visuals (Pixabay),
kinetic word-by-word captions, ducked music, whoosh cuts, progress bar and the brand end card.

Usage: render_tips_reel.py --plan reel.json --out reel.mp4 --preview preview.mp4 --work DIR
                           [--music track.mp3] [--logo logo.png] [--voices assets/voices.json] [--run N]
Plan (from Claude):
{"mode": "solo|dialogue", "hook": "...", "scenes": [
   {"speaker": "narrator|asker|expert|witness", "line": "Darija voice text", "title": "short on-screen headline",
    "visual": "english stock query", "visual_alt": "fallback query", "mood": "worry|happy|neutral|tension|relief"}]}
Env: ELEVENLABS_API_KEY, PIXABAY_API_KEY (both optional: without them the reel falls back to
estimated timing / brand backgrounds, so a render never fails because of an external service).
Prints one JSON line: {"seconds", "voice_ok", "voices", "credits_left", "visuals"}.
"""
import argparse, base64, json, os, random, re, subprocess, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_reel import end_card
from render_video import sfx_file, ass_time, esc

W, H, FPS = 1080, 1920, 30
END = 3.5
PAD = 0.28            # silence after each line
FONT = "DejaVu Sans"
UA = {"User-Agent": "Mozilla/5.0 (AOA reels bot)"}
BAN = ("monkey", "ape", "animal", "dog", "cat", "bird", "wildlife", "zoo", "quran", "koran", "mosque", "prayer", "islam",
       "muslim", "religion", "church", "bible", "christian", "cross", "god", "pray", "bikini", "lingerie", "alcohol", "beer",
       "wine", "apes", "monkeys", "cats", "dogs", "birds", "animals", "religious", "ramadan", "halloween", "zombie", "skull", "weapon", "gun", "war", "blood", "flag", "politic")
GENERIC = {"worry": ["worried man", "stress woman"], "tension": ["stress business", "confused couple"],
           "neutral": ["real estate agent", "apartment building"], "happy": ["happy couple home", "family home"],
           "relief": ["handshake business", "smiling couple"]}
STOP = {"the", "and", "with", "for", "from", "into", "at", "of", "on", "in", "a", "an", "his", "her", "their", "looking", "showing"}
ROLE_AR = {"asker": "المشتري", "expert": "الخبير", "witness": "تجربة", "narrator": ""}
MOOD_GRADE = {
    "worry": "eq=saturation=0.75:contrast=1.08:brightness=-0.03,colorbalance=bs=0.06:rs=-0.03",
    "tension": "eq=saturation=0.7:contrast=1.15:brightness=-0.05",
    "happy": "eq=saturation=1.2:contrast=1.04:brightness=0.02,colorbalance=rs=0.04:bs=-0.03",
    "relief": "eq=saturation=1.1:contrast=1.03:brightness=0.03",
    "neutral": "eq=saturation=1.05:contrast=1.04",
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode:
        log(p.stderr[-3000:])
        raise RuntimeError("ffmpeg failed: " + " ".join(cmd[:8]))
    return p.stdout


def http(url, method="GET", headers=None, data=None, timeout=120):
    r = urllib.request.Request(url, method=method, headers={**UA, **(headers or {})}, data=data)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return resp.read()


def duration(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path]).strip())


# ---------------------------------------------------------------- voices
def pick_voices(cfg, mode, run_no):
    """The expert is always the agency voice (assets/voices.json "agency", fixed); the other characters rotate."""
    narr = cfg.get("narrators") or []
    roles = cfg.get("roles") or {}
    rot = lambda lst, k=0: lst[(run_no + k) % len(lst)] if lst else None
    agency = cfg.get("agency")
    agency = rot(agency) if isinstance(agency, list) else agency
    expert = agency or rot(roles.get("expert") or narr)
    if mode != "dialogue":
        return {"narrator": expert, "expert": expert, "asker": expert, "witness": expert}
    asker = rot([x for x in (roles.get("asker") or narr) if x["id"] != expert["id"]] or narr, 1)
    witness = rot([x for x in (roles.get("witness") or narr) if x["id"] not in (expert["id"], asker["id"])] or narr, 2)
    return {"narrator": expert, "expert": expert, "asker": asker, "witness": witness}


TAG = re.compile(r"\[[^\]]{1,40}\]")
ROLE_SETTINGS = {   # expert = the agency voice: steady and calm; other characters: freer, more emotional
    "expert": {"stability": 0.55, "similarity_boost": 0.8},
    "narrator": {"stability": 0.55, "similarity_boost": 0.8},
    "asker": {"stability": 0.35, "similarity_boost": 0.8},
    "witness": {"stability": 0.4, "similarity_boost": 0.8},
}


def clean_line(text, model):
    """Audio tags ([calm], [worried], [sighs]...) are read by Eleven v4 as delivery directions."""
    return re.sub(r"\s+", " ", text).strip()


def tts(text, voice, model, key, prev, nxt, dst, role="narrator"):
    body = {"text": clean_line(text, model), "model_id": model,
            "voice_settings": dict(ROLE_SETTINGS.get(role, ROLE_SETTINGS["narrator"]))}
    raw = http(f"https://api.elevenlabs.io/v1/text-to-speech/{voice['id']}/with-timestamps?output_format=mp3_44100_128",
               "POST", {"xi-api-key": key, "Content-Type": "application/json"}, json.dumps(body).encode(), 180)
    j = json.loads(raw)
    open(dst, "wb").write(base64.b64decode(j["audio_base64"]))
    al = j.get("alignment") or j.get("normalized_alignment") or {}
    chars, st, en = al.get("characters") or [], al.get("character_start_times_seconds") or [], al.get("character_end_times_seconds") or []
    words, cur, ws, depth, last_end = [], "", None, 0, 0
    for c, a, b in zip(chars, st, en):
        if c == "[":
            depth += 1
        if depth or c.isspace():
            if c == "]":
                depth = max(0, depth - 1)
            if cur:
                words.append((cur, ws, last_end)); cur = ""
            continue
        if not cur:
            ws = a
        cur += c
        last_end = b
    if cur:
        words.append((cur, ws, last_end))
    return words


def sfx(desc, secs, key, dst):
    body = {"text": desc[:200], "duration_seconds": max(0.8, min(4.0, secs)), "prompt_influence": 0.5}
    raw = http("https://api.elevenlabs.io/v1/sound-generation?output_format=mp3_44100_128", "POST",
               {"xi-api-key": key, "Content-Type": "application/json"}, json.dumps(body).encode(), 120)
    open(dst, "wb").write(raw)
    return dst


def credits_left(key):
    try:
        j = json.loads(http("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=30))
        return int(j.get("character_limit", 0)) - int(j.get("character_count", 0))
    except Exception:
        return None


def estimate_words(text, t0=0.0):
    out, t = [], t0
    for w in TAG.sub(" ", text).split():
        d = 0.18 + 0.055 * len(w)
        out.append((w, t, t + d)); t += d
    return out


# ---------------------------------------------------------------- visuals
PERSON = re.compile(r"\b(man|woman|men|women|guy|lady|businessman|businesswoman|person|agent|realtor|consultant|advisor|expert|buyer|seller)\b", re.I)


OTHER_SEX = {"male": {"woman", "women", "female", "girl", "girls", "lady", "businesswoman", "mother", "wife"},
             "female": {"man", "men", "male", "boy", "boys", "guy", "businessman", "father", "husband", "beard"}}


def match_gender(query, gender):
    """Keep the person on screen consistent with the voice we hear (male voice -> man, female voice -> woman)."""
    if not query or gender not in ("male", "female") or not PERSON.search(query):
        return query
    m = gender == "male"
    q = re.sub(r"\bwom(a|e)n\b", "man" if m else "woman", query, flags=re.I) if m else re.sub(r"\bm(a|e)n\b", "woman", query, flags=re.I)
    q = re.sub(r"\bbusiness(wo)?man\b", "businessman" if m else "businesswoman", q, flags=re.I)
    q = re.sub(r"\b(lady|guy)\b", "man" if m else "woman", q, flags=re.I)
    if not re.search(r"\b(man|woman|businessman|businesswoman)\b", q, re.I):
        q = ("man " if m else "woman ") + q
    return q


def pixabay_pick(query, key, used, want, workdir, idx, avoid=()):
    """Return (path, kind) for a stock visual, preferring portrait video long enough."""
    if not key or not query:
        return None
    try:
        q = urllib.parse.urlencode({"key": key, "q": query[:90], "per_page": 30, "safesearch": "true", "video_type": "film"})
        vids = json.loads(http("https://pixabay.com/api/videos/?" + q, timeout=40)).get("hits") or []
    except Exception as e:
        log("pixabay video failed", query, e); vids = []
    try:
        q = urllib.parse.urlencode({"key": key, "q": query[:90], "per_page": 40, "safesearch": "true",
                                    "orientation": "vertical", "image_type": "photo"})
        pics = json.loads(http("https://pixabay.com/api/?" + q, timeout=40)).get("hits") or []
    except Exception as e:
        log("pixabay photo failed", query, e); pics = []
    words = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2 and w not in STOP]

    def score(h):
        toks = re.findall(r"[a-z]+", h.get("tags", "").lower())
        return sum(1 for w in words if any(t.startswith(w[:5]) or w.startswith(t[:5]) for t in toks if len(t) > 2))

    def fresh(h):
        sig = (h.get("user_id"), h.get("tags"))
        toks = set(re.findall(r"[a-z]+", h.get("tags", "").lower()))
        return h["id"] not in used and sig not in used and not toks.intersection(BAN) and not toks.intersection(avoid)

    def take(h):
        used.add(h["id"]); used.add((h.get("user_id"), h.get("tags")))

    cands = []
    for h in vids:
        v = h["videos"].get("medium") or h["videos"].get("small") or {}
        if fresh(h) and v.get("url") and (h.get("duration") or 0) >= min(want, 5):
            portrait = v.get("height", 0) > v.get("width", 1)
            cands.append((score(h), 0.6 + (0.3 if portrait else 0), "video", h, v["url"]))
    for h in pics:
        url = h.get("largeImageURL") or h.get("webformatURL")
        if fresh(h) and url:
            cands.append((score(h), 0.0, "image", h, url))
    need = min(2, len(words)) if words else 1
    cands = [c for c in cands if c[0] >= need]
    cands.sort(key=lambda c: (-(c[0] + c[1]), -c[3].get("likes", 0)))
    for sc, bonus, kind, h, url in cands[:4]:
        try:
            dst = os.path.join(workdir, f"{'v' if kind == 'video' else 'i'}{idx:02d}.{'mp4' if kind == 'video' else 'jpg'}")
            open(dst, "wb").write(http(url, timeout=120))
            take(h)
            log("visual", idx, kind, round(sc, 1), query, "->", h.get("tags"))
            return dst, kind
        except Exception as e:
            log("download failed", e)
    return None


def brand_bg(dst):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(im)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=(int(12 + 14 * t), int(18 + 20 * t), int(32 + 30 * t)))
    im.save(dst, quality=92)
    return dst, "image"


def scene_clip(src, kind, dur, mood, dst, first):
    grade = MOOD_GRADE.get(mood or "neutral", MOOD_GRADE["neutral"])
    fr = max(1, int(round(dur * FPS)))
    shade = "drawbox=x=0:y=ih*0.52:w=iw:h=ih*0.48:color=black@0.42:t=fill,drawbox=x=0:y=0:w=iw:h=ih*0.16:color=black@0.25:t=fill"
    if kind == "video":
        vd = duration(src)
        ss = 0.0 if vd <= dur + 0.5 else random.uniform(0.2, max(0.2, vd - dur - 0.2))
        zoom = "1.10" if first else "1.05"   # slow push-out, never below 1.0 (crop must stay inside the frame)
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"scale=w='trunc({W}*max(1.002,{zoom}-0.04*t/{dur:.2f})/2)*2+2':h=-2:eval=frame,crop={W}:{H},"
              f"fps={FPS},{grade},{shade},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-ss", f"{ss:.2f}", "-stream_loop", "-1", "-i", src, "-t", f"{dur:.3f}", "-an", "-vf", vf]
    else:
        vf = (f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
              f"zoompan=z='min(1+0.0011*on,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:s={W}x{H}:fps={FPS},"
              f"{grade},{shade},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", src, "-frames:v", str(fr), "-vf", vf]
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), dst])


# ---------------------------------------------------------------- captions
def build_ass(scenes, hook, total, path):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},74,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H96000000&,1,0,0,0,100,100,0,0,1,6,2,2,70,70,520,-1
Style: Hook,{FONT},96,&H00FFFFFF&,&H00FFFFFF&,&H0020120C&,&H64000000&,1,0,0,0,100,100,0,0,1,8,3,5,70,70,0,1
Style: Title,{FONT},58,&H0020120C&,&H0020120C&,&H004BB0E8&,&H00000000&,1,0,0,0,100,100,0,0,3,20,0,8,80,80,140,1
Style: Who,{FONT},46,&H004BB0E8&,&H004BB0E8&,&H00000000&,&H00000000&,1,0,0,0,100,100,0,0,1,4,0,2,70,70,760,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    add = lambda layer, a, b, st, tx: ev.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(b)},{st},,0,0,0,,{tx}")
    if hook:
        add(3, 0.0, min(2.6, scenes[0]["dur"]), "Hook", r"{\fad(120,250)\t(0,250,\fscx108\fscy108)\t(250,500,\fscx100\fscy100)}" + esc(hook))
    for s in scenes:
        t0, t1 = s["t0"], s["t0"] + s["dur"]
        if s.get("title") and not (s is scenes[0] and hook):
            add(2, t0 + 0.05, t1 - 0.05, "Title", r"{\fad(150,150)}" + esc(s["title"]))
        who = ROLE_AR.get(s.get("speaker") or "narrator", "")
        if who and s.get("dialogue"):
            add(2, t0, t1, "Who", r"{\fad(100,100)}" + who)
        words = [(esc(w), a + t0, b + t0) for w, a, b in s["words"] if esc(w)]
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= 4 or re.search(r"[.!؟?،,]$", w[0]):
                chunks.append(cur); cur = []
        if cur:
            chunks.append(cur)
        for ci, ch in enumerate(chunks):
            c_end = chunks[ci + 1][0][1] if ci + 1 < len(chunks) else t1
            for wi, (w, a, b) in enumerate(ch):
                nxt = ch[wi + 1][1] if wi + 1 < len(ch) else c_end
                txt = " ".join(r"{\c&H004BB0E8&\fscx112\fscy112}" + x + r"{\c&H00FFFFFF&\fscx100\fscy100}" if k == wi else x
                               for k, (x, _, _) in enumerate(ch))
                add(1, a, max(nxt, a + 0.05), "Cap", txt)
    open(path, "w", encoding="utf-8").write(head + "\n".join(ev) + "\n")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--preview", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--music")
    ap.add_argument("--logo")
    ap.add_argument("--voices", default=os.path.join(os.path.dirname(__file__), "..", "assets", "voices.json"))
    ap.add_argument("--run", type=int, default=int(os.environ.get("GITHUB_RUN_NUMBER", "1")))
    a = ap.parse_args()
    os.makedirs(a.work, exist_ok=True)
    plan = json.load(open(a.plan, encoding="utf-8"))
    scenes = [s for s in (plan.get("scenes") or []) if (s.get("line") or "").strip()][:24]
    if not scenes:
        raise RuntimeError("reel plan has no scenes")
    mode = "dialogue" if plan.get("mode") == "dialogue" else "solo"
    cfg = json.load(open(a.voices, encoding="utf-8"))
    model = "eleven_v4"          # owner decision 2026-10-23: only Eleven v4 voices (v3 / multilingual v2 banned)
    voices = pick_voices(cfg, mode, a.run)
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    pkey = os.environ.get("PIXABAY_API_KEY", "")
    random.seed(a.run)

    # 1) voice per line
    voice_ok = bool(key)
    t = 0.0
    for i, s in enumerate(scenes):
        s["dialogue"] = mode == "dialogue"
        mp3 = os.path.join(a.work, f"l{i:02d}.mp3")
        words = None
        if voice_ok:
            try:
                prev = scenes[i - 1]["line"] if i else ""
                nxt = scenes[i + 1]["line"] if i + 1 < len(scenes) else ""
                role = s.get("speaker") or "narrator"
                words = tts(s["line"].strip(), voices.get(role) or voices["narrator"], model, key, prev, nxt, mp3, role)
                s["audio"] = mp3
                s["dur"] = max(duration(mp3), words[-1][2] if words else 0) + PAD
            except Exception as e:
                log("tts failed, falling back to silent timing:", e)
                voice_ok = False
        if not words:
            words = estimate_words(s["line"])
            s["audio"] = None
            s["dur"] = (words[-1][2] if words else 2.0) + PAD
        s["dur"] = max(1.6, s["dur"])
        s["words"] = words
        s["t0"] = t
        t += s["dur"]
    body = t

    # 2) visuals
    used, kinds = set(), []
    clips = []
    for i, s in enumerate(scenes):
        got = None
        g = (voices.get(s.get("speaker") or "narrator") or {}).get("gender") if mode == "dialogue" else None
        qs = [match_gender(s.get("visual"), g), match_gender(s.get("visual_alt"), g)]
        avoid = OTHER_SEX.get(g, ()) if any(PERSON.search(x or "") for x in qs) else ()
        for q in qs + GENERIC.get(s.get("mood") or "neutral", GENERIC["neutral"]):
            got = pixabay_pick(q, pkey, used, s["dur"], a.work, i, avoid)
            if got:
                break
        got = got or brand_bg(os.path.join(a.work, f"bg{i:02d}.jpg"))
        kinds.append(got[1] if got[0] else "brand")
        c = os.path.join(a.work, f"c{i:02d}.mp4")
        scene_clip(got[0], got[1], s["dur"], s.get("mood"), c, i == 0)
        clips.append(c)
    ec = os.path.join(a.work, "end.jpg")
    end_card(ec, a.logo)
    endc = os.path.join(a.work, "cend.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", ec, "-t", f"{END}", "-vf",
         f"scale={W}:{H},zoompan=z='min(1+0.0008*on,1.04)':d={int(END*FPS)}:s={W}x{H}:fps={FPS},fade=t=in:d=0.35,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), endc])
    clips.append(endc)
    total = body + END
    lst = os.path.join(a.work, "list.txt")
    open(lst, "w").write("".join(f"file '{os.path.abspath(c)}'\n" for c in clips))
    vid = os.path.join(a.work, "video.mp4")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", vid])

    # 3) captions + progress bar
    ass = os.path.join(a.work, "caps.ass")
    build_ass(scenes, (plan.get("hook") or "").strip(), total, ass)
    vtx = os.path.join(a.work, "vtx.mp4")
    bar = f"color=c=0xE8B04B:s={W}x12:r={FPS}"
    run(["ffmpeg", "-y", "-i", vid, "-f", "lavfi", "-i", bar, "-filter_complex",
         f"[0:v]ass={ass}[c];[c][1:v]overlay=x='-W+W*t/{body:.2f}':y=0:enable='lt(t,{body:.2f})':shortest=1[v]",
         "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), vtx])

    # 4) audio: voice lines at their times + whoosh at cuts + ducked music
    ins, parts, labels = [], [], []
    k = 0
    for s in scenes:
        if s.get("audio"):
            ins += ["-i", s["audio"]]
            ms = int(s["t0"] * 1000)
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{k}]")
            labels.append(f"[a{k}]"); k += 1
    wh = os.path.join(a.work, "whoosh.wav")
    sfx_file("whoosh", 0.45, wh)
    for s in scenes[1:] + [{"t0": body}]:
        ins += ["-i", wh]
        ms = max(0, int((s["t0"] - 0.2) * 1000))
        parts.append(f"[{k}:a]adelay={ms}|{ms}[a{k}]"); labels.append(f"[a{k}]"); k += 1
    n_sfx = 0
    for i, s in enumerate(scenes):
        if not (key and voice_ok and s.get("sfx") and n_sfx < 3):
            continue
        try:
            fx = sfx(s["sfx"], min(3.0, s["dur"]), key, os.path.join(a.work, f"fx{i:02d}.mp3"))
            n_sfx += 1
            ins += ["-i", fx]
            ms = int(s["t0"] * 1000)
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume=0.32,afade=t=out:st=2.2:d=0.8,adelay={ms}|{ms}[a{k}]")
            labels.append(f"[a{k}]"); k += 1
            log("sfx", i, s["sfx"])
        except Exception as e:
            log("sfx failed", s.get("sfx"), e)
    parts.append(f"anullsrc=r=48000:cl=stereo,atrim=0:{total:.2f}[sil]")
    parts.append(f"[sil]{''.join(labels)}amix=inputs={1 + len(labels)}:normalize=0:duration=first,volume=1.35[vo]")
    if a.music:
        ins += ["-stream_loop", "-1", "-i", a.music]
        parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{total:.2f},"
                     f"volume=0.45,afade=t=in:d=1,afade=t=out:st={total - 2.5:.2f}:d=2.5[mus]")
        parts.append("[vo]asplit=2[vo1][key]")
        parts.append("[mus][key]sidechaincompress=threshold=0.03:ratio=9:attack=15:release=450[duck]")
        parts.append("[vo1][duck]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.95[aout]")
    else:
        parts.append("[vo]alimiter=limit=0.95[aout]")
    aud = os.path.join(a.work, "audio.m4a")
    run(["ffmpeg", "-y", *ins, "-filter_complex", ";".join(parts), "-map", "[aout]", "-t", f"{total:.2f}",
         "-c:a", "aac", "-b:a", "192k", aud])

    run(["ffmpeg", "-y", "-i", vtx, "-i", aud, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "copy",
         "-shortest", "-movflags", "+faststart", a.out])
    run(["ffmpeg", "-y", "-i", a.out, "-vf", "scale=720:1280", "-c:v", "libx264", "-preset", "medium", "-crf", "30",
         "-maxrate", "1100k", "-bufsize", "2200k", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", a.preview])
    print(json.dumps({"seconds": round(total, 1), "voice_ok": voice_ok, "mode": mode,
                      "voices": sorted({v["name"] for v in voices.values() if v}),
                      "credits_left": credits_left(key) if key else None, "visuals": kinds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
