"""Offline behavioral tests: no keys, no live API credits, no creator media."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/social"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills/social-account-hook-analysis/scripts"))
from metrics import analyze, distribution, enrich, summarize
from social import collect, normalize, page_data, parse_account, timestamp, csv_cell
from report import render
from hook_report import render as render_hook
try:
    from PIL import Image
except ImportError:
    Image = None


def tt(ident, views=100, comments=1, when=1767225600, **extra):
    return {"aweme_id": str(ident), "create_time": when, "statistics": {"play_count": views, "comment_count": comments}, "video": {"duration": 12000}, **extra}


class CollectionTests(unittest.TestCase):
    def run_feed(self, pages, **kwargs):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        output = Path(tmp.name)
        data = iter(pages)
        snapshot = collect("demo", kwargs.pop("platform", "tiktok"), lambda *_: next(data, None), output, fetched_at="2026-09-15T12:00:00Z", **kwargs)
        return output, snapshot

    def test_account_urls_and_ambiguity(self):
        self.assertEqual(parse_account("https://www.instagram.com/demo/reels/?x=1"), ("demo", "instagram"))
        self.assertEqual(parse_account("https://www.tiktok.com/@demo"), ("demo", "tiktok"))
        for invalid in ["demo", "https://instagram.com/reel/abc", "https://tiktok.com/@demo/video/123", "https://evil.com/@demo"]:
            with self.assertRaises(ValueError):
                parse_account(invalid)

    def test_wrappers_and_explicit_zero(self):
        body = {"content": [{"type": "text", "text": json.dumps({"data": {"items": [], "paging_info": {"more_available": False}}})}]}
        self.assertEqual(page_data(body, "instagram"), ([], None, False))
        r = normalize({"media": {"pk": "1", "code": "abc", "play_count": 0, "ig_play_count": 999, "created_at": "2026-09-02T12:00:00Z"}}, "instagram", "demo", "snapshot", 1)
        self.assertEqual(r["views"], 0)
        self.assertIsNone(r["comments"])
        self.assertEqual(r["published_at_utc"], "2026-09-02T12:00:00Z")
        with self.assertRaises(ValueError):
            page_data({"success": False, "items": []}, "instagram")

    def test_latest_sort_dedup_photos_and_pinned(self):
        pages = [
            {"aweme_list": [tt("old", when=100, is_top=True), tt("3", when=300), tt("photo", image_post_info={"images": [1]})], "has_more": 1, "max_cursor": "a"},
            {"aweme_list": [tt("3", when=300), tt("2", when=200)], "has_more": 0}]
        out, snap = self.run_feed(pages, count=2)
        rows = json.loads((out / "videos.json").read_text(encoding="utf-8"))
        self.assertEqual([r["id"] for r in rows], ["3", "2"])
        self.assertEqual(snap["duplicates_removed"], 1)
        self.assertEqual(snap["excluded_nonvideo_count"], 1)
        self.assertTrue(snap["scope_complete"])
        self.assertEqual(rows[0]["duration_seconds"], 12)

    def test_boundary_reads_extra_pages(self):
        pages = [{"aweme_list": [tt(i, when=100 - i)], "has_more": 1, "max_cursor": str(i)} for i in range(5)]
        _, snap = self.run_feed(pages, count=1)
        self.assertEqual(snap["pages"], 3)
        self.assertEqual(snap["stop_reason"], "latest_boundary_checked")

    def test_reordered_feed_does_not_stop_at_n(self):
        pages = [{"aweme_list": [tt(i, when=i + 100)], "has_more": 0 if i == 4 else 1, "max_cursor": str(i)} for i in range(5)]
        out, snap = self.run_feed(pages, count=1)
        self.assertEqual(snap["pages"], 5)
        self.assertTrue(snap["observed_order_issue"])
        self.assertEqual(json.loads((out / "videos.json").read_text(encoding="utf-8"))[0]["id"], "4")

    def test_repeated_cursor_is_partial(self):
        _, snap = self.run_feed([{"aweme_list": [tt(1)], "has_more": 1, "max_cursor": "loop"}, {"aweme_list": [tt(2)], "has_more": 1, "max_cursor": "loop"}])
        self.assertFalse(snap["scope_complete"])
        self.assertEqual(snap["stop_reason"], "missing_or_repeated_cursor")

    def test_empty_and_schema_failures_not_success(self):
        for body in [{"aweme_list": [], "has_more": 1}, {"unexpected": []}]:
            _, snap = self.run_feed([body])
            self.assertFalse(snap["scope_complete"])

    def test_all_obeys_cap_and_does_not_claim_complete(self):
        _, snap = self.run_feed([{"aweme_list": [tt(1)], "has_more": 1, "max_cursor": "x"}], all_videos=True, max_pages=1)
        self.assertEqual(snap["stop_reason"], "page_limit")
        self.assertFalse(snap["scope_complete"])

    def test_instagram_trimmed_and_missing_date(self):
        out, snap = self.run_feed([{"items": [{"pk": "123", "code": "abc", "play_count": 0}], "paging_info": {"more_available": False}}], platform="instagram", count=1)
        self.assertFalse(snap["latest_order_verified"])
        row = json.loads((out / "videos.json").read_text(encoding="utf-8"))[0]
        self.assertIsNone(row["published_at_utc"])
        self.assertEqual(row["id"], "abc")  # Numeric Instagram IDs may be rounded by a JSON transport.

    def test_tiktok_prefers_jpeg_cover_when_heic_is_first(self):
        row = normalize(tt("1", video={"duration": 1000, "origin_cover": {"url_list": ["https://cdn.test/a.heic?sig=1", "https://cdn.test/a.jpeg?sig=2"]}}), "tiktok", "demo", "snapshot", 1)
        self.assertEqual(row["cover_url"], "https://cdn.test/a.jpeg?sig=2")
        row = normalize(tt("2", video={"duration": 1000, "origin_cover": {"url_list": ["https://cdn.test/a.heic?sig=1"]}, "cover": {"url_list": ["https://cdn.test/b.jpeg?sig=2"]}}), "tiktok", "demo", "snapshot", 1)
        self.assertEqual(row["cover_url"], "https://cdn.test/b.jpeg?sig=2")
        row = normalize(tt("3", video={"duration": 1000, "origin_cover": {"url_list": ["https://cdn.test/a.heic", "https://cdn.test/a.jpg"]}}), "tiktok", "demo", "snapshot", 1)
        self.assertEqual(row["cover_url"], "https://cdn.test/a.jpg")

    def test_timestamp_and_csv_safety(self):
        self.assertIsNone(timestamp("bad"))
        self.assertEqual(timestamp(1767225600000), "2026-01-01T00:00:00Z")
        self.assertEqual(csv_cell("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(csv_cell("normal quote"), "normal quote")


class MetricTests(unittest.TestCase):
    def test_null_zero_and_weighted_denominator(self):
        rows = enrich([{"views": 100, "comments": 10}, {"views": 900, "comments": 9}, {"views": 500, "comments": None}, {"views": 0, "comments": 0}])
        stats = summarize(rows, 300)
        self.assertEqual(stats["weighted_comment_rate_pct"], 1.9)
        self.assertEqual(stats["comment_rate_pct"]["mean"], 5.5)
        self.assertEqual(stats["comment_rate_pct"]["known_n"], 2)
        self.assertEqual(stats["weighted_comment_rate_view_coverage"], 1000/1500)
        self.assertNotIn("sum", stats["virality_multiplier"])
        self.assertIsNone(distribution([None])["sum"])

    def test_exact_fractional_median_and_zero_baseline(self):
        rows = enrich([{"views": 2753}, {"views": 2754}])
        self.assertEqual(rows[0]["virality_multiplier"], 2753/2753.5)
        self.assertIsNone(enrich([{"views": 0, "comments": 0}])[0]["virality_multiplier"])

    def test_strict_annotations_and_separate_axes(self):
        rows = [{"id": str(i), "views": 100 * i, "comments": i, "published_at_utc": "2026-09-01T00:00:00Z"} for i in (1, 2, 3)]
        cards = [{"id": str(i), "hook_text_exact": "Hello!", "hook_status": "legible", "text_formula": "Hello [X]!", "visual_format": "close-up" if i < 3 else "phone", "character_role": "creator", "evidence_scope": "cover_only"} for i in (1, 2, 3)]
        for bad in [cards[:2], cards + [cards[0]], cards[:2] + [{**cards[2], "id": "foreign"}]]:
            with self.assertRaises(ValueError):
                analyze(rows, {}, bad)
        _, stats = analyze(rows, {}, cards)
        self.assertEqual(len(stats["patterns"]["text_formula"]), 1)
        self.assertEqual(len(stats["patterns"]["text_x_visual"]), 2)
        self.assertEqual(stats["patterns"]["text_formula"][0]["views"]["median"], 200)
        self.assertEqual(len(stats["patterns"]["text_formula"][0]["references"]), 2)


class ReportTests(unittest.TestCase):
    run_feed = CollectionTests.run_feed

    def test_hook_report_is_local_and_validates_source_ids(self):
        from social import export
        out, _ = self.run_feed([{"aweme_list": [tt(1)], "has_more": 0}], count=1)
        export(out)
        (out / "transcripts.json").write_text(json.dumps([{"id": "1", "status": "speech", "language": "English", "transcript": "A complete audio transcript.", "opening_0_3s": "A complete"}]), encoding="utf-8")
        insights = {"summary": [{"title": "Observed", "text": "<script>alert(1)</script>", "reference_ids": ["1"]}]}
        render_hook(out, insights, "ru")
        page = (out / "report.html").read_text(encoding="utf-8")
        self.assertIn('id="catalog"', page)
        self.assertIn('id="catalog-grid"', page)
        self.assertIn('id="catalog-table"', page)
        self.assertIn("A complete audio transcript.", page)
        self.assertIn('id="patterns"', page)
        self.assertIn("&lt;script&gt;", page)
        self.assertNotIn("<script>alert", page)
        insights["summary"][0]["reference_ids"] = ["foreign"]
        with self.assertRaises(ValueError):
            render_hook(out, insights, "ru")
        (out / "transcripts.json").write_text(json.dumps([{"id": "foreign", "transcript": "No match"}]), encoding="utf-8")
        with self.assertRaises(ValueError):
            render_hook(out, None, "ru")

    def test_html_escapes_untrusted_text_and_validates_refs(self):
        out, _ = self.run_feed([{"aweme_list": [tt(1)], "has_more": 0}], count=1)
        insights = {"sections": [{"title": "<script>alert(1)</script>", "items": [{"text": "Evidence", "formula": "Hello [X]", "reference_ids": ["1"]}]}]}
        render(out, insights)
        report = (out / "report.html").read_text(encoding="utf-8")
        self.assertNotIn("<script>alert", report)
        self.assertIn("&lt;script&gt;", report)
        insights["sections"][0]["items"][0]["reference_ids"] = ["foreign"]
        with self.assertRaises(ValueError):
            render(out, insights)

    @unittest.skipIf(Image is None, "Pillow required for contact-sheet test")
    def test_uncropped_sheet_and_portable_html(self):
        from covers import sheets
        out, _ = self.run_feed([{"aweme_list": [tt(1)], "has_more": 0}], count=1)
        (out / "covers").mkdir()
        (out / "sheets").mkdir()
        # A wide cover with colored corners detects accidental center cropping.
        image = Image.new("RGB", (400, 200), "red")
        image.paste("blue", (0, 0, 20, 200))
        image.save(out / "covers/test.png")
        rows = json.loads((out / "videos.json").read_text(encoding="utf-8"))
        rows[0]["cover_file"] = "covers/test.png"
        sheets(rows, out)
        with Image.open(out / "sheets/covers-01.jpg") as sheet:
            # contain places the 2:1 image centrally, and preserves its left edge.
            pixel = sheet.getpixel((5, 350))
            self.assertGreater(pixel[2], pixel[0])
        from social import write_json, export
        write_json(out / "videos.json", rows)
        export(out)
        render(out, {"sections": []})
        text = (out / "report.html").read_text(encoding="utf-8")
        self.assertIn("data:image/png;base64,", text)
        self.assertIn("data:image/jpeg;base64,", text)
        self.assertNotIn('src="covers/', text)


if __name__ == "__main__":
    unittest.main()
