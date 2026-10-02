import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("reference", Path(__file__).resolve().parents[1] / "scripts" / "reference.py")
reference = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reference)


class VideoUrlTest(unittest.TestCase):
    def test_tiktok_prefers_no_watermark(self):
        payload = {"aweme_detail": {"video": {
            "download_no_watermark_addr": {"url_list": ["https://a/clean.mp4"]},
            "play_addr": {"url_list": ["https://a/play.mp4"]}}}}
        self.assertEqual(reference.video_url_from(payload), "https://a/clean.mp4")

    def test_tiktok_falls_back_to_play_addr(self):
        payload = {"aweme_detail": {"video": {"play_addr": {"url_list": ["https://a/play.mp4"]}}}}
        self.assertEqual(reference.video_url_from(payload), "https://a/play.mp4")

    def test_instagram_post(self):
        payload = {"data": {"xdt_shortcode_media": {"video_url": "https://i/reel.mp4"}}}
        self.assertEqual(reference.video_url_from(payload), "https://i/reel.mp4")

    def test_nothing_found(self):
        self.assertIsNone(reference.video_url_from({"data": {}}))


if __name__ == "__main__":
    unittest.main()
