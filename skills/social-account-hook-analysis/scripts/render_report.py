#!/usr/bin/env python3
"""Render the hook analysis as a ready Artifact page: covers grid sized like the
TikTok web profile, virals slide by slide, patterns with stats, visual-layer bars,
storyboard formulas. Claude writes only the texts (insights.json); every number,
hook, cover, slide and top comment comes from the work dir.

Usage:
  python3 render_report.py WORK_DIR --out OUT_DIR [--insights insights.json] [--lang ru|en]

Reads WORK_DIR/meta.json, report.json (pattern_stats.py), clusters.json, cards.json
(hook_text per index), labels.json (theme / product_fit display names, optional) and
WORK_DIR/carousels/NN/ (fetch_slides.py; slides.json = verbatim slide texts, used only as
img alt: nothing is written under a viral). Missing absolute cover/slide paths fall back to the file of
the same name inside WORK_DIR, so a work dir copied into the project re-renders.
Writes OUT_DIR/index.html, covers/NN.jpg (≤480px), slides/cNN_K.jpg (≤540px, virals only),
publish_plan.json. Stdout: page size + publish batches (≤25 files, ≤2.5 MB each).
Young posts and the --since window come from report.json; meta.metric = likes relabels
every number (Instagram posts mode).

insights.json (every key optional; text supports **bold**, *italic*, [text](url or #p1)):
{
  "title": "...", "eyebrow": "...", "lead": "...",
  "summary": ["bullet", ...],
  "virals": [{"index": 13}],   # picks the hits; shown as slides + icon metrics, no texts
  "product": {"title": "...", "lead": "...", "notes": ["..."],
              "adaptations": [{"index": 60, "title": "...", "hook": "hook for the product", "how": "..."}]},
  "allPosts": true,
  "patternNotes": {"<patternName>": "note"},
  "splits": [{"key": "format", "title": "...", "labels": {"video": "Видео"}}],
  "visualNotes": ["..."],
  "formulasTitle": "...", "formulasLead": "...",
  "rulesBox": {"title": "...", "items": ["..."]},
  "formulas": [{"title": "...", "source": "...", "who": "...", "visual": "...", "alts": ["..."],
                "slides": [{"label": "Обложка", "text": "line\\nline", "demo": false}]}],
  "do": ["..."], "dont": ["..."], "caveats": ["..."], "footer": "..."
}
Defaults: virals = hits ≥5× median (up to 4), splits = format + every card split except pinned,
allPosts = a grid of the whole sample sortable by date / views (false hides it).
"""
import argparse, html, json, os, re, shutil, subprocess, sys, time

E = html.escape
PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>'
# stroke icons for the viral metric row (inner SVG markup, 24×24)
ICON = {
    "eye": '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "heart": '<path d="M12 20s-7.2-4.4-9.1-8.8C1.6 8 3.6 4.5 7 4.5c2 0 3.5 1.1 5 2.9 1.5-1.8 3-2.9 5-2.9 3.4 0 5.4 3.5 4.1 6.7C19.2 15.6 12 20 12 20z"/>',
    "comment": '<path d="M20.5 11.5a8 8 0 0 1-11.7 7.1L3.5 20l1.4-4.9a8 8 0 1 1 15.6-3.6z"/>',
    "bookmark": '<path d="M6.5 3.5h11v17l-5.5-4-5.5 4z"/>',
    "share": '<path d="M14 5l7 7-7 7"/><path d="M21 12H10a7 7 0 0 0-7 7"/>',
    "trend": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "layers": '<rect x="3" y="7" width="13" height="14" rx="2"/><path d="M8 3h11a2 2 0 0 1 2 2v11"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "open": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
}
MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
             "сентября", "октября", "ноября", "декабря"]
MONTHS_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTHS_RU_SHORT = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

