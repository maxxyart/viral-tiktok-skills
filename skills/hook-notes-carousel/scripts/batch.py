#!/usr/bin/env python3
"""
Batch driver for hook+notes carousels: one JSON config -> all final slides.

Usage:
  python3 batch.py --config batch.json [--only NAME]

batch.json:
{
  "output_root": "generated_carousel",     // default
  "version": "v1",                          // default
  "size": [1152, 2048],                     // notes-slide size, default 1152x2048
  "carousels": [
    {
      "name": "pause",
      "background": "optional/path.png",    // else {root}/{name}/{ver}/slide_1_bg.png must exist
      "hook":  { ...overlay_hook.py fields, without filename/out_name... },
      "notes": { ...render_notes.py content... }
    }
  ]
}

Per carousel it writes {dir}/slides_config.json and {dir}/notes.json (editable,
re-runnable), then renders:
  {dir}/final/slide_1.png   (hook over background)
  {dir}/final/slide_2.png   (iOS Notes render)

Exit code 0 if every carousel succeeded; prints a manifest either way.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.stdout.strip():
        print(p.stdout.strip())
    if p.stderr.strip():
        print(p.stderr.strip(), file=sys.stderr)
    return p.returncode


def process(c, root, version, size):
    name = c["name"]
    d = os.path.join(root, name, version)
    final = os.path.join(d, "final")
    os.makedirs(final, exist_ok=True)

    # background
    bg_default = os.path.join(d, "slide_1_bg.png")
    bg = c.get("background", bg_default)
    if bg != bg_default:
        if not os.path.exists(bg):
            return f"FAIL  {name}: background not found: {bg}"
        shutil.copy(bg, bg_default)
    if not os.path.exists(bg_default):
        return f"FAIL  {name}: missing {bg_default} — generate or supply a background first"

    # slide 1 — hook overlay
    hook = dict(c.get("hook", {}))
    hook.setdefault("filename", "slide_1_bg.png")
    hook.setdefault("out_name", "slide_1.png")
    cfg_path = os.path.join(d, "slides_config.json")
    with open(cfg_path, "w") as f:
        json.dump([hook], f, indent=2, ensure_ascii=False)
    rc1 = run([sys.executable, os.path.join(SCRIPTS, "overlay_hook.py"),
               "--config", cfg_path, "--input-dir", d, "--output-dir", final])

    # slide 2 — iOS Notes render
    if not c.get("notes"):
        return f"FAIL  {name}: missing 'notes' content"
    notes_path = os.path.join(d, "notes.json")
    with open(notes_path, "w") as f:
        json.dump(c["notes"], f, indent=2, ensure_ascii=False)
    rc2 = run([sys.executable, os.path.join(SCRIPTS, "render_notes.py"),
               "--content", notes_path,
               "--out", os.path.join(final, "slide_2.png"),
               "--width", str(size[0]), "--height", str(size[1])])

    s1 = os.path.exists(os.path.join(final, "slide_1.png"))
    s2 = os.path.exists(os.path.join(final, "slide_2.png"))
    ok = rc1 == 0 and rc2 == 0 and s1 and s2
    warn = " (notes overflow!)" if rc2 == 2 else ""
    return f"{'OK   ' if ok else 'FAIL '}{name}: slide_1={'✓' if s1 else '✗'} slide_2={'✓' if s2 else '✗'}{warn} -> {final}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--only", help="process a single carousel by name")
    a = ap.parse_args()
    with open(a.config) as f:
        cfg = json.load(f)

    root = cfg.get("output_root", "generated_carousel")
    version = cfg.get("version", "v1")
    size = cfg.get("size", [1152, 2048])
    items = cfg["carousels"]
    if a.only:
        items = [c for c in items if c["name"] == a.only]
        if not items:
            sys.exit(f"no carousel named {a.only!r} in config")

    results = []
    for c in items:
        print(f"\n=== {c['name']} ===")
        results.append(process(c, root, version, size))

    print("\n===== MANIFEST =====")
    for r in results:
        print(r)
    sys.exit(0 if all(r.startswith("OK") for r in results) else 1)


if __name__ == "__main__":
    main()
