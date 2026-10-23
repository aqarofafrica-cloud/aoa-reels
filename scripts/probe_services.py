#!/usr/bin/env python3
"""AQAR OF AFRICA - one-off probe of the new services (no secrets printed).
Checks: ElevenLabs (credits, models, voices, a short Darija TTS with timestamps),
Pixabay (video + photo search), Nuelink (media upload response shape, no post created)."""
import base64, json, os, urllib.request, urllib.parse, io

UA = {"User-Agent": "Mozilla/5.0 (AOA probe)"}


def log(*a):
    print(*a, flush=True)


def req(url, method="GET", headers=None, data=None, timeout=60):
    r = urllib.request.Request(url, method=method, headers={**UA, **(headers or {})}, data=data)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def shape(o, depth=0):
    """Keys/types only, never values."""
    if depth > 3:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:30]}
    if isinstance(o, list):
        return [shape(o[0], depth + 1)] if o else []
    return type(o).__name__


def eleven():
    k = os.environ.get("ELEVENLABS_API_KEY", "")
    log("== ElevenLabs key present:", bool(k))
    if not k:
        return
    h = {"xi-api-key": k}
    s, b = req("https://api.elevenlabs.io/v1/user/subscription", headers=h)
    if s == 200:
        j = json.loads(b)
        log("subscription:", j.get("tier"), "used", j.get("character_count"), "of", j.get("character_limit"))
    else:
        log("subscription status", s, b[:200])
    s, b = req("https://api.elevenlabs.io/v1/models", headers=h)
    if s == 200:
        for m in json.loads(b):
            langs = [l.get("language_id") for l in m.get("languages", [])]
            log("model", m.get("model_id"), "| arabic:", "ar" in langs, "| tts:", m.get("can_do_text_to_speech"))
    else:
        log("models status", s, b[:200])
    s, b = req("https://api.elevenlabs.io/v2/voices?page_size=50", headers=h)
    if s == 200:
        for v in json.loads(b).get("voices", []):
            lab = v.get("labels") or {}
            log("my voice:", v.get("name"), v.get("voice_id"), v.get("category"), lab.get("accent"), lab.get("language"), lab.get("gender"))
    else:
        log("voices status", s, b[:200])
    q = urllib.parse.urlencode({"page_size": 30, "language": "ar", "accent": "moroccan"})
    s, b = req("https://api.elevenlabs.io/v1/shared-voices?" + q, headers=h)
    if s == 200:
        for v in json.loads(b).get("voices", [])[:30]:
            log("library:", v.get("name"), v.get("voice_id"), v.get("gender"), v.get("age"), v.get("accent"), v.get("use_case"))
    else:
        log("shared voices status", s, b[:200])
    text = "أول حاجة كتحرق العقار هي الثمن المنفوخ. الثمن خاصو يتبنى على المقارنة مع عقارات تباعت فعلا فنفس الحي."
    for model in ("eleven_v3", "eleven_multilingual_v2"):
        body = json.dumps({"text": text, "model_id": model}).encode()
        s, b = req("https://api.elevenlabs.io/v1/text-to-speech/OfGMGmhShO8iL9jCkXy8/with-timestamps",
                   "POST", {**h, "Content-Type": "application/json"}, body, 120)
        if s == 200:
            j = json.loads(b)
            audio = base64.b64decode(j["audio_base64"])
            open(f"probe_{model}.mp3", "wb").write(audio)
            al = j.get("alignment") or {}
            ends = al.get("character_end_times_seconds") or [0]
            log("tts", model, "OK bytes", len(audio), "duration~", ends[-1])
        else:
            log("tts", model, "status", s, b[:300])


def pixabay():
    k = os.environ.get("PIXABAY_API_KEY", "")
    log("== Pixabay key present:", bool(k))
    if not k:
        return
    for kind, q in (("videos/", "notary signing contract"), ("videos/", "happy family new home"), ("", "worried man money")):
        s, b = req(f"https://pixabay.com/api/{kind}?" + urllib.parse.urlencode({"key": k, "q": q, "per_page": 5, "safesearch": "true"}))
        if s == 200:
            j = json.loads(b)
            log("pixabay", kind or "photos", repr(q), "total", j.get("totalHits"), "first:", shape(j["hits"][0]) if j.get("hits") else None)
        else:
            log("pixabay", q, "status", s)


def nuelink():
    k = os.environ.get("NUELINK_API_KEY", "")
    log("== Nuelink key present:", bool(k))
    if not k:
        return
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (12, 18, 32)).save(buf, "PNG")
    bnd = "----aoaprobe"
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"probe.png\"\r\n"
            f"Content-Type: image/png\r\n\r\n").encode() + buf.getvalue() + f"\r\n--{bnd}--\r\n".encode()
    s, b = req("https://nuelink.com/api/public/v1/brands/24728/media", "POST",
               {"Authorization": "Bearer " + k, "Content-Type": "multipart/form-data; boundary=" + bnd, "Accept": "application/json"}, body)
    log("nuelink media upload status", s)
    try:
        j = json.loads(b)
        log("nuelink response shape:", json.dumps(shape(j)))
        d = j.get("data") or {}
        url = d.get("url") or d.get("path") or ""
        log("has url:", bool(url), "| url host:", urllib.parse.urlparse(url).netloc if url else None)
    except Exception:
        log("non-json", b[:200])


if __name__ == "__main__":
    for f in (eleven, pixabay, nuelink):
        try:
            f()
        except Exception as e:
            log("ERROR", f.__name__, type(e).__name__, str(e)[:200])
