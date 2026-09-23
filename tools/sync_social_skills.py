#!/usr/bin/env python3
"""Vendor shared source into independently installable skill folders; --check for CI."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("social-account-short-analysis", "social-account-hook-analysis")
SCRIPTS = ("social.py", "metrics.py", "report.py")
REFS = ("collection.md", "metrics.md", "reporting.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    failures = []
    for skill in SKILLS:
        scripts = SCRIPTS + (("covers.py", "audio_transcribe.py") if "hook" in skill else ())
        refs = REFS + (("hook-analysis.md",) if "hook" in skill else ())
        pairs = [(ROOT / "src/social" / f, ROOT / "skills" / skill / "scripts" / f) for f in scripts]
        pairs += [(ROOT / "src/social/references" / f, ROOT / "skills" / skill / "references" / f) for f in refs]
        for src, dst in pairs:
            if args.check:
                if not dst.exists() or src.read_bytes() != dst.read_bytes():
                    failures.append(str(dst.relative_to(ROOT)))
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
    if failures:
        sys.exit("Stale skill resources; run tools/sync_social_skills.py: " + ", ".join(failures))
    print("Skill resources " + ("match source" if args.check else "synchronized"))


if __name__ == "__main__":
    main()
