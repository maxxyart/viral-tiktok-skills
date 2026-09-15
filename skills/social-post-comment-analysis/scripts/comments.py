#!/usr/bin/env python3
"""Bounded ScrapeCreators collection; offline CSV and semantic-label statistics."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

ENDPOINTS = {
    'tiktok': ('/v1/tiktok/video/comments', '/v1/tiktok/video/comment/replies'),
    'instagram': ('/v2/instagram/post/comments', '/v1/instagram/post/comment/replies'),
}


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def identify(url):
    p = urlparse(url)
    if p.scheme != 'https' or p.username or p.password or p.port:
        raise ValueError('Use a canonical HTTPS post URL')
    if p.hostname in ('www.tiktok.com', 'tiktok.com') and re.fullmatch(r'/@[^/]+/(video|photo)/\d+/?', p.path):
        return 'tiktok', 'https://www.tiktok.com' + p.path.rstrip('/')
    if p.hostname in ('www.instagram.com', 'instagram.com') and re.fullmatch(r'/(p|reel|reels)/[\w-]+/?', p.path):
        return 'instagram', 'https://www.instagram.com' + p.path.rstrip('/') + '/'
    raise ValueError('Expected a TikTok video/photo or Instagram post/reel URL; resolve short links first')


def raw_id(c):
    value = c.get('cid', c.get('id', c.get('pk')))
    if value is None or isinstance(value, (bool, float)):
        raise ValueError('Missing or imprecise comment ID; inspect the response schema')
    return str(value)


def number(value):
    return None if value is None else int(value)


def normalize(c, platform, url, parent, fetched_at, source):
    cid = raw_id(c)
    user = c.get('user') or {}
    parent = parent or c.get('parent_comment_id') or c.get('reply_id')
    parent = '' if str(parent) in ('None', '', '0') else str(parent)
    stamp = c.get('create_time') if platform == 'tiktok' else c.get('created_at')
    if isinstance(stamp, (int, float)):
        stamp = datetime.fromtimestamp(stamp, timezone.utc).isoformat()
    handle = user.get('unique_id') if platform == 'tiktok' else user.get('username')
    return {
        'id': platform + ':' + cid, 'raw_id': cid, 'platform': platform,
        'parent_id': platform + ':' + parent if parent else '',
        'reply_to_id': str(c.get('reply_to_reply_id') or ''),
        'type': 'reply' if parent else 'top_level', 'username': handle or '',
        'author_id': str(user.get('uid', user.get('id', user.get('pk', ''))) or ''),
        'author_name': user.get('nickname', user.get('full_name', '')) or '',
        'text': c.get('text') or '', 'language': c.get('comment_language'),
        'created_at': stamp, 'likes': number(c.get('digg_count') if platform == 'tiktok' else c.get('comment_like_count')),
        'reply_count': number(c.get('reply_comment_total') if platform == 'tiktok' else c.get('child_comment_count')),
        'post_url': url, 'fetched_at': fetched_at, 'source': source,
    }


def page(body):
    if body.get('success') is False or body.get('status_code', 0) not in (None, 0):
        raise ValueError('Provider reported failure; inspect saved response')
    comments = body.get('comments')
    if not isinstance(comments, list):
        raise ValueError('Response has no comments array; schema mismatch, not an empty result')
    cursor = body.get('cursor')
    more = body.get('has_more')
    if more is None:
        more = cursor not in (None, '', 0, '0')
    elif more not in (True, False, 0, 1):
        raise ValueError('Unexpected has_more type')
    return comments, cursor, bool(more)


def rebuild(out):
    meta = read(out / 'manifest.json')
    records, duplicates = {}, 0
    for path in sorted((out / 'raw').glob('*.json')):
        envelope = read(path)
        items, _, _ = page(envelope['response'])
        parent = envelope['params'].get('comment_id', '')
        def add(c, parent_id=''):
            nonlocal duplicates
            row = normalize(c, meta['platform'], meta['url'], parent_id,
                            envelope['fetched_at'], str(path.relative_to(out)))
            if row['id'] in records:
                duplicates += 1
                if not row['parent_id'] and records[row['id']]['parent_id']:
                    row['parent_id'] = records[row['id']]['parent_id']
                    row['type'] = 'reply'
            records[row['id']] = row
            for child in c.get('reply_comment', c.get('replies')) or []:
                add(child, row['raw_id'])
        for c in items:
            add(c, parent)
    rows = list(records.values())
    meta['counts'] = {'unique': len(rows), 'top_level': sum(r['type'] == 'top_level' for r in rows),
                      'replies': sum(r['type'] == 'reply' for r in rows), 'duplicate_occurrences': duplicates}
    meta['raw_pages'] = len(list((out / 'raw').glob('*.json')))
    save(out / 'manifest.json', meta)
    save(out / 'records.json', rows)
    with (out / 'reading.jsonl').open('w', encoding='utf-8') as f:
        for r in rows:
            f.write(json.dumps({k: r[k] for k in ('id', 'parent_id', 'type', 'username', 'text', 'likes')}, ensure_ascii=False) + '\n')
    export_csv(out, rows)
    return rows


def export_csv(out, rows, labels=None):
    labels = labels or {}
    fields = ['id', 'parent_id', 'platform', 'type', 'username', 'author_id', 'author_name',
              'text', 'language', 'created_at', 'likes', 'reply_count', 'post_url', 'fetched_at',
              'source', 'primary', 'secondary', 'relevance', 'actor', 'note', 'csv_escaped_fields']
    expected = []
    for r in rows:
        label = labels.get(r['id'], {})
        row = {k: r.get(k) for k in fields}
        for k in ('primary', 'relevance', 'actor', 'note'):
            row[k] = label.get(k, '')
        row['secondary'] = ';'.join(label.get('secondary', []))
        row['author_id'] = r['platform'] + ':' + r['author_id'] if r['author_id'] else ''
        escaped = []
        for k, value in row.items():
            if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
                escaped.append(k)
                row[k] = "'" + value
        row['csv_escaped_fields'] = ';'.join(escaped)
        expected.append({k: '' if v is None else str(v) for k, v in row.items()})
    target = out / 'comments.csv'
    with target.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(expected)
    with target.open(encoding='utf-8-sig', newline='') as f:
        actual = list(csv.DictReader(f))
    if actual != expected or len({r['id'] for r in actual}) != len(rows):
        raise ValueError('CSV round-trip or ID uniqueness verification failed')
    for original, result in zip(rows, actual):
        restored = result['text'][1:] if 'text' in result['csv_escaped_fields'].split(';') else result['text']
        if restored != original['text']:
            raise ValueError('CSV text preservation failed')


def import_page(url, source, out, parent=''):
    platform, url = identify(url)
    body = read(source)
    page(body)
    manifest = out / 'manifest.json'
    meta = read(manifest) if manifest.exists() else {'platform': platform, 'url': url, 'runs': []}
    if meta['platform'] != platform or meta['url'] != url:
        raise ValueError('Output directory belongs to a different post')
    # Imported source mtime is provenance, not a verified request timestamp.
    timestamp = datetime.fromtimestamp(source.stat().st_mtime, timezone.utc).isoformat()
    digest = hashlib.sha256(json.dumps([body, parent], sort_keys=True).encode()).hexdigest()[:24]
    meta.setdefault('imports', []).append({'imported_at': now(), 'source_file': source.name,
                                           'timestamp_basis': 'source_mtime', 'parent_id': parent})
    save(manifest, meta)
    if not list((out / 'raw').glob('*-' + digest + '.json')):
        seq = len(list((out / 'raw').glob('*.json')))
        save(out / 'raw' / f'{seq:06d}-{digest}.json', {
            'params': {'comment_id': parent} if parent else {}, 'fetched_at': timestamp,
            'timestamp_basis': 'source_mtime', 'response': body})
    return rebuild(out)


class BudgetStop(Exception):
    pass


class Collector:
    def __init__(self, args):
        self.args = args
        self.out = args.out
        self.platform, self.url = identify(args.url)
        self.key = os.environ.get('SCRAPE_CREATORS_API_KEY') or os.environ.get('SCRAPECREATORS_API_KEY')
        if not self.key and args.env_file:
            for line in args.env_file.read_text().splitlines():
                key, sep, value = line.strip().partition('=')
                if sep and key in ('SCRAPE_CREATORS_API_KEY', 'SCRAPECREATORS_API_KEY'):
                    self.key = value.strip().strip('"\'')
        self.stopped = False
        self.deadline = time.monotonic() + args.max_seconds
        self.run = {'started_at': now(), 'attempts': 0, 'confirmed_credits': 0,
                    'unknown_charge_attempts': 0, 'cached_pages': 0, 'streams': []}
        manifest = self.out / 'manifest.json'
        self.meta = read(manifest) if manifest.exists() else {'platform': self.platform, 'url': self.url, 'runs': []}
        if self.meta['url'] != self.url or self.meta['platform'] != self.platform:
            raise ValueError('Output directory belongs to a different post')
        self.meta['runs'].append(self.run)
        self.checkpoint()

    def checkpoint(self):
        save(self.out / 'manifest.json', self.meta)

    def check(self, network=False):
        if self.stopped:
            raise BudgetStop('user_stop')
        if time.monotonic() >= self.deadline:
            raise BudgetStop('time_limit')
        if network and self.run['attempts'] >= self.args.max_calls:
            raise BudgetStop('call_limit')

    def request(self, endpoint, params):
        self.check()
        digest = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()[:24]
        cached = next(iter((self.out / 'raw').glob('*-' + digest + '.json')), None)
        if cached:
            self.run['cached_pages'] += 1
            return read(cached)['response']
        if not self.key:
            raise ValueError('Set SCRAPE_CREATORS_API_KEY or use export for offline work')
        for attempt in range(2):
            self.check(network=True)
            self.run['attempts'] += 1
            self.run['unknown_charge_attempts'] += 1
            self.checkpoint()
            request = Request('https://api.scrapecreators.com' + endpoint + '?' + urlencode(params),
                              headers={'x-api-key': self.key})
            try:
                with urlopen(request, timeout=max(0.1, min(30, self.deadline - time.monotonic()))) as response:
                    body = json.load(response)
                if body.get('credits_charged') is not None:
                    self.run['confirmed_credits'] += int(body['credits_charged'])
                    self.run['unknown_charge_attempts'] -= 1
                try:
                    page(body)
                except ValueError:
                    save(self.out / 'errors' / f'{self.run["attempts"]:06d}-{digest}.json',
                         {'endpoint': endpoint, 'params': params, 'fetched_at': now(), 'response': body})
                    raise
                seq = len(list((self.out / 'raw').glob('*.json')))
                save(self.out / 'raw' / f'{seq:06d}-{digest}.json', {
                    'endpoint': endpoint, 'params': params, 'fetched_at': now(), 'response': body})
                self.checkpoint()
                return body
            except HTTPError as exc:
                if exc.code not in (429, 500, 502, 503, 504) or attempt:
                    raise ValueError(f'ScrapeCreators HTTP {exc.code}; saved pages remain usable') from None
            except (URLError, TimeoutError):
                if attempt:
                    raise ValueError('ScrapeCreators network failure; saved pages remain usable') from None
            for _ in range(10):
                self.check()
                time.sleep(0.1)

    def stream(self, parent=''):
        cursor, seen_cursors, seen_ids = None, set(), set()
        state = {'parent_id': parent or None, 'pages': 0, 'stop_reason': 'running'}
        self.run['streams'].append(state)
        try:
            while True:
                self.check()
                params = {'url': self.url}
                if cursor is not None:
                    params['cursor'] = cursor
                if parent:
                    params['comment_id'] = parent
                body = self.request(ENDPOINTS[self.platform][bool(parent)], params)
                items, next_cursor, more = page(body)
                state['pages'] += 1
                state['provider_has_more'] = more
                state['next_cursor'] = next_cursor
                if body.get('total') is not None:
                    state.setdefault('observed_totals', []).append(body['total'])
                ids = {raw_id(c) for c in items}
                added = ids - seen_ids
                seen_ids.update(ids)
                state['unique_in_stream'] = len(seen_ids)
                self.checkpoint()
                print(json.dumps({'stream': parent or 'top_level', 'unique': len(seen_ids),
                                  'attempts': self.run['attempts']}, ensure_ascii=False), flush=True)
                if not more:
                    state['stop_reason'] = 'api_exhausted'
                    break
                if not parent and not self.args.all and len(seen_ids) >= self.args.limit:
                    state['stop_reason'] = 'sample_limit'
                    break
                if not added:
                    state['stop_reason'] = 'no_new_ids'
                    break
                if next_cursor in (None, '') or str(next_cursor) in seen_cursors:
                    state['stop_reason'] = 'cursor_stalled'
                    break
                seen_cursors.add(str(next_cursor))
                cursor = next_cursor
        except BudgetStop as exc:
            state['stop_reason'] = str(exc)
            raise
        except Exception:
            state['stop_reason'] = 'error'
            raise

    def run_collection(self):
        try:
            if self.args.reply_id:
                for parent in dict.fromkeys(self.args.reply_id):
                    self.stream(parent.removeprefix(self.platform + ':'))
            else:
                self.stream()
            self.run['stop_reason'] = self.run['streams'][-1]['stop_reason']
        except BudgetStop as exc:
            self.run['stop_reason'] = str(exc)
        except Exception:
            self.run['stop_reason'] = 'error'
            raise
        finally:
            self.run['finished_at'] = now()
            self.checkpoint()
            rows = rebuild(self.out)
            print(json.dumps({'rows': len(rows), 'stop_reason': self.run['stop_reason'],
                              'out': str(self.out)}, ensure_ascii=False), flush=True)


def analyze(out, labels_path, allow_partial=False):
    rows = read(out / 'records.json')
    data = read(labels_path)
    themes = data['themes']
    if not isinstance(themes, dict) or not themes or any(not isinstance(v, str) or not v.strip() for v in themes.values()):
        raise ValueError('Define nonempty theme names')
    known = {r['id'] for r in rows}
    labels = {}
    for label in data['labels']:
        cid = label['id']
        if cid not in known or cid in labels:
            raise ValueError('Unknown or duplicate label ID: ' + cid)
        assigned = [label['primary']] + label.get('secondary', [])
        if any(t not in themes for t in assigned) or len(assigned) != len(set(assigned)):
            raise ValueError('Undefined or duplicate themes: ' + cid)
        if label['relevance'] not in ('substantive', 'social', 'spam', 'unclear') or label['actor'] not in ('audience', 'creator', 'unknown'):
            raise ValueError('Invalid relevance/actor: ' + cid)
        if not isinstance(label.get('note'), str) or not label['note'].strip():
            raise ValueError('Missing evidence note: ' + cid)
        labels[cid] = label
    missing = sorted(known - labels.keys())
    if missing and not allow_partial:
        raise ValueError(f'{len(missing)} unreviewed IDs; label them or explicitly use --allow-partial')
    summary = {'collected': len(rows), 'analyzed': len(labels), 'unreviewed': len(missing),
               'unreviewed_ids': missing, 'actors': {}, 'relevance': {}, 'views': {}}
    for field, dest in [('actor', 'actors'), ('relevance', 'relevance')]:
        for label in labels.values():
            k = label[field]
            summary[dest][k] = summary[dest].get(k, 0) + 1
    for kind in ('top_level', 'reply'):
        subset = [r for r in rows if r['type'] == kind and r['id'] in labels
                  and labels[r['id']]['actor'] == 'audience' and labels[r['id']]['relevance'] == 'substantive']
        entries = []
        for theme, title in themes.items():
            primary = [r for r in subset if labels[r['id']]['primary'] == theme]
            mentioned = [r for r in subset if theme in [labels[r['id']]['primary']] + labels[r['id']].get('secondary', [])]
            entries.append({'theme': theme, 'title': title, 'primary_count': len(primary),
                            'primary_pct': 100 * len(primary) / len(subset) if subset else None,
                            'mention_count': len(mentioned),
                            'likes_observed_sum': sum(r['likes'] or 0 for r in mentioned),
                            'likes_missing': sum(r['likes'] is None for r in mentioned),
                            'example_ids': [r['id'] for r in sorted(mentioned, key=lambda r: r['likes'] or 0, reverse=True)[:3]]})
        summary['views'][kind] = {'denominator': len(subset), 'themes': sorted(entries, key=lambda e: -e['primary_count'])}
    save(out / 'analysis.json', summary)
    export_csv(out, rows, labels)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fetch = commands.add_parser('fetch')
    fetch.add_argument('url')
    fetch.add_argument('--out', type=Path, required=True)
    fetch.add_argument('--limit', type=int, default=300, help='Root target; final page can exceed it')
    fetch.add_argument('--max-calls', type=int, default=20)
    fetch.add_argument('--max-seconds', type=float, default=120)
    fetch.add_argument('--all', action='store_true', help='Explicit exhaustive intent; time/call caps still apply')
    fetch.add_argument('--reply-id', action='append', default=[])
    fetch.add_argument('--env-file', type=Path)
    export = commands.add_parser('export')
    export.add_argument('--out', type=Path, required=True)
    imported = commands.add_parser('import-page', help='Import a saved provider response; zero network calls')
    imported.add_argument('url')
    imported.add_argument('source', type=Path)
    imported.add_argument('--out', type=Path, required=True)
    imported.add_argument('--parent-id', default='', help='Raw parent ID for a saved replies page')
    analysis = commands.add_parser('analyze')
    analysis.add_argument('--out', type=Path, required=True)
    analysis.add_argument('--labels', type=Path, required=True)
    analysis.add_argument('--allow-partial', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'fetch':
            if min(args.limit, args.max_calls, args.max_seconds) <= 0:
                raise ValueError('Limits must be positive')
            collector = Collector(args)
            def stop(signum, frame):
                collector.stopped = True
                raise BudgetStop('user_stop')
            signal.signal(signal.SIGINT, stop)
            signal.signal(signal.SIGTERM, stop)
            collector.run_collection()
        elif args.command == 'export':
            print(json.dumps({'rows': len(rebuild(args.out)), 'network_calls': 0}))
        elif args.command == 'import-page':
            print(json.dumps({'rows': len(import_page(args.url, args.source, args.out, args.parent_id)), 'network_calls': 0}))
        else:
            result = analyze(args.out, args.labels, args.allow_partial)
            print(json.dumps({k: result[k] for k in ('collected', 'analyzed', 'unreviewed')}))
    except (ValueError, KeyError, OSError) as exc:
        parser.exit(1, f'Error: {exc}\n')


if __name__ == '__main__':
    main()
