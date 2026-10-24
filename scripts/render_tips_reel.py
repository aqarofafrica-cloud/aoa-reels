#!/usr/bin/env python3
"""AQAR OF AFRICA - advice reel with Darija voice-over (ElevenLabs), expressive stock visuals (Pixabay),
calm word-by-word captions, ducked calm music, soft dissolves (no commercial whooshes), progress bar,
brand watermark and the brand end card (brand constitution 2026-10-23: trust and mini-lessons, never cheap ads).

Usage: render_tips_reel.py --plan reel.json --out reel.mp4 --preview preview.mp4 --work DIR
                           [--music track.mp3] [--logo logo.png] [--voices assets/voices.json] [--run N]
Plan (from Claude, built from the montage scenario validated in the TIPS PDF):
{"mode": "solo|dialogue", "title": "fixed top title", "hook": "...", "music": "calm|warm|upbeat|energetic",
 "cast": {"asker": "Loubna", "witness": "Hamid"},           # optional, names from assets/voices.json
 "scenes": [{"speaker": "narrator|asker|expert|witness", "line": "Darija voice text",
             "keywords": ["exact words of the line shown in the brand colour"],
             "visual": "english stock query", "visual_alt": "fallback query",
             "mood": "worry|happy|neutral|tension|relief", "sfx": "optional sound effect"}]}
On screen (reference style 2026-10-24): fixed title pill on top for the whole video, round logo badge top-right,
big captions of 2-3 words, keywords in brand gold, ordinal words (اولا، ثانيا...) alone and bigger.
Env: ELEVENLABS_API_KEY, PIXABAY_API_KEY, PEXELS_API_KEY (all optional: without them the reel falls back to
estimated timing / brand backgrounds, so a render never fails because of an external service).
Prints one JSON line: {"seconds", "voice_ok", "voices", "credits_left", "visuals"}.
"""
import argparse, base64, json, os, random, re, subprocess, sys, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from render_reel import end_card
from render_video import ass_time, esc

W, H, FPS = 1080, 1920, 30
END = 3.5
PAD = 0.28            # silence after each line
XF = 0.5              # soft dissolve between scenes (cinematic, calm rhythm)
MUSIC_VOL = 0.16      # owner feedback 2026-10-23: music well under the voice-over (was 0.45)
FONT = "Tajawal ExtraBold"   # assets/fonts (Google Fonts, OFL), Arabic + Latin
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "fonts")
GOLD_ASS, NAVY_ASS = "&H004BB0E8&", "&H00201209&"   # brand gold (232,176,75) / navy (9,18,32) in ASS BGR
BADGE_D, BADGE_M = 190, 40
ORDINAL = re.compile(r"^[وف]?(أولا|اولا|أولاً|ثانيا|ثانياً|ثالثا|ثالثاً|رابعا|رابعاً|خامسا|خامساً|سادسا|سابعا|ثامنا|تاسعا|عاشرا|وأخيرا|أخيرا|اخيرا)[،,.:!]?$")
UA = {"User-Agent": "Mozilla/5.0 (AOA reels bot)"}
BAN = ("monkey", "ape", "animal", "dog", "cat", "bird", "wildlife", "zoo", "quran", "koran", "mosque", "prayer", "islam",
       "muslim", "religion", "church", "bible", "christian", "cross", "god", "pray", "bikini", "lingerie", "alcohol", "beer",
       "wine", "christmas", "xmas", "santa", "gift", "gifts", "present", "holiday", "costume", "robe", "kimono",
       "asian", "asia", "china", "japan", "india", "hindu", "buddha", "buddhism", "temple", "dollar", "dollars", "usd", "parchment",
       "antique", "vintage", "grunge", "texture", "background", "wallpaper", "illustration", "cartoon", "vector", "sign", "signs", "signage", "billboard", "banner", "poster", "advertisement", "logo", "brand", "chinese", "japanese", "korean", "calligraphy", "kanji", "hieroglyph", "newspaper", "graffiti", "apes", "monkeys", "cats", "dogs", "birds", "animals", "religious", "ramadan", "halloween", "zombie", "skull", "weapon", "gun", "war", "blood", "flag", "politic")