L = {
 "ru": {
  "title": "Разбор @{h}", "eyebrow": "Разбор {p}-аккаунта · {d}",
  "lead": "Какие хуки стоят на обложках, что внутри у виралов и какие паттерны повторяются. Клик по любой обложке открывает пост.",
  "followers": "Подписчиков", "totalPosts": "Постов всего", "analyzed": "разобрано {n}",
  "carVid": "Каруселей / видео в выборке", "carVidPh": "Каруселей / видео / фото в выборке", "median": "Медиана просмотров",
  "hitsShare": "Виралы ≥5× ({n}) дали", "ofTotal": "из {t}",
  "summary": "Коротко", "virals": "Виралы, слайд за слайдом",
  "viralsLead": "Лента слайдов прокручивается вбок, первый слайд и есть обложка.",
  "viralsCovers": "Виралы крупно", "viralsLeadCovers": "У рилсов нет слайдов, поэтому здесь обложки хитов крупно, со ссылкой на пост.",
  "patterns": "Паттерны обложек",
  "patternsLead": "Каждая обложка попала ровно в один паттерн. Порядок по виральности: медиана просмотров паттерна, делённая на медиану аккаунта ({m}). Под обложкой: множитель к медиане, дата, формат и текст хука как на обложке. Цветная рамка: пост выше 5× медианы.",
  "unassigned": "Без паттерна", "unassignedLead": "Обложки, которым не нашлось хотя бы двух похожих.",
  "visual": "Визуальный слой", "formulas": "Формулы", "rules": "Правила сборки и чего избегать",
  "do": "Делать", "dont": "Не делать", "caveats": "Оговорки",
  "views": "просмотров", "ofMedian": "медианы", "saves": "сохр.", "shares": "репостов",
  "comments": "комм.", "sl": "сл.", "video": "видео", "pinned": "закреп",
  "med": "медиана", "avg": "среднее", "likesMed": "медиана лайков", "savesMed": "медиана сохр.",
  "saveRate": "сохранений", "er": "ER", "outlier": "среднее раздуто одним виралом",
  "small": "меньше 3 постов, это не паттерн", "formula": "Формула", "visualF": "Визуал",
  "topComment": "топ-коммент", "open": "Открыть пост",
  "source": "Источник:", "who": "Кто и где:", "alts": "Ещё хуки:",
  "footer": "Данные ScrapeCreators на {d}. Обложки прочитаны и разложены по двум осям: формула текста и визуальный формат. Цифры посчитал pattern_stats.py, множитель = медиана группы / медиана аккаунта, ER = (лайки + комментарии + репосты + сохранения) / просмотры.",
  "posts": ("пост", "поста", "постов"), "slidesW": ("слайд", "слайда", "слайдов"),
  "photo": "фото", "young": "новый", "few": "мало данных", "slideText": "Текст слайдов",
  "likesW": "лайков", "medianLikes": "Медиана лайков",
  "sampleAll": "Разобраны все {n} постов аккаунта.",
  "sampleLatest": "Разобраны последние {n} из {t} постов: более ранние посты, в том числе возможные виралы, в выборку не попали.",
  "sampleSince": "Разобраны {n} постов, опубликованных с {d}.",
  "windowNote": "В цифрах только посты с {d}, ещё {k} более ранних не учтены.",
  "youngNote": "{n} {posts} моложе {d} дней ещё набирают просмотры: в сетке они есть, в медианах нет.",
  "metricLikes": "Instagram не показывает просмотры каруселей и фото, поэтому все сравнения здесь по лайкам.",
  "product": "Что взять для продукта", "yourHook": "Хук для продукта", "how": "Как адаптировать",
  "allPosts": "Все посты", "allLead": "Вся выборка одной сеткой. По дате видны серии и то, как форматы выдыхаются.",
  "sortBy": "Сортировка", "sortDate": "По дате", "sortViews": "По просмотрам", "sortLikes": "По лайкам",
  "splitTitles": {"format": "Медиана просмотров по формату", "pinned": "Закреп",
                  "has_creator_face": "Лицо автора на обложке", "has_text": "Текст на обложке",
                  "visual_format": "Визуальный формат обложки", "background": "Фон обложки",
                  "has_person": "Человек на обложке", "period": "Медиана по месяцам публикации",
                  "theme": "Темы", "product_fit": "Связь с продуктом"},
  "valueLabels": {"format": {"video": "Видео", "photo": "Фото", "1": "Карусель, 1 слайд", "2-3": "Карусель, 2–3 слайда",
                             "4+": "Карусель, 4+ слайдов"},
                  "pinned": {"true": "Закреплённые", "false": "Остальные"},
                  "product_fit": {"direct": "Прямо в тему продукта", "adjacent": "Рядом", "off": "Мимо"},
                  "_bool": {"true": "Да", "false": "Нет", "unknown": "Не определено"}},
 },
 "en": {
  "title": "@{h} breakdown", "eyebrow": "{p} account breakdown · {d}",
  "lead": "Which cover hooks the account uses, what is inside the hits and which patterns repeat. Click any cover to open the post.",
  "followers": "Followers", "totalPosts": "Posts total", "analyzed": "{n} analyzed",
  "carVid": "Carousels / videos in sample", "carVidPh": "Carousels / videos / photos in sample", "median": "Median views",
  "hitsShare": "Hits ≥5× ({n}) brought", "ofTotal": "of {t}",
  "summary": "In short", "virals": "Hits, slide by slide",
  "viralsLead": "Slides scroll sideways; the first slide is the cover.",
  "viralsCovers": "Hits up close", "viralsLeadCovers": "Reels have no slides, so these are the hit covers, large, linked to the post.",
  "patterns": "Cover patterns",
  "patternsLead": "Every cover sits in exactly one pattern. Sorted by virality: pattern median views divided by the account median ({m}). Under each cover: multiplier, date, format and the hook exactly as written. Colored frame: post above 5× median.",
  "unassigned": "No pattern", "unassignedLead": "Covers without at least two similar ones.",
  "visual": "Visual layer", "formulas": "Formulas", "rules": "Build rules and what to avoid",
  "do": "Do", "dont": "Don't", "caveats": "Caveats",
  "views": "views", "ofMedian": "median", "saves": "saves", "shares": "shares",
  "comments": "comments", "sl": "sl.", "video": "video", "pinned": "pinned",
  "med": "median", "avg": "average", "likesMed": "median likes", "savesMed": "median saves",
  "saveRate": "save rate", "er": "ER", "outlier": "average inflated by one hit",
  "small": "fewer than 3 posts, not a pattern", "formula": "Formula", "visualF": "Visual",
  "topComment": "top comment", "open": "Open post",
  "source": "Source:", "who": "Who and where:", "alts": "More hooks:",
  "footer": "ScrapeCreators data as of {d}. Covers were read and grouped on two axes: text formula and visual format. Numbers by pattern_stats.py; multiplier = group median / account median; ER = (likes + comments + shares + saves) / views.",
  "posts": ("post", "posts", "posts"), "slidesW": ("slide", "slides", "slides"),
  "photo": "photo", "young": "new", "few": "too few", "slideText": "Slide text",
  "likesW": "likes", "medianLikes": "Median likes",
  "sampleAll": "All {n} posts of the account analyzed.",
  "sampleLatest": "The latest {n} of {t} posts analyzed: older posts, possible hits included, are outside the sample.",
  "sampleSince": "{n} posts published since {d} analyzed.",
  "windowNote": "Numbers cover posts since {d}; {k} older ones are left out.",
  "youngNote": "{n} {posts} younger than {d} days are still collecting views: shown in the grids, left out of the medians.",
  "metricLikes": "Instagram shows no views for carousels and photos, so every comparison here uses likes.",
  "product": "What to take for the product", "yourHook": "Hook for the product", "how": "How to adapt",
  "allPosts": "All posts", "allLead": "The whole sample in one grid. Sorted by date it shows series and formats wearing out.",
  "sortBy": "Sort", "sortDate": "By date", "sortViews": "By views", "sortLikes": "By likes",
  "splitTitles": {"format": "Median views by format", "pinned": "Pinned",
                  "has_creator_face": "Creator face on cover", "has_text": "Text on cover",
                  "visual_format": "Cover visual format", "background": "Cover background",
                  "has_person": "Person on cover", "period": "Median by publication month",
                  "theme": "Themes", "product_fit": "Fit with the product"},
  "valueLabels": {"format": {"video": "Video", "photo": "Photo", "1": "Carousel, 1 slide", "2-3": "Carousel, 2–3 slides",
                             "4+": "Carousel, 4+ slides"},
                  "pinned": {"true": "Pinned", "false": "Other"},
                  "product_fit": {"direct": "On the product's topic", "adjacent": "Adjacent", "off": "Off topic"},
                  "_bool": {"true": "Yes", "false": "No", "unknown": "Unknown"}},
 },
}

