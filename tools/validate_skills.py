#!/usr/bin/env python3
"""Validate installable skills and their relative instruction links (PyYAML)."""
from pathlib import Path
import re
import yaml

root = Path(__file__).resolve().parents[1]
for name in ("social-account-short-analysis", "social-account-hook-analysis"):
    folder = root / "skills" / name
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n"), name
    meta = yaml.safe_load(text.split("---", 2)[1])
    assert meta["name"] == name and len(name) < 64, name
    assert isinstance(meta["description"], str) and meta["description"].strip(), name
    for relative in re.findall(r"\]\(([^)]+)\)", text):
        if "://" not in relative:
            assert (folder / relative).is_file(), relative
    ui = yaml.safe_load((folder / "agents/openai.yaml").read_text(encoding="utf-8"))["interface"]
    assert 25 <= len(ui["short_description"]) <= 64, name
    assert "$" + name in ui["default_prompt"], name
    assert "Viral Camp" in ui["display_name"], name
    print(name + ": metadata, references and UI valid")