GENERIC = {"worry": ["worried man", "stress woman"], "tension": ["stress business", "confused couple"],
           "neutral": ["real estate agent", "apartment building"], "happy": ["happy couple home", "family home"],
           "relief": ["handshake business", "smiling couple"]}
HUMAN = {"man", "men", "woman", "women", "person", "people", "girl", "boy", "businessman", "businesswoman", "couple",
         "family", "hand", "hands", "lady", "guy", "male", "female", "adult", "worker", "father", "mother", "child", "human"}
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
def pick_voices(cfg, mode, run_no, cast=None):
    """The expert is always the agency voice (assets/voices.json "agency", fixed); the other characters are the ones
    Claude cast in the montage scenario (only names present in voices.json are accepted), else they rotate."""
    v = _pick_voices(cfg, mode, run_no)
    if mode == "dialogue" and isinstance(cast, dict):
        by = {x["name"].lower(): x for x in cfg.get("voices") or []}
        for role in ("asker", "witness"):
            x = by.get(str(cast.get(role) or "").strip().lower())
            if x and x["id"] != v["expert"]["id"]:
                v[role] = x
    return v


def _pick_voices(cfg, mode, run_no):
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
    "expert": {"stability": 0.62, "similarity_boost": 0.8},
    "narrator": {"stability": 0.62, "similarity_boost": 0.8},
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


# What is SAID decides what is SEEN: real-estate terms of the spoken line -> stock-footage queries that show them.
# (owner feedback 2026-10-23: "title deed" must show someone reading property papers, never accounting sheets)
CONCEPTS = [
    (r"تصميم|التصميم|البلان|بلان|المهندس|مهندس|الهندسي|مكتب الدراسات|رخصة البناء", ["architect blueprint", "architect drawing plans", "engineer construction plans"]),
    (r"الورش|ورش|الشانطي|البني|بناء|البناء|المقاول", ["construction site worker", "building construction", "construction workers"]),
    (r"الموثق|موثق|العدول|عدول|العقد|عقد|توقيع|التوقيع|الكونطرا|كونطرا|سنيي", ["signing contract", "notary signing documents", "handshake contract"]),
    (r"الرسم|رسم|المحافظة|محافظة|التحفيظ|محفظ|الشهادة|شهادة|الملكية|ملكية|الوثائق|وثائق|الأوراق|الاوراق|الورقة|ورقة|الملف|ملف|الكاغيط",
     ["man reading documents", "couple reading documents", "woman reading papers", "checking documents"]),
    (r"العربون|عربون|خلص|خلّص|الخلاص|الفلوس|فلوس|درهم|الثمن|ثمن|السومة|ريال|مليون", ["cash money hands", "counting money", "paying cash"]),
    (r"الساروت|ساروت|المفاتيح|مفاتيح|السوارت", ["house keys hand", "keys new home", "giving keys"]),
    (r"البنك|بنك|القرض|قرض|الكريدي|كريدي|التمويل", ["bank loan meeting", "bank advisor client"]),
    (r"السمسار|سمسار|الوسيط|وسيط", ["real estate agent client", "agent showing house"]),
    (r"الكراء|كراء|كاري|المكتري|مكتري|الكاري", ["tenant apartment", "moving into apartment"]),
    (r"البحر|الشاطئ|البلاية|بلاية", ["beach sea view", "sea coast"]),
]
MONEY_Q = re.compile(r"\b(money|cash|bank|loan|tax|pay|paying|payment|price|budget|finance|counting)\b", re.I)
OFFICE_NOISE = {"accountant", "accounting", "financial", "finance", "chart", "charts", "graph", "graphs", "statistics",
                "analytics", "spreadsheet", "budget", "report", "data", "trading", "stock", "stocks", "diagram",
                "calculator", "invoice", "tax", "taxes", "economy", "profit", "analysis", "audit", "excel"}