CSS = """
:root{
  --bg:#F3EDE2; --surface:#FBF8F2; --ink:#1D2A22; --muted:#5C685E; --line:#DDD4C4;
  --green:#22432F; --ember:#B4542A; --ember-soft:#F2DDCC; --chip:#EAE2D3;
  --frame-a:#2E3E33; --frame-b:#56634F; --frame-ink:#FFFFFF;
  --display:"Newsreader", Georgia, "Times New Roman", serif;
  --ui:"Hanken Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
  --wrap:1220px;
}
@media (prefers-color-scheme: dark){ :root:not([data-theme="light"]){
  --bg:#121A15; --surface:#19231D; --ink:#ECE5D7; --muted:#A3ADA2; --line:#2D3A31;
  --green:#93C6A3; --ember:#E68F5C; --ember-soft:#3B261A; --chip:#212C25;
  --frame-a:#26332B; --frame-b:#3E4B40; color-scheme:dark } }
:root[data-theme="dark"]{
  --bg:#121A15; --surface:#19231D; --ink:#ECE5D7; --muted:#A3ADA2; --line:#2D3A31;
  --green:#93C6A3; --ember:#E68F5C; --ember-soft:#3B261A; --chip:#212C25;
  --frame-a:#26332B; --frame-b:#3E4B40; color-scheme:dark }
*{box-sizing:border-box}
body{background:var(--bg); color:var(--ink); font-family:var(--ui); font-size:16px; line-height:1.55;
  padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:0 64px}
.wrap{max-width:var(--wrap); margin:0 auto}
a{color:var(--green)} a:focus-visible,.strip:focus-visible{outline:2px solid var(--ember); outline-offset:3px; border-radius:6px}
h1,h2,h3{font-family:var(--display); font-weight:600; text-wrap:balance; line-height:1.15; margin:0}
h2{font-size:clamp(28px,3.4vw,40px); margin-bottom:8px}
h3{font-size:22px}
h4{font-family:var(--ui); font-size:13px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin:0 0 6px}
p{margin:0}
.lead{max-width:68ch; color:var(--muted)}
section.block{padding-top:56px; display:grid; gap:20px}
.eyebrow{font-size:13px; letter-spacing:.08em; text-transform:uppercase; color:var(--ember); font-weight:600}
.hero{padding-top:40px; display:grid; gap:18px}
.hero h1{font-size:clamp(34px,5.6vw,64px); word-break:break-word}
.hero h1 a{color:var(--ink); text-decoration:none} .hero h1 a:hover{text-decoration:underline; text-decoration-thickness:2px}
.facts{display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:1px; background:var(--line); border:1px solid var(--line); border-radius:10px; overflow:hidden; margin:6px 0 0}
.facts div{background:var(--surface); padding:14px 16px}
.facts dt{font-size:13px; color:var(--muted)}
.facts dd{margin:2px 0 0; font-family:var(--display); font-size:28px; font-variant-numeric:tabular-nums}
.facts dd small{font-family:var(--ui); font-size:13px; color:var(--muted)}
.summary{display:grid; gap:12px; max-width:78ch; padding:0; margin:0; list-style:none}
.summary li{display:grid; grid-template-columns:18px 1fr; gap:8px}
.summary li::before{content:""; width:8px; height:8px; margin-top:9px; border-radius:2px; background:var(--ember)}
.chips{display:flex; flex-wrap:wrap; gap:6px; margin-top:8px}
.chip{font-size:13px; background:var(--chip); border-radius:999px; padding:3px 10px; font-variant-numeric:tabular-nums; white-space:nowrap}
.chip.strong{background:var(--green); color:var(--bg); font-weight:600}
.chip.warn{background:var(--ember-soft); color:var(--ember)}
.viral{background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:20px; display:grid; gap:14px}
.vstats{display:flex; flex-wrap:wrap; align-items:center; gap:8px 18px; font-variant-numeric:tabular-nums}
.vs{display:inline-flex; align-items:center; gap:6px; font-size:16px; font-weight:600; white-space:nowrap; color:var(--ink)}
.vs svg{width:19px; height:19px; flex:0 0 auto; fill:none; stroke:var(--muted); stroke-width:2; stroke-linecap:round; stroke-linejoin:round}
.vs small{font-size:13px; font-weight:400; color:var(--muted)}
.vs.mult{color:var(--green)} .vs.mult svg{stroke:var(--green)}
.vs.open{margin-left:auto; padding:4px; border-radius:6px; text-decoration:none}
.vs.open:hover svg{stroke:var(--green)}
.sr{position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap}
.strip{display:flex; gap:10px; overflow-x:auto; padding-bottom:8px; scroll-snap-type:x proximity}
.strip img{height:460px; width:auto; border-radius:8px; flex:0 0 auto; scroll-snap-align:start; background:var(--chip)}
.patnav{display:flex; flex-wrap:wrap; gap:8px}
.patnav a{font-size:14px; text-decoration:none; color:var(--ink); border:1px solid var(--line); border-radius:999px; padding:5px 12px; background:var(--surface)}
.patnav a b{color:var(--ember); font-variant-numeric:tabular-nums}
.patnav a:hover{border-color:var(--ember)}
.pattern{display:grid; gap:16px; padding-top:28px; border-top:1px solid var(--line)}
.pattern h3{display:flex; flex-wrap:wrap; align-items:baseline; gap:8px 10px}
.badge{font-size:20px}
.rate{font-family:var(--ui); font-size:15px; font-weight:600; color:var(--ember); font-variant-numeric:tabular-nums}
.fv{display:grid; gap:6px; margin:10px 0 0; max-width:90ch}
.fv div{display:grid; grid-template-columns:80px 1fr; gap:10px}
.fv dt{font-size:13px; color:var(--muted); padding-top:2px}
.fv dd{margin:0; min-width:0}
.fv code{font-family:var(--ui); font-weight:600; background:var(--chip); padding:1px 6px; border-radius:4px; overflow-wrap:anywhere}
.note{margin-top:8px; max-width:80ch; color:var(--muted)}
.grid{display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:22px 16px}
.tile{margin:0; display:grid; gap:8px; min-width:0; align-content:start}
.cover{position:relative; display:block; aspect-ratio:9/16; max-width:100%; border-radius:8px; overflow:hidden; background:var(--chip)}
.cover img{display:block; width:100%; height:100%; object-fit:cover; transition:transform .25s ease}
.cover:hover img{transform:scale(1.02)}
.cover::after{content:""; position:absolute; inset:auto 0 0; height:22%; background:linear-gradient(transparent, rgba(0,0,0,.55)); pointer-events:none}
.views{position:absolute; left:10px; bottom:8px; z-index:1; color:#fff; font-weight:600; font-size:15px; display:flex; align-items:center; gap:4px; text-shadow:0 1px 2px rgba(0,0,0,.5); font-variant-numeric:tabular-nums}
.views svg{width:16px; height:16px; fill:#fff}
.tile.hot .cover{box-shadow:0 0 0 3px var(--ember)}
figcaption{display:grid; gap:2px; font-size:13px}
.mult{font-weight:700; font-variant-numeric:tabular-nums; color:var(--ember)}
.tile:not(.hot) .mult{color:var(--ink)}
.meta{color:var(--muted)}
.hook{color:var(--muted); display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden}
.bars{display:grid; gap:10px; max-width:860px; margin-bottom:12px}
.bar{display:grid; grid-template-columns:minmax(150px,240px) 1fr 120px; gap:12px; align-items:center}
.bl{font-size:14px} .bl small,.bv small{color:var(--muted)}
.track{height:14px; background:var(--chip); border-radius:3px; overflow:hidden}
.fill{display:block; height:100%; background:var(--green); border-radius:3px}
.bv{font-variant-numeric:tabular-nums; font-size:14px; text-align:right}
.obs{display:grid; gap:10px; max-width:80ch; padding-left:20px; margin:0}
.rulesbox{background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px 20px; max-width:90ch}
.rulesbox ul{margin:8px 0 0; padding-left:20px; display:grid; gap:4px}
.formula{display:grid; gap:12px; padding-top:28px; border-top:1px solid var(--line)}
.formula header{display:grid; grid-template-columns:44px 1fr; gap:12px; align-items:start}
.rank{font-family:var(--display); font-size:40px; line-height:1; color:var(--ember)}
.src{font-size:14px; color:var(--muted); margin-top:4px}
.who,.vis,.alts{max-width:90ch; font-size:15px}
.vis{color:var(--muted)}
.alts q{font-weight:600}
ol.slides{list-style:none; margin:0; padding:0 0 8px; display:flex; gap:10px; overflow-x:auto}
ol.slides li{flex:0 0 190px; aspect-ratio:9/16; border-radius:10px; background:linear-gradient(170deg,var(--frame-a),var(--frame-b)); color:var(--frame-ink);
  display:flex; flex-direction:column; justify-content:center; align-items:center; text-align:center; padding:14px; position:relative}
ol.slides li.demo{box-shadow:inset 0 0 0 3px var(--ember)}
.sn{position:absolute; top:8px; left:10px; font-size:11px; letter-spacing:.05em; text-transform:uppercase; opacity:.8}
.st{font-weight:600; font-size:15px; line-height:1.3; text-shadow:0 1px 2px rgba(0,0,0,.45)}
.twocol{display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:24px}
.twocol > div{min-width:0}
.twocol ul{margin:8px 0 0; padding-left:20px; display:grid; gap:6px}
footer{padding-top:48px; color:var(--muted); font-size:14px; max-width:90ch}
.sample{max-width:90ch}
.young{color:var(--ember); font-weight:600}
.bar.thin .fill{background:var(--line)} .bar.thin .bl,.bar.thin .bv{color:var(--muted)}
details.stext{max-width:90ch} details.stext summary{cursor:pointer; font-size:14px; color:var(--green); font-weight:600}
details.stext ol{margin:8px 0 0; padding-left:22px; display:grid; gap:6px; font-size:15px}
details.stext small{color:var(--muted)}
.adapts{display:grid; gap:18px}
.adapt{display:grid; grid-template-columns:200px 1fr; gap:18px; align-items:start; background:var(--surface); border:1px solid var(--line); border-radius:12px; padding:16px}
.adapt > div{display:grid; gap:8px; min-width:0}
.adapt .orig{color:var(--muted); font-size:14px}
.adapt .yh{font-family:var(--display); font-size:21px; line-height:1.3}
.sortbar{display:flex; gap:8px; flex-wrap:wrap}
.sortbar button{font:inherit; font-size:14px; border:1px solid var(--line); background:var(--surface); color:var(--ink); border-radius:999px; padding:5px 14px; cursor:pointer}
.sortbar button[aria-pressed="true"]{background:var(--green); color:var(--bg); border-color:var(--green)}
.sortbar button:focus-visible{outline:2px solid var(--ember); outline-offset:2px}
@media (max-width:560px){
  .adapt{grid-template-columns:110px 1fr; gap:12px; padding:12px}
  .adapt .yh{font-size:18px}
  .grid{grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px 10px}
  .strip img{height:340px}
  .bar{grid-template-columns:1fr 90px}
  .bar .track{grid-column:1 / -1; order:3}
  .views{font-size:13px}
  ol.slides li{flex-basis:160px}
}
@media (prefers-reduced-motion: reduce){ .cover img{transition:none} .cover:hover img{transform:none} }
"""

