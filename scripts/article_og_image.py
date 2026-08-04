#!/usr/bin/env python3
"""記事別 OGP 画像を固定フォーマットで生成する。"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SITE_BASE = "https://errorlog.jp"
WIDTH = 1200
HEIGHT = 630
OG_PREFIX = "og/posts"


def die(msg: str) -> None:
    raise SystemExit(f"[停止] {msg}")


def article_og_rel(slug: str) -> str:
    if not re.fullmatch(r"[a-z0-9_+-]+", slug):
        die(f"slug に想定外の文字があります: {slug}")
    return f"{OG_PREFIX}/{slug}.png"


def split_title(title: str) -> list[str]:
    marker = "原因と解決策"
    if marker in title:
        before, after = title.split(marker, 1)
        lines = [before.rstrip(), marker + after]
        return [line for line in lines if line]
    return [title]


def fit_title_font(draw, lines: list[str], font_path: str, max_width: int, max_lines: int):
    from PIL import ImageFont

    for size in range(68, 47, -2):
        font = ImageFont.truetype(font_path, size)
        if len(lines) <= max_lines and all(draw.textlength(line, font=font) <= max_width for line in lines):
            return font, size
    die("タイトルが OGP 画像に収まりません。短い title にするか、生成ルールを見直してください。")


def generate_article_og_image(slug: str, title: str, service: str, public_too: bool = False) -> str:
    if not title:
        die("title が空です。")
    if not service:
        die("service が空です。")

    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError as e:
        die(f"Pillow が見つからないため OGP 画像を生成できません: {e}")

    rel = article_og_rel(slug)
    outputs = [BASE / "static" / rel]
    if public_too:
        outputs.append(BASE / "public" / rel)

    icon_path = BASE / "static" / "logo.png"
    if not icon_path.exists():
        die(f"ロゴ画像が見つかりません: {icon_path}")

    courier_bold = r"C:\Windows\Fonts\courbd.ttf"
    meiryo = r"C:\Windows\Fonts\meiryo.ttc"
    meiryo_bold = r"C:\Windows\Fonts\meiryob.ttc"
    for font_path in [courier_bold, meiryo, meiryo_bold]:
        if not Path(font_path).exists():
            die(f"フォントが見つかりません: {font_path}")

    bg = (26, 26, 46)
    red = (224, 82, 82)
    primary = (232, 232, 238)
    secondary = (166, 163, 186)
    line = (88, 86, 113)

    im = Image.new("RGB", (WIDTH, HEIGHT), bg)
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((-220, -180, 620, 540), fill=(42, 44, 70, 58))
    od.ellipse((670, 230, 1430, 820), fill=(18, 18, 34, 62))
    od.rectangle((0, 0, WIDTH, HEIGHT), outline=(42, 42, 66, 255), width=2)
    overlay = overlay.filter(ImageFilter.GaussianBlur(72))
    im = Image.alpha_composite(im.convert("RGBA"), overlay)
    draw = ImageDraw.Draw(im)

    logo_font = ImageFont.truetype(courier_bold, 62)
    badge_font = ImageFont.truetype(meiryo_bold, 31)
    url_font = ImageFont.truetype(meiryo, 31)
    title_lines = split_title(title)
    title_font, title_size = fit_title_font(draw, title_lines, meiryo_bold, 1036, 3)

    icon = Image.open(icon_path).convert("RGBA").resize((98, 98), Image.Resampling.LANCZOS)
    im.alpha_composite(icon, (82, 58))
    logo_x, logo_y = 194, 68
    draw.text((logo_x, logo_y), "Error", font=logo_font, fill=red)
    error_w = draw.textlength("Error", font=logo_font)
    draw.text((logo_x + error_w, logo_y), "Log", font=logo_font, fill=primary)

    badge_x, badge_y = 82, 176
    badge_text_w = draw.textlength(service, font=badge_font)
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_text_w + 42, badge_y + 56),
        radius=9,
        fill=(16, 163, 127, 42),
        outline=(16, 163, 127, 150),
        width=2,
    )
    draw.text((badge_x + 21, badge_y + 9), service, font=badge_font, fill=(88, 232, 194))

    y = 265
    line_step = title_size + 20
    for line_text in title_lines:
        draw.text((82, y), line_text, font=title_font, fill=primary)
        y += line_step

    rule_y = 505
    draw.line((82, rule_y, 1118, rule_y), fill=line, width=3)
    draw.text((82, 532), f"{SITE_BASE}/posts/{slug}/", font=url_font, fill=secondary)

    for out in outputs:
        out.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGB").save(out, optimize=True)

    return rel


def main() -> None:
    ap = argparse.ArgumentParser(description="記事別 OGP 画像を生成")
    ap.add_argument("slug")
    ap.add_argument("--title", required=True)
    ap.add_argument("--service", required=True)
    ap.add_argument("--public", action="store_true", help="public/ にも同じ画像を出力する")
    args = ap.parse_args()
    rel = generate_article_og_image(args.slug, args.title, args.service, public_too=args.public)
    print(rel)


if __name__ == "__main__":
    main()
