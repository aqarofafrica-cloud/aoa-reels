#!/usr/bin/env python3
"""AQAR OF AFRICA - advice pipeline v2 (GitHub Actions).

Event 'tipsdoc' payload {job, callback, text_path, date}:
    read the validated-to-be master script from branch 'incoming' (text_path), render the branded PDF,
    put it on branch 'previews' (history-free, last 6 jobs only), call back {kind:"doc", pdf_path}.
Event 'tips2' payload {job, callback, plan, test?}:
    plan = {title, subtitle, tips[{heading, body}], cta, reel{mode, hook, scenes[...]}}
    render carousel (cover + tips + agency card, max 10) + story cards + voiced reel,
    upload the publishable media straight to Nuelink (nothing kept on GitHub except a light preview),
    call back {kind:"render", carousel_media, story_media, reel_media, preview_path, seconds, ...}.
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

import video_pipeline as vp

REPO = vp.REPO
RUN = vp.RUN
NUE = "https://nuelink.com/api/public/v1/brands/24728/media"
KEEP = 6


def nuelink_upload(path, mime):
    key = os.environ.get("NUELINK_API_KEY", "")
    if not key:
        raise RuntimeError("NUELINK_API_KEY missing")
    bnd = "----aoa" + str(int(time.time() * 1000))
    name = os.path.basename(path)
    body = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"media\"; filename=\"{name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{bnd}--\r\n".encode()
    last = None
    for wait in (0, 20, 45):
        time.sleep(wait)
        req = urllib.request.Request(NUE, method="POST", data=body, headers={
            "Authorization": "Bearer " + key, "Accept": "application/json",
            "Content-Type": "multipart/form-data; boundary=" + bnd, "User-Agent": "Mozilla/5.0 (AOA reels bot)"})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["data"]["id"]
        except Exception as e:
            last = e
            vp.log("nuelink upload retry", name, e)
    raise RuntimeError(f"nuelink upload failed for {name}: {last}")


def publish_fresh(files, msg):
    """Branch 'previews' without history: keep the last KEEP job folders + the new files, force-push one orphan commit."""
    wt = "wt_previews"
    shutil.rmtree(wt, ignore_errors=True)
    os.makedirs(wt)
    if subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", "previews"]).returncode == 0:
        vp.sh("git", "fetch", "--depth", "1", "origin", "previews")
        tree = subprocess.run(["git", "archive", "FETCH_HEAD"], check=True, stdout=subprocess.PIPE).stdout
        subprocess.run(["tar", "-x", "-C", wt], input=tree, check=True)
    for rel, src in files.items():
        os.makedirs(os.path.dirname(os.path.join(wt, rel)), exist_ok=True)
        shutil.copy(src, os.path.join(wt, rel))
    dirs = sorted(d for d in os.listdir(wt) if not d.startswith("."))
    for old in dirs[:-KEEP]:
        shutil.rmtree(os.path.join(wt, old), ignore_errors=True)
    vp.sh("git", "-C", wt, "init", "-q", "-b", "previews")
    vp.sh("git", "-C", wt, "add", "-A")
    vp.sh("git", "-C", wt, "commit", "-q", "-m", msg)
    url = subprocess.run(["git", "remote", "get-url", "origin"], check=True, stdout=subprocess.PIPE, text=True).stdout.strip()
    hdr = subprocess.run(["git", "config", "--get-regexp", "http.*extraheader"], stdout=subprocess.PIPE, text=True).stdout.split("\n")[0]
    args = ["git", "-C", wt]
    if hdr:
        k, v = hdr.split(" ", 1)
        args += ["-c", f"{k}={v}"]
    vp.sh(*args, "push", "-f", url, "previews")


def logo_file():
    open("work/logo.png", "wb").write(base64.b64decode(open("assets/logo.b64").read()))
    return "work/logo.png"


def music_file():
    tracks = [l.strip().split("|", 1) for l in open("assets/tracks.txt") if l.strip() and not l.startswith("#")]
    name, url = tracks[RUN % len(tracks)]
    try:
        return name, vp.fetch(url, "work/music.mp3")
    except Exception as e:
        vp.log("music failed", e)
        return "none", None


def do_doc(job, p, cb):
    path = p.get("text_path") or ""
    vp.get_incoming(path, "work/master.txt")
    pdf = "work/script.pdf"
    subprocess.run(["python3", "scripts/render_doc.py", "--text", "work/master.txt", "--out", pdf,
                    "--logo", logo_file(), "--date", p.get("date") or time.strftime("%Y-%m-%d")], check=True)
    folder = time.strftime("%Y%m%d%H%M%S") + "-" + job
    rel = f"{folder}/AQAR-OF-AFRICA-{job}.pdf"
    publish_fresh({rel: pdf}, f"doc {job}")
    vp.callback(cb, {"job": job, "kind": "doc", "status": "ok", "pdf_path": rel, "pdf_name": os.path.basename(rel)})


def do_render(job, p, cb):
    plan = p.get("plan") or {}
    if isinstance(plan, str):
        plan = json.loads(plan)
    reel = plan.get("reel") or {}
    if isinstance(reel, str):
        reel = json.loads(reel)
    json.dump(plan, open("work/plan.json", "w", encoding="utf-8"), ensure_ascii=False)
    json.dump(reel, open("work/reel.json", "w", encoding="utf-8"), ensure_ascii=False)
    logo = logo_file()
    track, music = music_file()
    # cards: carousel 1080x1350 + story 1080x1920 (render_tips keeps cover + <=8 tips + agency card)
    cmd = ["python3", "scripts/render_tips.py", "--plan", "work/plan.json", "--out", "work/cards", "--logo", logo]
    info = json.loads(subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()[-1])
    # voiced reel
    cmd = ["python3", "scripts/render_tips_reel.py", "--plan", "work/reel.json", "--out", "work/reel.mp4",
           "--preview", "work/preview.mp4", "--work", "work/reel", "--logo", logo]
    if music:
        cmd += ["--music", music]
    if p.get("voices"):          # manual test: try a casting without touching assets/voices.json
        json.dump(p["voices"], open("work/voices.json", "w", encoding="utf-8"), ensure_ascii=False)
        cmd += ["--voices", "work/voices.json"]
    rinfo = json.loads(subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout.strip().splitlines()[-1])
    # publishable media -> Nuelink only
    car = [{"id": nuelink_upload(f"work/cards/{f}", "image/png")} for f in info["carousel"]]
    sto = [{"id": nuelink_upload(f"work/cards/{f}", "image/png")} for f in info["stories"]]
    reel_id = nuelink_upload("work/reel.mp4", "video/mp4")
    # light preview for WhatsApp (video + cover card), history-free branch
    folder = time.strftime("%Y%m%d%H%M%S") + "-" + job
    files = {f"{folder}/preview.mp4": "work/preview.mp4", f"{folder}/cover.png": f"work/cards/{info['carousel'][0]}"}
    publish_fresh(files, f"preview {job}")
    vp.callback(cb, {"job": job, "kind": "render", "status": "ok",
                     "carousel_media": json.dumps(car), "story_media": json.dumps(sto),
                     "reel_media": json.dumps([{"id": reel_id}]),
                     "preview_path": f"{folder}/preview.mp4", "cover_path": f"{folder}/cover.png",
                     "cards": len(car), "seconds": rinfo.get("seconds"), "voice_ok": rinfo.get("voice_ok"),
                     "voices": ", ".join(rinfo.get("voices") or []), "credits_left": rinfo.get("credits_left"),
                     "mode": rinfo.get("mode"), "track": track})


def main():
    kind, p = vp.event()
    job = str(p.get("job") or f"manual-{RUN}")
    cb = p.get("callback") or ""
    os.makedirs("work", exist_ok=True)
    vp.git_identity()
    try:
        if kind == "tipsdoc":
            do_doc(job, p, cb)
        else:
            do_render(job, p, cb)
    except Exception as e:
        vp.log("FAILED", e)
        vp.callback(cb, {"job": job, "kind": "doc" if kind == "tipsdoc" else "render", "status": "error", "error": str(e)[:300]})
        sys.exit(1)


if __name__ == "__main__":
    main()
