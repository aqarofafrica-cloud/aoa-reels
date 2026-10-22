#!/usr/bin/env python3
"""AQAR OF AFRICA - real video pipeline (GitHub Actions).

Event 'vframes': take the uploaded walkthrough (branch 'incoming'), extract dated frames for Claude,
                 publish them on branch 'frames', call back Make with their public URLs.
Event 'vrender': render the montage from Claude's plan, publish final + preview on branch 'videos',
                 call back Make with both URLs.
Payload: {job, video_path, callback, plan?}
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

REPO = os.environ.get("GITHUB_REPOSITORY", "aqarofafrica-cloud/aoa-reels")
RUN = int(os.environ.get("GITHUB_RUN_NUMBER", "1"))
RAW = f"https://raw.githubusercontent.com/{REPO}"
UA = {"User-Agent": "Mozilla/5.0 (AOA video bot)"}


def log(*a):
    print(*a, flush=True)


def sh(*cmd, check=True):
    return subprocess.run(cmd, check=check)


def event():
    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    p = ev.get("client_payload") or {}
    if not p and ev.get("inputs", {}).get("payload"):
        p = json.loads(ev["inputs"]["payload"])
    kind = ev.get("action") or p.get("kind") or ""
    return kind, p


def fetch(url, dst):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    return dst


def callback(url, data):
    if not url:
        log("no callback url", data); return
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json", **UA})
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                log("callback", r.status); return
        except Exception as e:
            log("callback error", e); time.sleep(10)


def git_identity():
    sh("git", "config", "--global", "user.name", "aoa-bot")
    sh("git", "config", "--global", "user.email", "aoa-bot@users.noreply.github.com")


def get_incoming(path, dst):
    """Read the uploaded video from branch 'incoming' (fresh, no CDN cache)."""
    sh("git", "fetch", "--depth", "1", "origin", "incoming")
    with open(dst, "wb") as f:
        subprocess.run(["git", "show", f"FETCH_HEAD:{path}"], check=True, stdout=f)
    return dst


def publish(branch, files, keep_prefix_count, msg):
    """Add files {dest_rel_path: local_path} to branch, keep the N most recent top-level entries."""
    wt = f"wt_{branch}"
    if os.path.exists(wt):
        sh("git", "worktree", "remove", "--force", wt, check=False)
    exists = subprocess.run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch]).returncode == 0
    if exists:
        sh("git", "fetch", "--depth", "1", "origin", branch)
        sh("git", "worktree", "add", "-f", wt, "FETCH_HEAD")
        sh("git", "-C", wt, "checkout", "-B", branch)
    else:
        sh("git", "worktree", "add", "--detach", wt)
        sh("git", "-C", wt, "checkout", "--orphan", branch)
        subprocess.run(["git", "-C", wt, "rm", "-rf", "--quiet", "."])
    for rel, src in files.items():
        os.makedirs(os.path.dirname(os.path.join(wt, rel)) or wt, exist_ok=True)
        shutil.copy(src, os.path.join(wt, rel))
    entries = sorted([e for e in os.listdir(wt) if not e.startswith(".")])
    for old in entries[:-keep_prefix_count]:
        p = os.path.join(wt, old)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)
    sh("git", "-C", wt, "add", "-A")
    sh("git", "-C", wt, "commit", "-q", "-m", msg)
    for _ in range(6):
        if subprocess.run(["git", "-C", wt, "push", "origin", branch]).returncode == 0:
            return
        time.sleep(5)
        subprocess.run(["git", "-C", wt, "pull", "--rebase", "origin", branch])
    raise RuntimeError("push failed on " + branch)


def duration(src):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src],
                         check=True, stdout=subprocess.PIPE, text=True).stdout
    return float(out.strip())


def do_frames(job, p):
    src = get_incoming(p["video_path"], "work/src.mp4")
    d = duration(src)
    n = int(min(40, max(12, d / 2.5)))
    step = d / n
    files, frames = {}, []
    for i in range(n):
        t = round(step * (i + 0.5), 1)
        name = f"f{i:02d}_{int(t * 10):05d}.jpg"
        local = f"work/{name}"
        sh("ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", src, "-frames:v", "1",
           "-vf", "scale='if(gt(iw,ih),768,-2)':'if(gt(iw,ih),-2,768)'", "-q:v", "5", local)
        files[f"{job}/{name}"] = local
        frames.append({"t": t, "url": f"{RAW}/frames/{job}/{name}"})
    publish("frames", files, 12, f"frames {job}")
    return {"job": job, "kind": "frames", "status": "ok", "duration": round(d, 1), "frames": frames}


def do_render(job, p):
    src = get_incoming(p["video_path"], "work/src.mp4")
    plan = p.get("plan") or {}
    if isinstance(plan, str):
        plan = json.loads(plan)
    json.dump(plan, open("work/plan.json", "w", encoding="utf-8"), ensure_ascii=False)
    tracks = [l.strip().split("|", 1) for l in open("assets/tracks.txt") if l.strip() and not l.startswith("#")]
    name, turl = tracks[RUN % len(tracks)]
    cmd = ["python3", "scripts/render_video.py", "--src", src, "--plan", "work/plan.json",
           "--out", "work/final.mp4", "--preview", "work/preview.mp4", "--logo", "work/logo.png"]
    try:
        cmd += ["--music", fetch(turl, "work/music.mp3")]
    except Exception as e:
        log("music failed", e); name = "none"
    open("work/logo.png", "wb").write(base64.b64decode(open("assets/logo.b64").read()))
    out = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, text=True).stdout
    log(out)
    info = json.loads(out.strip().splitlines()[-1])
    stamp = time.strftime("%Y%m%d%H%M%S")
    fin, prev = f"{stamp}-{job}-video.mp4", f"{stamp}-{job}-preview.mp4"
    publish("videos", {fin: "work/final.mp4", prev: "work/preview.mp4"}, 40, f"video {job}")
    return {"job": job, "kind": "render", "status": "ok", "video_url": f"{RAW}/videos/{fin}",
            "preview_url": f"{RAW}/videos/{prev}", "seconds": info.get("seconds"), "track": name,
            "preview_mb": info.get("preview_mb")}


def main():
    kind, p = event()
    job = str(p.get("job") or f"manual-{RUN}")
    cb = p.get("callback") or os.environ.get("VIDEO_HOOK_URL", "")
    os.makedirs("work", exist_ok=True)
    git_identity()
    try:
        if kind == "vframes":
            res = do_frames(job, p)
        elif kind == "vrender":
            res = do_render(job, p)
        else:
            raise RuntimeError("unknown event " + kind)
        callback(cb, res)
    except Exception as e:
        log("FAILED", e)
        callback(cb, {"job": job, "kind": "render" if kind == "vrender" else "frames", "status": "error",
                      "error": str(e)[:300]})
        sys.exit(1)


if __name__ == "__main__":
    main()
