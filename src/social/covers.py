#!/usr/bin/env python3
"""Download covers and make uncropped contact sheets of 20. Requires Pillow."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import io
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps
from social import export, load, write_json


def font(size):
    for name in ("DejaVuSans.ttf", "Arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def download(row, out):
    row = dict(row)
    url = row.get("cover_url")
    if not url:
        return {**row, "cover_status": "missing_url"}
    if urlparse(url).scheme != "https":
        return {**row, "cover_status": "invalid_url"}
    try:
        # No credential headers are ever sent to media CDNs.
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as response:
            data = response.read(20 * 1024 * 1024 + 1)
        if len(data) > 20 * 1024 * 1024:
            raise ValueError("image exceeds 20 MB")
        with Image.open(io.BytesIO(data)) as image:
            converted = ImageOps.exif_transpose(image).convert("RGB")
            target = out / "covers" / f"{row['recent_rank']:03d}.jpg"
            converted.save(target, quality=94)
        row.update(cover_file=target.relative_to(out).as_posix(), cover_status="downloaded")
    except Exception as error:
        # A broken cover remains a cohort row; don't turn it into a no-text hook.
        row.update(cover_file=None, cover_status="download_failed", cover_error=type(error).__name__)
    return row


def sheets(rows, out):
    w, h, label, columns = 420, 747, 126, 4
    for batch, start in enumerate(range(0, len(rows), 20), 1):
        group = rows[start:start + 20]
        canvas = Image.new("RGB", (columns * w, ((len(group) + columns - 1) // columns) * (h + label)), "#192321")
        draw = ImageDraw.Draw(canvas)
        for i, row in enumerate(group):
            x, y = i % columns * w, i // columns * (h + label)
            if row.get("cover_file"):
                with Image.open(out / row["cover_file"]) as original:
                    thumb = ImageOps.contain(original.convert("RGB"), (w, h))
                canvas.paste(thumb, (x + (w - thumb.width) // 2, y + (h - thumb.height) // 2))
            else:
                draw.text((x + 16, y + h // 2), "COVER UNAVAILABLE", font=font(22), fill="white")
            fmt = lambda n: "N/A" if n is None else f"{n:,}"
            draw.text((x + 12, y + h + 10), f"#{row['recent_rank']}  {(row.get('published_at_utc') or 'unknown')[:10]}", font=font(22), fill="white")
            draw.text((x + 12, y + h + 46), f"Views {fmt(row.get('views'))}", font=font(22), fill="white")
            draw.text((x + 12, y + h + 81), f"Comments {fmt(row.get('comments'))}", font=font(22), fill="#b3e7c5")
        canvas.save(out / "sheets" / f"covers-{batch:02d}.jpg", quality=92)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--sheets-only", action="store_true")
    args = parser.parse_args()
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass
    rows = load(args.out / "videos.json")
    for folder in ("covers", "sheets"):
        (args.out / folder).mkdir(parents=True, exist_ok=True)
    if not args.sheets_only:
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
            rows = list(pool.map(lambda r: download(r, args.out), rows))
        write_json(args.out / "videos.json", rows)
        export(args.out)
    sheets(rows, args.out)
    print(f"Covers available: {sum(bool(r.get('cover_file')) for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
