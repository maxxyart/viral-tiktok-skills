"""Offline checks for the hook overlay renderer."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_hook_overlay.py"
SPEC = importlib.util.spec_from_file_location("render_hook_overlay", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)
FONT = next((path for path in FONT_CANDIDATES if path.is_file()), None)
HOOK = "Ur telling me I yelled at my kids for 6 YEARS and never knew this?!?!?!"


@unittest.skipUnless(FONT, "A local TrueType font is required")
class RenderHookOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_transparent_full_frame_with_balanced_lines(self):
        out = self.root / "overlay.png"
        info = MODULE.render(HOOK, FONT, out)
        img = Image.open(out)
        self.assertEqual(img.size, (1080, 1920))
        self.assertEqual(img.mode, "RGBA")
        self.assertEqual(img.getpixel((10, 1900))[3], 0)  # outside the text stays transparent
        self.assertGreater(len(info["lines"]), 1)
        self.assertGreater(len(info["lines"][-1].split()), 1)  # no orphan last word

    def test_manual_line_breaks_are_kept(self):
        info = MODULE.render("POV:\nme finding this app", FONT, self.root / "o.png")
        self.assertEqual(info["lines"], ["POV:", "me finding this app"])

    def test_block_outside_safe_zone_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.render(HOOK, FONT, self.root / "o.png", center_y=0.95)

    def test_missing_font_fails_loudly(self):
        with self.assertRaises(FileNotFoundError):
            MODULE.render(HOOK, self.root / "missing.ttf", self.root / "o.png")

    def test_plate_style_and_preview(self):
        out = self.root / "plate.png"
        MODULE.render("Wait what", FONT, out, style="plate")
        Image.new("RGB", (720, 1280), "#557799").save(self.root / "still.png")
        MODULE.preview(out, self.root / "still.png", self.root / "preview.jpg")
        self.assertEqual(Image.open(self.root / "preview.jpg").size, (1080, 1920))


if __name__ == "__main__":
    unittest.main()
