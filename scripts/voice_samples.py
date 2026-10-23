#!/usr/bin/env python3
"""AQAR OF AFRICA - voice casting v2.
Renders the same natural Darija line (expert / agency voice: calm, reassuring) with every Moroccan candidate
voice on several ElevenLabs models, then assembles ONE labeled video (number + name + model card per clip)
so the owner can choose by ear. Output on branch 'previews': <stamp>-voices/casting.mp4, list.txt, mp3 files."""
import json, os, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import video_pipeline as vp
from tips2_pipeline import publish_fresh

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
H = {"xi-api-key": KEY, "User-Agent": "Mozilla/5.0 (AOA voices)"}
# Spoken Moroccan Darija, written the way it is said (no MSA words), short breath groups.
LINE = ("[calm] شوف، ما تخافش. [reassuring] قبل ما تخلّص حتى ريال، طلب الشهادة ديال المحافظة، "
        "وتأكّد بلّي الرسم سميتو هو... هاكّا غادي تبقى مرتاح، والحق ديالك مضمون.")
MODELS = ["eleven_v4"]   # owner decision: Eleven v4 only
BASE = [("Ghizlane", "OfGMGmhShO8iL9jCkXy8", "F"), ("Loubna", "C5sH6vPhsC46AKaQmXXJ", "F"),
        ("Tariq", "hiDWCdbsrOy64l833ab2", "M"), ("Jawad", "PmGnwGtnBs40iau7JfoF", "M"),
        ("Radi", "eTfPFOvJJdhsKezAqEZm", "M"), ("Hamid", "A9ATTqUUQ6GHu0coCz8t", "M"),
        ("Houssam", "NMWQDQipWXm8HlCLKapi", "M"), ("Ali", "5lXEHh42xcasVuJofypc", "M"),
        ("Anas", "JyOZ8fOJkYGmajIlFsJ4", "M"), ("Khalil", "NrhVFquWMOHTRNOAY8AO", "M"),
        ("Yassine", "H6pm0ljbvfqt4fzJd9Py", "M"), ("Rachid", "0Up3glsGKvZx3M5JI0XB", "M"),
        ("Mehdi", "Vsm8jlUqY4LxvQNtr7R6", "M"), ("Abdelhadi", "cdfQ4039m26btcsBkvxH", "M")]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method, data=body,
                               headers={**H, **({"Content-Type": "application/json"} if body else {})})
    with urllib.request.urlopen(r, timeout=180) as resp:
        return resp.read()


def credits():
    try:
        j = json.loads(req("https://api.elevenlabs.io/v1/user/subscription"))
        return int(j.get("character_limit", 0)) - int(j.get("character_count", 0))
    except Exception as e:
        vp.log("credits check failed", e); return None


def extra_females(have):
    out = []
    for params in ({"language": "ar", "accent": "moroccan", "gender": "female"},
                   {"language": "ar", "search": "darija", "gender": "female"},
                   {"language": "ar", "search": "moroccan", "gender": "female"}):
        try:
            q = urllib.parse.urlencode({"page_size": 50, **params})
            for v in json.loads(req("https://api.elevenlabs.io/v1/shared-voices?" + q)).get("voices", []):
                acc = (v.get("accent") or "").lower()
                if v["voice_id"] not in have and "moroc" in acc + (v.get("description") or "").lower():
                    have.add(v["voice_id"])
                    out.append((v.get("name", "F").split(" ")[0], v["voice_id"], "F"))
        except Exception as e:
            vp.log("search failed", params, e)
    return out[:3]


def card(path, num, name, sex, model):
    from PIL import Image, ImageDraw, ImageFont
    im = Image.new("RGB", (1280, 720), (12, 28, 48))
    d = ImageDraw.Draw(im)
    big, mid = ImageFont.truetype(FONT, 230), ImageFont.truetype(FONT, 86)
    d.text((640, 250), f"{num:02d}", font=big, fill=(212, 175, 55), anchor="mm")
    d.text((640, 470), f"{name}  ({sex})", font=mid, fill=(255, 255, 255), anchor="mm")
    d.text((640, 590), model.replace("eleven_", ""), font=mid,
           fill=(150, 190, 230), anchor="mm")
    im.save(path)


def main():
    os.makedirs("work/vs", exist_ok=True)
    before = credits()
    vp.log("credits before:", before)
    voices = BASE + extra_females({v[1] for v in BASE})
    need = len(voices) * len(MODELS) * len(LINE)
    if before is not None and before < need + 3000:
        raise SystemExit(f"not enough credits: {before} < {need + 3000}")
    stamp = time.strftime("%Y%m%d%H%M%S") + "-voices"
    files, segs, rows = {}, [], []
    for i, (name, vid, sex) in enumerate(voices, 1):
        for m in MODELS:
            body = {"text": LINE, "model_id": m, "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}
            short = m.replace("eleven_", "")
            mp3 = f"work/vs/{i:02d}-{name}-{short}.mp3"
            try:
                open(mp3, "wb").write(req(f"https://api.elevenlabs.io/v1/text-to-speech/{vid}?output_format=mp3_44100_128",
                                          "POST", json.dumps(body).encode()))
            except Exception as e:
                msg = e.read().decode()[:200] if hasattr(e, "read") else str(e)
                vp.log("tts failed", name, m, msg); rows.append(f"{i:02d} {name} {short}: FAILED {msg}"); continue
            files[f"{stamp}/{os.path.basename(mp3)}"] = mp3
            png, ts = mp3[:-4] + ".png", mp3[:-4] + ".ts"
            card(png, i, name, sex, m)
            vp.sh("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-framerate", "2", "-i", png, "-i", mp3,
                  "-af", "apad=pad_dur=0.8", "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p",
                  "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-shortest", "-f", "mpegts", ts)
            segs.append(ts)
            rows.append(f"{i:02d} {name} ({sex}) {short}: {vid}")
    after = credits()
    rows += ["", f"credits before: {before}", f"credits after: {after}", "", "text: " + LINE]
    open("work/vs/list.txt", "w").write("\n".join(rows))
    files[f"{stamp}/list.txt"] = "work/vs/list.txt"
    if segs:
        vp.sh("ffmpeg", "-y", "-loglevel", "error", "-i", "concat:" + "|".join(segs), "-c", "copy",
              "-movflags", "+faststart", "work/vs/casting.mp4")
        files[f"{stamp}/casting.mp4"] = "work/vs/casting.mp4"
    vp.log("\n".join(rows))
    vp.git_identity()
    publish_fresh(files, "voice casting")
    vp.log("folder:", stamp)


if __name__ == "__main__":
    main()
