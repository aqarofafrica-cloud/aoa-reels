#!/usr/bin/env python3
"""AQAR OF AFRICA - admin monitor (owner only, never sent to platform users).

Every 3 hours (GitHub Actions cron): checks the keys and services the bot depends on and writes
status.json on the history-free branch 'health'. The Make scenario 'AOA Admin Monitor' reads it and sends
a WhatsApp message to the agency owner only when there is something new to fix.
Checks: key expiry dates (assets/keys_registry.json), Claude API key, ElevenLabs credits, Coverr, Pixabay,
failed GitHub workflow runs. No secret value is ever written to the status file or the logs.
"""
import datetime as dt, hashlib, json, os, shutil, subprocess, urllib.request, urllib.error

REPO = os.environ.get("GITHUB_REPOSITORY", "aqarofafrica-cloud/aoa-reels")
UA = {"User-Agent": "aoa-health"}


def req(url, headers=None, timeout=30):
    r = urllib.request.Request(url, headers={**UA, **(headers or {})})
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return 0, b""


def main():
    now = dt.datetime.now(dt.timezone.utc)
    lines = []
    reg = json.load(open("assets/keys_registry.json", encoding="utf-8"))
    for k in reg.get("keys", []):
        left = (dt.date.fromisoformat(k["expires"]) - now.date()).days
        if left < 0:
            lines.append(f"- {k['name']}: انتهى من {-left} يوم ({k['where']}). خاص يتجدد دابا.")
        elif left <= 14:
            lines.append(f"- {k['name']}: كينتهي من بعد {left} يوم ({k['expires']}). خاص يتجدد قبل.")

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        code, _ = req("https://api.anthropic.com/v1/models", {"x-api-key": key, "anthropic-version": "2023-06-01"})
        if code != 200:
            lines.append(f"- مفتاح Claude ديال GitHub ما خدامش (الرمز {code}). اختيار اللقطات بالرؤية واقف.")
    key = os.environ.get("ELEVENLABS_API_KEY", "")
    if key:
        code, body = req("https://api.elevenlabs.io/v1/user/subscription", {"xi-api-key": key})
        if code == 200:
            j = json.loads(body)
            left = int(j.get("character_limit", 0)) - int(j.get("character_count", 0))
            if left < int(reg.get("elevenlabs_min_credits", 5000)):
                lines.append(f"- رصيد ElevenLabs قليل: باقي {left} credit (ريل كياكل تقريبا 900).")
        else:
            lines.append(f"- ElevenLabs ما جاوبش (الرمز {code}). الصوت ديال الريلز ممكن يوقف.")
    key = os.environ.get("COVERR_API_KEY", "")
    if key:
        code, _ = req("https://api.coverr.co/videos?query=office&page_size=1", {"Authorization": "Bearer " + key})
        if code in (401, 403):
            lines.append(f"- مفتاح Coverr ما خدامش (الرمز {code}).")
    key = os.environ.get("PIXABAY_API_KEY", "")
    if key:
        code, _ = req("https://pixabay.com/api/?key=" + key + "&q=office&per_page=3")
        if code != 200:
            lines.append(f"- Pixabay ما جاوبش (الرمز {code}). الصور والفيديوهات ديال الريلز ممكن يوقفو.")

    gh = os.environ.get("GITHUB_TOKEN", "")
    since = (now - dt.timedelta(hours=3, minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    code, body = req(f"https://api.github.com/repos/{REPO}/actions/runs?status=failure&per_page=20&created=%3E%3D{since}",
                     {"Authorization": "Bearer " + gh, "Accept": "application/vnd.github+json"})
    if code == 200:
        runs = [r for r in json.loads(body).get("workflow_runs", []) if r.get("name") != "health"]
        if runs:
            names = ", ".join(sorted({r.get("name", "?") for r in runs}))
            lines.append(f"- {len(runs)} خدمة طاحت فـ GitHub فآخر 3 ساعات ({names}).")

    text = ("مراقبة AOA (خاص بصاحب الوكالة):\n" + "\n".join(lines)) if lines else ""
    alert_id = hashlib.sha1((text + now.strftime("%Y-%m-%d")).encode()).hexdigest()[:16] if text else ""
    status = {"generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "alert_id": alert_id, "text": text, "issues": len(lines)}
    print(json.dumps({"issues": len(lines)}))

    wt = "wt_health"
    shutil.rmtree(wt, ignore_errors=True)
    os.makedirs(wt)
    json.dump(status, open(os.path.join(wt, "status.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    run = lambda *a: subprocess.run(["git", "-C", wt, *a], check=True)
    run("init", "-q", "-b", "health")
    run("-c", "user.name=aoa-health", "-c", "user.email=health@aoa.local", "add", "-A")
    run("-c", "user.name=aoa-health", "-c", "user.email=health@aoa.local", "commit", "-q", "-m", "health")
    url = f"https://x-access-token:{gh}@github.com/{REPO}.git"
    subprocess.run(["git", "-C", wt, "push", "-q", "-f", url, "health"], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