def concept_queries(line):
    """Stock queries for the first real-estate term spoken in the line (earliest match wins)."""
    text = NORM.sub("", TAG.sub(" ", line or ""))   # harakat are for the voice only
    best = None
    for pat, qs in CONCEPTS:
        # whole words only (optional و/ف/ب/ل/ك prefix and pronoun suffix), so "معقد" never matches "عقد"
        m = re.search(r"(?<![\u0621-\u064A])[وفبلك]?(?:" + pat + r")(?:ها|هم|و|ك|نا|ي|ت|تي)?(?![\u0621-\u064A])", text)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), qs)
    return list(best[1]) if best else []


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
    want_person = bool(PERSON.search(query) or re.search(r"\b(couple|family|people|hands?|clerk|notary|lawyer|tenant)\b", query, re.I))

    def score(h):
        toks = re.findall(r"[a-z]+", h.get("tags", "").lower())
        return sum(1 for w in words if any(t.startswith(w[:5]) or w.startswith(t[:5]) for t in toks if len(t) > 2))

    def fresh(h):
        sig = (h.get("user_id"), h.get("tags"))
        toks = set(re.findall(r"[a-z]+", h.get("tags", "").lower()))
        noise = set() if MONEY_Q.search(query) else OFFICE_NOISE
        if want_person and not toks.intersection(HUMAN):
            return False                      # the query asks for a person: no empty paper / object shots
        return (h["id"] not in used and sig not in used and not toks.intersection(BAN) and not toks.intersection(avoid)
                and not toks.intersection(noise))

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
    # real footage first (reference style: moving video, photos only when no clip matches)
    cands.sort(key=lambda c: (c[2] != "video", -(c[0] + c[1]), -c[3].get("likes", 0)))
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


def pexels_pick(query, key, used, want, workdir, idx, avoid=()):
    """Optional second free source (PEXELS_API_KEY): portrait videos only, tags read from the page slug."""
    if not key or not query:
        return None
    try:
        q = urllib.parse.urlencode({"query": query[:90], "orientation": "portrait", "per_page": 20})
        vids = json.loads(http("https://api.pexels.com/videos/search?" + q, headers={"Authorization": key}, timeout=40)).get("videos") or []
    except Exception as e:
        log("pexels failed", query, e); return None
    words = [w for w in re.findall(r"[a-z]+", query.lower()) if len(w) > 2 and w not in STOP]
    need = min(2, len(words)) if words else 1
    noise = set() if MONEY_Q.search(query) else OFFICE_NOISE
    best = []
    for h in vids:
        toks = set(re.findall(r"[a-z]+", (h.get("url") or "").lower().rsplit("/video/", 1)[-1]))
        if ("px", h["id"]) in used or toks & set(BAN) or toks & set(avoid) or toks & noise or (h.get("duration") or 0) < min(want, 5):
            continue
        sc = sum(1 for w in words if any(t.startswith(w[:5]) or w.startswith(t[:5]) for t in toks if len(t) > 2))
        files = [f for f in h.get("video_files") or [] if (f.get("height") or 0) > (f.get("width") or 0) and 1000 <= (f.get("height") or 0) <= 2000]
        if sc >= need and files:
            best.append((sc, min(files, key=lambda f: abs(f["height"] - 1920))["link"], h))
    best.sort(key=lambda b: -b[0])
    for sc, url, h in best[:3]:
        try:
            dst = os.path.join(workdir, f"p{idx:02d}.mp4")
            open(dst, "wb").write(http(url, timeout=120))
            used.add(("px", h["id"]))
            log("visual", idx, "pexels", sc, query, "->", h.get("url"))
            return dst, "video"
        except Exception as e:
            log("pexels download failed", e)
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
              f"zoompan=z='min(1+0.0006*on,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={fr}:s={W}x{H}:fps={FPS},"
              f"{grade},{shade},format=yuv420p")
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", src, "-frames:v", str(fr), "-vf", vf]
    run(cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), dst])


