#!/usr/bin/env python3
"""Check the rendered report in headless Chrome before publishing.

Usage:
  python3 snapshot_report.py REPORT_DIR [--widths 390,1280] [--sections top,virals,...]

REPORT_DIR is render_report.py's --out (has index.html). Writes REPORT_DIR/_check/
(never published): page.html (the report with doctype + viewport, eager images),
frame.html (holds page.html in an iframe of the exact width), check.json and one PNG
per width × section: top + every top-level <section class="block" id>.

Headless Chrome will not make a window narrower than 500 px, so a plain --window-size=390
silently checks a 500 px layout. The page therefore runs inside a 390 px iframe, and
the screenshot is cropped to the iframe.

check.json comes from a script run inside the page at the first width:
  overflowX     page is wider than the viewport (horizontal scroll on a phone)
  offenders     up to 15 elements whose right edge sticks out (sideways scrollers excluded)
  brokenImages  <img> that failed to load
  sections      [{id, top, height}]
Exit code 2 when overflowX or brokenImages, so the problem is not missed; fix and rerun.
Claude Reads the PNGs: every section at 390, top + virals + product at 1280.

Chrome runs with a throwaway --user-data-dir (never the user's profile) and is killed once
the screenshot is written or the timeout passes: headless Chrome on macOS sometimes never exits.
"""
import argparse, html as H, json, os, re, shutil, subprocess, sys, tempfile, time
from concurrent.futures import ThreadPoolExecutor

