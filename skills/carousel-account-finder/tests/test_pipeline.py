"""Offline tests: no network, no API key. ScrapeCreators is replaced by a fake `api`; slides are local files
served through file:// URLs. All accounts and posts below are synthetic."""
import contextlib
import csv
import importlib.util
import io
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import time
import unittest
from unittest import mock

from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('common', SCRIPTS / 'common.py')
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)

NOW = int(time.time())
DAY = 86400
GAL = [500_000, 30_000, 25_000, 20_000, 15_000, 5_000, 4_000, 3_000]  # carousel-first account


def aweme(i, views, age_days, slides=(), handle=''):
    images = [{'display_image': {'url_list': [u]}} for u in slides]
    return {'aweme_id': str(i), 'create_time': NOW - age_days * DAY, 'aweme_type': 150 if slides else 0,
            'statistics': {'play_count': views, 'digg_count': views // 10, 'comment_count': views // 100,
                           'collect_count': views // 50, 'share_count': 1},
            'image_post_info': {'images': images} if slides else {}, 'desc': f'post {i} link in bio',
            'author': {'unique_id': handle}}


class FakeScrapeCreators:
    def __init__(self, slide_urls):
        s = slide_urls
        self.feeds = {
            'carouselgal': [aweme(100 + k, v, k + 1, s) for k, v in enumerate(GAL)]
                           + [aweme(200, 1_000, 2), aweme(201, 1_000, 3)],
            'vidguy': [aweme(300 + k, 2_000, k + 1) for k in range(10)] + [aweme(399, 200_000, 4, s)],
            'oldie': [aweme(400, 90_000, 700, s)],
        }

    def __call__(self, path, params, tries=5):
        if path == '/v1/tiktok/search/top':
            items = []
            for h, pid, days in (('carouselgal', '100', 1), ('vidguy', '399', 4), ('oldie', '400', 700)):
                date = time.strftime('%Y-%m-%dT00:00:00', time.gmtime(NOW - days * DAY))
                items.append({'id': pid, 'content_type': 'multi_photo', 'create_time': date,
                              'author': {'unique_id': h}, 'statistics': {'play_count': 1}, 'images': [1, 2, 3]})
            items.append({'id': '999', 'content_type': 'video', 'author': {'unique_id': 'nobody'}})
            return {'items': items, 'cursor': None}
        if path == '/v1/tiktok/profile':
            return {'user': {'signature': 'synthetic bio', 'nickname': params['handle']},
                    'stats': {'followerCount': 10_000, 'heartCount': 50_000, 'videoCount': 40}}
        if path == '/v3/tiktok/profile/videos':
            return {'aweme_list': self.feeds.get(params['handle'], []), 'has_more': False}
        raise AssertionError(path)


def run(script, *argv):
    out = io.StringIO()
    with mock.patch.object(sys, 'argv', [str(SCRIPTS / script), *map(str, argv)]), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        runpy.run_path(str(SCRIPTS / script), run_name='__main__')
    return out.getvalue()


class PipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        cls.out = root / 'run'
        slides = []
        for n, color in enumerate(('red', 'green', 'blue'), 1):
            p = root / f'slide{n}.jpeg'
            Image.new('RGB', (1080, 1350), color).save(p)
            slides.append(p.as_uri())
        cls.fake = FakeScrapeCreators(slides)
        common.api = cls.fake
        cls.patch = mock.patch.dict(sys.modules, {'common': common})
        cls.patch.start()
        since = time.strftime('%Y-%m-%d', time.gmtime(NOW - 365 * DAY))
        cls.search_log = run('search.py', cls.out, '--since', since, 'sex ed for couples')
        cls.screen_log = run('screen.py', cls.out, '--since', since, '--pool', cls.out / 'pool.txt', '--workers', 2)
        cls.cand_log = run('candidates.py', cls.out)
        run('fetch_top5.py', cls.out, '--jobs')

    @classmethod
    def tearDownClass(cls):
        cls.patch.stop()
        cls.tmp.cleanup()

    def load(self, name):
        return json.loads((self.out / name).read_text())

    def test_search_keeps_fresh_carousel_authors(self):
        pool = (self.out / 'pool.txt').read_text().split('\n')
        self.assertEqual(pool, ['carouselgal', 'vidguy'])
        self.assertIn('oldie', self.load('search_candidates.json')['handles'])
        self.assertNotIn('nobody', self.load('search_candidates.json')['handles'])

    def test_screen_passes_only_the_carousel_first_account(self):
        scr = self.load('screening.json')
        gal, vid = scr['carouselgal'], scr['vidguy']
        self.assertTrue(gal['pass'])
        self.assertEqual((gal['carousels_win'], gal['videos_win'], gal['carousel_share']), (8, 2, 0.8))
        self.assertEqual(gal['car_median_views'], 17_500)
        self.assertEqual(gal['tier'], 'карусельный')
        self.assertFalse(vid['pass'])
        self.assertTrue(any(r.startswith('карусели 1/11') for r in vid['reasons']))

    def test_candidates_three_blocks(self):
        c = self.load('candidates.json')
        self.assertEqual(c['mono'], ['carouselgal'])
        self.assertEqual(c['median_all'], {'carouselgal': 10_000, 'vidguy': 2_000})
        self.assertEqual({(s['handle'], s['id']) for s in c['super']}, {('carouselgal', '100'), ('vidguy', '399')})
        self.assertEqual(c['repeat'], {'carouselgal': ['100', '101', '102', '103', '104']})
        self.assertEqual(c['jobs']['vidguy'], {'ids': ['399'], 'roles': ['super']})

    def test_fetch_writes_assets_and_brief(self):
        base = self.out / 'acc' / 'carouselgal'
        brief = json.loads((base / 'brief.json').read_text())
        self.assertEqual(len(brief['top5']), 5)
        self.assertEqual(brief['top5'][0]['x'], 50.0)
        with Image.open(base / 'strips' / '100.jpg') as im:
            self.assertEqual(im.size, (720 * 3, 900))
        with Image.open(base / 'full' / '100_01.jpg') as im:
            self.assertLessEqual(max(im.size), 1080)
        self.assertTrue((base / 'sheets' / '100.jpg').exists() and (base / 'thumbs' / '100.jpg').exists())
        self.assertGreater(brief['product_signals']['posts_with_anchor_or_keyword'], 0)

    def test_triage_and_hooks_sheets(self):
        run('triage.py', self.out, '--workers', 2)
        self.assertEqual(self.load('triage/index.json'), {'carouselgal': 5, 'vidguy': 1})
        self.assertIn('synthetic bio', (self.out / 'triage' / 'carouselgal.txt').read_text())
        log = run('hooks.py', self.out, '--accounts', 'carouselgal,vidguy', '--full-top', 2)
        self.assertEqual(self.load('hooks/full_ids.json'), {'carouselgal': ['100'], 'vidguy': ['399']})
        self.assertEqual([t['id'] for t in self.load('hooks/carouselgal.json')], ['101', '102', '103', '104'])
        self.assertIn('slide-1 only: 4 carousels', log)

    def test_validate_then_build(self):
        (self.out / 'ocr').mkdir(exist_ok=True)
        (self.out / 'analysis').mkdir(exist_ok=True)
        (self.out / 'taxonomy.json').write_text(json.dumps({
            'personas': [{'id': 'P1', 'name': 'Couples in a dry spell', 'label_en': 'dry-spell couples'}],
            'angles': [{'id': 'A1', 'name': 'Signs list', 'label_en': 'signs list'}]}))
        jobs = self.load('candidates.json')['jobs']
        for h, j in jobs.items():
            for i in j['ids']:
                (self.out / 'ocr' / f'{i}.json').write_text(json.dumps({
                    'id': i, 'handle': h, 'slides': [{'n': 1, 'text': f'hook {i}'}], 'visual': {'format': 'text on photo'},
                    'hook': f'hook {i}', 'hook_meaning': 'signs your partner wants more', 'formula': 'hook → signs → CTA'}))
            (self.out / 'analysis' / f'{h}.json').write_text(json.dumps({
                'handle': h, 'topic': 'couples intimacy tips', 'hooks': {i: f'hook {i}' for i in j['ids']},
                'carousels': {i: {'fit': 'в нише', 'persona': 'P1', 'angle': 'A1'} for i in j['ids']},
                'consistency_level': 'высокая', 'niche_fit': 'в нише', 'fit_reason': 'Couples advice slides.',
                'persona': 'P1', 'angle': 'A1', 'angle_use': 'Signs list ending on the app.', 'product_yes': h == 'carouselgal',
                'product_name': 'Notes app' if h == 'carouselgal' else '', 'product': 'Last slide.',
                'repeats': [{'hook_template': 'signs your partner wants more', 'formula': 'hook → signs → CTA',
                             'ids': ['101', '102', '103'], 'why': 'same list template'}] if h == 'carouselgal' else []}))
        self.assertIn('0 need a rerun', run('validate.py', self.out))

        (self.out / 'analysis' / 'carouselgal.integration.json').write_text(json.dumps(
            {'handle': 'carouselgal', 'quotes': [{'where': 'bio', 'text': 'synthetic bio'}]}))
        log = run('build.py', self.out, '--topic', 'couples intimacy', '--max-accounts', 10)
        self.assertIn('1 accounts shown of 1 passing', log)
        page = (self.out / 'carousel-accounts.html').read_text(encoding='utf-8')
        for placeholder in ('__TITLE__', '__TOPIC__', 'const DATA = /*DATA*/'):
            self.assertNotIn(placeholder, page)
        data = json.loads(page.split('const DATA = ', 1)[1].split(';\n', 1)[0].replace('<\\/', '</'))
        acc = data['accounts'][0]
        self.assertEqual((acc['handle'], acc['analysis']['niche_fit'], acc['analysis']['persona']),
                         ('carouselgal', 'in niche', 'P1 · dry-spell couples'))
        self.assertEqual(acc['analysis']['quotes'][0]['text'], 'synthetic bio')
        self.assertEqual([s['handle'] for s in data['supers']], ['vidguy'])  # carouselgal's super is in its account card
        self.assertEqual([(g['handle'], g['n'], g['group_x']) for g in data['repeats']], [('carouselgal', 3, 2.5)])
        with (self.out / 'accounts.csv').open(encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual([r['handle'] for r in rows], ['carouselgal', 'vidguy'])
        self.assertEqual(rows[0]['found_via'], 'sex ed for couples')
        batches = self.load('publish_batches.json')
        files = [f for b in batches for f in b]
        self.assertTrue(files and all((self.out / f).exists() for f in files))


class KeyTest(unittest.TestCase):
    def test_key_comes_only_from_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
                common.api_key()
        with mock.patch.dict(os.environ, {'SCRAPECREATORS_API_KEY': 'test-value'}, clear=True):
            self.assertEqual(common.api_key(), 'test-value')

    def test_to_jpeg_limits_the_longest_side(self):
        with tempfile.TemporaryDirectory() as td:
            src, dst = os.path.join(td, 'in.png'), os.path.join(td, 'out.jpg')
            Image.new('RGB', (2000, 1000), 'white').save(src)
            self.assertTrue(common.to_jpeg(src, dst, 600))
            with Image.open(dst) as im:
                self.assertEqual((im.format, im.size), ('JPEG', (600, 300)))


if __name__ == '__main__':
    unittest.main()