# ---------------------------------------------------------------- brand layer
def round_badge(logo, dst, d=BADGE_D):
    """AQAR OF AFRICA logo inside a white round badge with a thin gold ring, visible on any footage."""
    if not logo or not os.path.exists(logo):
        return None
    from PIL import Image, ImageDraw
    k = 3                                   # supersampled, then reduced: smooth circle edge
    D = d * k
    im = Image.new("RGBA", (D, D), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    dr.ellipse([0, 0, D - 1, D - 1], fill=(232, 176, 75, 255))
    ring = int(D * 0.035)
    dr.ellipse([ring, ring, D - 1 - ring, D - 1 - ring], fill=(255, 255, 255, 250))
    lg = Image.open(logo).convert("RGBA")
    box = D * 0.64
    sc = min(box / lg.width, box / lg.height)
    lg = lg.resize((int(lg.width * sc), int(lg.height * sc)), Image.LANCZOS)
    im.alpha_composite(lg, ((D - lg.width) // 2, (D - lg.height) // 2 + int(D * 0.01)))
    im.resize((d, d), Image.LANCZOS).save(dst)
    return dst


def text_width(text, size):
    try:
        from PIL import ImageFont
        eng = ImageFont.Layout.RAQM if ImageFont.core.HAVE_RAQM else ImageFont.Layout.BASIC
        f = ImageFont.truetype(os.path.join(FONTS_DIR, "Tajawal-ExtraBold.ttf"), size, layout_engine=eng)
        return f.getlength(text)
    except Exception:
        return 0.5 * size * len(text)


def pill(w, h, r):
    """ASS vector drawing of a rounded rectangle (w x h, radius r)."""
    return (f"m {r} 0 l {w - r} 0 b {w} 0 {w} 0 {w} {r} l {w} {h - r} b {w} {h} {w} {h} {w - r} {h} "
            f"l {r} {h} b 0 {h} 0 {h} 0 {h - r} l 0 {r} b 0 0 0 0 {r} 0")


NORM = re.compile(r"[ً-ْـ]")
PUNCT = "،,.!؟?:;\"'«»()…-"


def norm(w):
    return NORM.sub("", w).strip(PUNCT).replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")


def keyword_marks(words, keywords):
    """Indices of the spoken words that belong to one of the scene keywords (exact phrase, in order)."""
    toks = [norm(w[0]) for w in words]
    marks = set()
    for kw in keywords or []:
        kt = [norm(x) for x in TAG.sub(" ", str(kw)).split() if norm(x)]
        if not kt:
            continue
        for i in range(len(toks) - len(kt) + 1):
            if toks[i:i + len(kt)] == kt:
                marks.update(range(i, i + len(kt)))
    return marks


def build_ass(scenes, title, total, path, body):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT},98,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H80000000&,0,0,0,0,100,100,0,0,1,7,3,2,60,60,640,-1
Style: Ord,{FONT},124,{GOLD_ASS},{GOLD_ASS},&H00000000&,&H80000000&,0,0,0,0,100,100,0,0,1,8,3,2,60,60,640,-1
Style: Title,{FONT},62,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,5,0,0,0,-1
Style: Box,{FONT},20,{NAVY_ASS},{NAVY_ASS},{GOLD_ASS},&H00000000&,0,0,0,0,100,100,0,0,1,3,0,7,0,0,0,1
Style: Who,{FONT},46,{GOLD_ASS},{GOLD_ASS},&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,4,0,2,60,60,800,-1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    add = lambda layer, a, b, st, tx: ev.append(f"Dialogue: {layer},{ass_time(a)},{ass_time(b)},{st},,0,0,0,,{tx}")
    # fixed title pill on top, whole body (reference: the topic stays on screen from the first to the last second)
    title = re.sub(r"\s+", " ", TAG.sub(" ", title or "")).strip()
    if title:
        size = 62
        while size > 40 and text_width(title, size) > W - 2 * BADGE_M - 2 * BADGE_D - 40:
            size -= 2
        tw = min(W - 80, max(320, int(text_width(title, size) + 2 * 46)))
        th = int(size * 1.75)
        ty = BADGE_M + BADGE_D + 34
        x0 = (W - tw) // 2
        add(4, 0, body, "Box", r"{\an7\pos(%d,%d)\1a&H22&\fad(300,0)\p1}" % (x0, ty) + pill(tw, th, th // 2) + r"{\p0}")
        add(5, 0, body, "Title", r"{\an5\pos(%d,%d)\fs%d\fad(300,0)}" % (W // 2, ty + th // 2 + 2, size) + esc(title))
    for s in scenes:
        t0, t1 = s["t0"], s["t0"] + s["dur"]
        who = ROLE_AR.get(s.get("speaker") or "narrator", "")
        if who and s.get("dialogue"):
            add(2, t0, t1, "Who", r"{\fad(100,100)}" + who)
        # reference style: no punctuation and no harakat on screen (the harakat only guide the voice)
        words = [(NORM.sub("", w).strip("،,.!؟?:;…\"'«»"), a + t0, b + t0) for w, a, b in s["words"] if esc(w.strip("،,.!؟?:;…\"'«»"))]
        marks = keyword_marks(words, s.get("keywords"))
        raw = [NORM.sub("", w) for w, _, _ in s["words"] if esc(NORM.sub("", w).strip("،,.!؟?:;…\"'«»"))]
        chunks, cur = [], []
        for i, w in enumerate(words):
            if ORDINAL.match(norm(w[0])):
                if cur:
                    chunks.append(cur); cur = []
                chunks.append([(i, w, True)])
                continue
            cur.append((i, w, False))
            chars = sum(len(x[1][0]) for x in cur)
            if len(cur) >= 3 or chars >= 16 or (i + 1 < len(raw) and re.search(r"[.!؟?،,:]$", raw[i])):
                chunks.append(cur); cur = []
        if cur:
            chunks.append(cur)
        for ci, ch in enumerate(chunks):
            a = ch[0][1][1]
            b = chunks[ci + 1][0][1][1] if ci + 1 < len(chunks) else t1
            if ch[0][2]:
                add(1, a, max(b, a + 0.4), "Ord", r"{\fad(80,0)\fscx88\fscy88\t(0,140,\fscx100\fscy100)}" + esc(ch[0][1][0]))
                continue
            txt = " ".join((r"{\c" + GOLD_ASS + "}" + esc(w[0]) + r"{\c&H00FFFFFF&}") if i in marks else esc(w[0])
                           for i, w, _ in ch)
            add(1, a, max(b, a + 0.25), "Cap", r"{\fad(60,0)\fscx94\fscy94\t(0,120,\fscx100\fscy100)}" + txt)
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
    voices = pick_voices(cfg, mode, a.run, plan.get("cast"))
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    pkey = os.environ.get("PIXABAY_API_KEY", "")
    xkey = os.environ.get("PEXELS_API_KEY", "")
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
        # the montage scenario (validated by the owner in the PDF) decides the shot; spoken-term concepts are only a fallback
        qs = [match_gender(q, g) for q in [s.get("visual"), s.get("visual_alt")] + concept_queries(s.get("line"))[:2] if q]
        avoid = OTHER_SEX.get(g, ()) if any(PERSON.search(x or "") for x in qs) else ()
        for q in qs + GENERIC.get(s.get("mood") or "neutral", GENERIC["neutral"]):
            got = pixabay_pick(q, pkey, used, s["dur"], a.work, i, avoid)
            if got and got[1] != "video":        # a photo only if no free source has a matching clip
                got = pexels_pick(q, xkey, used, s["dur"], a.work, i, avoid) or got
            elif not got:
                got = pexels_pick(q, xkey, used, s["dur"], a.work, i, avoid)
            if got:
                break
        got = got or brand_bg(os.path.join(a.work, f"bg{i:02d}.jpg"))
        kinds.append(got[1] if got[0] else "brand")
        c = os.path.join(a.work, f"c{i:02d}.mp4")
        scene_clip(got[0], got[1], s["dur"] + XF, s.get("mood"), c, i == 0)
        clips.append(c)
    ec = os.path.join(a.work, "end.jpg")
    end_card(ec, a.logo)
    endc = os.path.join(a.work, "cend.mp4")
    run(["ffmpeg", "-y", "-loop", "1", "-i", ec, "-t", f"{END}", "-vf",
         f"scale={W}:{H},zoompan=z='min(1+0.0008*on,1.04)':d={int(END*FPS)}:s={W}x{H}:fps={FPS},fade=t=in:d=0.35,format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-r", str(FPS), endc])
    clips.append(endc)
    total = body + END
    # soft dissolves: clip i lasts dur_i + XF and fades into clip i+1 exactly at scene i+1's start time
    vid = os.path.join(a.work, "video.mp4")
    starts = [s["t0"] for s in scenes[1:]] + [body]
    ins_v, fx, last = [], [], "0:v"
    for c in clips:
        ins_v += ["-i", c]
    for j, off in enumerate(starts, 1):
        fx.append(f"[{last}][{j}:v]xfade=transition=fade:duration={XF}:offset={off:.3f}[x{j}]")
        last = f"x{j}"
    run(["ffmpeg", "-y", *ins_v, "-filter_complex", ";".join(fx), "-map", f"[{last}]", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS), vid])

    # 3) captions + progress bar
    ass = os.path.join(a.work, "caps.ass")
    build_ass(scenes, (plan.get("title") or plan.get("hook") or "").strip(), total, ass, body)
    vtx = os.path.join(a.work, "vtx.mp4")
    bar = f"color=c=0xE8B04B:s={W}x12:r={FPS}"
    badge = round_badge(a.logo, os.path.join(a.work, "badge.png"))
    fc = (f"[0:v]ass={ass}:fontsdir={os.path.abspath(FONTS_DIR)}[c];"
          f"[c][1:v]overlay=x='-W+W*t/{body:.2f}':y=0:enable='lt(t,{body:.2f})':shortest=1")
    fc = fc + (f"[pb];[pb][2:v]overlay=x=W-w-{BADGE_M}:y={BADGE_M}:enable='lt(t,{body:.2f})'[v]" if badge else "[v]")
    run(["ffmpeg", "-y", "-i", vid, "-f", "lavfi", "-i", bar, *(["-i", badge] if badge else []), "-filter_complex", fc,
         "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), vtx])

    # 4) audio: voice lines at their times + situational sfx + ducked calm music
    ins, parts, labels = [], [], []
    k = 0
    for s in scenes:
        if s.get("audio"):
            ins += ["-i", s["audio"]]
            ms = int(s["t0"] * 1000)
            parts.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{k}]")
            labels.append(f"[a{k}]"); k += 1
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
                     f"volume={MUSIC_VOL},afade=t=in:d=1,afade=t=out:st={total - 2.5:.2f}:d=2.5[mus]")
        parts.append("[vo]asplit=2[vo1][key]")
        parts.append("[mus][key]sidechaincompress=threshold=0.015:ratio=14:attack=10:release=500[duck]")
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
                      "voices": sorted({(voices.get(s.get("speaker") or "narrator") or voices["narrator"])["name"] for s in scenes}),
                      "credits_left": credits_left(key) if key else None, "visuals": kinds}, ensure_ascii=False))


if __name__ == "__main__":
    main()
