"""Offline tests for report.py: synthetic rows, no downloads."""
import csv
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'report.py'
spec = importlib.util.spec_from_file_location('fb_report', SCRIPT)
rep = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rep
spec.loader.exec_module(rep)

COLS = ['impression_rank', 'ad_archive_id', 'ad_library_url', 'media_type', 'display_format', 'start_date',
        'days_running', 'cta_text', 'title', 'body_text', 'video_hd_url', 'video_preview_image_url', 'image_url',
        'hook_text_overlay', 'visual_hook', 'script', 'emotion', 'cta', 'product_moment', 'analysis_status']


def row(rank, aid, hook):
    return {'impression_rank': rank, 'ad_archive_id': aid, 'ad_library_url': '', 'media_type': 'video',
            'display_format': 'VIDEO', 'start_date': '1759000000', 'days_running': '30', 'cta_text': 'Download',
            'title': 'Example', 'body_text': 'Synthetic body', 'video_hd_url': f'https://example.com/v/{aid}.mp4',
            'video_preview_image_url': '', 'image_url': '', 'hook_text_overlay': hook, 'visual_hook': 'A person',
            'script': '[0:00] hello', 'emotion': '', 'cta': 'Download now', 'product_moment': '0:03 app UI',
            'analysis_status': 'ok'}


class ReportTest(unittest.TestCase):
    def test_markdown_is_escaped(self):
        self.assertEqual(rep.md('**a** <b>'), '<b>a</b> &lt;b&gt;')
        self.assertIn('href="https://x.io"', rep.md('[x](https://x.io)'))
        self.assertNotIn('href', rep.md('[x](javascript:alert(1))'))

    def test_asset_key_falls_back_to_file_name(self):
        self.assertEqual(rep.asset_key('https://example.com/v/123_abc.mp4?x=1'), '123_abc')

    def _run(self, insights):
        d = Path(tempfile.mkdtemp())
        with open(d / 'acme_enriched.csv', 'w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            for r in (row(1, '111', 'Hook one'), row(4, '222', 'Hook two'), row('', '333', 'Unranked')):
                w.writerow(r)
        (d / 'insights.json').write_text(json.dumps(insights))
        p = subprocess.run([sys.executable, str(SCRIPT), '--enriched-csv', str(d / 'acme_enriched.csv'),
                            '--insights', str(d / 'insights.json'), '--media', 'none'],
                           capture_output=True, text=True)
        return p, d

    def test_renders_shares_from_ranks(self):
        p, d = self._run({'title': 'Acme', 'clusters': [{'id': 'A', 'name': 'Angle', 'ad_ids': ['111']}]})
        self.assertEqual(p.returncode, 0, p.stderr)
        page = (d / 'acme_report.html').read_text()
        self.assertIn('66.7%', page)  # 1/sqrt(1) / (1 + 1/sqrt(4))
        self.assertIn('Hook one', page)

    def test_unknown_ad_id_fails(self):
        p, _ = self._run({'title': 'Acme', 'clusters': [{'id': 'A', 'name': 'Angle', 'ad_ids': ['999']}]})
        self.assertNotEqual(p.returncode, 0)
        self.assertIn('unknown ad_archive_id 999', p.stderr)


if __name__ == '__main__':
    unittest.main()
