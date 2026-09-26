"""Small offline checks for the reusable overlay renderer."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "render_overlay.py"
SPEC = importlib.util.spec_from_file_location("render_overlay", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
    Path("C:/Windows/Fonts/arial.ttf"),
)
FONT = next((path for path in FONT_CANDIDATES if path.is_file()), None)


@unittest.skipUnless(FONT, "A local TrueType font is required")
class RenderOverlayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        Image.new("RGB", (300, 400), "#335577").save(self.root / "background.png")
        self.config = {
            "canvas": [300, 400],
            "styles": {
                "caption": {
                    "font": "regular", "size": 22, "text_color": "#000000",
                    "box_color": "#FFFFFF", "padding_x": 10, "padding_y": 6,
                    "line_step": 31, "corner_radius": 5, "max_width": 280,
                }
            },
            "slides": [{"background": "background.png", "output": "slides/01.png",
                        "layers": [{"style": "caption", "top": 30, "lines": ["A useful idea"]}]}],
        }

    def _save(self):
        path = self.root / "config.json"
        path.write_text(json.dumps(self.config), encoding="utf-8")
        return path

    def test_render_preserves_background_and_writes_expected_canvas(self):
        output = MODULE.render(self._save(), str(FONT), str(FONT))[0]
        with Image.open(output) as rendered, Image.open(self.root / "background.png") as background:
            self.assertEqual(rendered.size, (300, 400))
            self.assertEqual(background.getpixel((150, 40)), (51, 85, 119))
            self.assertNotEqual(rendered.getpixel((150, 40)), (51, 85, 119))

    def test_overwide_copy_fails_instead_of_shrinking_silently(self):
        self.config["slides"][0]["layers"][0]["lines"] = ["A very long caption that cannot fit on this image"]
        with self.assertRaisesRegex(ValueError, "exceeds max_width"):
            MODULE.render(self._save(), str(FONT), str(FONT))

    def test_real_asset_is_composited_without_changing_clean_background(self):
        Image.new("RGB", (100, 50), "#FF0000").save(self.root / "product.png")
        self.config["slides"][0]["asset_layers"] = [
            {"path": "product.png", "width": 100, "top": 200, "corner_radius": 8}
        ]
        output = MODULE.render(self._save(), str(FONT), str(FONT))[0]
        with Image.open(output) as rendered, Image.open(self.root / "background.png") as background:
            self.assertEqual(rendered.getpixel((150, 225)), (255, 0, 0))
            self.assertEqual(background.getpixel((150, 225)), (51, 85, 119))


if __name__ == "__main__":
    unittest.main()