SORT_JS = """<script>
(function () {
  var grid = document.getElementById("allgrid"), btns = document.querySelectorAll("#all .sortbar button");
  btns.forEach(function (b) {
    b.addEventListener("click", function () {
      var byViews = b.dataset.k === "v";
      Array.prototype.slice.call(grid.children).sort(function (x, y) {
        if (byViews) return y.dataset.v - x.dataset.v;
        return x.dataset.d < y.dataset.d ? 1 : x.dataset.d > y.dataset.d ? -1 : 0;
      }).forEach(function (el) { grid.appendChild(el); });
      btns.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
    });
  });
})();
</script>"""

def load(path, default=None):
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default

def compress(src, dst, max_w):
    """Recompress for publishing: macOS sips barely shrinks JPEG, PIL q74 halves it."""
    try:
        from PIL import Image
        im = Image.open(src).convert("RGB")
        if im.width > max_w:
            im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
        im.save(dst, "JPEG", quality=74, optimize=True, progressive=True)
        return im.size
    except ImportError:
        shutil.copy(src, dst)
        subprocess.run(["sips", "--resampleWidth", str(max_w), dst], capture_output=True)
        return None

def local(path, folder):
    """Absolute paths in meta.json / post.json break once the work dir is copied into the
    project; fall back to the file of the same name in its folder."""
    if not path:
        return None
    if os.path.exists(path):
        return path
    alt = os.path.join(folder, os.path.basename(path))
    return alt if os.path.exists(alt) else None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("work_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--insights")
    ap.add_argument("--lang", choices=["ru", "en"], default="ru")
    args = ap.parse_args()
    W, OUT, lang = args.work_dir, args.out, args.lang
    T = L[lang]

    meta = load(os.path.join(W, "meta.json"))
    rep = load(os.path.join(W, "report.json"))
    if not meta or not rep:
        sys.exit("ERROR: WORK_DIR needs meta.json and report.json (run pattern_stats.py --out report.json)")
    clusters = load(os.path.join(W, "clusters.json"), {"patterns": []})
    raw_cards = load(os.path.join(W, "cards.json"), [])
    cards = {int(c.get("index", k)): c for k, c in
             (raw_cards.items() if isinstance(raw_cards, dict) else enumerate(raw_cards))}
    ins = load(args.insights, {}) if args.insights else {}
    videos, handle, platform = meta["videos"], meta["handle"], meta.get("platform", "tiktok")
    profile = meta.get("profile") or {}
    metric = rep.get("metric") or meta.get("metric") or "views"
    if metric != "views":  # Instagram posts mode: every number on the page is likes
        T = dict(T, views=T["likesW"], median=T["medianLikes"], sortViews=T["sortLikes"],
                 patternsLead=T["patternsLead"].replace("просмотров", "лайков").replace("views", "likes"),
                 youngNote=T["youngNote"].replace("просмотры", "лайки").replace("views", "likes"))
        for v in videos:
            v["views"] = v.get(metric) or 0
    labels_raw = load(os.path.join(W, "labels.json"))
    label_names = (labels_raw.get("names") if isinstance(labels_raw, dict) else None) or rep.get("labelNames") or {}
    young = set((rep.get("young") or {}).get("indexes") or [])
    excluded = set((rep.get("window") or {}).get("excluded") or [])
    MED = rep["accountMedianViews"] or 1
    # Instagram /user/reels returns no saves/shares: hide those chips instead of showing 0
    has_eng = any(v.get("saves") or v.get("shares") for v in videos)
    fetched = meta.get("fetchedAt") or time.strftime("%Y-%m-%d")
    if not cards:
        print("WARNING: no cards.json, tiles fall back to post captions", file=sys.stderr)

    def fmt(n):
        n = n or 0
        if lang == "ru":
            if n >= 1_000_000:
                return f"{n / 1e6:.2f}".replace(".", ",") + " млн"
            if n >= 10_000:
                return f"{round(n / 1000)} тыс"
            return f"{int(n):,}".replace(",", " ")
        if n >= 1_000_000:
            return f"{n / 1e6:.2f}M"
        return f"{round(n / 1000)}K" if n >= 10_000 else f"{int(n):,}"

    def fmt_exact(n):  # post counts: every digit matters, only thousands separators
        return f"{int(n or 0):,}".replace(",", " " if lang == "ru" else ",")

    def dec(x, nd=1):
        s = f"{x:.{nd}f}"
        return s.replace(".", ",") if lang == "ru" else s

    def mult(r):
        return dec(r, 1 if r < 10 else 0) + "×"

    def plural(n, forms):
        if lang != "ru":
            return forms[0] if n == 1 else forms[1]
        if n % 10 == 1 and n % 100 != 11:
            return forms[0]
        return forms[1] if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else forms[2]

    def fdate(d, long=False):
        if not re.match(r"\d{4}-\d{2}-\d{2}", d or ""):
            return d or ""
        y, m, dd = int(d[:4]), int(d[5:7]), int(d[8:10])
        if lang == "ru":
            return f"{dd} {MONTHS_RU[m - 1]} {y}" if long else f"{d[8:10]}.{d[5:7]}.{d[2:4]}"
        return f"{MONTHS_EN[m - 1]} {dd}, {y}" if long else d

    def md(s):
        s = E(s or "")
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<i>\1</i>", s)
        def a(m):
            ext = "" if m.group(2).startswith("#") else ' target="_blank" rel="noopener"'
            return f'<a href="{m.group(2)}"{ext}>{m.group(1)}</a>'
        s = re.sub(r"\[([^\]]+)\]\(((?:https?://|#)[^)\s]+)\)", a, s)
        return s.replace("\n", "<br>")

    def hook_of(i):
        c = cards.get(i) or {}
        return (c.get("hook_text") or "").strip() or (videos[i].get("desc") or "").strip()[:140]

    # ---------- images ----------
    for sub in ("covers", "slides"):
        shutil.rmtree(os.path.join(OUT, sub), ignore_errors=True)
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    cover_size = {}
    for i, v in enumerate(videos):
        src = local(v.get("coverFile"), os.path.join(W, "covers"))
        if src:
            cover_size[i] = compress(src, os.path.join(OUT, "covers", f"{i:02d}.jpg"), 480) or (480, 852)

    def tile(i):
        v = videos[i]
        r = v["views"] / MED
        if "isCarousel" in v:
            kind = (f" · {v['slides']} {T['sl']}" if v["isCarousel"]
                    else f" · {T['photo'] if v.get('kind') == 'photo' else T['video']}")
        else:
            kind = ""
        pin = f" · {T['pinned']}" if v.get("isPinned") else ""
        new = f' · <span class="young">{T["young"]}</span>' if i in young else ""
        hook = hook_of(i)
        if i in cover_size:
            w, h = cover_size[i]
            img = f'<img src="covers/{i:02d}.jpg" alt="{E(hook)}" loading="lazy" width="{w}" height="{h}">'
        else:
            img = ""
        return (f'<figure class="tile{" hot" if r >= 5 else ""}" data-d="{E(v["date"])}" data-v="{v["views"]}">'
                f'<a href="{E(v["link"])}" target="_blank" rel="noopener" class="cover" title="{T["open"]}">{img}'
                f'<span class="views">{PLAY}{fmt(v["views"])}</span></a>'
                f'<figcaption><span class="mult">{mult(r)}</span>'
                f'<span class="meta">{fdate(v["date"])}{kind}{pin}{new} · #{i:02d}</span>'
                f'<span class="hook">{E(hook)}</span></figcaption></figure>')

    # ---------- virals ----------
    hits = rep.get("concentration", {}).get("hits", [])
    viral_specs = ins.get("virals") or [{"index": h["index"]} for h in hits[:4]]

    def viral(d):
        i = d["index"]
        v = videos[i]
        cdir = os.path.join(W, "carousels", f"{i:02d}")
        post = load(os.path.join(cdir, "post.json"), {})
        files = [f for f in (local(p, cdir) for p in post.get("slide_files") or []) if f] or (sorted(
            (os.path.join(cdir, f) for f in os.listdir(cdir) if re.match(r"slide\d+\.jpg$", f)),
            key=lambda p: int(re.search(r"(\d+)\.jpg$", p).group(1))) if os.path.isdir(cdir) else [])
        # slides.json (verbatim texts) goes to alt only: by design nothing is written under a viral
        texts = {int(t.get("slide", k)): (t.get("text") or "") for k, t in
                 enumerate(load(os.path.join(cdir, "slides.json"), []) or [], 1)}
        imgs = []
        for k, src in enumerate(files, 1):
            rel = f"slides/c{i:02d}_{k}.jpg"
            w, h = compress(src, os.path.join(OUT, rel), 540) or (540, 960)
            imgs.append(f'<img src="{rel}" alt="{E(texts.get(k) or str(k))}" loading="lazy" width="{w}" height="{h}">')
        if not imgs and i in cover_size:
            w, h = cover_size[i]
            imgs.append(f'<img src="covers/{i:02d}.jpg" alt="" loading="lazy" width="{w}" height="{h}">')
        # no hook text (it is on the slides), no comment, no descriptions: slides + icon metrics only
        def stat(icon, num, label, cls="", rate=None):
            pct = f" <small>{dec(rate)}%</small>" if rate is not None else ""
            return (f'<span class="vs{cls}" title="{E(label)}"><svg viewBox="0 0 24 24" aria-hidden="true">{ICON[icon]}</svg>'
                    f'{num}{pct}<span class="sr">{E(label)}</span></span>')
        base = v["views"] or 1
        stats = [stat("eye" if metric == "views" else "heart", fmt(v["views"]), T["views"]),
                 stat("trend", mult(v["views"] / MED), T["ofMedian"], " mult")]
        if metric == "views" and v.get("likes") is not None:
            stats.append(stat("heart", fmt(v["likes"]), T["likesW"]))
        stats.append(stat("comment", fmt(v["comments"]), T["comments"]))
        if has_eng:
            stats.append(stat("bookmark", fmt(v["saves"]), T["saves"], rate=100 * v["saves"] / base))
            stats.append(stat("share", fmt(v["shares"]), T["shares"], rate=100 * v["shares"] / base))
        n_sl = v.get("slides") or len(files)
        if n_sl:
            stats.append(stat("layers", str(n_sl), plural(n_sl, T["slidesW"])))
        stats.append(stat("calendar", fdate(v["date"]), "дата" if lang == "ru" else "date"))
        stats.append(f'<a class="vs open" href="{E(v["link"])}" target="_blank" rel="noopener" title="{T["open"]}">'
                     f'<svg viewBox="0 0 24 24" aria-hidden="true">{ICON["open"]}</svg><span class="sr">{T["open"]}</span></a>')
        return f"""<article class="viral">
  <p class="vstats">{''.join(stats)}</p>
  <div class="strip" tabindex="0">{''.join(imgs)}</div>
</article>"""

    # ---------- patterns ----------
    cl_by = {c["patternName"]: c for c in clusters.get("patterns", [])}
    notes = ins.get("patternNotes") or {}

    def badge(r):
        return "🏆" if r > 5 else "🔥" if r > 3 else "⚡" if r > 1.5 else "·" if r >= 1 else "⚠️" if r >= 0.5 else "📉"

    pats = sorted(rep["patterns"], key=lambda p: -p["viralityRate"])
    pat_html = []
    for k, p in enumerate(pats, 1):
        idx = p.get("indexes") or cl_by.get(p["patternName"], {}).get("indexes", [])
        idx = sorted((i for i in idx if i not in excluded), key=lambda i: -videos[i]["views"])
        flags = ""
        if p.get("outlierWarning"):
            flags += f'<span class="chip warn">{T["outlier"]}</span>'
        if p.get("belowMinimum"):
            flags += f'<span class="chip warn">{T["small"]}</span>'
        save = f'<span class="chip">{T["saveRate"]} {dec(p["medianSaveRate"])}%</span>' if "medianSaveRate" in p and has_eng else ""
        saves_med = f'<span class="chip">{T["savesMed"]} {fmt(p["medianSaves"])}</span>' if has_eng else ""
        er_chip = (f'<span class="chip">{T["er"]} {dec(p["medianEngagement"], 2)}%</span>'
                   if p.get("medianEngagement") is not None else "")
        note = f'<p class="note">{md(notes[p["patternName"]])}</p>' if p["patternName"] in notes else ""
        pat_html.append(f"""<section class="pattern" id="p{k}">
  <header>
    <h3><span class="badge" aria-hidden="true">{badge(p['viralityRate'])}</span>{E(p['patternName'])} <span class="rate">{mult(p['viralityRate'])} · {p['count']} {plural(p['count'], T['posts'])}</span></h3>
    <p class="chips"><span class="chip strong">{T['med']} {fmt(p['medianViews'])}</span><span class="chip">{T['avg']} {fmt(p['avgViews'])}</span><span class="chip">{T['likesMed']} {fmt(p['medianLikes'])}</span>{saves_med}{save}{er_chip}{flags}</p>
    <dl class="fv"><div><dt>{T['formula']}</dt><dd><code>{E(p.get('formula', ''))}</code></dd></div><div><dt>{T['visualF']}</dt><dd>{E(p.get('visualFormat', ''))}</dd></div></dl>
    {note}
  </header>
  <div class="grid">{''.join(tile(i) for i in idx)}</div>
</section>""")
    patnav = "".join(f'<a href="#p{k}">{E(p["patternName"])} <b>{mult(p["viralityRate"])}</b></a>'
                     for k, p in enumerate(pats, 1))
    un = rep.get("unassigned") or {}
    un_html = ""
    if un.get("count"):
        idx = sorted(un["indexes"], key=lambda i: -videos[i]["views"])
        un_html = (f'<section class="pattern" id="unassigned"><header><h3>{T["unassigned"]} '
                   f'<span class="rate">{un["count"]} {plural(un["count"], T["posts"])}</span></h3>'
                   f'<p class="note">{T["unassignedLead"]}</p></header>'
                   f'<div class="grid">{"".join(tile(i) for i in idx)}</div></section>')

    # ---------- splits ----------
    splits = rep.get("splits") or {}
    order = {"video": 0, "photo": 1, "1": 2, "2-3": 3, "4+": 4}

    def period_label(p):
        m = re.match(r"(\d{4})-(?:(\d{2})|Q(\d))$", p)
        if not m:
            return p
        if m.group(3):
            return f"{m.group(3)} кв. {m.group(1)}" if lang == "ru" else f"Q{m.group(3)} {m.group(1)}"
        names = MONTHS_RU_SHORT if lang == "ru" else MONTHS_EN
        return f"{names[int(m.group(2)) - 1]} {m.group(1)}"

    specs = ins.get("splits") or [{"key": k} for k in splits if k != "pinned"]
    bars_html = []
    for s in specs:
        rows = splits.get(s["key"])
        if not rows:
            continue
        if s["key"] == "format":
            rows = sorted(rows, key=lambda r: order.get(r["value"], 9))
        elif s["key"] == "period":
            rows = sorted(rows, key=lambda r: r["value"])
        if s["key"] == "period":
            labels = {r["value"]: period_label(r["value"]) for r in rows}
        else:
            labels = (s.get("labels") or label_names.get(s["key"]) or T["valueLabels"].get(s["key"])
                      or T["valueLabels"]["_bool"])
        mx = max(r["medianViews"] for r in rows) or 1
        out = "".join(
            f'<div class="bar{" thin" if r.get("belowMinimum") else ""}">'
            f'<span class="bl">{E(labels.get(r["value"], r["value"]))} <small>n={r["count"]}'
            f'{" · " + T["few"] if r.get("belowMinimum") else ""}</small></span>'
            f'<span class="track"><span class="fill" style="width:{100 * r["medianViews"] / mx:.1f}%"></span></span>'
            f'<span class="bv">{fmt(r["medianViews"])} <small>{mult(r["viralityRate"])}</small></span></div>'
            for r in rows)
        title = s.get("title") or T["splitTitles"].get(s["key"], s["key"])
        bars_html.append(f'<h4>{E(title)}</h4><div class="bars">{out}</div>')
    vnotes = ins.get("visualNotes") or []
    visual_html = ""
    if bars_html or vnotes:
        obs = f'<ul class="obs">{"".join(f"<li>{md(x)}</li>" for x in vnotes)}</ul>' if vnotes else ""
        visual_html = f'<section class="block" id="visual"><h2>{T["visual"]}</h2>{"".join(bars_html)}{obs}</section>'

    # ---------- formulas ----------
    def formula(k, f):
        demo = ' class="demo"'
        frames = "".join(
            f'<li{demo if s.get("demo") else ""}><span class="sn">{E(s.get("label", ""))}</span>'
            f'<span class="st">{md(s.get("text", ""))}</span></li>' for s in f.get("slides", []))
        alts = (f'<p class="alts"><b>{T["alts"]}</b> ' + " · ".join(f"<q>{E(a)}</q>" for a in f["alts"]) + "</p>"
                ) if f.get("alts") else ""
        src = f'<p class="src">{T["source"]} {md(f["source"])}</p>' if f.get("source") else ""
        who = f'<p class="who"><b>{T["who"]}</b> {md(f["who"])}</p>' if f.get("who") else ""
        vis = f'<p class="vis">{md(f["visual"])}</p>' if f.get("visual") else ""
        return (f'<article class="formula"><header><span class="rank">{k}</span><div><h3>{E(f.get("title", ""))}</h3>{src}</div></header>'
                f'{who}<ol class="slides">{frames}</ol>{vis}{alts}</article>')

    formulas_html = ""
    if ins.get("formulas"):
        rb = ins.get("rulesBox")
        rules = (f'<div class="rulesbox"><h4>{E(rb.get("title", ""))}</h4><ul>'
                 f'{"".join(f"<li>{md(x)}</li>" for x in rb.get("items", []))}</ul></div>') if rb else ""
        lead = f'<p class="lead">{md(ins["formulasLead"])}</p>' if ins.get("formulasLead") else ""
        formulas_html = (f'<section class="block" id="formulas"><h2>{E(ins.get("formulasTitle") or T["formulas"])}</h2>'
                         f'{lead}{rules}{"".join(formula(k, f) for k, f in enumerate(ins["formulas"], 1))}</section>')

    def ul(items, cls="obs"):
        return f'<ul class="{cls}">{"".join(f"<li>{md(x)}</li>" for x in items)}</ul>'

    rules_html = ""
    if ins.get("do") or ins.get("dont"):
        cols = "".join(f'<div><h4>{T[key]}</h4>{ul(ins[key], "")}</div>' for key in ("do", "dont") if ins.get(key))
        rules_html = f'<section class="block" id="rules"><h2>{T["rules"]}</h2><div class="twocol">{cols}</div></section>'
    caveats_html = (f'<section class="block" id="caveats"><h2>{T["caveats"]}</h2>{ul(ins["caveats"])}</section>'
                    if ins.get("caveats") else "")
    summary_html = (f'<section class="block" id="summary"><h2>{T["summary"]}</h2><ul class="summary">'
                    f'{"".join(f"<li><span>{md(x)}</span></li>" for x in ins["summary"])}</ul></section>'
                    if ins.get("summary") else "")
    any_slides = any(os.path.isdir(os.path.join(W, "carousels", f'{d["index"]:02d}')) for d in viral_specs)
    vt, vl = (T["virals"], T["viralsLead"]) if any_slides else (T["viralsCovers"], T["viralsLeadCovers"])
    virals_html = (f'<section class="block" id="virals"><h2>{vt}</h2><p class="lead">{vl}</p>'
                   f'{"".join(viral(d) for d in viral_specs)}</section>') if viral_specs else ""

    # ---------- product: what to take from this account ----------
    product_html = ""
    pr = ins.get("product")
    if pr:
        cards_p = []
        for a in pr.get("adaptations") or []:
            i = a.get("index")
            src = tile(i) if isinstance(i, int) and 0 <= i < len(videos) else ""  # its caption carries the original hook
            how = f'<p><b>{T["how"]}:</b> {md(a["how"])}</p>' if a.get("how") else ""
            cards_p.append(f'<article class="adapt">{src}<div><h3>{E(a.get("title", ""))}</h3>'
                           f'<p><b>{T["yourHook"]}:</b></p><p class="yh">{md(a.get("hook", ""))}</p>{how}</div></article>')
        lead = f'<p class="lead">{md(pr["lead"])}</p>' if pr.get("lead") else ""
        notes = ul(pr["notes"]) if pr.get("notes") else ""
        product_html = (f'<section class="block" id="product"><h2>{E(pr.get("title") or T["product"])}</h2>'
                        f'{lead}{notes}<div class="adapts">{"".join(cards_p)}</div></section>')

    # ---------- all posts, sortable ----------
    all_html = ""
    if ins.get("allPosts") is not False:
        shown = sorted((i for i in range(len(videos)) if i not in excluded), key=lambda i: videos[i]["date"], reverse=True)
        all_html = (f'<section class="block" id="all"><h2>{T["allPosts"]}</h2><p class="lead">{T["allLead"]}</p>'
                    f'<div class="sortbar" role="group" aria-label="{T["sortBy"]}">'
                    f'<button type="button" data-k="d" aria-pressed="true">{T["sortDate"]}</button>'
                    f'<button type="button" data-k="v" aria-pressed="false">{T["sortViews"]}</button></div>'
                    f'<div class="grid" id="allgrid">{"".join(tile(i) for i in shown)}</div>{SORT_JS}</section>')

    # ---------- hero ----------
    n = len(videos)
    facts = []
    if profile.get("followers") is not None:
        facts.append((T["followers"], fmt(profile["followers"]), ""))
    if profile.get("totalPosts") is not None:
        facts.append((T["totalPosts"], fmt_exact(profile["totalPosts"]), T["analyzed"].format(n=n)))
    cars = sum(1 for v in videos if v.get("isCarousel"))
    if any("isCarousel" in v for v in videos) and (cars or platform == "tiktok"):
        photos = sum(1 for v in videos if v.get("kind") == "photo")
        facts.append((T["carVidPh"], f"{cars} / {n - cars - photos} / {photos}", "") if photos
                     else (T["carVid"], f"{cars} / {n - cars}", ""))
    facts.append((T["median"], fmt(MED), ""))
    conc = rep.get("concentration") or {}
    if conc.get("hits"):
        facts.append((T["hitsShare"].format(n=len(conc["hits"])), f'{dec(conc["hitsShare"])}%',
                      T["ofTotal"].format(t=fmt(conc["totalViews"]))))
    facts_html = "".join(f'<div><dt>{E(a)}</dt><dd>{b}{f" <small>{E(c)}</small>" if c else ""}</dd></div>'
                         for a, b, c in facts)
    sample, win, yg = meta.get("sample") or {}, rep.get("window") or {}, rep.get("young") or {}
    total = sample.get("accountTotal") or profile.get("totalPosts")
    notes = []
    if sample.get("mode") == "since" and sample.get("since"):
        notes.append(T["sampleSince"].format(n=n, d=fdate(sample["since"], long=True)))
    elif sample.get("mode") == "latest" and total and total > n:
        notes.append(T["sampleLatest"].format(n=n, t=fmt_exact(total)))
    elif sample.get("mode"):
        notes.append(T["sampleAll"].format(n=n))
    if win.get("since") and excluded:
        notes.append(T["windowNote"].format(d=fdate(win["since"], long=True), k=len(excluded)))
    if young and not yg.get("fallbackAllYoung"):
        notes.append(T["youngNote"].format(n=len(young), posts=plural(len(young), T["posts"]), d=yg.get("minAgeDays", 7)))
    if metric != "views":
        notes.append(T["metricLikes"])
    sample_html = f'<p class="sample note">{" ".join(E(x) for x in notes)}</p>' if notes else ""
    pname = "TikTok" if platform == "tiktok" else "Instagram"
    purl = f"https://www.tiktok.com/@{handle}" if platform == "tiktok" else f"https://www.instagram.com/{handle}/"
    title = ins.get("title") or T["title"].format(h=handle)
    eyebrow = ins.get("eyebrow") or T["eyebrow"].format(p=pname, d=fdate(fetched, long=True))

    page = f"""<title>{E(title)}</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&display=swap">
<style>{CSS}</style>
<div class="wrap">
<header class="hero">
  <p class="eyebrow">{E(eyebrow)}</p>
  <h1><a href="{purl}" target="_blank" rel="noopener">@{E(handle)}</a></h1>
  <p class="lead">{md(ins.get("lead") or T["lead"])}</p>
  <dl class="facts">{facts_html}</dl>
  {sample_html}
</header>
{summary_html}
{virals_html}
{product_html}
<section class="block" id="patterns">
  <h2>{T["patterns"]}</h2>
  <p class="lead">{T["patternsLead"].format(m=fmt(MED))}</p>
  <nav class="patnav">{patnav}</nav>
  {"".join(pat_html)}
  {un_html}
</section>
{visual_html}
{formulas_html}
{rules_html}
{all_html}
{caveats_html}
<footer>{md(ins.get("footer") or T["footer"].format(d=fdate(fetched, long=True)))}</footer>
</div>
"""
    os.makedirs(OUT, exist_ok=True)
    page_path = os.path.join(OUT, "index.html")
    with open(page_path, "w", encoding="utf-8") as f:
        f.write(page)

    # ---------- publish batches ----------
    files = sorted(f"{sub}/{name}" for sub in ("covers", "slides")
                   for name in os.listdir(os.path.join(OUT, sub)))
    batches, cur, cur_b = [], [], 0
    for rel in files:
        size = os.path.getsize(os.path.join(OUT, rel))
        if cur and (len(cur) >= 25 or cur_b + size > 2_500_000):
            batches.append(cur)
            cur, cur_b = [], 0
        cur.append(rel)
        cur_b += size
    if cur:
        batches.append(cur)
    total = sum(os.path.getsize(os.path.join(OUT, r)) for r in files)
    plan = {"file_path": os.path.abspath(page_path), "root": os.path.abspath(OUT),
            "totalImageBytes": total, "batches": batches}
    with open(os.path.join(OUT, "publish_plan.json"), "w") as f:
        json.dump(plan, f, indent=1)
    print(f"PAGE {plan['file_path']} ({os.path.getsize(page_path) // 1024} KB) | "
          f"{len(files)} images, {total / 1e6:.1f} MB | {len(batches)} batches")
    print(f"Publish: Artifact with file_path=<PAGE> and root={plan['root']} for EVERY batch, "
          f"files = the batch list. Icon only on the first publish. Then verify with list scope=files.")
    for k, b in enumerate(batches, 1):
        print(f"batch {k}: {json.dumps(b)}")

if __name__ == "__main__":
    main()
