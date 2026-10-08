"""Offline tests: no network, no model calls. Data below is synthetic."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze.py'
spec = importlib.util.spec_from_file_location('fb_deep', MODULE)
d = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = d
spec.loader.exec_module(d)


class DeepAnalysisTest(unittest.TestCase):
    def test_parse_json_with_wrapping_text(self):
        self.assertEqual(d.parse_json('```json\n{"cta": "Download", "x": {"y": 1}}\n```'),
                         {'cta': 'Download', 'x': {'y': 1}})

    def test_sniff_mime(self):
        self.assertEqual(d.sniff_mime(b'\x89PNG\r\n\x1a\n0000'), 'image/png')
        self.assertEqual(d.sniff_mime(b'RIFF0000WEBP'), 'image/webp')
        self.assertEqual(d.sniff_mime(b'\xff\xd8\xff'), 'image/jpeg')

    def test_no_automatic_key_search(self):
        self.assertEqual(d.ENV_FILES, [])

    def test_env_key_reads_explicit_file(self):
        name = 'FB_DEEP_TEST_KEY'
        os.environ.pop(name, None)
        with tempfile.NamedTemporaryFile('w', suffix='.env', delete=False) as f:
            f.write(f'{name}=abc123\n')
        try:
            d.ENV_FILES.append(f.name)
            self.assertEqual(d.env_key(name), 'abc123')
        finally:
            d.ENV_FILES.clear()
            os.unlink(f.name)


if __name__ == '__main__':
    unittest.main()
