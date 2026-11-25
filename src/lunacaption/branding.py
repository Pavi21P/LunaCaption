"""LunaCaption palette and logo: a faceted crescent moon holding two caption lines.

The mark is drawn with Pillow from the same geometry as assets/lunacaption-logo.svg,
so the desktop window and the packaged executable need no image data files.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

# Palette shared by the desktop UI and the logo.
MIST = "#f2eef6"  # window background
CARD = "#fbfaff"  # raised surfaces
LINE = "#ddd6ee"  # borders and dividers
WASH = "#e4ddf5"  # chips, selection, troughs
SOFT = "#ece6f8"  # secondary buttons and headings
LILAC = "#9a86e2"  # light crescent facet
VIOLET = "#6a52c4"  # primary accent
PLUM = "#45338f"  # dark crescent facet, pressed states
NIGHT = "#2f2560"  # text and caption lines
MUTED = "#625a85"  # secondary text (>= 4.5:1 on MIST and CARD)
DANGER = "#b3261e"

# Logo geometry in the SVG's coordinate space.
_OUTER = (775, 165, 100)  # crescent body: centre x, centre y, radius
_CUT = (819, 133, 86)  # circle removed to form the hollow
_TOP_FACET = [(819, 133), (600, 40), (600, 0), (1000, 0), (1000, 133)]
_LOW_FACET = [(819, 133), (690, 350), (1000, 350), (1000, 133)]
_CAPTIONS = [((790, 166), (856, 166)), ((790, 194), (828, 194))]
_STROKE = 14
_SUPERSAMPLE = 4


def _circle_box(cx: float, cy: float, r: float, scale: float, ox: float, oy: float):
    return (
        (cx - r - ox) * scale,
        (cy - r - oy) * scale,
        (cx + r - ox) * scale,
        (cy + r - oy) * scale,
    )


def _draw_mark(size: int, origin: tuple[float, float], side: float) -> Image.Image:
    """Render the crescent with its caption lines on a transparent canvas."""
    big = size * _SUPERSAMPLE
    scale = big / side
    ox, oy = origin

    def point(xy):
        return ((xy[0] - ox) * scale, (xy[1] - oy) * scale)

    facets = Image.new("RGBA", (big, big), VIOLET)
    draw = ImageDraw.Draw(facets)
    draw.polygon([point(p) for p in _TOP_FACET], fill=LILAC)
    draw.polygon([point(p) for p in _LOW_FACET], fill=PLUM)

    mask = Image.new("L", (big, big), 0)
    shape = ImageDraw.Draw(mask)
    shape.ellipse(_circle_box(*_OUTER, scale, ox, oy), fill=255)
    shape.ellipse(_circle_box(*_CUT, scale, ox, oy), fill=0)

    mark = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    mark.paste(facets, (0, 0), mask)
    pen = ImageDraw.Draw(mark)
    width = _STROKE * scale
    for start, end in _CAPTIONS:
        a, b = point(start), point(end)
        pen.line([a, b], fill=NIGHT, width=round(width))
        for x, y in (a, b):  # round caps
            pen.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=NIGHT)
    return mark.resize((size, size), Image.Resampling.LANCZOS)


def logo_mark(size: int) -> Image.Image:
    """The crescent alone, tightly framed, for use on light backgrounds."""
    return _draw_mark(size, origin=(668, 58), side=214)


def app_icon(size: int) -> Image.Image:
    """The crescent on a rounded lavender tile, legible on light or dark taskbars."""
    big = size * _SUPERSAMPLE
    tile = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(tile).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=round(big * 0.22), fill=MIST
    )
    tile = tile.resize((size, size), Image.Resampling.LANCZOS)
    inset = max(1, round(size * 0.1))
    mark = logo_mark(size - 2 * inset)
    tile.alpha_composite(mark, (inset, inset))
    return tile
