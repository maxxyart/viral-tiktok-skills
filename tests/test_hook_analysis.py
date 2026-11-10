"""Offline tests for skills/social-account-hook-analysis (no network, no images needed)."""
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills/social-account-hook-analysis/scripts"

# index: (date, views, likes, comments, shares, saves, pattern)
POSTS = [
    ("2026-11-02", 900, 90, 9, 1, 1, "A"),       # young
    ("2026-11-01", 50000, 5000, 50, 40, 400, "A"),  # young hit
    ("2026-10-20", 1000, 100, 10, 5, 5, "A"),
    ("2026-10-10", 2000, 200, 20, 10, 10, "A"),
    ("2026-10-01", 3000, 300, 30, 15, 15, "B"),
    ("2026-09-20", 4000, 400, 40, 20, 20, "B"),
    ("2026-09-10", 30000, 3000, 300, 150, 900, "B"),  # hit
    ("2026-08-01", 500, 50, 5, 2, 2, None),
]


def run(*args):
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)


def make_work_dir(root, metric="views"):
    videos = []
    for i, (date, views, likes, comments, shares, saves, _) in enumerate(POSTS):
        videos.append({"id": f"7{i:018d}", "desc": f"post {i}", "views": views, "likes": likes,
                       "comments": comments, "shares": shares, "saves": saves, "date": date,
                       "duration": 0, "slides": 4, "isCarousel": True, "isPinned": i == 6,
                       "kind": "carousel", "music": "", "coverUrl": None,
                       "link": f"https://www.tiktok.com/@demo/photo/7{i:018d}"})
    meta = {"platform": "tiktok", "handle": "demo", "fetchedAt": "2026-11-03", "metric": metric,
            "sample": {"mode": "all", "since": None, "fetched": len(videos), "accountTotal": len(videos),
                       "skippedPinned": 0, "autoMax": 150},
            "profile": {"followers": 1000, "totalPosts": len(videos), "likes": 1, "nickname": "demo", "bio": ""},
            "videos": videos}
    clusters = {"patterns": [
        {"patternName": "A", "formula": "[N] ways to [X]", "visualFormat": "photo", "indexes": [i for i, p in enumerate(POSTS) if p[6] == "A"]},
        {"patternName": "B", "formula": "[X] you need", "visualFormat": "selfie", "indexes": [i for i, p in enumerate(POSTS) if p[6] == "B"]},
    ], "unassigned": [7]}
    cards = [{"index": i, "hook_text": f"hook {i}", "has_creator_face": i % 2 == 0} for i in range(len(POSTS))]
    labels = {"names": {"theme": {"focus": "Focus", "other": "Other"}},
              "labels": [{"index": i, "theme": "focus" if i < 4 else "other", "product_fit": "direct"} for i in range(len(POSTS))]}
    for name, data in (("meta", meta), ("clusters", clusters), ("cards", cards), ("labels", labels)):
        (root / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")
    slides = root / "carousels" / "06"
    slides.mkdir(parents=True)
    (slides / "slides.json").write_text(json.dumps([{"slide": 1, "text": "first\nline", "visual": "x"},
                                                    {"slide": 2, "text": "second", "visual": "y"}]), encoding="utf-8")
    return root


def stats(root, *extra):
    res = run(SCRIPTS / "pattern_stats.py", root / "meta.json", root / "clusters.json", "--cards", root / "cards.json",
              "--labels", root / "labels.json", "--out", root / "report.json", *extra)
    return res, (json.loads((root / "report.json").read_text()) if res.returncode == 0 else None)


class PatternStatsTest(unittest.TestCase):
    def test_young_posts_leave_medians_but_stay_hits(self):
        with tempfile.TemporaryDirectory() as d:
            res, rep = stats(make_work_dir(Path(d)))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(sorted(rep["young"]["indexes"]), [0, 1])
            self.assertEqual(rep["accountMedianViews"], 2500)  # median of posts 2..7
            hits = {h["index"]: h.get("young") for h in rep["concentration"]["hits"]}
            self.assertEqual(hits, {1: True, 6: False})

    def test_small_groups_and_periods_are_flagged(self):
        with tempfile.TemporaryDirectory() as d:
            res, rep = stats(make_work_dir(Path(d)))
            # a group of 2 mature posts is not a pattern: it leaves the ranking for smallGroups
            self.assertEqual([p["patternName"] for p in rep["patterns"]], ["B"])
            self.assertFalse(rep["patterns"][0]["belowMinimum"])
            self.assertEqual([(g["patternName"], g["belowMinimum"]) for g in rep["smallGroups"]], [("A", True)])
            self.assertIn("smallGroups: A (", res.stderr)
            periods = {s["value"]: (s["count"], s["belowMinimum"]) for s in rep["splits"]["period"]}
            self.assertEqual(periods, {"2026-08": (1, True), "2026-09": (2, True), "2026-10": (3, False)})
            self.assertIn("theme", rep["splits"])

    def test_engagement_matches_short_analysis_formula(self):
        with tempfile.TemporaryDirectory() as d:
            _, rep = stats(make_work_dir(Path(d)))
            # (likes + comments + shares + saves) / views * 100 per post, then the median
            ers = sorted(100 * sum(p[2:6]) / p[1] for p in POSTS[2:])
            self.assertAlmostEqual(rep["accountMedianEngagement"], round((ers[2] + ers[3]) / 2, 2), places=1)

    def test_likes_metric_has_no_engagement(self):
        with tempfile.TemporaryDirectory() as d:
            res, rep = stats(make_work_dir(Path(d), metric="likes"))
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(rep["metric"], "likes")
            self.assertIsNone(rep["accountMedianEngagement"])
            self.assertEqual(rep["accountMedianViews"], 250)  # median likes of posts 2..7

    def test_clusters_must_cover_every_index_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_work_dir(Path(d))
            cl = json.loads((root / "clusters.json").read_text())
            cl["unassigned"] = [7, 2]
            (root / "clusters.json").write_text(json.dumps(cl))
            res, _ = stats(root)
            self.assertEqual(res.returncode, 1)


class RenderAndExportTest(unittest.TestCase):
    def test_report_has_product_all_posts_and_sample_note(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_work_dir(Path(d))
            stats(root)
            (root / "insights.json").write_text(json.dumps({"product": {"adaptations": [
                {"index": 6, "title": "T", "hook": "hook for the product", "how": "how"}]}}))
            res = run(SCRIPTS / "render_report.py", root, "--out", root / "report", "--insights", root / "insights.json")
            self.assertEqual(res.returncode, 0, res.stderr)
            html = (root / "report" / "index.html").read_text(encoding="utf-8")
            for marker in ('id="product"', 'id="allgrid"', 'class="sample note"', "hook for the product", 'data-k="v"'):
                self.assertIn(marker, html)
            self.assertEqual(html.split('id="allgrid"')[1].count("<figure"), len(POSTS))

    def test_csv_export_sorted_with_slide_texts(self):
        with tempfile.TemporaryDirectory() as d:
            root = make_work_dir(Path(d))
            stats(root)
            res = run(SCRIPTS / "export_csv.py", root, "--out", root / "posts.csv")
            self.assertEqual(res.returncode, 0, res.stderr)
            with open(root / "posts.csv", encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["index"] for r in rows[:2]], ["1", "6"])
            self.assertEqual(rows[0]["young"], "true")
            row6 = next(r for r in rows if r["index"] == "6")
            self.assertEqual(row6["slide_texts"], "1: first / line | 2: second")
            self.assertEqual(row6["pattern"], "B")
            self.assertEqual(row6["theme"], "other")


if __name__ == "__main__":
    unittest.main()
