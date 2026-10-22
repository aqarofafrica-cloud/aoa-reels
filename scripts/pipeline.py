#!/usr/bin/env python3
"""AQAR OF AFRICA reel pipeline (GitHub Actions).
1) read job payload  2) download photos  3) pick music (rotation)  4) render reel
5) publish the mp4 on branch 'videos' (public raw URL)  6) wait until target time  7) call Make webhook."""
import base64, json, os, subprocess, sys, time, urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "aqarofafrica-cloud/aoa-reels")
RUN = int(os.environ.get("GITHUB_RUN_NUMBER", "1"))
HOOK = os.environ.get("MAKE_HOOK_URL", "").strip()
UA = {"User-Agent": "Mozilla/5.0 (AOA reels bot)"}

def log(*a):
    print(*a, flush=True)

def payload():
    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    p = ev.get("client_payload") or {}
    if not p and ev.get("inputs", {}).get("payload"):
        p = json.loads(ev["inputs"]["payload"])
    return p

def fetch(url, dst):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r, open(dst, "wb") as f:
        f.write(r.read())
    return dst

def callback(data):
    if not HOOK:
        log("no MAKE_HOOK_URL, skip callback", data); return
    req = urllib.request.Request(HOOK, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", **UA})
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                log("callback", r.status); return
        except Exception as e:
            log("callback error", e); time.sleep(10)

def sh(*cmd):
    subprocess.run(cmd, check=True)

def main():
    p = payload()
    job = str(p.get("job") or f"manual-{RUN}")
    media = p.get("media") or []
    if isinstance(media, str):
        media = json.loads(media)
    urls = p.get("images") or []
    for m in media:
        if isinstance(m, dict) and m.get("url"):
            urls.append(m["url"])
        elif isinstance(m, dict) and m.get("id"):
            urls.append("https://media.nuelink.com/media/" + m["id"])
    target = float(p.get("target_ts") or 0)
    os.makedirs("work", exist_ok=True)
    try:
        imgs = []
        for i, u in enumerate(urls[:10]):
            try:
                imgs.append(fetch(u, f"work/p{i:02d}.jpg"))
            except Exception as e:
                log("photo failed", u, e)
        if not imgs:
            raise RuntimeError("no photo could be downloaded")
        tracks = [l.strip().split("|", 1) for l in open("assets/tracks.txt") if l.strip() and not l.startswith("#")]
        name, turl = tracks[RUN % len(tracks)]
        music = None
        try:
            music = fetch(turl, "work/music.mp3")
        except Exception as e:
            log("music failed, video without music", e); name = "none"
        open("work/logo.png", "wb").write(base64.b64decode(open("assets/logo.b64").read()))
        out = f"work/{job}.mp4"
        cmd = ["python3", "scripts/render_reel.py", "--out", out, "--logo", "work/logo.png"]
        if music:
            cmd += ["--music", music]
        sh(*cmd, *imgs)
        # publish on branch 'videos' (keep the 30 latest)
        sh("git", "config", "user.name", "aoa-bot")
        sh("git", "config", "user.email", "aoa-bot@users.noreply.github.com")
        exists = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", "videos"]).returncode == 0
        if exists:
            sh("git", "fetch", "--depth", "1", "origin", "videos")
            sh("git", "worktree", "add", "vid", "FETCH_HEAD")
            sh("git", "-C", "vid", "checkout", "-B", "videos")
        else:
            sh("git", "worktree", "add", "--detach", "vid")
            sh("git", "-C", "vid", "checkout", "--orphan", "videos")
            subprocess.run(["git", "-C", "vid", "rm", "-rf", "--quiet", "."])
        sh("cp", out, f"vid/{job}.mp4")
        vids = sorted([f for f in os.listdir("vid") if f.endswith(".mp4")], key=lambda f: f)
        for old in vids[:-30]:
            os.remove(os.path.join("vid", old))
        sh("git", "-C", "vid", "add", "-A")
        sh("git", "-C", "vid", "commit", "-q", "-m", f"reel {job}")
        for attempt in range(6):
            if subprocess.run(["git", "-C", "vid", "push", "origin", "videos"]).returncode == 0:
                break
            time.sleep(5)
            subprocess.run(["git", "-C", "vid", "pull", "--rebase", "origin", "videos"])
        else:
            raise RuntimeError("could not push video")
        video_url = f"https://raw.githubusercontent.com/{REPO}/videos/{job}.mp4"
        wait = target - time.time()
        if wait > 0:
            wait = min(wait, 28 * 60)
            log(f"waiting {int(wait)} s until publish time"); time.sleep(wait)
        callback({"job": job, "status": "ok", "video_url": video_url, "track": name, "photos": len(imgs)})
    except Exception as e:
        log("FAILED", e)
        callback({"job": job, "status": "error", "error": str(e)[:300]})
        sys.exit(1)

if __name__ == "__main__":
    main()
