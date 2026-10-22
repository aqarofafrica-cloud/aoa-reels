#!/usr/bin/env python3
"""AQAR OF AFRICA - advice content pipeline (GitHub Actions, event 'tips').
Payload: {job, callback, plan}. Renders carousel + story cards + reel, publishes them on branch 'tips',
calls back Make with the public URLs (and ready-to-use Nuelink media arrays)."""
import base64, json, os, subprocess, sys, time

import video_pipeline as vp

REPO = vp.REPO
RUN = vp.RUN


def main():
    kind, p = vp.event()
    job = str(p.get("job") or f"manual-{RUN}")
    cb = p.get("callback") or ""
    os.makedirs("work", exist_ok=True)
    vp.git_identity()
    try:
        plan = p.get("plan") or {}
        if isinstance(plan, str):
            plan = json.loads(plan)
        json.dump(plan, open("work/plan.json", "w", encoding="utf-8"), ensure_ascii=False)
        open("work/logo.png", "wb").write(base64.b64decode(open("assets/logo.b64").read()))
        tracks = [l.strip().split("|", 1) for l in open("assets/tracks.txt") if l.strip() and not l.startswith("#")]
        name, turl = tracks[RUN % len(tracks)]
        cmd = ["python3", "scripts/render_tips.py", "--plan", "work/plan.json", "--out", "work/tips", "--logo", "work/logo.png"]
        try:
            cmd += ["--music", vp.fetch(turl, "work/music.mp3")]
        except Exception as e:
            vp.log("music failed", e); name = "none"
        out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout
        info = json.loads(out.strip().splitlines()[-1])
        folder = time.strftime("%Y%m%d%H%M%S") + "-" + job
        files = {f"{folder}/{f}": f"work/tips/{f}" for f in info["carousel"] + info["stories"] + [info["reel"]]}
        vp.publish("tips", files, 15, f"tips {job}")
        base = f"https://raw.githubusercontent.com/{REPO}/tips/{folder}/"
        car = [base + f for f in info["carousel"]]
        sto = [base + f for f in info["stories"]]
        vp.callback(cb, {"job": job, "kind": "render", "status": "ok", "cover_url": car[0],
                         "carousel_media": json.dumps([{"url": u} for u in car]),
                         "story_media": json.dumps([{"url": u} for u in sto]),
                         "reel_url": base + info["reel"], "seconds": info["seconds"], "cards": len(car),
                         "track": name})
    except Exception as e:
        vp.log("FAILED", e)
        vp.callback(cb, {"job": job, "kind": "render", "status": "error", "error": str(e)[:300]})
        sys.exit(1)


if __name__ == "__main__":
    main()