CHROMES = [os.environ.get("CHROME", ""),
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
           "/Applications/Chromium.app/Contents/MacOS/Chromium",
           "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
MIN_WINDOW = 500

CHECK_JS = """<script>
window.addEventListener("load", function () {
  setTimeout(function () {
    var m = /s=([\\w-]+)/.exec(location.hash), vw = document.documentElement.clientWidth;
    if (m && m[1] !== "top") {
      var el = document.getElementById(m[1]);
      if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY);
    }
    function inScroller(el) {  // slide strips scroll sideways on purpose
      for (var a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        if (getComputedStyle(a).overflowX !== "visible") return true;
      }
      return false;
    }
    var off = [];
    document.querySelectorAll("body *").forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.width && r.right > vw + 1 && off.length < 15 && !inScroller(el)) {
        var cls = typeof el.className === "string" && el.className.trim() ? "." + el.className.trim().replace(/\\s+/g, ".") : "";
        off.push(el.tagName.toLowerCase() + cls + " right=" + Math.round(r.right));
      }
    });
    var broken = Array.prototype.filter.call(document.images, function (i) { return i.complete && !i.naturalWidth; })
      .map(function (i) { return i.getAttribute("src"); });
    var secs = Array.prototype.map.call(document.querySelectorAll("section.block[id]"), function (s) {
      var r = s.getBoundingClientRect();
      return {id: s.id, top: Math.round(r.top + window.scrollY), height: Math.round(r.height)};
    });
    parent.postMessage(JSON.stringify({width: vw, scrollWidth: document.documentElement.scrollWidth,
      overflowX: document.documentElement.scrollWidth > vw + 1, offenders: off, brokenImages: broken,
      height: document.documentElement.scrollHeight, sections: secs}), "*");
  }, 300);
});
</script>"""

FRAME = """<!doctype html><html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}
iframe{border:0;display:block}</style></head><body>
<iframe id="f" width="%(w)d" height="%(h)d"></iframe>
<script>
document.getElementById("f").src = "page.html" + location.hash;
addEventListener("message", function (e) {
  var p = document.createElement("pre"); p.id = "snapcheck"; p.textContent = e.data; document.body.appendChild(p);
});
</script></body></html>"""

def find_chrome():
    for c in CHROMES:
        if c and os.path.exists(c):
            return c
    sys.exit("ERROR: no Chrome/Chromium found; set CHROME=/path/to/chrome")

def run_chrome(chrome, args, url, wait_file=None, timeout=60):
    prof = tempfile.mkdtemp(prefix="hook-snap-")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--no-default-browser-check", "--disable-extensions", f"--user-data-dir={prof}", *args, url]
    out = tempfile.TemporaryFile()
    p = subprocess.Popen(cmd, stdout=out, stderr=subprocess.DEVNULL)
    deadline, last = time.time() + timeout, -1
    while time.time() < deadline and p.poll() is None:
        if wait_file and os.path.exists(wait_file):
            size = os.path.getsize(wait_file)
            if size and size == last:
                break
            last = size
        time.sleep(0.5)
    if p.poll() is None:
        p.kill()
        p.wait()
    shutil.rmtree(prof, ignore_errors=True)
    out.seek(0)
    return out.read().decode("utf-8", "replace")

def crop(png, w, h):
    try:
        from PIL import Image
        im = Image.open(png)
        if im.width > w:
            im.crop((0, 0, w, min(h, im.height))).save(png)
    except ImportError:
        subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", "0", "0", png], capture_output=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report_dir")
    ap.add_argument("--widths", default="390,1280")
    ap.add_argument("--sections", default="", help="comma list; default top + every block section")
    ap.add_argument("--budget", type=int, default=4000, help="virtual time for fonts/images, ms")
    args = ap.parse_args()
    R = os.path.abspath(args.report_dir)
    index = os.path.join(R, "index.html")
    if not os.path.exists(index):
        sys.exit(f"ERROR: {index} not found (run render_report.py first)")
    C = os.path.join(R, "_check")
    shutil.rmtree(C, ignore_errors=True)
    os.makedirs(C)
    body = open(index, encoding="utf-8").read().replace(' loading="lazy"', "")
    with open(os.path.join(C, "page.html"), "w", encoding="utf-8") as f:
        f.write('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width, initial-scale=1"><base href="../">'
                f'</head><body>{body}{CHECK_JS}</body></html>')
    chrome = find_chrome()
    widths = [int(w) for w in args.widths.split(",") if w.strip()]
    height = {w: 1500 if w < 600 else 1100 for w in widths}
    frames = {}
    for w in widths:
        frames[w] = os.path.join(C, f"frame{w}.html")
        with open(frames[w], "w", encoding="utf-8") as f:
            f.write(FRAME % {"w": w, "h": height[w]})

    w0 = widths[0]
    dom = run_chrome(chrome, [f"--window-size={max(w0, MIN_WINDOW)},{height[w0]}",
                              f"--virtual-time-budget={args.budget}", "--dump-dom"],
                     "file://" + frames[w0], timeout=60)
    m = re.search(r'<pre id="snapcheck">(.*?)</pre>', dom, re.S)
    if not m:
        sys.exit("ERROR: the in-page check did not run (Chrome timed out or the page failed to load)")
    check = json.loads(H.unescape(m.group(1)))
    json.dump(check, open(os.path.join(C, "check.json"), "w"), ensure_ascii=False, indent=1)

    ids = ["top"] + [s["id"] for s in check["sections"]]
    if args.sections:
        want = {s.strip() for s in args.sections.split(",") if s.strip()}
        ids = [i for i in ids if i in want]
    jobs = [(w, sid, os.path.join(C, f"w{w}_{k:02d}_{sid}.png")) for w in widths for k, sid in enumerate(ids)]

    def shoot(job):
        w, sid, png = job
        run_chrome(chrome, [f"--window-size={max(w, MIN_WINDOW)},{height[w]}",
                            f"--virtual-time-budget={args.budget}", f"--screenshot={png}"],
                   f"file://{frames[w]}#s={sid}", wait_file=png, timeout=60)
        if not os.path.exists(png):
            return None
        crop(png, w, height[w])
        return png

    with ThreadPoolExecutor(4) as ex:
        pngs = list(ex.map(shoot, jobs))

    print(f"page at {check['width']}px: height {check['height']}px, scrollWidth {check['scrollWidth']}, "
          f"sections: {', '.join(s['id'] for s in check['sections'])}")
    problems = []
    if check["overflowX"]:
        problems.append(f"horizontal overflow at {check['width']}px: " + "; ".join(check["offenders"]))
    if check["brokenImages"]:
        problems.append(f"{len(check['brokenImages'])} broken images: " + ", ".join(check["brokenImages"][:10]))
    for p in problems:
        print("PROBLEM: " + p)
    missing = [j[2] for j, p in zip(jobs, pngs) if not p]
    if missing:
        print(f"WARNING: {len(missing)} screenshots missing: {', '.join(os.path.basename(x) for x in missing)}")
    print(f"Screenshots in {C} (Read them before publishing):")
    for p in pngs:
        if p:
            print("  " + os.path.basename(p))
    sys.exit(2 if problems else 0)

if __name__ == "__main__":
    main()
