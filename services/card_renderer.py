"""原神のビルドカード画像（計算機風レイアウト）。"""

from __future__ import annotations

import io
from collections import Counter
from pathlib import Path

import messages as msg
from games.base import CharacterBuild, ParsedPiece
from games.genshin import GenshinGame
from games.genshin.score import score_piece
from games.genshin.stats import format_stat_value
from services.copy import t
from services.enka_client import EnkaAvatar, EnkaShowcase

_ELEMENT_COLORS = {
    "pyro": (232, 88, 66),
    "hydro": (75, 160, 232),
    "cryo": (120, 200, 230),
    "electro": (176, 112, 224),
    "anemo": (96, 200, 172),
    "geo": (232, 184, 72),
    "dendro": (128, 200, 80),
}

_SLOT_ORDER = ["flower", "feather", "sands", "goblet", "circlet"]

_RANK_COLOR = {
    "godly": (232, 196, 80),
    "great": (232, 140, 64),
    "good": (220, 72, 72),
    "ok": (80, 160, 220),
    "growing": (150, 154, 160),
}

_BG = (22, 28, 34)
_PANEL = (36, 44, 54)
_PANEL2 = (44, 54, 66)
_TEXT = (245, 246, 248)
_MUTED = (168, 176, 186)
_SUB = (210, 214, 220)

_FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\YuGothB.ttc"),
    Path(r"C:\Windows\Fonts\YuGothM.ttc"),
    Path(r"C:\Windows\Fonts\YuGothR.ttc"),
    Path(r"C:\Windows\Fonts\meiryo.ttc"),
    Path(r"C:\Windows\Fonts\msgothic.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
]


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    paths = list(_FONT_CANDIDATES)
    if not bold:
        paths = [p for p in paths if "GothB" not in p.name] + paths
    for path in paths:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size, index=0)
            except OSError:
                continue
    return ImageFont.load_default()


def _open_bytes(data: bytes | None):
    from PIL import Image

    if not data:
        return None
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except OSError:
        return None


def _opaque_ratio(image) -> float:
    if image.mode != "RGBA":
        return 1.0
    hist = image.getchannel("A").histogram()
    visible = sum(hist[16:])
    area = image.width * image.height
    return visible / area if area else 0.0


def _densest_left(image, width: int) -> int:
    """横長画像から、不透明が一番多い幅の左端を返す。"""
    if image.width <= width:
        return 0
    alpha = image.getchannel("A")
    pixels = alpha.load()
    height = image.height
    col = [0] * image.width
    for x in range(image.width):
        total = 0
        for y in range(height):
            total += pixels[x, y]
        col[x] = total
    prefix = [0]
    for value in col:
        prefix.append(prefix[-1] + value)
    best_x = 0
    best = -1
    for x in range(0, image.width - width + 1):
        window = prefix[x + width] - prefix[x]
        if window > best:
            best = window
            best_x = x
    return best_x


def _cover(image, size: tuple[int, int], *, bottom: bool = True):
    from PIL import Image

    if image.mode == "RGBA":
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw, nh = int(image.width * scale), int(image.height * scale)
    fitted = image.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (nw - tw) // 2
    y = nh - th if bottom else (nh - th) // 2
    return fitted.crop((x, max(0, y), x + tw, max(0, y) + th))


