"""Temporary: print the structure of S&WB's press release pages."""
import re, urllib.request
UA = {"User-Agent": "utility-watch/0.1 (+https://github.com/wordle-death/utility-watch)"}
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
        return r.status, r.read().decode("utf-8", "replace")
for url in ["https://www.swbno.org/PressReleases", "https://www.swbno.org/PressReleases?page=2", "https://www.swbno.org/PressReleases/Details/5127"]:
    try:
        status, html = get(url)
    except Exception as exc:
        print("FAIL", url, exc); continue
    print("==", url, status, len(html))
    ids = re.findall(r'PressReleases/Details/(\d+)', html)
    print("ids", ids[:30])
    i = html.find("PressReleases/Details/")
    print(html[max(0, i - 700): i + 900])
    for m in re.finditer(r'(?i)href="([^"]*PressReleases[^"]*(?:page|Page|p=|skip|offset)[^"]*)"', html):
        print("pager", m.group(1))
    if "Details/5127" in url:
        j = html.find("For Immediate Release")
        print(html[max(0, j - 600): j + 1500])
    forms = re.findall(r'(?is)<form.*?</form>', html)
    for f in forms[:3]:
        print("FORM", re.sub(r"\s+", " ", f)[:900])
