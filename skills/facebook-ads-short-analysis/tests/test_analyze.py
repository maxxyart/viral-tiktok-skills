"""Offline tests: no network, no API key. Ads below are synthetic."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze.py'
spec = importlib.util.spec_from_file_location('fb_short', MODULE)
a = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = a
spec.loader.exec_module(a)


class ShortAnalysisTest(unittest.TestCase):
    def test_landing_classes(self):
        self.assertEqual(a.classify_landing('https://apps.apple.com/app/id1')[0], 'ios_app_store')
        self.assertEqual(a.classify_landing('https://play.google.com/store/apps/details?id=x')[0], 'google_play')
        self.assertEqual(a.classify_landing('https://app.onelink.me/abc')[0], 'attribution_link')
        self.assertEqual(a.classify_landing('https://quiz.example.com/start')[0], 'web_funnel')
        self.assertEqual(a.classify_landing('')[0], 'none')

    def test_media_type_prefers_snapshot_content(self):
        self.assertEqual(a.classify_media({'snapshot': {'videos': [{}]}}), 'video')
        self.assertEqual(a.classify_media({'snapshot': {'cards': [{}]}}), 'carousel')
        self.assertEqual(a.classify_media({'snapshot': {'display_format': 'IMAGE'}}), 'image')

    def test_days_running_uses_end_date(self):
        self.assertEqual(a.days_running({'start_date': 1759000000, 'end_date': 1759000000 + 10 * 86400}), 10)
        self.assertEqual(a.days_running({}), '')

    def test_env_file_is_explicit(self):
        a.API_KEY = ''
        with tempfile.NamedTemporaryFile('w', suffix='.env', delete=False) as f:
            f.write('export SCRAPECREATORS_API_KEY="test-value"\n')
        try:
            a.load_env_file(f.name)
            self.assertEqual(a.API_KEY, 'test-value')
        finally:
            os.unlink(f.name)
            a.API_KEY = ''


if __name__ == '__main__':
    unittest.main()
