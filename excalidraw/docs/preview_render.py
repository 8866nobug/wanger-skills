"""轻量 SVG 预览渲染器（仅用于生成 README 图片，不属于 Skill 运行时）。

只使用 Python 标准库：读取引擎解析后的 Document，按元素类型画成 SVG。
它不是 Excalidraw 的完整渲染器，不处理手绘抖动、图片、字体度量等细节；
真实效果以 Obsidian + Excalidraw 插件打开为准。
"""
from __future__ import annotations

import math
from html import escape

FONT_FAMILIES = {
    1: "'Comic Sans MS', 'Segoe Print', cursive",
    2: "Arial, 'Microsoft YaHei', 'PingFang SC', sans-serif",
    3: "Consolas, 'Cascadia Mono', monospace",
    5: "'Comic Sans MS', 'Segoe Print', cursive",
}

ARROW_LEN = 14.0
ARROW_HALF = 7.0


def _num(v, default=0.0):
    return float(v) if isinstance(v, (int, float)) else default


def _points(e):
    pts = e.get("points") or []
    x, y = _num(e.get("x")), _num(e.get("y"))
    return [(x + _num(p[0]), y + _num(p[1])) for p in pts]


def _bbox(e):
    if e.get("type") in ("line", "arrow"):
        pts = _points(e)
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            return min(xs), min(ys), max(xs), max(ys)
    x, y = _num(e.get("x")), _num(e.get("y"))
    return x, y, x + _num(e.get("width")), y + _num(e.get("height"))


def _head(points, at_end, kind, stroke):
    if not kind or len(points) < 2:
        return ""
    if at_end:
        tip, prev = points[-1], points[-2]
    else:
        tip, prev = points[0], points[1]
    dx, dy = tip[0] - prev[0], tip[1] - prev[1]
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ""
    ux, uy = dx / length, dy / length
    px, py = -uy, ux
    if kind == "arrow":
        base = (tip[0] - ux * ARROW_LEN, tip[1] - uy * ARROW_LEN)
        a = (base[0] + px * ARROW_HALF, base[1] + py * ARROW_HALF)
        b = (base[0] - px * ARROW_HALF, base[1] - py * ARROW_HALF)
        return (f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} '
                f'{a[0]:.1f},{a[1]:.1f} {b[0]:.1f},{b[1]:.1f}" '
                f'fill="{stroke}" stroke="{stroke}" stroke-width="1"/>')
    if kind == "triangle_outline":
        base = (tip[0] - ux * 16.0, tip[1] - uy * 16.0)
        a = (base[0] + px * 8.5, base[1] + py * 8.5)
        b = (base[0] - px * 8.5, base[1] - py * 8.5)
        return (f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} '
                f'{a[0]:.1f},{a[1]:.1f} {b[0]:.1f},{b[1]:.1f}" '
                f'fill="#ffffff" stroke="{stroke}" stroke-width="1.5"/>')
    if kind == "bar":
        a = (tip[0] + px * 10.0, tip[1] + py * 10.0)
        b = (tip[0] - px * 10.0, tip[1] - py * 10.0)
        return (f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" '
                f'x2="{b[0]:.1f}" y2="{b[1]:.1f}" '
                f'stroke="{stroke}" stroke-width="2"/>')
    if kind in ("diamond", "diamond_outline"):
        back = (tip[0] - ux * 20.0, tip[1] - uy * 20.0)
        mid = (tip[0] - ux * 10.0, tip[1] - uy * 10.0)
        a = (mid[0] + px * 8.0, mid[1] + py * 8.0)
        b = (mid[0] - px * 8.0, mid[1] - py * 8.0)
        fill = "#ffffff" if kind == "diamond_outline" else stroke
        return (f'<polygon points="{tip[0]:.1f},{tip[1]:.1f} '
                f'{a[0]:.1f},{a[1]:.1f} {back[0]:.1f},{back[1]:.1f} '
                f'{b[0]:.1f},{b[1]:.1f}" fill="{fill}" '
                f'stroke="{stroke}" stroke-width="1.4"/>')
    return ""


