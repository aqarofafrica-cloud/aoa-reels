#!/usr/bin/env python3
"""AQAR OF AFRICA - render the long advice script (master script) as a branded Arabic PDF.

Usage: render_doc.py --text master.txt --out script.pdf [--logo logo.png] [--date 2026-10-23]
The text follows the advice-project format:
  النصيحة: <title>
  النصيحة 1 / العنوان: / الشرح: / المثال: / القانون: / الواقع: / إلا وقع المشكل:
  الخلاصة / نقط للتحقق (numbered lines) / Sources: (- [title](url))
"""
import argparse, base64, html, os, re
from weasyprint import HTML

LABELS = ["العنوان", "الشرح", "المثال", "القانون", "الواقع", "إلا وقع المشكل"]
PHONE = "+212 660 96 66 20"
BRAND = "AQAR OF AFRICA"

CSS = """
@page { size: A4; margin: 22mm 18mm 20mm 18mm;
  @bottom-center { content: counter(page) " / " counter(pages); font: 9pt 'DejaVu Sans'; color: #7a869a; }
  @bottom-left { content: "\\202A%(phone)s\\202C"; font: 9pt 'DejaVu Sans'; color: #7a869a; }
  @bottom-right { content: "%(brand)s"; font: bold 9pt 'DejaVu Sans'; color: #c9932f; } }
html { direction: rtl; }
body { font-family: 'Noto Naskh Arabic', 'DejaVu Sans', sans-serif; font-size: 12.5pt; line-height: 1.75; color: #1b2433; }
.head { display: flex; align-items: center; justify-content: space-between; border-bottom: 3px solid #e8b04b; padding-bottom: 8px; margin-bottom: 14px; }
.head img { height: 46px; }
.head .meta { font: 9.5pt 'DejaVu Sans'; color: #7a869a; direction: ltr; }
h1 { font-size: 21pt; color: #0c1220; margin: 6px 0 14px; line-height: 1.4; }
h2 { font-size: 15pt; color: #0c1220; background: #f6efe0; border-right: 5px solid #e8b04b; padding: 4px 10px; margin: 20px 0 8px; page-break-after: avoid; }
p { margin: 4px 0 8px; text-align: justify; }
p.lab b { color: #a8761c; }
ol { margin: 4px 22px 8px 0; padding: 0; }
li { margin-bottom: 6px; }
.verify { border: 1px dashed #b9c2d0; background: #f7f9fc; padding: 6px 12px; border-radius: 6px; font-size: 11pt; }
.verify h2 { background: none; border: none; padding: 0; margin: 4px 0; font-size: 13pt; color: #5a6a82; }
.src { font-size: 9.5pt; direction: ltr; text-align: left; color: #5a6a82; word-break: break-all; }
"""


def inline(s):
    s = html.escape(s)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)


def to_html(text, logo, date):
    out, in_list, in_verify = [], False, False

    def close_list():
        nonlocal in_list
        if in_list:
            out.append("</ol>"); in_list = False

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.match(r"^النصيحة\s*:", line):
            close_list(); out.append(f"<h1>{inline(line.split(':', 1)[1].strip())}</h1>"); continue
        if re.match(r"^النصيحة\s+\d+\s*$", line) or line in ("الخلاصة",):
            close_list(); out.append(f"<h2>{inline(line)}</h2>"); continue
        if line.startswith("نقط للتحقق"):
            close_list(); in_verify = True; out.append('<div class="verify"><h2>نقط للتحقق (للمراجعة الداخلية)</h2>'); continue
        if re.match(r"^(Sources|المصادر)\s*:?$", line):
            close_list()
            if in_verify:
                out.append("</div>"); in_verify = False
            out.append('<h2>المصادر</h2>'); continue
        m = re.match(r"^(\d+)[.)]\s+(.*)$", line)
        if m:
            if not in_list:
                out.append("<ol>"); in_list = True
            out.append(f"<li>{inline(m.group(2))}</li>"); continue
        if line.startswith("- ["):
            close_list(); out.append(f'<p class="src">{inline(line[2:])}</p>'); continue
        close_list()
        lab = next((l for l in LABELS if line.startswith(l + ":") or line.startswith(l + " :")), None)
        if lab:
            body = line.split(":", 1)[1].strip()
            out.append(f'<p class="lab"><b>{lab}:</b> {inline(body)}</p>')
        else:
            out.append(f"<p>{inline(line)}</p>")
    close_list()
    if in_verify:
        out.append("</div>")
    img = ""
    if logo and os.path.exists(logo):
        img = '<img src="data:image/png;base64,%s"/>' % base64.b64encode(open(logo, "rb").read()).decode()
    head = f'<div class="head">{img}<div class="meta">{BRAND} &nbsp;|&nbsp; {html.escape(date)}</div></div>'
    css = CSS % {"phone": PHONE, "brand": BRAND}
    return f'<html lang="ar" dir="rtl"><head><meta charset="utf-8"><style>{css}</style></head><body>{head}{"".join(out)}</body></html>'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--logo")
    ap.add_argument("--date", default="")
    a = ap.parse_args()
    doc = to_html(open(a.text, encoding="utf-8").read(), a.logo, a.date)
    HTML(string=doc).write_pdf(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
