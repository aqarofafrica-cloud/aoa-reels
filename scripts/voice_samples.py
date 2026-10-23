#!/usr/bin/env python3
"""AQAR OF AFRICA - voice casting: rank the Moroccan/Arabic voices of the ElevenLabs library and render the same
Darija lines with each candidate (several models), so the owner can choose by ear.
Output: branch 'previews', folder <stamp>-voices/ with one mp3 per voice x model + ranking.txt"""
import base64, json, os, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import video_pipeline as vp
from tips2_pipeline import publish_fresh

KEY = os.environ.get("ELEVENLABS_API_KEY", "")
H = {"xi-api-key": KEY, "User-Agent": "Mozilla/5.0 (AOA voices)"}
EXPERT = ("خلّيني نقولّيك واحد الحاجة مهمّة. قبل ما تعرض الدار ديالك، وَجّد المِلفّ القانوني ديالها كامل: "
          "الشهادة العقارية، رخصة السكن، وإبراء الذمّة. هادشي هو اللي كيخلّي المشتري يرتاح ويثق فيك.")
ASKER = "بصراحة، أنا خايف نبيع الدار ونندم من بعد... شنو خاصّني نعرف قبل ما نبدا؟"
MODELS = os.environ.get("MODELS", "eleven_multilingual_v2,eleven_v3").split(",")


def req(url, method="GET", body=None):
    r = urllib.request.Request(url, method=method, data=body, headers={**H, **({"Content-Type": "application/json"} if body else {})})
    with urllib.request.urlopen(r, timeout=180) as resp:
        return resp.read()


def shared(params):
    q = urllib.parse.urlencode({"page_size": 100, **params})
    return json.loads(req("https://api.elevenlabs.io/v1/shared-voices?" + q)).get("voices", [])


def main():
    found = {}
    for params in ({"language": "ar", "accent": "moroccan"}, {"language": "ar", "search": "moroccan"},
                   {"language": "ar", "search": "darija"}):
        try:
            for v in shared(params):
                found[v["voice_id"]] = v
        except Exception as e:
            vp.log("shared voices failed", params, e)
    vs = sorted(found.values(), key=lambda v: (v.get("category") != "professional", -(v.get("cloned_by_count") or 0),
                                               -(v.get("usage_character_count_1y") or 0)))
    lines = []
    for v in vs:
        lines.append(" | ".join(str(x) for x in (v.get("name"), v.get("voice_id"), v.get("gender"), v.get("age"),
                                                 v.get("accent"), v.get("category"), v.get("cloned_by_count"),
                                                 v.get("usage_character_count_1y"), v.get("use_case"))))
    vp.log("\n".join(lines))
    top = int(os.environ.get("TOP", "10"))
    os.makedirs("work/vs", exist_ok=True)
    files = {}
    stamp = time.strftime("%Y%m%d%H%M%S") + "-voices"
    open("work/vs/ranking.txt", "w").write("\n".join(lines))
    files[f"{stamp}/ranking.txt"] = "work/vs/ranking.txt"
    for i, v in enumerate(vs[:top], 1):
        text = EXPERT if (v.get("age") in ("middle_aged", "old") or i % 2) else ASKER + " " + EXPERT
        for m in MODELS:
            body = {"text": text, "model_id": m}
            if m != "eleven_v3":
                body["voice_settings"] = {"stability": 0.45, "similarity_boost": 0.8, "style": 0.35, "use_speaker_boost": True}
            try:
                audio = req(f"https://api.elevenlabs.io/v1/text-to-speech/{v['voice_id']}?output_format=mp3_44100_128",
                            "POST", json.dumps(body).encode())
                name = f"{i:02d}-{v.get('name','voice').split(' ')[0]}-{v.get('gender','')}-{m.replace('eleven_','')}.mp3"
                p = f"work/vs/{name}"
                open(p, "wb").write(audio)
                files[f"{stamp}/{name}"] = p
            except Exception as e:
                vp.log("tts failed", v.get("name"), m, e)
    vp.git_identity()
    publish_fresh(files, "voice samples")
    vp.log("folder:", stamp)


if __name__ == "__main__":
    main()