def _render_text(e, ox=0.0, oy=0.0):
    text = e.get("text")
    if not text:
        return ""
    size = _num(e.get("fontSize"), 20)
    fam = FONT_FAMILIES.get(e.get("fontFamily"), FONT_FAMILIES[2])
    color = e.get("strokeColor") or "#1e1e1e"
    align = e.get("textAlign") or "left"
    valign = e.get("verticalAlign") or "top"
    x, y = _num(e.get("x")) - ox, _num(e.get("y")) - oy
    w, h = _num(e.get("width")), _num(e.get("height"))
    lines = text.split("\n")
    line_h = size * 1.25
    block_h = line_h * len(lines)
    if valign == "middle":
        top = y + (h - block_h) / 2.0
    elif valign == "bottom":
        top = y + h - block_h
    else:
        top = y
    if align == "center":
        tx, anchor = x + w / 2.0, "middle"
    elif align == "right":
        tx, anchor = x + w, "end"
    else:
        tx, anchor = x, "start"
    out = []
    for i, line in enumerate(lines):
        baseline = top + size * 0.92 + i * line_h
        out.append(
            f'<text x="{tx:.1f}" y="{baseline:.1f}" fill="{color}" '
            f'font-family="{fam}" font-size="{size:.1f}" '
            f'text-anchor="{anchor}" xml:space="preserve">'
            f'{escape(line)}</text>')
    return "".join(out)


def render_content(doc, *, padding=48):
    """返回 (内部 SVG 元素列表, 宽, 高, 背景色)。"""
    els = [e for e in doc.elements if not e.get("isDeleted")]
    boxes = [_bbox(e) for e in els]
    min_x = min(b[0] for b in boxes) - padding
    min_y = min(b[1] for b in boxes) - padding
    max_x = max(b[2] for b in boxes) + padding
    max_y = max(b[3] for b in boxes) + padding
    w, h = max_x - min_x, max_y - min_y
    bg = doc.app_state.get("viewBackgroundColor") or "#ffffff"

    def X(v):
        return v - min_x

    def Y(v):
        return v - min_y

    out = [f'<rect x="0" y="0" width="{w:.0f}" height="{h:.0f}" fill="{bg}"/>']
    for e in els:
        t = e.get("type")
        stroke = e.get("strokeColor") or "#1e1e1e"
        fill = e.get("backgroundColor") or "transparent"
        sw = _num(e.get("strokeWidth"), 1)
        dash = ""
        if e.get("strokeStyle") == "dashed":
            dash = ' stroke-dasharray="9 7"'
        elif e.get("strokeStyle") == "dotted":
            dash = ' stroke-dasharray="2 6" stroke-linecap="round"'
        opacity = _num(e.get("opacity"), 100) / 100.0
        op = f' opacity="{opacity:.2f}"' if opacity < 1 else ""
        if t == "rectangle":
            rx = 10 if e.get("roundness") else 0
            out.append(
                f'<rect x="{X(_num(e.get("x"))):.1f}" '
                f'y="{Y(_num(e.get("y"))):.1f}" '
                f'width="{_num(e.get("width")):.1f}" '
                f'height="{_num(e.get("height")):.1f}" rx="{rx}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
                f'{dash}{op}/>')
        elif t == "ellipse":
            cx = X(_num(e.get("x")) + _num(e.get("width")) / 2.0)
            cy = Y(_num(e.get("y")) + _num(e.get("height")) / 2.0)
            out.append(
                f'<ellipse cx="{cx:.1f}" cy="{cy:.1f}" '
                f'rx="{_num(e.get("width")) / 2.0:.1f}" '
                f'ry="{_num(e.get("height")) / 2.0:.1f}" '
                f'fill="{fill}" stroke="{stroke}" stroke-width="{sw}"'
                f'{dash}{op}/>')
        elif t == "diamond":
            cx = X(_num(e.get("x")) + _num(e.get("width")) / 2.0)
            cy = Y(_num(e.get("y")) + _num(e.get("height")) / 2.0)
            hw, hh = _num(e.get("width")) / 2.0, _num(e.get("height")) / 2.0
            out.append(
                f'<polygon points="{cx:.1f},{cy - hh:.1f} '
                f'{cx + hw:.1f},{cy:.1f} {cx:.1f},{cy + hh:.1f} '
                f'{cx - hw:.1f},{cy:.1f}" fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{sw}"{dash}{op}/>')
        elif t in ("line", "arrow"):
            pts = _points(e)
            if not pts:
                continue
            path = " ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in pts)
            out.append(
                f'<polyline points="{path}" fill="none" stroke="{stroke}" '
                f'stroke-width="{sw}" stroke-linejoin="round" '
                f'stroke-linecap="round"{dash}{op}/>')
            screen_pts = [(X(p[0]), Y(p[1])) for p in pts]
            out.append(_head(screen_pts, False, e.get("startArrowhead"), stroke))
            out.append(_head(screen_pts, True, e.get("endArrowhead"), stroke))
        elif t == "text":
            out.append(_render_text(e, min_x, min_y))
    return out, w, h, bg


def render_svg(doc, *, padding=48):
    inner, w, h, _bg = render_content(doc, padding=padding)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" '
            f'height="{h:.0f}" viewBox="0 0 {w:.0f} {h:.0f}">\n'
            + "\n".join(inner) + "\n</svg>\n"), w, h
