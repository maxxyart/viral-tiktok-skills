"""Offline regression tests. All comments and accounts below are synthetic."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / 'scripts' / 'comments.py'
spec = importlib.util.spec_from_file_location('comments', MODULE)
c = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = c
spec.loader.exec_module(c)

TT = 'https://www.tiktok.com/@example/video/1234567890123456789'
IG = 'https://www.instagram.com/reel/Example123/'


def comment(cid='1234567890123456789', text='Where can I download it?'):
    return {'cid': cid, 'text': text, 'user': {'unique_id': 'example'},
            'digg_count': 10, 'reply_id': '0'}


class CommentsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **kwargs):
        values = dict(url=TT, out=self.out, limit=2, max_calls=3, max_seconds=10,
                      all=False, reply_id=[], env_file=None)
        values.update(kwargs)
        return argparse.Namespace(**values)

    def add_page(self, n, items, platform='tiktok', parent='', more=False, cursor=None):
        if not (self.out / 'manifest.json').exists():
            c.save(self.out / 'manifest.json', {'platform': platform, 'url': TT if platform == 'tiktok' else IG, 'runs': []})
        c.save(self.out / 'raw' / f'{n:06d}.json', {
            'params': {'comment_id': parent} if parent else {}, 'fetched_at': '2026-09-15T00:00:00Z',
            'response': {'comments': items, 'has_more': more, 'cursor': cursor}})

    def test_url_scope(self):
        self.assertEqual(c.identify(IG + '?igsh=abc')[1], IG)
        for url in ('https://tiktok.com.evil.test/@x/video/1', 'https://www.instagram.com/user/', 'http://www.tiktok.com/@x/video/1'):
            with self.assertRaises(ValueError):
                c.identify(url)

    def test_instagram_nulls_and_replies(self):
        self.add_page(0, [{'id': '90000000000000001', 'text': 'Hello', 'child_comment_count': None,
                          'replies': [{'id': '90000000000000002', 'text': 'A reply', 'comment_like_count': 0}]}], 'instagram')
        rows = c.rebuild(self.out)
        self.assertIsNone(rows[0]['reply_count'])
        self.assertIsNone(rows[0]['likes'])
        self.assertEqual(rows[1]['parent_id'], 'instagram:90000000000000001')
        self.assertEqual(rows[1]['likes'], 0)

    def test_dedupe_embedded_and_reply_endpoint(self):
        root = comment('10')
        reply = comment('11', 'Reply')
        root['reply_comment'] = [reply]
        self.add_page(0, [root])
        self.add_page(1, [reply], parent='10')
        rows = c.rebuild(self.out)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1]['type'], 'reply')
        self.assertEqual(c.read(self.out / 'manifest.json')['counts']['duplicate_occurrences'], 1)

    def test_safe_lossless_multiline_csv(self):
        text = '  =HYPERLINK("bad")\nкириллица, "quote" 😁'
        self.add_page(0, [comment(text=text)])
        rows = c.rebuild(self.out)
        with (self.out / 'comments.csv').open(encoding='utf-8-sig', newline='') as f:
            result = list(csv.DictReader(f))[0]
        self.assertTrue(result['id'].startswith('tiktok:'))
        self.assertEqual(result['text'][1:], text)
        self.assertEqual(rows[0]['text'], text)
        self.assertIn('text', result['csv_escaped_fields'])

    def test_schema_failure_not_empty_result(self):
        for body in ({'success': False, 'comments': []}, {'success': True}, {'comments': [], 'has_more': 'false'}):
            with self.assertRaises(ValueError):
                c.page(body)
        self.assertTrue(c.page({'comments': [], 'cursor': 'opaque'})[2])
        self.assertFalse(c.page({'comments': [], 'cursor': None})[2])

    def test_looping_cursor_stops(self):
        collector = c.Collector(self.args(limit=100))
        bodies = [{'comments': [comment('1')], 'has_more': 1, 'cursor': 20},
                  {'comments': [comment('2')], 'has_more': 1, 'cursor': 20}]
        with patch.object(collector, 'request', side_effect=bodies) as request:
            collector.run_collection()
        self.assertEqual(request.call_count, 2)
        self.assertEqual(collector.run['stop_reason'], 'cursor_stalled')

    def test_budget_and_stop_prevent_new_calls(self):
        collector = c.Collector(self.args(max_calls=1))
        collector.run['attempts'] = 1
        with patch.object(c, 'urlopen') as network, self.assertRaises(c.BudgetStop):
            collector.key = 'synthetic'
            collector.request('/fake', {})
        network.assert_not_called()
        collector.stopped = True
        with self.assertRaisesRegex(c.BudgetStop, 'user_stop'):
            collector.check()

    def test_cached_pages_reused_without_key(self):
        collector = c.Collector(self.args())
        collector.key = 'synthetic'
        body = {'comments': [comment()], 'has_more': False, 'credits_charged': 1}
        import io
        with patch.object(c, 'urlopen', return_value=io.StringIO(json.dumps(body))) as network:
            collector.request('/fake', {'url': TT})
        self.assertEqual(network.call_count, 1)
        collector.key = None
        with patch.object(c, 'urlopen') as network:
            self.assertEqual(collector.request('/fake', {'url': TT}), body)
        network.assert_not_called()
        self.assertEqual(collector.run['confirmed_credits'], 1)

    def labels(self, rows):
        labels = [{'id': r['id'], 'primary': 'access', 'secondary': [], 'actor': 'audience',
                   'relevance': 'substantive', 'note': 'Asks about download.'} for r in rows]
        return {'themes': {'access': 'Access', 'price': 'Pricing'}, 'labels': labels}

    def test_labels_missing_duplicate_unknown_rejected(self):
        self.add_page(0, [comment('1'), comment('2')])
        rows = c.rebuild(self.out)
        data = self.labels(rows)
        for broken in (data['labels'][:1], [data['labels'][0]] * 2,
                       [dict(data['labels'][0], id='tiktok:999')]):
            c.save(self.out / 'labels.json', dict(data, labels=broken))
            with self.assertRaises(ValueError):
                c.analyze(self.out, self.out / 'labels.json')

    def test_audience_denominators_and_secondary_overlap(self):
        self.add_page(0, [comment(str(i)) for i in range(1, 6)])
        self.add_page(1, [comment('6')], parent='1')
        rows = c.rebuild(self.out)
        data = self.labels(rows)
        data['labels'][1]['actor'] = 'creator'
        data['labels'][2]['actor'] = 'unknown'
        data['labels'][3]['relevance'] = 'social'
        data['labels'][0]['secondary'] = ['price']
        c.save(self.out / 'labels.json', data)
        result = c.analyze(self.out, self.out / 'labels.json')
        roots = result['views']['top_level']
        self.assertEqual(roots['denominator'], 2)
        self.assertEqual(result['views']['reply']['denominator'], 1)
        self.assertEqual(roots['themes'][0]['primary_pct'], 100)
        self.assertEqual(roots['themes'][1]['mention_count'], 1)

    def test_partial_explicit_and_tracked(self):
        self.add_page(0, [comment('1'), comment('2')])
        rows = c.rebuild(self.out)
        data = self.labels(rows[:1])
        c.save(self.out / 'labels.json', data)
        result = c.analyze(self.out, self.out / 'labels.json', allow_partial=True)
        self.assertEqual(result['unreviewed_ids'], ['tiktok:2'])
        self.assertEqual(result['views']['top_level']['denominator'], 1)

    def test_empty_response_valid_export(self):
        self.add_page(0, [])
        self.assertEqual(c.rebuild(self.out), [])
        self.assertTrue((self.out / 'comments.csv').read_text(encoding='utf-8-sig').startswith('id,'))

    def test_sample_limit_preserves_last_page(self):
        collector = c.Collector(self.args(limit=1))
        with patch.object(collector, 'request', return_value={'comments': [comment('1'), comment('2')], 'cursor': 20, 'has_more': 1}) as request:
            collector.run_collection()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(collector.run['stop_reason'], 'sample_limit')

    def test_output_directory_cannot_mix_posts(self):
        c.Collector(self.args())
        with self.assertRaises(ValueError):
            c.Collector(self.args(url=IG))

    def test_import_existing_page_offline(self):
        source = self.out / 'existing.json'
        c.save(source, {'comments': [comment()], 'has_more': 0})
        target = self.out / 'imported'
        with patch.object(c, 'urlopen') as network:
            first = c.import_page(TT, source, target)
            second = c.import_page(TT, source, target)
        network.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual(c.read(target / 'manifest.json')['raw_pages'], 1)

    def test_sigterm_exits_and_exports(self):
        import subprocess
        import signal
        runner = '''import sys, time, importlib.util
spec = importlib.util.spec_from_file_location("comments", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
def slow(*args, **kwargs):
    print("REQUEST_STARTED", flush=True)
    time.sleep(30)
m.urlopen = slow
sys.argv = [sys.argv[1], "fetch", sys.argv[2], "--out", sys.argv[3]]
m.main()
'''
        import os
        env = dict(os.environ, SCRAPE_CREATORS_API_KEY='synthetic')
        process = subprocess.Popen([sys.executable, '-c', runner, str(MODULE), TT, str(self.out)],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            self.assertEqual(process.stdout.readline().strip(), 'REQUEST_STARTED')
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(c.read(self.out / 'manifest.json')['runs'][-1]['stop_reason'], 'user_stop')
            self.assertTrue((self.out / 'comments.csv').exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

    def test_end_to_end_fetch_both_platforms(self):
        import io
        for platform, url in [('tiktok', TT), ('instagram', IG)]:
            out = self.out / platform
            collector = c.Collector(self.args(url=url, out=out, limit=100))
            collector.key = 'synthetic'
            item = comment('1') if platform == 'tiktok' else {'id': '1', 'text': 'Where?', 'user': {'username': 'example'}}
            first = {'success': True, 'comments': [item], 'cursor': 'next', 'credits_charged': 1}
            second = {'success': True, 'comments': [], 'cursor': None, 'has_more': False, 'credits_charged': 1}
            with patch.object(c, 'urlopen', side_effect=[io.StringIO(json.dumps(first)), io.StringIO(json.dumps(second))]) as network:
                collector.run_collection()
            self.assertEqual(network.call_count, 2)
            self.assertIn(c.ENDPOINTS[platform][0], network.call_args_list[0].args[0].full_url)
            self.assertIn('cursor=next', network.call_args_list[1].args[0].full_url)
            self.assertNotIn('include_replies', network.call_args_list[0].args[0].full_url)
            self.assertEqual(len(c.read(out / 'records.json')), 1)
            self.assertEqual(collector.run['stop_reason'], 'api_exhausted')

    def test_auth_failure_does_not_retry(self):
        from urllib.error import HTTPError
        collector = c.Collector(self.args())
        collector.key = 'synthetic'
        with patch.object(c, 'urlopen', side_effect=HTTPError('test', 401, 'Unauthorized', {}, None)) as network:
            with self.assertRaisesRegex(ValueError, 'HTTP 401'):
                collector.run_collection()
        self.assertEqual(network.call_count, 1)
        self.assertEqual(collector.run['unknown_charge_attempts'], 1)
        self.assertTrue((self.out / 'comments.csv').exists())

    def test_time_limit_preserves_cache(self):
        collector = c.Collector(self.args())
        collector.deadline = 0
        with patch.object(c, 'urlopen') as network:
            collector.run_collection()
        network.assert_not_called()
        self.assertEqual(collector.run['stop_reason'], 'time_limit')


if __name__ == '__main__':
    unittest.main()
