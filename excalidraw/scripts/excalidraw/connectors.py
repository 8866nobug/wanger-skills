"""箭头、绑定与连接关系。

箭头通过 Excalidraw 原生绑定（orbit）挂到形状上：移动形状时插件会自动更新箭头。
真实文件验证的绑定格式：

    "startBinding": {"elementId": "<id>", "mode": "orbit", "fixedPoint": [fx, fy]}

- fixedPoint 为 [0,1] 归一化坐标（相对目标元素包围盒）；
- 目标元素的 boundElements 中需有 {"type": "arrow", "id": "<arrow id>"}；
- 箭头自身 x/y 为绝对坐标，points 以 [0,0] 起始。
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import elements, styles

BBox = tuple[float, float, float, float]   # (x, y, width, height)


def _center(b: BBox) -> tuple[float, float]:
    x, y, w, h = b
    return (x + w / 2.0, y + h / 2.0)


def bbox(el: dict) -> BBox:
    return (el["x"], el["y"], el["width"], el["height"])


def _boundary_rect(b: BBox, toward: tuple[float, float]) -> tuple[float, float]:
    cx, cy = _center(b)
    x, y, w, h = b
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    scale = min(
        (w / 2.0) / abs(dx) if dx != 0 else float("inf"),
        (h / 2.0) / abs(dy) if dy != 0 else float("inf"),
    )
    return (cx + dx * scale, cy + dy * scale)


def _boundary_ellipse(b: BBox, toward: tuple[float, float]) -> tuple[float, float]:
    cx, cy = _center(b)
    x, y, w, h = b
    rx, ry = w / 2.0, h / 2.0
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    theta = math.atan2(dy / ry, dx / rx)
    return (cx + rx * math.cos(theta), cy + ry * math.sin(theta))


def _boundary_diamond(b: BBox, toward: tuple[float, float]) -> tuple[float, float]:
    cx, cy = _center(b)
    x, y, w, h = b
    rx, ry = w / 2.0, h / 2.0
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    denom = abs(dx) / rx + abs(dy) / ry
    scale = 1.0 / denom if denom else 0.0
    return (cx + dx * scale, cy + dy * scale)


def boundary_point(el: dict, toward: tuple[float, float]) -> tuple[float, float]:
    """元素边界上朝 toward 方向的首个交点（按元素形状精确计算）。"""
    b = bbox(el)
    t = el.get("type")
    if t == "ellipse":
        return _boundary_ellipse(b, toward)
    if t == "diamond":
        return _boundary_diamond(b, toward)
    return _boundary_rect(b, toward)


def fixed_point(el: dict, pt: tuple[float, float]) -> list[float]:
    """把绝对坐标换算为目标元素包围盒内 [0,1] 归一化坐标（绑定用）。"""
    x, y, w, h = bbox(el)
    fx = (pt[0] - x) / w if w else 0.5
    fy = (pt[1] - y) / h if h else 0.5
    return [min(1.0, max(0.0, fx)), min(1.0, max(0.0, fy))]


def _orbit_binding(el: dict, pt: tuple[float, float]) -> dict:
    return {"elementId": el["id"], "mode": "orbit", "fixedPoint": fixed_point(el, pt)}


def _ray_exit(b: BBox, toward: tuple[float, float],
              inflate: float = 0.0) -> tuple[float, float]:
    """从 b 中心沿 toward 方向射出，与「外扩 inflate」后包围盒的交点。"""
    cx, cy = _center(b)
    x, y, w, h = b
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, cy
    rx, ry = w / 2.0 + inflate, h / 2.0 + inflate
    ts = []
    if dx != 0:
        ts.append(rx / abs(dx))
    if dy != 0:
        ts.append(ry / abs(dy))
    t = min(ts)
    return (cx + dx * t, cy + dy * t)


def extend_anchor(el: dict, anchor: tuple[float, float],
                  toward: tuple[float, float],
                  gap: float = styles.BINDING_GAP) -> tuple[float, float]:
    """从包围盒上的锚点沿 toward 方向延伸到「外扩 gap」包围盒，即箭头端点。

    与插件实测行为一致：箭头端点不在形状边界上，而是在外扩 gap 的包围盒上。
    """
    x, y, w, h = bbox(el)
    x0, y0, x1, y1 = x - gap, y - gap, x + w + gap, y + h + gap
    dx, dy = toward[0] - anchor[0], toward[1] - anchor[1]
    ts: list[float] = []
    if dx > 0:
        ts.append((x1 - anchor[0]) / dx)
    elif dx < 0:
        ts.append((x0 - anchor[0]) / dx)
    if dy > 0:
        ts.append((y1 - anchor[1]) / dy)
    elif dy < 0:
        ts.append((y0 - anchor[1]) / dy)
    ts = [t for t in ts if t > 0]
    if not ts:
        return anchor
    t = min(ts)
    return (anchor[0] + dx * t, anchor[1] + dy * t)


def _binding_geometry(src_el: dict, dst_el: dict,
                      gap: float = styles.BINDING_GAP):
    """按插件实测行为计算绑定点。

    - 锚点：两中心连线与元素**未外扩**包围盒的交点（用于 fixedPoint）；
    - 端点：从锚点沿连线延伸到**外扩 gap** 包围盒的交点（箭头实际起止）。
    """
    src_b, dst_b = bbox(src_el), bbox(dst_el)
    sc, dc = _center(src_b), _center(dst_b)
    anchor0 = _ray_exit(src_b, dc)
    anchor1 = _ray_exit(dst_b, sc)
    p0 = extend_anchor(src_el, anchor0, anchor1, gap)
    p1 = extend_anchor(dst_el, anchor1, anchor0, gap)
    return p0, p1, anchor0, anchor1


def _geometry(src_el: dict, dst_el: dict):
    p0 = boundary_point(src_el, _center(bbox(dst_el)))
    p1 = boundary_point(dst_el, _center(bbox(src_el)))
    return p0, p1


def straight_arrow(env: elements.Env, src: BBox, dst: BBox, *,
                   start_arrowhead: str | None = None,
                   end_arrowhead: str | None = styles.END_ARROWHEAD,
                   **kw) -> dict:
    """生成从 src 包围盒边界到 dst 包围盒边界的直线箭头（无绑定）。"""
    p0 = _boundary_rect(src, _center(dst))
    p1 = _boundary_rect(dst, _center(src))
    x, y = p0
    points = [[0.0, 0.0], [p1[0] - p0[0], p1[1] - p0[1]]]
    return elements.arrow(env, x, y, points,
                          start_arrowhead=start_arrowhead,
                          end_arrowhead=end_arrowhead, **kw)


def bound_arrow(env: elements.Env, src_el: dict, dst_el: dict, *,
                start_arrowhead: str | None = None,
                end_arrowhead: str | None = styles.END_ARROWHEAD,
                **kw) -> dict:
    """生成两端都绑定到形状的箭头（orbit 模式，移动形状时自动跟随）。

    端点按插件行为在包围盒外留 `styles.BINDING_GAP`，fixedPoint 记录未外扩
    包围盒上的锚点，保证与 Obsidian 保存后的结果一致。
    """
    p0, p1, anchor0, anchor1 = _binding_geometry(src_el, dst_el)
    arrow = elements.arrow(
        env, p0[0], p0[1], [[0.0, 0.0], [p1[0] - p0[0], p1[1] - p0[1]]],
        start_binding=_orbit_binding(src_el, anchor0),
        end_binding=_orbit_binding(dst_el, anchor1),
        start_arrowhead=start_arrowhead,
        end_arrowhead=end_arrowhead, **kw)
    elements.bind_arrow(src_el, arrow["id"])
    elements.bind_arrow(dst_el, arrow["id"])
    return arrow


def line_between(env: elements.Env, src_el: dict, dst_el: dict, **kw) -> dict:
    """生成从 src 边界到 dst 边界的直线（无箭头、无绑定）。"""
    p0, p1 = _geometry(src_el, dst_el)
    points = [[0.0, 0.0], [p1[0] - p0[0], p1[1] - p0[1]]]
    return elements.line(env, p0[0], p0[1], points, **kw)


# --------------------------------------------------------------------------- #
# ER 图：基数解析、正交路由、鸦爪符号
# --------------------------------------------------------------------------- #

@dataclass
class Cardinality:
    """一端基数的解析结果。"""
    raw: str = ""
    many: bool = False
    optional: bool = False
    display: str = ""
    known: bool = True


def _card_side(raw: str) -> Cardinality:
    s = (raw or "").strip()
    if not s:
        return Cardinality()
    key = s.lower().replace(" ", "").replace("_", "")
    key = key.replace("..", "-").replace("—", "-")
    if key in ("1", "one", "1-1"):
        return Cardinality(s, False, False, "1")
    if key in ("0-1", "01", "optional", "zeroorone", "0to1"):
        return Cardinality(s, False, True, "0..1")
    if key in ("n", "m", "*", "many", "0-n", "0-*", "zeromany", "0tomany"):
        raw = s.upper()
        display = raw if raw in ("N", "M") else "N"
        return Cardinality(s, True, True, display)
    if key in ("1-n", "1-*", "onemany", "oneormany", "1tomany"):
        return Cardinality(s, True, False, "1..N")
    if key.startswith("0") and ("n" in key or "m" in key or "*" in key):
        return Cardinality(s, True, True, "0..N")
    if key.startswith("1") and ("n" in key or "m" in key or "*" in key):
        return Cardinality(s, True, False, "1..N")
    return Cardinality(s, False, False, s, known=False)


def parse_cardinality(spec: str) -> tuple[Cardinality, Cardinality]:
    """把 "1:N" / "0..1:N" / "N:M" 解析为 (src 端, dst 端)。

    单个值（如 "N"）默认作用于 dst 端；未知写法保留原文作为标签、不画符号。
    """
    s = (spec or "").strip()
    if not s:
        return Cardinality(), Cardinality()
    for sep in (":", "→", "->", "—"):
        if sep in s:
            left, right = s.split(sep, 1)
            return _card_side(left), _card_side(right)
    return Cardinality(), _card_side(s)


def _unit(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = math.hypot(dx, dy)
    return (dx / d, dy / d) if d else (0.0, 0.0)


def _side_point(el: dict, side: str,
                frac: float = 0.5) -> tuple[tuple[float, float], tuple[float, float]]:
    """返回 (边界锚点, 归一化 fixedPoint)。"""
    x, y, w, h = bbox(el)
    frac = round(min(1.0, max(0.0, frac)), 6)
    if side == "right":
        return (x + w, y + h * frac), (1.0, frac)
    if side == "left":
        return (x, y + h * frac), (0.0, frac)
    if side == "bottom":
        return (x + w * frac, y + h), (frac, 1.0)
    return (x + w * frac, y), (frac, 0.0)


def _offset_side(p: tuple[float, float], side: str,
                 gap: float) -> tuple[float, float]:
    if side == "right":
        return (p[0] + gap, p[1])
    if side == "left":
        return (p[0] - gap, p[1])
    if side == "bottom":
        return (p[0], p[1] + gap)
    return (p[0], p[1] - gap)


def er_sides(src_el: dict, dst_el: dict) -> tuple[str, str]:
    """按两卡片的相对位置选择连线出口/入口边（同一侧可被多条边共享）。"""
    if src_el.get("id") == dst_el.get("id"):
        return "right", "right"
    sc = _center(bbox(src_el))
    dc = _center(bbox(dst_el))
    dx, dy = dc[0] - sc[0], dc[1] - sc[1]
    if abs(dx) >= abs(dy):
        return ("right", "left") if dx >= 0 else ("left", "right")
    return ("bottom", "top") if dy >= 0 else ("top", "bottom")


def er_route(src_el: dict, dst_el: dict,
              gap: float = styles.ER_TOUCH_GAP,
              start_frac: float = 0.5,
              end_frac: float = 0.5
              ) -> tuple[list[tuple[float, float]], tuple[float, float],
                         tuple[float, float]]:
    """计算 ER 正交折线（贴着卡片边缘出发），返回绝对点和两端 fixedPoint。"""
    if src_el.get("id") == dst_el.get("id"):
        x, y, w, h = bbox(src_el)
        p0 = (x + w + gap, y + h * 0.35)
        p1 = (x + w + gap, y + h * 0.65)
        loop_x = x + w + gap + 52.0
        pts = [p0, (loop_x, p0[1]), (loop_x, p1[1]), p1]
        return pts, (1.0, 0.35), (1.0, 0.65)

    s_side, d_side = er_sides(src_el, dst_el)
    a0, f0 = _side_point(src_el, s_side, start_frac)
    a1, f1 = _side_point(dst_el, d_side, end_frac)
    p0 = _offset_side(a0, s_side, gap)
    p1 = _offset_side(a1, d_side, gap)

    if s_side in ("left", "right"):
        midx = (p0[0] + p1[0]) / 2.0
        if s_side == "right" and p0[0] >= p1[0] - 10.0:
            midx = max(p0[0], p1[0]) + 46.0
        elif s_side == "left" and p0[0] <= p1[0] + 10.0:
            midx = min(p0[0], p1[0]) - 46.0
        pts = [p0]
        if abs(p0[1] - p1[1]) > 0.5:
            pts.extend([(midx, p0[1]), (midx, p1[1])])
        pts.append(p1)
    else:
        midy = (p0[1] + p1[1]) / 2.0
        if s_side == "bottom" and p0[1] >= p1[1] - 10.0:
            midy = max(p0[1], p1[1]) + 46.0
        elif s_side == "top" and p0[1] <= p1[1] + 10.0:
            midy = min(p0[1], p1[1]) - 46.0
        pts = [p0]
        if abs(p0[0] - p1[0]) > 0.5:
            pts.extend([(p0[0], midy), (p1[0], midy)])
        pts.append(p1)
    return pts, f0, f1


def _orbit_fixed(el: dict, fixed: tuple[float, float]) -> dict:
    return {"elementId": el["id"], "mode": "orbit",
            "fixedPoint": [fixed[0], fixed[1]]}


def _er_arrowhead(card: Cardinality) -> str | None:
    if card.known and card.display and not card.many:
        return "bar"
    return None


def _crowfoot(env: elements.Env, base: tuple[float, float],
              u: tuple[float, float], *, stroke_color: str,
              stroke_width: float, roughness: int) -> list[dict]:
    """在端点画一个三叉鸦爪：三线在卡片边缘汇合，沿连线向外张开。"""
    perp = (-u[1], u[0])
    away = (-u[0], -u[1])
    length, spread = styles.CROWFOOT_LEN, styles.CROWFOOT_SPREAD
    tips = [
        (base[0] + away[0] * length + perp[0] * spread,
         base[1] + away[1] * length + perp[1] * spread),
        (base[0] + away[0] * length, base[1] + away[1] * length),
        (base[0] + away[0] * length - perp[0] * spread,
         base[1] + away[1] * length - perp[1] * spread),
    ]
    out = []
    for tip in tips:
        dx, dy = tip[0] - base[0], tip[1] - base[1]
        out.append(elements.line(
            env, base[0], base[1], [[0.0, 0.0], [dx, dy]],
            stroke_color=stroke_color, stroke_width=stroke_width,
            roughness=roughness))
    return out


@dataclass
class ErEdge:
    """一条 ER 关系的装配结果：箭头 + 装饰元素 + 关系标签所在线段。"""
    arrow: dict
    decorations: list[tuple[str, dict]]
    label_seg: tuple[tuple[float, float], tuple[float, float]]
    self_loop: bool = False
    label_anchor: tuple[float, float] | None = None


def er_edge(env: elements.Env, src_el: dict, dst_el: dict, *,
            start_card: Cardinality, end_card: Cardinality,
            stroke_color: str, stroke_width: float = 1,
            roughness: int = 0, font_family: int = 2,
            font_size: float = 14,
            muted_color: str = "#868e96",
            start_frac: float = 0.5, end_frac: float = 0.5) -> ErEdge:
    """生成 ER 关系：正交折线 + 两端基数（1 画竖杠、N 画鸦爪）+ 基数标签。"""
    pts, f0, f1 = er_route(src_el, dst_el,
                           start_frac=start_frac, end_frac=end_frac)
    p0 = pts[0]
    rel_points = [[0.0, 0.0]] + [[p[0] - p0[0], p[1] - p0[1]] for p in pts[1:]]
    arrow = elements.arrow(
        env, p0[0], p0[1], rel_points,
        start_binding=_orbit_fixed(src_el, f0),
        end_binding=_orbit_fixed(dst_el, f1),
        start_arrowhead=_er_arrowhead(start_card),
        end_arrowhead=_er_arrowhead(end_card),
        stroke_color=stroke_color, stroke_width=stroke_width,
        roughness=roughness, stroke_style="solid", elbowed=False)
    elements.bind_arrow(src_el, arrow["id"])
    elements.bind_arrow(dst_el, arrow["id"])

    decos: list[tuple[str, dict]] = []
    start_u = _unit(pts[1], pts[0])
    end_u = _unit(pts[-2], pts[-1])
    for side, base, u, card in (("start", pts[0], start_u, start_card),
                                ("end", pts[-1], end_u, end_card)):
        if card.many and (u != (0.0, 0.0)):
            for i, el in enumerate(_crowfoot(
                    env, base, u, stroke_color=stroke_color,
                    stroke_width=stroke_width, roughness=roughness)):
                decos.append((f"crow::{side}::{i}", el))
        if card.display:
            perp = (-u[1], u[0])
            lx = base[0] - u[0] * styles.CARD_LABEL_GAP \
                + perp[0] * styles.CARD_LABEL_PERP
            ly = base[1] - u[1] * styles.CARD_LABEL_GAP \
                + perp[1] * styles.CARD_LABEL_PERP
            tw, th = elements.estimate_text_size(card.display, font_size)
            t = elements.text(
                env, lx - tw / 2.0, ly - th / 2.0, card.display,
                width=tw, height=th, stroke_color=muted_color,
                font_family=font_family, font_size=font_size,
                text_align=styles.TEXT_ALIGN_CENTER,
                vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
            decos.append((f"card::{side}::text", t))

    if src_el.get("id") == dst_el.get("id"):
        # 自关联：关系动词放在回环外侧，避免压住回环竖线
        mid_y = (pts[0][1] + pts[-1][1]) / 2.0
        return ErEdge(arrow=arrow, decorations=decos,
                      label_seg=(pts[1], pts[2]), self_loop=True,
                      label_anchor=(pts[1][0] + 56.0, mid_y))

    if len(pts) >= 4:
        seg = (pts[1], pts[2])
    elif len(pts) == 3:
        seg = (pts[0], pts[-1])
    else:
        seg = (pts[0], pts[-1])
    return ErEdge(arrow=arrow, decorations=decos, label_seg=seg)
