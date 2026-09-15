#!/usr/bin/env python3
"""Create clean self-contained skill ZIPs for releases. No run data or secrets."""
from pathlib import Path
import subprocess
import sys
import zipfile

root = Path(__file__).resolve().parents[1]
subprocess.run([sys.executable, str(root / "tools/sync_social_skills.py"), "--check"], check=True)
target = root / "dist"
target.mkdir(exist_ok=True)
for name in ("social-account-short-analysis", "social-account-hook-analysis"):
    folder = root / "skills" / name
    with zipfile.ZipFile(target / f"{name}.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(folder.rglob("*")):
            if file.is_file() and file.suffix in {".md", ".py", ".yaml"} and "__pycache__" not in file.parts:
                archive.write(file, file.relative_to(folder.parent))
    print(target / f"{name}.zip")