def _fit_portrait(image, size: tuple[int, int]):
    """立ち絵を枠に収める。縦長は拡大切りせず、横長は高さ合わせでキャラ位置を切る。"""
    from PIL import Image

    if image.mode == "RGBA":
        bbox = image.getchannel("A").getbbox()
        if bbox:
            image = image.crop(bbox)
    tw, th = size
    src_aspect = image.width / image.height
    box_aspect = tw / th
    if src_aspect < box_aspect:
        scale = th / image.height
        nw = max(1, int(image.width * scale))
        fitted = image.resize((nw, th), Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.paste(fitted, ((tw - nw) // 2, 0), fitted)
        return canvas
    scale = th / image.height
    nw = max(1, int(image.width * scale))
    fitted = image.resize((nw, th), Image.Resampling.LANCZOS)
    if nw <= tw:
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.paste(fitted, ((tw - nw) // 2, 0), fitted)
        return canvas
    x = _densest_left(fitted, tw)
    return fitted.crop((x, 0, x + tw, th))


def _paste(base, src, xy: tuple[int, int], size: tuple[int, int] | None = None) -> None:
    from PIL import Image

    if src is None:
        return
    img = src
    if size:
        img = img.copy()
        img.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        ox = (size[0] - img.width) // 2
        oy = (size[1] - img.height) // 2
        canvas.paste(img, (ox, oy), img)
        img = canvas
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    base.paste(img, xy, img)


def _circle_icon(src, size: int, *, dim: bool = False):
    from PIL import Image, ImageDraw

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if src is not None:
        fitted = _cover(src, (size, size), bottom=False)
        canvas.paste(fitted, (0, 0), fitted)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    canvas.putalpha(mask)
    if dim:
        overlay = Image.new("RGBA", (size, size), (0, 0, 0, 140))
        overlay.putalpha(mask.point(lambda p: int(p * 0.7)))
        canvas = Image.alpha_composite(canvas, overlay)
    return canvas


def _text_with_shadow(
    draw,
    xy: tuple[int, int],
    text: str,
    font,
    fill,
    *,
    stroke: int = 2,
) -> None:
    """背景なしで読めるよう、暗い縁と影を付ける。"""
    x, y = xy
    shadow = (0, 0, 0, 160)
    for dx, dy in ((2, 2), (1, 3)):
        draw.text((x + dx, y + dy), text, font=font, fill=shadow)
    draw.text(
        (x, y),
        text,
        font=font,
        fill=fill,
        stroke_width=stroke,
        stroke_fill=(0, 0, 0),
    )


def _set_summary(pieces: list[ParsedPiece]) -> tuple[str, int]:
    names = [p.set_name_ja for p in pieces if p.set_name_ja]
    if not names:
        return "", 0
    name, count = Counter(names).most_common(1)[0]
    return name, count


def render_build_card(
    showcase: EnkaShowcase,
    avatar: EnkaAvatar,
    build: CharacterBuild,
    *,
    portrait_bytes: bytes | list[bytes] | None,
    weapon_bytes: bytes | None,
    icon_bytes: dict[str, bytes] | None = None,
) -> bytes:
    """紹介キャラ1体のカード PNG を返す。"""
    from PIL import Image, ImageDraw

    icons = icon_bytes or {}
    game = GenshinGame()
    accent = _ELEMENT_COLORS.get(avatar.element, (180, 180, 180))
    width, height = 1600, 900
    image = Image.new("RGBA", (width, height), _BG + (255,))
    draw = ImageDraw.Draw(image)

    font_name = _font(44, bold=True)
    font_xl = _font(64, bold=True)
    font_rank = _font(72, bold=True)
    font_lg = _font(28, bold=True)
    font_md = _font(22)
    font_sm = _font(18)
    font_xs = _font(15)

    splash_h = 520
    splash_w = 470
    blobs: list[bytes] = []
    if isinstance(portrait_bytes, (bytes, bytearray)):
        blobs.append(bytes(portrait_bytes))
    elif portrait_bytes:
        blobs.extend(bytes(item) for item in portrait_bytes if item)
    for key in (avatar.splash_icon, avatar.icon):
        extra = icons.get(key) if key else None
        if extra:
            blobs.append(extra)
    covered = None
    for blob in blobs:
        src = _open_bytes(blob)
        if src is None:
            continue
        fitted = _fit_portrait(src, (splash_w, splash_h))
        if _opaque_ratio(fitted) < 0.08:
            continue
        covered = fitted
        break
    if covered is not None:
        fade = Image.new("RGBA", (splash_w, splash_h), (0, 0, 0, 0))
        fade.paste(covered, (0, 0), covered)
        grad = Image.new("RGBA", (80, splash_h), (0, 0, 0, 0))
        gdraw = ImageDraw.Draw(grad)
        for x in range(80):
            alpha = int(255 * x / 80)
            gdraw.line([(x, 0), (x, splash_h)], fill=_BG + (alpha,))
        fade.alpha_composite(grad, (splash_w - 80, 0))
        left = Image.new("RGBA", (90, splash_h), (0, 0, 0, 0))
        ldraw = ImageDraw.Draw(left)
        for x in range(90):
            alpha = int(110 * (1 - x / 90))
            ldraw.line([(x, 0), (x, splash_h)], fill=(16, 20, 26, alpha))
        fade.alpha_composite(left, (0, 0))
        image.alpha_composite(fade, (16, 16))

    _text_with_shadow(draw, (32, 28), avatar.name_ja, font_name, _TEXT, stroke=3)
    meta = f"Lv.{avatar.level}    {t(msg.MSG_38, level=avatar.friendship)}"
    _text_with_shadow(draw, (32, 88), meta, font_sm, _MUTED, stroke=2)

    # 天賦
    for i, (icon_name, level) in enumerate(avatar.skills[:3]):
        y = 140 + i * 78
        icon = _open_bytes(icons.get(icon_name))
        badge = _circle_icon(icon, 56)
        image.alpha_composite(badge, (28, y))
        draw.ellipse((28 + 36, y + 36, 28 + 62, y + 62), fill=(16, 20, 26, 230))
        draw.text((28 + 42, y + 38), str(level), font=font_xs, fill=_TEXT)

    # 命の星座
    for i, icon_name in enumerate(avatar.constellation_icons[:6]):
        y = 130 + i * 58
        icon = _open_bytes(icons.get(icon_name))
        locked = i >= avatar.constellations
        badge = _circle_icon(icon, 44, dim=locked)
        image.alpha_composite(badge, (430, y))

    # ステータス
    stats_x = 520
    stats_y = 36
    draw.text((stats_x, stats_y), showcase.nickname, font=font_xs, fill=_MUTED)
    stats_y = 64
    stats = avatar.stats

    rows: list[tuple[str, str, str]] = [
        ("HP", f"{stats.get('hp', 0):,.0f}", f"({avatar.hp_base:,.0f} + {max(0, stats.get('hp', 0) - avatar.hp_base):,.0f})"),
        (
            game.stat_label("atk_flat"),
            f"{stats.get('atk', 0):,.0f}",
            f"({avatar.atk_base:,.0f} + {max(0, stats.get('atk', 0) - avatar.atk_base):,.0f})",
        ),
        (
            game.stat_label("def_flat"),
            f"{stats.get('def', 0):,.0f}",
            f"({avatar.def_base:,.0f} + {max(0, stats.get('def', 0) - avatar.def_base):,.0f})",
        ),
        (game.stat_label("em"), f"{stats.get('em', 0):.0f}", ""),
        (game.stat_label("crit_rate"), f"{stats.get('crit_rate', 0):.1f}%", ""),
        (game.stat_label("crit_dmg"), f"{stats.get('crit_dmg', 0):.1f}%", ""),
        (game.stat_label("er"), f"{stats.get('er', 0):.1f}%", ""),
    ]
    if avatar.dmg_bonus_key and avatar.dmg_bonus >= 0.5:
        rows.append(
            (game.stat_label(avatar.dmg_bonus_key), f"{avatar.dmg_bonus:.1f}%", "")
        )

    for i, (label, value, extra) in enumerate(rows):
        y = stats_y + i * 48
        draw.rounded_rectangle((stats_x, y, stats_x + 8, y + 36), radius=3, fill=accent)
        draw.text((stats_x + 22, y + 6), label, font=font_sm, fill=_MUTED)
        draw.text((stats_x + 210, y + 2), value, font=font_lg, fill=_TEXT)
        if extra:
            draw.text((stats_x + 360, y + 8), extra, font=font_xs, fill=_MUTED)

    # 右パネル: 武器・セット・総合
    rx = 1080
    draw.rounded_rectangle((rx, 28, 1572, 500), radius=16, fill=_PANEL)
    if avatar.weapon:
        wicon = _open_bytes(weapon_bytes or icons.get(avatar.weapon.icon))
        _paste(image, wicon, (rx + 24, 48), (96, 96))
        draw.text((rx + 136, 52), avatar.weapon.name_ja, font=font_md, fill=_TEXT)
        draw.text(
            (rx + 136, 86),
            f"R{avatar.weapon.refine}   Lv.{avatar.weapon.level}",
            font=font_sm,
            fill=accent,
        )
        if avatar.weapon.base_atk:
            draw.text(
                (rx + 136, 118),
                f"{game.stat_label('atk_flat')}  {avatar.weapon.base_atk:.0f}",
                font=font_xs,
                fill=_SUB,
            )
        if avatar.weapon.sub_key:
            draw.text(
                (rx + 136, 140),
                f"{game.stat_label(avatar.weapon.sub_key)}  {format_stat_value(avatar.weapon.sub_key, avatar.weapon.sub_value)}",
                font=font_xs,
                fill=_SUB,
            )

    set_name, set_count = _set_summary(avatar.pieces)
    if set_name:
        draw.text((rx + 24, 180), set_name, font=font_sm, fill=_TEXT)
        draw.rounded_rectangle((rx + 420, 176, rx + 460, 208), radius=6, fill=accent)
        draw.text((rx + 432, 180), str(min(set_count, 4)), font=font_sm, fill=(16, 20, 26))

    pieces_by_slot = {p.slot: p for p in avatar.pieces}
    total = 0.0
    scored: dict[str, tuple[float, str]] = {}
    for slot in _SLOT_ORDER:
        piece = pieces_by_slot.get(slot)
        if piece is None:
            continue
        result = score_piece(piece, build)
        total += result.total
        scored[slot] = (result.total, result.band_key)
    total = round(total, 1)
    overall_band = "growing"
    # 5部位合計の目安: 花換算 30*5=150 B、40*5=200 A、45*5=225 S、50*5=250 SS
    if total >= 230:
        overall_band = "godly"
    elif total >= 200:
        overall_band = "great"
    elif total >= 170:
        overall_band = "good"
    elif total >= 130:
        overall_band = "ok"

    draw.text((rx + 24, 230), t(msg.MSG_35), font=font_sm, fill=_MUTED)
    draw.text((rx + 24, 268), f"{total:.1f}", font=font_xl, fill=_TEXT)
    rank = msg.MSG_RANK[overall_band]
    draw.text((rx + 360, 268), rank, font=font_rank, fill=_RANK_COLOR[overall_band])
    draw.text(
        (rx + 24, 360),
        t(msg.MSG_36, build=build.name_ja),
        font=font_xs,
        fill=_MUTED,
    )

    # 聖遺物5枠
    box_w, box_h = 300, 340
    gap = 12
    start_x = 20
    start_y = 540
    for index, slot in enumerate(_SLOT_ORDER):
        x = start_x + index * (box_w + gap)
        y = start_y
        draw.rounded_rectangle((x, y, x + box_w, y + box_h), radius=14, fill=_PANEL)
        piece = pieces_by_slot.get(slot)
        if piece is None:
            draw.text((x + 20, y + 20), t(msg.MSG_37), font=font_md, fill=_MUTED)
            continue
        icon = _open_bytes(icons.get(piece.icon or ""))
        _paste(image, icon, (x + 16, y + 16), (72, 72))
        main_text = "—"
        if piece.main:
            main_text = f"{game.stat_label(piece.main.key)}  {format_stat_value(piece.main.key, piece.main.value)}"
        draw.text((x + 100, y + 22), main_text, font=font_sm, fill=_TEXT)
        lv = piece.level if piece.level is not None else 0
        draw.text((x + 100, y + 50), f"+{lv}", font=font_sm, fill=accent)

        sy = y + 100
        for sub in piece.subs[:4]:
            draw.text((x + 20, sy), game.stat_label(sub.key), font=font_xs, fill=_MUTED)
            draw.text(
                (x + 168, sy),
                format_stat_value(sub.key, sub.value),
                font=font_sm,
                fill=_SUB,
            )
            sy += 32

        score_val, band = scored.get(slot, (0.0, "growing"))
        letter = msg.MSG_RANK.get(band, msg.MSG_44)
        draw.rounded_rectangle((x + 16, y + box_h - 58, x + 70, y + box_h - 16), radius=8, fill=_PANEL2)
        draw.text((x + 28, y + box_h - 52), letter, font=font_lg, fill=_RANK_COLOR.get(band, _MUTED))
        draw.text((x + 88, y + box_h - 48), t(msg.MSG_39), font=font_xs, fill=_MUTED)
        draw.text((x + 168, y + box_h - 52), f"{score_val:.1f}", font=font_lg, fill=_TEXT)

    rgb = image.convert("RGB")
    buffer = io.BytesIO()
    rgb.save(buffer, format="PNG")
    return buffer.getvalue()
