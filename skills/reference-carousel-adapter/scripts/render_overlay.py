#!/usr/bin/env python3
"""Render editable caption stickers on clean carousel backgrounds.

Usage: python3 render_overlay.py carousel.json --font-regular /path/reg.ttf
       --font-bold /path/bold.ttf
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont, ImageOps


def _relative_path(value: str, config_dir: Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_dir / path


def _positive_int(value: Any, name: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _style_font(style: dict[str, Any], fonts: dict[str, Path]) -> ImageFont.FreeTypeFont:
    alias = style.get("font")
    if alias not in fonts:
        raise ValueError(f"Unknown font alias {alias!r}; configure font_files or CLI font paths")
    path = fonts[alias]
    if not path.is_file():
        raise FileNotFoundError(f"Font file missing: {path}. Install the font and pass its file path.")
    font = ImageFont.truetype(str(path), _positive_int(style.get("size"), "font size"))
    if "weight" in style:
        weight = _positive_int(style["weight"], "font weight")
        try:
            axes = font.get_variation_axes()
        except OSError as exc:
            raise ValueError(f"Font {path} is not variable; remove 'weight' or use a variable font") from exc
        values = [axis["default"] for axis in axes]
        weight_axis = next(
            (index for index, axis in enumerate(axes)
             if axis["name"].decode("utf-8", errors="ignore").lower() == "weight"),
            None,
        )
        if weight_axis is None:
            raise ValueError(f"Font {path} has no Weight variation axis")
        axis = axes[weight_axis]
        if not axis["minimum"] <= weight <= axis["maximum"]:
            raise ValueError(f"Font weight {weight} is outside {axis['minimum']}–{axis['maximum']}")
        values[weight_axis] = weight
        font.set_variation_by_axes(values)
    return font


def _paint_layer(
    image: Image.Image,
    layer: dict[str, Any],
    styles: dict[str, Any],
    fonts: dict[str, Path],
    slide_number: int,
) -> None:
    style_name = layer.get("style")
    if style_name not in styles:
        raise ValueError(f"Slide {slide_number}: unknown style {style_name!r}")
    style = styles[style_name]
    lines = layer.get("lines")
    if not isinstance(lines, list) or not lines or any(not isinstance(s, str) or not s.strip() for s in lines):
        raise ValueError(f"Slide {slide_number}: lines must be a nonempty list of nonblank strings")

    font = _style_font(style, fonts)
    draw = ImageDraw.Draw(image)
    top = _positive_int(layer.get("top"), "top", minimum=0)
    pad_x = _positive_int(style.get("padding_x"), "padding_x", minimum=0)
    pad_y = _positive_int(style.get("padding_y"), "padding_y", minimum=0)
    step = _positive_int(style.get("line_step"), "line_step")
    radius = _positive_int(style.get("corner_radius", 0), "corner_radius", minimum=0)
    max_width = _positive_int(style.get("max_width", image.width), "max_width")
    stroke = _positive_int(style.get("stroke_width", 0), "stroke_width", minimum=0)
    text_color = ImageColor.getrgb(style["text_color"])
    box_color = ImageColor.getrgb(style["box_color"])
    stroke_color = ImageColor.getrgb(style.get("stroke_color", style["text_color"]))
    align = layer.get("align", "center")
    if align not in ("center", "left", "right"):
        raise ValueError(f"Slide {slide_number}: align must be center, left, or right")
    default_x = image.width // 2 if align == "center" else (40 if align == "left" else image.width - 40)
    anchor_x = _positive_int(layer.get("x", default_x), "x", minimum=0)

    measured = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=stroke)
        width, height = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if width + 2 * pad_x > max_width:
            raise ValueError(f"Slide {slide_number}: line exceeds max_width: {line!r}")
        if height > step:
            raise ValueError(f"Slide {slide_number}: line_step is too small for {line!r}")
        measured.append((line, bbox, width))

    if top + len(lines) * step + 2 * pad_y > image.height:
        raise ValueError(f"Slide {slide_number}: {style_name} layer crosses the bottom edge")

    boxes = []
    for index, (line, bbox, width) in enumerate(measured):
        full_width = width + 2 * pad_x
        x0 = round(anchor_x - full_width / 2) if align == "center" else (anchor_x if align == "left" else anchor_x - full_width)
        x1 = x0 + full_width
        if x0 < 0 or x1 > image.width:
            raise ValueError(f"Slide {slide_number}: {style_name} layer crosses a side edge")
        y0 = top + index * step
        boxes.append((x0, y0, x1, y0 + step + 2 * pad_y, line, bbox))

    # Draw all rectangles before text; overlapping rows become one stepped sticker.
    for x0, y0, x1, y1, _, _ in boxes:
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=box_color)
    for x0, y0, _, _, line, bbox in boxes:
        draw.text(
            (x0 + pad_x - bbox[0], y0 + pad_y - bbox[1]),
            line,
            font=font,
            fill=text_color,
            stroke_width=stroke,
            stroke_fill=stroke_color,
        )


def _paint_asset(image: Image.Image, asset: dict[str, Any], config_dir: Path, slide_number: int) -> None:
    """Place a real product screenshot or other supplied asset, independent of the photo."""
    source = _relative_path(asset["path"], config_dir)
    if not source.is_file():
        raise FileNotFoundError(f"Slide {slide_number}: asset missing: {source}")
    width = _positive_int(asset.get("width"), "asset width")
    top = _positive_int(asset.get("top"), "asset top", minimum=0)
    radius = _positive_int(asset.get("corner_radius", 0), "asset corner_radius", minimum=0)
    align = asset.get("align", "center")
    if align not in ("center", "left", "right"):
        raise ValueError(f"Slide {slide_number}: asset align must be center, left, or right")
    default_x = image.width // 2 if align == "center" else (40 if align == "left" else image.width - 40)
    anchor_x = _positive_int(asset.get("x", default_x), "asset x", minimum=0)
    x = round(anchor_x - width / 2) if align == "center" else (anchor_x if align == "left" else anchor_x - width)
    with Image.open(source) as raw:
        height = round(width * raw.height / raw.width)
        overlay = raw.convert("RGBA").resize((width, height), Image.Resampling.LANCZOS)
    if x < 0 or x + width > image.width or top + height > image.height:
        raise ValueError(f"Slide {slide_number}: asset crosses the canvas edge")
    if radius:
        mask = Image.new("L", overlay.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width, height), radius=radius, fill=255)
        overlay.putalpha(ImageChops.multiply(overlay.getchannel("A"), mask))
    image.alpha_composite(overlay, (x, top))


def render(config_path: Path, regular_override: str | None = None, bold_override: str | None = None) -> list[Path]:
    config_path = config_path.expanduser().resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config_dir = config_path.parent
    size = config.get("canvas")
    if not isinstance(size, list) or len(size) != 2:
        raise ValueError("canvas must be [width, height]")
    width = _positive_int(size[0], "canvas width")
    height = _positive_int(size[1], "canvas height")
    styles = config.get("styles")
    slides = config.get("slides")
    if not isinstance(styles, dict) or not styles or not isinstance(slides, list) or not slides:
        raise ValueError("styles and slides must be nonempty")

    font_files = config.get("font_files", {})
    fonts = {}
    for alias, override in (("regular", regular_override), ("bold", bold_override)):
        value = override or font_files.get(alias)
        if value:
            fonts[alias] = Path(value).expanduser().resolve() if override else _relative_path(value, config_dir)

    outputs = []
    for number, slide in enumerate(slides, start=1):
        source = _relative_path(slide["background"], config_dir)
        output = _relative_path(slide["output"], config_dir)
        if source.resolve() == output.resolve():
            raise ValueError(f"Slide {number}: output cannot overwrite its clean background")
        if output.suffix.lower() != ".png":
            raise ValueError(f"Slide {number}: output must be a PNG")
        if not source.is_file():
            raise FileNotFoundError(f"Slide {number}: background missing: {source}")
        with Image.open(source) as raw:
            ratio_error = abs(raw.width / raw.height - width / height)
            if ratio_error > 0.015 and not slide.get("allow_crop", False):
                raise ValueError(f"Slide {number}: background ratio differs from canvas; prepare its crop or set allow_crop")
            image = ImageOps.fit(raw.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
        for asset in slide.get("asset_layers", []):
            _paint_asset(image, asset, config_dir, number)
        for layer in slide.get("layers", []):
            _paint_layer(image, layer, styles, fonts, number)
        output.parent.mkdir(parents=True, exist_ok=True)
        image.convert("RGB").save(output, optimize=True)
        outputs.append(output)
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path, help="JSON config for backgrounds, styles and exact text")
    parser.add_argument("--font-regular", help="Installed regular .ttf/.otf file path")
    parser.add_argument("--font-bold", help="Installed bold .ttf/.otf file path")
    args = parser.parse_args()
    for path in render(args.config, args.font_regular, args.font_bold):
        print(path)


if __name__ == "__main__":
    main()
