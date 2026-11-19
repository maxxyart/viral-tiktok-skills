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
def pixels(img):
    return img.get_flattened_data() if hasattr(img, "get_flattened_data") else img.getdata()


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
        with Image.open(self.root / "preview.jpg") as im:
            self.assertEqual(im.size, (1080, 1920))

    def test_calibration_matches_reference_width(self):
        ref = "everyone's July period late??"
        info = MODULE.render("Same fight different day", FONT, self.root / "c.png", canvas=(720, 1280),
                             calib=ref, calib_frac=0.73, center_y=0.165)
        width = MODULE.load_font(FONT, info["font_size"], None).getlength(ref)
        self.assertLessEqual(width, 0.73 * 720)
        self.assertGreater(width, 0.70 * 720)
        self.assertEqual(Image.open(self.root / "c.png").size, (720, 1280))

    def test_line_pitch_and_literal_newline(self):
        info = MODULE.render("POV:\\nme finding this app", FONT, self.root / "p.png", canvas=(720, 1280),
                             line_pitch=0.05)
        self.assertEqual(info["lines"], ["POV:", "me finding this app"])
        self.assertEqual(info["step"], 64)

    def test_emoji_only_at_the_end(self):
        self.assertEqual(MODULE.split_emoji("who showed me this🥹"), ("who showed me this", "🥹"))
        self.assertEqual(MODULE.split_emoji("same fight 😭 😭"), ("same fight", "😭😭"))
        with self.assertRaises(ValueError):
            MODULE.render("hi 😭 there", FONT, self.root / "e.png")

    @unittest.skipUnless(any(Path(p).is_file() for p, _ in MODULE.EMOJI_FONTS), "No colour emoji font")
    def test_trailing_emoji_is_drawn_in_colour(self):
        out = self.root / "emoji.png"
        info = MODULE.render("who showed me this🥹", FONT, out, canvas=(720, 1280))
        self.assertEqual(info["emoji"], "🥹")
        img = Image.open(out).convert("RGBA")
        colour = [p for p in pixels(img) if p[3] > 200 and max(p[:3]) - min(p[:3]) > 80]
        self.assertTrue(colour)  # the yellow face, not white text or a black halo

    def test_neon_style_glows_magenta(self):
        out = self.root / "neon.png"
        MODULE.render("SAME FIGHT", FONT, out, style="neon", canvas=(720, 1280), center_y=0.74)
        img = Image.open(out).convert("RGBA")
        glow = [p for p in pixels(img) if p[3] > 60 and p[0] > 180 and p[1] < 120]
        self.assertTrue(glow)


if __name__ == "__main__":
    unittest.main()
