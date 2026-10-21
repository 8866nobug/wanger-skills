"""Diagram IR → Excalidraw 原生 JSON 的装配器。

职责：把 models.Diagram 转成插件可直接打开的绘图对象
（{"type","version","source","elements","appState","files"}）。

主要能力：
- 树形流程布局（决策分支）、UML 类元素与关系、旁注独立区域、画布范围；
- 每个引擎生成元素写入 customData.semId，供 patch 按语义 ID 幂等定位；
- 传入 existing（已解析文档）时做「声明式对账」：复用相同 semId 的元素 id、
  删除已消失的引擎元素、保留手绘（无 semId）元素。
"""
from __future__ import annotations

import hashlib
import math
from typing import Any

from . import connectors, elements, layout, models, styles

_SHAPE_KINDS = ("process", "decision", "terminator", "uml_class", "entity")


def _is_shape(kind: str) -> bool:
    return kind in _SHAPE_KINDS


def _node_size(node: models.Node) -> tuple[float, float]:
    """节点的实际渲染尺寸（UML 类框 / ER 实体卡片随内容变化）。"""
    if node.kind == "uml_class":
        return uml_class_size(node.text)
    if node.kind == "entity":
        return entity_size(node)
    return layout.node_size(node.kind)


def _tag(el: dict, sem_id: str | None) -> dict:
    if sem_id:
        el["customData"] = {"semId": sem_id}
    return el


def _paint(node: models.Node, preset: dict) -> dict:
    """合并节点局部覆盖与样式预设，得到形状/线条的通用绘制参数。"""
    return {
        "stroke_color": node.style.get("strokeColor", preset["stroke"]),
        "fill_style": node.style.get("fillStyle", preset["fill_style"]),
        "stroke_width": node.style.get("strokeWidth", preset["stroke_width"]),
        "stroke_style": node.style.get("strokeStyle", preset["stroke_style"]),
        "roughness": node.style.get("roughness", preset["roughness"]),
    }


# --------------------------------------------------------------------------- #
# 形状与文本
# --------------------------------------------------------------------------- #

def _make_shape(env: elements.Env, node: models.Node, x: float, y: float,
                w: float, h: float, preset: dict) -> dict:
    colors = preset["colors"]
    bg = node.style.get("backgroundColor", colors.get(node.kind,
                                                      styles.BACKGROUND_TRANSPARENT))
    kw = _paint(node, preset)
    if node.kind == "decision":
        return elements.diamond(env, x, y, w, h, background=bg, **kw)
    if node.kind == "terminator":
        return elements.ellipse(env, x, y, w, h, background=bg, **kw)
    return elements.rectangle(env, x, y, w, h, background=bg,
                              roundness=node.style.get("roundness",
                                                       preset["roundness"]), **kw)


def _label_text(env: elements.Env, node: models.Node, shape: dict,
                preset: dict) -> dict:
    """为带标签的形状生成居中的绑定文本。"""
    cx = shape["x"] + shape["width"] / 2.0
    cy = shape["y"] + shape["height"] / 2.0
    tw, th = elements.estimate_text_size(node.text)
    t = elements.text(env, cx - tw / 2.0, cy - th / 2.0, node.text,
                      width=tw, height=th, container_id=shape["id"],
                      stroke_color=node.style.get("textColor", preset["text"]),
                      font_family=node.style.get("fontFamily", preset["font_family"]),
                      font_size=node.style.get("fontSize", preset["font_size"]),
                      text_align=styles.TEXT_ALIGN_CENTER,
                      vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
    elements.bind_text(shape, t["id"])
    return t


def _uml_parts(text: str) -> tuple[str, str, str]:
    parts = [p.strip() for p in text.split("---")]
    name = parts[0] if parts else ""
    attrs = parts[1] if len(parts) > 1 else ""
    methods = parts[2] if len(parts) > 2 else ""
    return name, attrs, methods


def uml_class_size(text: str) -> tuple[float, float]:
    name, attrs, methods = _uml_parts(text)
    nlines = (1 if name else 0) + len(attrs.splitlines()) + len(methods.splitlines())
    widest = max((elements.estimate_text_size(p)[0]
                  for p in (name, attrs, methods) if p), default=0.0)
    w = max(widest + 40.0, styles.NODE_W)
    h = max(nlines * styles.FONT_SIZE * styles.LINE_HEIGHT + 2 * 24 + 20.0,
            styles.NODE_H)
    return w, h


def _build_uml_class(env: elements.Env, node: models.Node, x: float, y: float,
                     w: float, h: float, preset: dict) -> tuple[list[dict], dict]:
    name, attrs, methods = _uml_parts(node.text)
    colors = preset["colors"]
    rect = elements.rectangle(
        env, x, y, w, h,
        background=node.style.get("backgroundColor", colors["uml_class"]),
        roundness=preset["roundness"], **_paint(node, preset))
    _tag(rect, node.sem_id)
    out = [rect]
    cy = y + 8.0

    text_kw = dict(
        stroke_color=node.style.get("textColor", preset["text"]),
        font_family=node.style.get("fontFamily", preset["font_family"]),
        font_size=node.style.get("fontSize", preset["font_size"]),
        auto_resize=True)

    if name:
        tw, th = elements.estimate_text_size(name)
        t = elements.text(env, x + w / 2.0 - tw / 2.0, cy, name, width=tw, height=th,
                          container_id=rect["id"], text_align=styles.TEXT_ALIGN_CENTER,
                          vertical_align=styles.V_ALIGN_TOP, **text_kw)
        elements.bind_text(rect, t["id"])
        _tag(t, node.sem_id and f"{node.sem_id}::name")
        out.append(t)
        cy += th + 8.0

    def _separator(cy: float, tag: str) -> float:
        sep = elements.line(env, x + 4.0, cy, [[0.0, 0.0], [w - 8.0, 0.0]],
                            stroke_color=node.style.get("strokeColor", preset["stroke"]),
                            stroke_width=preset["stroke_width"],
                            roughness=preset["roughness"])
        _tag(sep, node.sem_id and f"{node.sem_id}::{tag}")
        out.append(sep)
        return cy + 12.0

    if attrs or methods:
        cy = _separator(cy, "sep1")
    if attrs:
        tw, th = elements.estimate_text_size(attrs)
        t = elements.text(env, x + 12.0, cy, attrs, width=tw, height=th,
                          container_id=rect["id"], text_align=styles.TEXT_ALIGN_LEFT,
                          vertical_align=styles.V_ALIGN_TOP, **text_kw)
        elements.bind_text(rect, t["id"])
        _tag(t, node.sem_id and f"{node.sem_id}::attrs")
        out.append(t)
        cy += th + 8.0
    if methods:
        cy = _separator(cy, "sep2")
        tw, th = elements.estimate_text_size(methods)
        t = elements.text(env, x + 12.0, cy, methods, width=tw, height=th,
                          container_id=rect["id"], text_align=styles.TEXT_ALIGN_LEFT,
                          vertical_align=styles.V_ALIGN_TOP, **text_kw)
        elements.bind_text(rect, t["id"])
        _tag(t, node.sem_id and f"{node.sem_id}::methods")
        out.append(t)
    return out, rect


# --------------------------------------------------------------------------- #
# ER 实体卡片
# --------------------------------------------------------------------------- #

def _entity_fields(node: models.Node) -> list[dict]:
    out: list[dict] = []
    for f in node.fields or []:
        if isinstance(f, str):
            out.append({"name": f})
        elif isinstance(f, dict):
            out.append(dict(f))
    return out


def _field_badge(f: dict) -> str:
    pk, fk, uq = bool(f.get("pk")), bool(f.get("fk")), bool(f.get("unique"))
    if pk and fk:
        return "PK·FK"
    if pk:
        return "PK"
    if fk:
        return "FK"
    if uq:
        return "UQ"
    return ""


def _field_type(f: dict) -> str:
    typ = str(f.get("type") or "")
    default = f.get("default")
    if default not in (None, ""):
        typ = f"{typ} = {default}" if typ else f"= {default}"
    return typ


def _entity_badge_width(node: models.Node) -> float:
    fields = _entity_fields(node)
    if not any(_field_badge(f) for f in fields):
        return 0.0
    widest = max(elements.estimate_text_size(
        _field_badge(f), styles.ENTITY_FIELD_FONT_SIZE)[0] for f in fields)
    return max(styles.ENTITY_BADGE_W, widest) + 10.0


def entity_size(node: models.Node) -> tuple[float, float]:
    """实体卡片尺寸：由表名、字段名、类型列和徽标列共同决定。"""
    pad = styles.ENTITY_PAD
    fields = _entity_fields(node)
    title_w = elements.estimate_text_size(
        node.text or "", styles.ENTITY_HEADER_FONT_SIZE)[0]
    badge_w = _entity_badge_width(node)
    name_w = type_w = 0.0
    for f in fields:
        name_w = max(name_w, elements.estimate_text_size(
            str(f.get("name") or ""), styles.ENTITY_FIELD_FONT_SIZE)[0])
        type_w = max(type_w, elements.estimate_text_size(
            _field_type(f), styles.ENTITY_FIELD_FONT_SIZE)[0])
    gap = styles.ENTITY_TYPE_GAP if type_w else 0.0
    w = max(styles.ENTITY_MIN_W, title_w + 2 * pad,
            pad * 2 + badge_w + 8.0 + name_w + gap + type_w)
    h = (styles.ENTITY_HEADER_H + len(fields) * styles.ENTITY_ROW_H + pad
         if fields else styles.ENTITY_HEADER_H + 2 * pad)
    return w, h


def _entity_group_id(node: models.Node) -> str:
    key = node.sem_id or node.text or "entity"
    return "g" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:11]


def _group_element_id(node: models.Node) -> str:
    key = node.sem_id or node.text or "group"
    return "g" + hashlib.sha1(("group:" + key).encode("utf-8")).hexdigest()[:11]


def _validate_groups(nodes: list[models.Node]) -> list[models.Node]:
    """校验并返回 group 节点；成员必须是形状节点且不能重复归属。"""
    groups = [n for n in nodes if n.kind == "group"]
    if not groups:
        return groups
    shape_sems = {n.sem_id for n in nodes
                  if n.kind != "group" and n.sem_id and _is_shape(n.kind)}
    node_sems = {n.sem_id for n in nodes if n.kind != "group" and n.sem_id}
    seen: set[str] = set()
    owner: dict[str, str] = {}
    for g in groups:
        if not g.sem_id:
            raise ValueError("group 节点必须有 sem_id")
        if g.sem_id in seen or g.sem_id in node_sems:
            raise ValueError(f"sem_id 冲突: {g.sem_id!r}")
        seen.add(g.sem_id)
        if not g.members:
            raise ValueError(f"group {g.sem_id!r} 没有 members")
        for m in g.members:
            if m not in shape_sems:
                raise ValueError(
                    f"group {g.sem_id!r} 的成员 {m!r} 不是形状节点")
            if m in owner:
                raise ValueError(f"节点 {m!r} 同时属于多个 group")
            owner[m] = g.sem_id
    return groups


def _build_group_boxes(env: elements.Env, nodes: list[models.Node],
                       group_nodes: list[models.Node],
                       pos: dict[int, tuple[float, float]],
                       sem_to_index: dict[str, int], size_fn, preset: dict,
                       new_elements: list[dict]
                       ) -> list[tuple[models.Node, list[int], dict, dict, dict | None]]:
    """创建分组背景框 + 顶部色带 + 标题，返回对账/分组所需的元数据。"""
    info: list[tuple[models.Node, list[int], dict, dict, dict | None]] = []
    for g in group_nodes:
        member_idxs = []
        for m in g.members:
            mi = sem_to_index.get(m)
            if mi is None or not _is_shape(nodes[mi].kind):
                raise ValueError(
                    f"group {g.sem_id!r} 的成员 {m!r} 不是形状节点")
            member_idxs.append(mi)
        boxes = []
        for mi in member_idxs:
            x, y = pos[mi]
            w, h = size_fn(nodes[mi])
            boxes.append((x, y, w, h))
        min_x = min(b[0] for b in boxes)
        min_y = min(b[1] for b in boxes)
        max_x = max(b[0] + b[2] for b in boxes)
        max_y = max(b[1] + b[3] for b in boxes)
        block_w, block_h = max_x - min_x, max_y - min_y
        tw, th = elements.estimate_text_size(
            g.text or "", styles.GROUP_TITLE_FONT_SIZE)
        box_w = max(block_w + 2 * styles.GROUP_PAD,
                    tw + 2 * styles.GROUP_PAD, styles.GROUP_MIN_W)
        box_h = block_h + styles.GROUP_HEADER_H + styles.GROUP_PAD
        box_x = min_x - (box_w - block_w) / 2.0
        box_y = min_y - styles.GROUP_HEADER_H
        colors = preset["colors"]
        # 透明底 + 顶部色带：即使 patch 时背景框 index 落在成员之后，也不会盖住卡片
        rect = elements.rectangle(
            env, box_x, box_y, box_w, box_h,
            background=g.style.get("backgroundColor", "transparent"),
            stroke_color=g.style.get("strokeColor",
                                      colors.get("group_border", "#adb5bd")),
            stroke_width=g.style.get("strokeWidth", 1),
            stroke_style=g.style.get("strokeStyle", "dashed"),
            roughness=g.style.get("roughness", preset["roughness"]),
            fill_style="solid",
            roundness=g.style.get("roundness", {"type": 3}))
        _tag(rect, g.sem_id)
        new_elements.append(rect)
        header_fill = g.style.get(
            "headerColor", colors.get("group_fill", "#f8f9fa"))
        hdr = elements.rectangle(
            env, box_x + 1, box_y + 1, max(0.0, box_w - 2),
            max(0.0, styles.GROUP_HEADER_H - 1),
            background=header_fill, stroke_color=header_fill, stroke_width=1,
            fill_style="solid", roundness={"type": 3}, roughness=0)
        _tag(hdr, f"{g.sem_id}::hdr")
        new_elements.append(hdr)
        title_el = None
        if g.text:
            title_el = elements.text(
                env, box_x + styles.GROUP_PAD,
                box_y + (styles.GROUP_HEADER_H - th) / 2.0, g.text,
                width=tw, height=th,
                stroke_color=g.style.get(
                    "textColor", colors.get("group_title", preset["text"])),
                font_family=g.style.get("fontFamily", preset["font_family"]),
                font_size=styles.GROUP_TITLE_FONT_SIZE,
                text_align=styles.TEXT_ALIGN_LEFT,
                vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
            _tag(title_el, f"{g.sem_id}::title")
            new_elements.append(title_el)
        info.append((g, member_idxs, rect, hdr, title_el))
    return info


def _badge_color(f: dict, colors: dict, preset: dict) -> str:
    if f.get("pk"):
        return colors.get("entity_pk", preset["text"])
    if f.get("fk"):
        return colors.get("entity_fk", preset["text"])
    return colors.get("entity_muted", preset["text"])


def _build_entity(env: elements.Env, node: models.Node, x: float, y: float,
                  w: float, h: float, preset: dict) -> tuple[list[dict], dict]:
    """表卡片：圆角外框 + 表头色带 + 表名 + 字段行（PK/FK/UQ 徽标、类型右对齐）。"""
    colors = preset["colors"]
    pad = styles.ENTITY_PAD
    header_h = styles.ENTITY_HEADER_H
    row_h = styles.ENTITY_ROW_H
    field_fs = styles.ENTITY_FIELD_FONT_SIZE
    header_fs = styles.ENTITY_HEADER_FONT_SIZE

    card = elements.rectangle(
        env, x, y, w, h,
        background=node.style.get("backgroundColor",
                                   colors.get("entity", "#ffffff")),
        stroke_color=node.style.get(
            "strokeColor", colors.get("entity_border", preset["stroke"])),
        stroke_width=node.style.get("strokeWidth", 1),
        stroke_style=node.style.get("strokeStyle", preset["stroke_style"]),
        roughness=node.style.get("roughness", 0),
        fill_style="solid",
        roundness=node.style.get("roundness", {"type": 3}))
    _tag(card, node.sem_id)
    out = [card]

    header_bg = node.style.get("headerColor",
                               colors.get("entity_header", "#dbe4ff"))
    hdr = elements.rectangle(
        env, x + 1, y + 1, max(0.0, w - 2), max(0.0, header_h - 1),
        background=header_bg, stroke_color=header_bg, stroke_width=1,
        fill_style="solid", roundness={"type": 3}, roughness=0)
    _tag(hdr, node.sem_id and f"{node.sem_id}::hdr")
    out.append(hdr)

    title = node.text or ""
    if title:
        tw, th = elements.estimate_text_size(title, header_fs)
        t = elements.text(
            env, x + (w - tw) / 2.0, y + (header_h - th) / 2.0, title,
            width=tw, height=th, container_id=hdr["id"],
            stroke_color=node.style.get(
                "headerTextColor",
                colors.get("entity_header_text", preset["text"])),
            font_family=node.style.get("fontFamily", preset["font_family"]),
            font_size=header_fs, text_align=styles.TEXT_ALIGN_CENTER,
            vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
        elements.bind_text(hdr, t["id"])
        _tag(t, node.sem_id and f"{node.sem_id}::title")
        out.append(t)

    sep = elements.line(
        env, x + 1, y + header_h, [[0.0, 0.0], [max(0.0, w - 2), 0.0]],
        stroke_color=colors.get("entity_border", preset["stroke"]),
        stroke_width=1, roughness=0)
    _tag(sep, node.sem_id and f"{node.sem_id}::hsep")
    out.append(sep)

    badge_w = _entity_badge_width(node)
    row_y = y + header_h + pad / 2.0
    for i, f in enumerate(_entity_fields(node)):
        badge = _field_badge(f)
        name = str(f.get("name") or "")
        typ = _field_type(f)
        if badge:
            bw, bh = elements.estimate_text_size(badge, field_fs)
            bt = elements.text(
                env, x + pad + (badge_w - bw), row_y + (row_h - bh) / 2.0,
                badge, width=bw, height=bh,
                stroke_color=_badge_color(f, colors, preset),
                font_family=node.style.get("fontFamily", preset["font_family"]),
                font_size=field_fs, text_align=styles.TEXT_ALIGN_RIGHT,
                vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=False)
            _tag(bt, node.sem_id and f"{node.sem_id}::f{i}::badge")
            out.append(bt)
        if name:
            nw, nh = elements.estimate_text_size(name, field_fs)
            nt = elements.text(
                env, x + pad + badge_w + 8.0, row_y + (row_h - nh) / 2.0,
                name, width=nw, height=nh,
                stroke_color=node.style.get("textColor", preset["text"]),
                font_family=node.style.get("fontFamily", preset["font_family"]),
                font_size=field_fs, text_align=styles.TEXT_ALIGN_LEFT,
                vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=False)
            _tag(nt, node.sem_id and f"{node.sem_id}::f{i}::name")
            out.append(nt)
        if typ:
            tyw, tyh = elements.estimate_text_size(typ, field_fs)
            tt = elements.text(
                env, x + w - pad - tyw, row_y + (row_h - tyh) / 2.0, typ,
                width=tyw, height=tyh,
                stroke_color=colors.get("entity_muted", preset["text"]),
                font_family=node.style.get("fontFamily", preset["font_family"]),
                font_size=field_fs, text_align=styles.TEXT_ALIGN_RIGHT,
                vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=False)
            _tag(tt, node.sem_id and f"{node.sem_id}::f{i}::type")
            out.append(tt)
        row_y += row_h

    elements.group(out, _entity_group_id(node))
    return out, card


# --------------------------------------------------------------------------- #
# 连线
# --------------------------------------------------------------------------- #

_BINDABLE = ("rectangle", "diamond", "ellipse")


def _arrow_for_edge(env: elements.Env, edge: models.Edge,
                    src_el: dict, dst_el: dict, preset: dict) -> dict:
    """生成边的连线：两端都是形状时用 orbit 绑定（移动形状箭头跟随）。"""
    if edge.rel:
        start_ah, end_ah, stroke = styles.UML_REL_STYLE.get(
            edge.rel, (None, "arrow", "solid"))
    else:
        start_ah, end_ah, stroke = None, styles.END_ARROWHEAD, "solid"

    paint = {
        "stroke_color": preset["arrow_stroke"],
        "stroke_width": preset["stroke_width"],
        "stroke_style": stroke,
        "roughness": preset["roughness"],
    }

    if edge.arrow == "none" and not edge.rel:
        return connectors.line_between(env, src_el, dst_el, **paint)

    if (src_el.get("type") in _BINDABLE) and (dst_el.get("type") in _BINDABLE):
        return connectors.bound_arrow(env, src_el, dst_el,
                                      start_arrowhead=start_ah,
                                      end_arrowhead=end_ah, **paint)
    return connectors.straight_arrow(env, connectors.bbox(src_el),
                                     connectors.bbox(dst_el),
                                     start_arrowhead=start_ah,
                                     end_arrowhead=end_ah, **paint)


def _is_er_edge(edge: models.Edge, src_node: models.Node,
                dst_node: models.Node) -> bool:
    return bool(edge.cardinality or edge.rel == "er"
                or (src_node.kind == "entity" and dst_node.kind == "entity"))


def _label_top_left(mid: tuple[float, float], u: tuple[float, float],
                    lw: float, lh: float, gap: float = 14.0
                    ) -> tuple[float, float]:
    """把关系动词放到线段的一侧（竖直段放左右，水平段放上下）。"""
    perp = (-u[1], u[0])
    if abs(u[0]) < abs(u[1]):
        if perp[0] >= 0:
            return mid[0] + gap, mid[1] - lh / 2.0
        return mid[0] - gap - lw, mid[1] - lh / 2.0
    if perp[1] >= 0:
        return mid[0] - lw / 2.0, mid[1] + gap
    return mid[0] - lw / 2.0, mid[1] - gap - lh


def _place_edge_label(env: elements.Env, arrow: dict, text: str,
                      preset: dict, edge_tag: str,
                      obstacles: list[tuple[float, float, float, float]]
                      ) -> dict:
    """普通流程/UML 边标签：在线段中点附近搜索不压住节点和其他标签的位置。"""
    fs = preset.get("label_font_size", 16)
    lw, lh = elements.estimate_text_size(text, fs)
    pts = _absolute_points(arrow)
    if len(pts) >= 2:
        a, b = pts[0], pts[1]
    else:
        a = (arrow.get("x", 0.0), arrow.get("y", 0.0))
        b = (a[0] + arrow.get("width", 0.0), a[1] + arrow.get("height", 0.0))
    u = _unit_vec(a, b)
    perp = (-u[1], u[0])
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    perps = [10.0 + lh / 2.0, -10.0 - lh / 2.0,
             26.0 + lh / 2.0, -26.0 - lh / 2.0,
             44.0 + lh / 2.0, -44.0 - lh / 2.0]
    alongs = [0.0]
    for d in (0.12, 0.24, 0.36):
        if length > 1e-6:
            alongs.extend((length * d, -length * d))
    candidates = []
    for py in perps:
        for ax in alongs:
            score = abs(py) + abs(ax) * 0.5
            candidates.append((score, ax, py))
    candidates.sort(key=lambda c: c[0])

    chosen = None
    for _score, ax, py in candidates:
        cx = mid[0] + u[0] * ax + perp[0] * py
        cy = mid[1] + u[1] * ax + perp[1] * py
        box = (cx - lw / 2.0, cy - lh / 2.0, lw, lh)
        if not _chen_box_overlaps(box, obstacles, 6.0):
            chosen = (cx, cy)
            break
    if chosen is None:
        lx, ly = _label_top_left(mid, u, lw, lh)
        chosen = (lx + lw / 2.0, ly + lh / 2.0)
    cx, cy = chosen
    t = elements.text(
        env, cx - lw / 2.0, cy - lh / 2.0, text, width=lw, height=lh,
        stroke_color=preset["text"], font_family=preset["font_family"],
        font_size=fs, text_align=styles.TEXT_ALIGN_CENTER,
        vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
    _tag(t, f"{edge_tag}::text")
    obstacles.append((t["x"], t["y"], t["width"], t["height"]))
    return t


def _build_er_edge(env: elements.Env, edge: models.Edge, edge_tag: str,
                   src_el: dict, dst_el: dict, preset: dict,
                   start_frac: float = 0.5,
                   end_frac: float = 0.5) -> list[dict]:
    """ER 关系：正交折线 + 两端基数符号/标签 + 可选关系动词。"""
    left, right = connectors.parse_cardinality(edge.cardinality)
    colors = preset["colors"]
    res = connectors.er_edge(
        env, src_el, dst_el, start_card=left, end_card=right,
        stroke_color=preset["arrow_stroke"],
        stroke_width=preset.get("stroke_width", 1),
        roughness=preset.get("roughness", 0),
        font_family=preset["font_family"],
        font_size=preset.get("label_font_size", 14),
        muted_color=colors.get("entity_muted", preset["text"]),
        start_frac=start_frac, end_frac=end_frac)
    out = [res.arrow]
    _tag(res.arrow, edge_tag)
    res.arrow.setdefault("customData", {})["er"] = True
    for suffix, el in res.decorations:
        _tag(el, f"{edge_tag}::{suffix}")
        out.append(el)
    if edge.label:
        fs = preset.get("label_font_size", 14)
        lw, lh = elements.estimate_text_size(edge.label, fs)
        if res.self_loop and res.label_anchor:
            lx = res.label_anchor[0]
            ly = res.label_anchor[1] - lh / 2.0
        else:
            a, b = res.label_seg
            mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
            lx, ly = _label_top_left(mid, _unit_vec(a, b), lw, lh)
        t = elements.text(
            env, lx, ly, edge.label,
            width=lw, height=lh, stroke_color=preset["text"],
            font_family=preset["font_family"], font_size=fs,
            text_align=styles.TEXT_ALIGN_CENTER,
            vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
        _tag(t, f"{edge_tag}::text")
        out.append(t)
    return out


# --------------------------------------------------------------------------- #
# 声明式对账
# --------------------------------------------------------------------------- #

_VOLATILE_KEYS = ("id", "index", "created", "updated", "version", "versionNonce", "seed")


def _same_content(a: dict, b: dict) -> bool:
    """忽略易变字段（id/时间戳/版本/随机种子）后比较内容是否一致。"""
    strip = lambda d: {k: v for k, v in d.items() if k not in _VOLATILE_KEYS}
    return strip(a) == strip(b)


_STYLE_KEYS = {
    "arrow": ("strokeColor", "strokeWidth", "strokeStyle", "roughness", "opacity"),
    "text": ("strokeColor", "fontFamily", "fontSize", "textAlign"),
    "shape": ("strokeColor", "backgroundColor", "fillStyle", "strokeWidth",
              "strokeStyle", "roughness", "opacity", "roundness"),
}


def _reconcile(new_elements: list[dict], existing_elements: list[dict],
               preserve_geometry: bool = False,
               preserve_style: bool = False,
               style_locked_sems: set[str] | None = None,
               dynamic_size_sems: set[str] | None = None,
               dynamic_position_sems: set[str] | None = None) -> list[dict]:
    """用现有元素的 id/index/created 复用相同 semId 的新元素；
    保留无 semId 的手绘元素；删除已消失的引擎元素（有 semId 但不在新 spec）。
    内容未变化的元素连 version/updated 一并复用（幂等），变化元素 version 递增。

    preserve_geometry：保留现有元素的位置/尺寸（箭头连同 points/绑定），
    仅更新内容，避免 patch 抹掉用户手动拖动的布局。
    preserve_style：保留现有元素的颜色/字体/粗糙度等（不因重建而回到预设）；
        style_locked_sems 中的节点（spec 显式给了 style）除外。
    dynamic_position_sems：不保留几何的 semId 集合（Chen 模式自动生成的
        属性/关系/连线等，需要按实体新位置重算）。
    """
    dynamic_size_sems = dynamic_size_sems or set()
    dynamic_position_sems = dynamic_position_sems or set()
    style_locked_sems = style_locked_sems or set()
    sem_to_existing: dict[str, dict] = {}
    for e in existing_elements:
        sd = (e.get("customData") or {}).get("semId")
        if sd and sd not in sem_to_existing:
            sem_to_existing[sd] = e

    id_map: dict[str, str] = {}   # 新分配的临时 id -> 复用的现有 id
    matched: dict[str, dict] = {}  # semId -> 现有元素（用于变化检测）
    new_sem: set[str] = set()
    for e in new_elements:
        sd = (e.get("customData") or {}).get("semId")
        if not sd:
            continue
        new_sem.add(sd)
        ex = sem_to_existing.get(sd)
        if not ex:
            continue
        id_map[e["id"]] = ex["id"]
        e["id"] = ex["id"]
        e["index"] = ex.get("index", e["index"])
        e["created"] = ex.get("created", e["created"])
        e["seed"] = ex.get("seed", e["seed"])
        e["versionNonce"] = ex.get("versionNonce", e["versionNonce"])
        matched[sd] = ex

    # id 复用后，重映射元素间的引用（containerId / boundElements / 箭头绑定）
    for e in new_elements:
        cid = e.get("containerId")
        if cid and cid in id_map:
            e["containerId"] = id_map[cid]
        for b in e.get("boundElements") or []:
            if isinstance(b, dict) and b.get("id") in id_map:
                b["id"] = id_map[b["id"]]
        for key in ("startBinding", "endBinding"):
            bd = e.get(key)
            if isinstance(bd, dict) and bd.get("elementId") in id_map:
                bd["elementId"] = id_map[bd["elementId"]]

    # 保留现有几何（位置/尺寸/箭头走向与绑定）
    if preserve_geometry:
        for e in new_elements:
            sd = (e.get("customData") or {}).get("semId")
            ex = matched.get(sd)
            if not ex:
                continue
            if dynamic_position_sems and sd in dynamic_position_sems:
                continue
            for k in ("x", "y"):
                if k in ex:
                    e[k] = ex[k]
            if e.get("type") == "arrow":
                for k in ("points", "width", "height",
                          "startArrowhead", "endArrowhead", "elbowed"):
                    if k in ex:
                        e[k] = ex[k]
                # 旧版本生成的箭头没有绑定：保留新算出的 orbit 绑定（升级），
                # 已有绑定则原样保留（用户可能改过连接点）。
                for k in ("startBinding", "endBinding"):
                    if ex.get(k):
                        e[k] = ex[k]
            elif e.get("type") in ("rectangle", "diamond", "ellipse") \
                    and sd not in dynamic_size_sems:
                # 用户手动调整过的形状尺寸保留；UML 类框尺寸随内容变化
                for k in ("width", "height"):
                    if k in ex:
                        e[k] = ex[k]
            elif e.get("type") == "text" and ex.get("rawText") == e.get("rawText") \
                    and preserve_style:
                # 保留插件按实际字形算好的折行（text）与尺寸；换风格时按新字体重算
                for k in ("text", "width", "height", "fontSize", "fontFamily",
                          "textAlign", "verticalAlign"):
                    if k in ex:
                        e[k] = ex[k]

    # 保留现有样式（颜色/字体/粗糙度），避免 patch 把手改外观重置为预设
    if preserve_style:
        for e in new_elements:
            sd = (e.get("customData") or {}).get("semId")
            ex = matched.get(sd)
            if not ex or sd in style_locked_sems:
                continue
            if e.get("type") == "arrow":
                keys = _STYLE_KEYS["arrow"]
            elif e.get("type") == "text":
                keys = _STYLE_KEYS["text"]
            else:
                keys = _STYLE_KEYS["shape"]
            for k in keys:
                if k in ex:
                    e[k] = ex[k]

    if preserve_geometry:
        # 绑定一致化：按 fixedPoint 重算箭头端点，修正形状被移动后的陈旧坐标
        by_id = {e.get("id"): e for e in new_elements}
        for e in new_elements:
            if e.get("type") != "arrow" or len(e.get("points") or []) != 2:
                continue
            # ER 连线使用贴边 2px 的端点，不能按普通箭头的 6px 重新外扩
            if (e.get("customData") or {}).get("er"):
                continue
            sb, eb = e.get("startBinding"), e.get("endBinding")
            if not (isinstance(sb, dict) and isinstance(eb, dict)):
                continue
            s, d = by_id.get(sb.get("elementId")), by_id.get(eb.get("elementId"))
            if not (s and d):
                continue
            try:
                a0 = (s["x"] + sb["fixedPoint"][0] * s["width"],
                      s["y"] + sb["fixedPoint"][1] * s["height"])
                a1 = (d["x"] + eb["fixedPoint"][0] * d["width"],
                      d["y"] + eb["fixedPoint"][1] * d["height"])
            except (KeyError, TypeError, IndexError):
                continue
            p0n = connectors.extend_anchor(s, a0, a1)
            p1n = connectors.extend_anchor(d, a1, a0)
            p0 = (e["x"], e["y"])
            p1 = (e["x"] + e["points"][1][0], e["y"] + e["points"][1][1])
            eps = 0.5   # 亚像素差异（插件舍入）视为已一致，保持幂等
            if (abs(p0n[0] - p0[0]) <= eps and abs(p0n[1] - p0[1]) <= eps
                    and abs(p1n[0] - p1[0]) <= eps
                    and abs(p1n[1] - p1[1]) <= eps):
                continue
            e["x"], e["y"] = p0n
            e["points"] = [[0.0, 0.0], [p1n[0] - p0n[0], p1n[1] - p0n[1]]]
            e["width"] = abs(p1n[0] - p0n[0])
            e["height"] = abs(p1n[1] - p0n[1])

    # 内容未变化 → 复用 version/updated（彻底幂等）；变化 → version 递增
    for e in new_elements:
        sd = (e.get("customData") or {}).get("semId")
        ex = matched.get(sd)
        if not ex:
            continue
        if _same_content(e, ex):
            e["version"] = ex.get("version", e["version"])
            e["updated"] = ex.get("updated", e["updated"])
        else:
            e["version"] = ex.get("version", 0) + 1

    kept = [e for e in existing_elements if not (e.get("customData") or {}).get("semId")]
    return kept + new_elements


def _unit_vec(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    d = (dx * dx + dy * dy) ** 0.5
    return (dx / d, dy / d) if d else (0.0, 0.0)


def _absolute_points(arrow: dict) -> list[tuple[float, float]]:
    return [(arrow.get("x", 0.0) + p[0], arrow.get("y", 0.0) + p[1])
            for p in arrow.get("points") or []]


def _path_mid(points: list[tuple[float, float]]):
    if len(points) >= 4:
        a, b = points[1], points[2]
        return ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0), _unit_vec(a, b)
    if len(points) == 3:
        return points[1], _unit_vec(points[0], points[-1])
    return ((points[0][0] + points[-1][0]) / 2.0,
            (points[0][1] + points[-1][1]) / 2.0), _unit_vec(points[0], points[-1])


def _sync_entity_layout(els: list[dict], nodes: list[models.Node]) -> None:
    """把实体子元素重新对齐到卡片最终坐标（patch 保留卡片位置后仍能对齐）。"""
    by_sem = {sd: e for e in els
              if isinstance(e, dict) and (sd := (e.get("customData") or {}).get("semId"))}
    pad = styles.ENTITY_PAD
    header_h = styles.ENTITY_HEADER_H
    row_h = styles.ENTITY_ROW_H
    for node in nodes:
        if node.kind != "entity" or not node.sem_id:
            continue
        card = by_sem.get(node.sem_id)
        if not card:
            continue
        x, y = card.get("x", 0.0), card.get("y", 0.0)
        w, h = card.get("width", 0.0), card.get("height", 0.0)
        hdr = by_sem.get(f"{node.sem_id}::hdr")
        if hdr:
            hdr["x"], hdr["y"] = x + 1, y + 1
            hdr["width"], hdr["height"] = max(0.0, w - 2), max(0.0, header_h - 1)
        title = by_sem.get(f"{node.sem_id}::title")
        if title:
            title["x"] = x + (w - title.get("width", 0)) / 2.0
            title["y"] = y + (header_h - title.get("height", 0)) / 2.0
        sep = by_sem.get(f"{node.sem_id}::hsep")
        if sep:
            sep["x"], sep["y"] = x + 1, y + header_h
            sep["points"] = [[0.0, 0.0], [max(0.0, w - 2), 0.0]]
            sep["width"], sep["height"] = max(0.0, w - 2), 0.0
        badge_w = _entity_badge_width(node)
        row_y = y + header_h + pad / 2.0
        for i, _f in enumerate(_entity_fields(node)):
            badge = by_sem.get(f"{node.sem_id}::f{i}::badge")
            if badge:
                badge["x"] = x + pad + (badge_w - badge.get("width", 0))
                badge["y"] = row_y + (row_h - badge.get("height", 0)) / 2.0
            name = by_sem.get(f"{node.sem_id}::f{i}::name")
            if name:
                name["x"] = x + pad + badge_w + 8.0
                name["y"] = row_y + (row_h - name.get("height", 0)) / 2.0
            typ = by_sem.get(f"{node.sem_id}::f{i}::type")
            if typ:
                typ["x"] = x + w - pad - typ.get("width", 0)
                typ["y"] = row_y + (row_h - typ.get("height", 0)) / 2.0
            row_y += row_h


def _sync_group_boxes(els: list[dict], nodes: list[models.Node],
                      extra_sems: dict[str, list[str]] | None = None) -> None:
    """按成员卡片最终位置重新计算 group 背景框和标题位置。

    extra_sems 可把组内自动生成的元素（如 Chen 联系菱形）也计入组框范围，
    避免菱形伸出组框。
    """
    by_sem = {sd: e for e in els
              if isinstance(e, dict) and (sd := (e.get("customData") or {}).get("semId"))}
    for g in nodes:
        if g.kind != "group" or not g.sem_id:
            continue
        rect = by_sem.get(g.sem_id)
        if not rect:
            continue
        gid = _group_element_id(g)
        members = list(g.members or [])
        if extra_sems:
            members.extend(extra_sems.get(gid, []))
        cards = []
        for m in members:
            el = by_sem.get(m)
            if el and el.get("type") in ("rectangle", "diamond", "ellipse"):
                cards.append(el)
        if not cards:
            continue
        min_x = min(e["x"] for e in cards)
        min_y = min(e["y"] for e in cards)
        max_x = max(e["x"] + e.get("width", 0) for e in cards)
        max_y = max(e["y"] + e.get("height", 0) for e in cards)
        block_w, block_h = max_x - min_x, max_y - min_y
        tw, _th = elements.estimate_text_size(
            g.text or "", styles.GROUP_TITLE_FONT_SIZE)
        box_w = max(block_w + 2 * styles.GROUP_PAD,
                    tw + 2 * styles.GROUP_PAD, styles.GROUP_MIN_W)
        box_h = block_h + styles.GROUP_HEADER_H + styles.GROUP_PAD
        rect["x"] = min_x - (box_w - block_w) / 2.0
        rect["y"] = min_y - styles.GROUP_HEADER_H
        rect["width"], rect["height"] = box_w, box_h
        hdr = by_sem.get(f"{g.sem_id}::hdr")
        if hdr:
            hdr["x"], hdr["y"] = rect["x"] + 1, rect["y"] + 1
            hdr["width"] = max(0.0, box_w - 2)
            hdr["height"] = max(0.0, styles.GROUP_HEADER_H - 1)
        title = by_sem.get(f"{g.sem_id}::title")
        if title:
            title["x"] = rect["x"] + styles.GROUP_PAD
            title["y"] = rect["y"] + (styles.GROUP_HEADER_H
                                      - title.get("height", 0)) / 2.0


def _sync_decor_side(decos: dict[str, dict], side: str,
                     base: tuple[float, float], u: tuple[float, float]) -> None:
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
    for i, tip in enumerate(tips):
        el = decos.get(f"crow::{side}::{i}")
        if not el:
            continue
        dx, dy = tip[0] - base[0], tip[1] - base[1]
        el["x"], el["y"] = base
        el["points"] = [[0.0, 0.0], [dx, dy]]
        el["width"], el["height"] = abs(dx), abs(dy)
    lab = decos.get(f"card::{side}::text")
    if lab:
        lx = base[0] - u[0] * styles.CARD_LABEL_GAP \
            + perp[0] * styles.CARD_LABEL_PERP
        ly = base[1] - u[1] * styles.CARD_LABEL_GAP \
            + perp[1] * styles.CARD_LABEL_PERP
        lab["x"] = lx - lab.get("width", 0) / 2.0
        lab["y"] = ly - lab.get("height", 0) / 2.0


def _sync_edge_decor(els: list[dict]) -> None:
    """按箭头最终几何重新放置鸦爪、基数标签和关系动词（拖动/回写后保持一致）。"""
    by_sem = {sd: e for e in els
              if isinstance(e, dict) and (sd := (e.get("customData") or {}).get("semId"))}
    for sem, arrow in by_sem.items():
        if arrow.get("type") != "arrow":
            continue
        if not (arrow.get("customData") or {}).get("er"):
            continue
        pts = _absolute_points(arrow)
        if len(pts) < 2:
            continue
        prefix = sem + "::"
        decos = {s[len(prefix):]: e for s, e in by_sem.items()
                 if s.startswith(prefix)}
        _sync_decor_side(decos, "start", pts[0], _unit_vec(pts[1], pts[0]))
        _sync_decor_side(decos, "end", pts[-1], _unit_vec(pts[-2], pts[-1]))
        lab = decos.get("text")
        if lab:
            lw, lh = lab.get("width", 0), lab.get("height", 0)
            sb = arrow.get("startBinding") or {}
            eb = arrow.get("endBinding") or {}
            if sb.get("elementId") and sb.get("elementId") == eb.get("elementId"):
                lx = pts[1][0] + 56.0
                ly = (pts[0][1] + pts[-1][1]) / 2.0 - lh / 2.0
            else:
                mid, u = _path_mid(pts)
                lx, ly = _label_top_left(mid, u, lw, lh)
            lab["x"], lab["y"] = lx, ly


def _sync_title(els: list[dict]) -> None:
    """把图标题重新居中放到主图上方（patch 保留卡片位置后仍然对齐）。"""
    title = next((e for e in els
                  if (e.get("customData") or {}).get("semId") == styles.TITLE_SEM_ID),
                 None)
    if not title:
        return
    shapes = [e for e in els
              if e.get("type") in ("rectangle", "diamond", "ellipse")
              and (e.get("customData") or {}).get("semId")]
    if not shapes:
        return
    min_x = min(e["x"] for e in shapes)
    max_x = max(e["x"] + e.get("width", 0) for e in shapes)
    min_y = min(e["y"] for e in shapes)
    tw, th = title.get("width", 0), title.get("height", 0)
    title["x"] = min_x + (max_x - min_x - tw) / 2.0
    title["y"] = min_y - th - styles.TITLE_GAP


def _resize_er_arrows(els: list[dict], changed_ids: set[str]) -> None:
    """实体卡片尺寸变化时，重路由绑定到它的 ER 连线（避免端点脱开）。"""
    if not changed_ids:
        return
    by_id = {e.get("id"): e for e in els
             if e.get("type") in ("rectangle", "ellipse", "diamond")}
    for e in els:
        if e.get("type") != "arrow" or not (e.get("customData") or {}).get("er"):
            continue
        sb = e.get("startBinding") or {}
        eb = e.get("endBinding") or {}
        if (sb.get("elementId") not in changed_ids
                and eb.get("elementId") not in changed_ids):
            continue
        src = by_id.get(sb.get("elementId"))
        dst = by_id.get(eb.get("elementId"))
        if not src or not dst:
            continue
        f0 = sb.get("fixedPoint") or [0.5, 0.5]
        f1 = eb.get("fixedPoint") or [0.5, 0.5]
        s_side, d_side = connectors.er_sides(src, dst)
        sf = f0[1] if s_side in ("left", "right") else f0[0]
        ef = f1[1] if d_side in ("left", "right") else f1[0]
        pts, nf0, nf1 = connectors.er_route(
            src, dst, start_frac=sf, end_frac=ef)
        p0 = pts[0]
        e["x"], e["y"] = p0
        e["points"] = [[0.0, 0.0]] + [[p[0] - p0[0], p[1] - p0[1]]
                                      for p in pts[1:]]
        xs = [p[0] for p in e["points"]]
        ys = [p[1] for p in e["points"]]
        e["width"], e["height"] = max(xs) - min(xs), max(ys) - min(ys)
        e["startBinding"] = {"elementId": src["id"], "mode": "orbit",
                             "fixedPoint": [nf0[0], nf0[1]]}
        e["endBinding"] = {"elementId": dst["id"], "mode": "orbit",
                           "fixedPoint": [nf1[0], nf1[1]]}


def _refresh_versions(new_elements: list[dict],
                      existing_elements: list[dict]) -> None:
    """几何/装饰同步之后重新判定幂等版本（避免同步改动未升 version）。"""
    ex_by_sem: dict[str, dict] = {}
    for e in existing_elements:
        sd = (e.get("customData") or {}).get("semId")
        if sd and sd not in ex_by_sem:
            ex_by_sem[sd] = e
    for e in new_elements:
        sd = (e.get("customData") or {}).get("semId")
        ex = ex_by_sem.get(sd)
        if not ex:
            continue
        if _same_content(e, ex):
            e["version"] = ex.get("version", e["version"])
            e["updated"] = ex.get("updated", e["updated"])
        else:
            e["version"] = ex.get("version", 0) + 1


# --------------------------------------------------------------------------- #
# 主装配
# --------------------------------------------------------------------------- #

def build_diagram(diagram: models.Diagram,
                  positions: list[tuple[float, float]] | None = None,
                  existing: models.Document | None = None,
                  preserve_geometry: bool = False,
                  style: str | None = None,
                  preserve_style: bool | None = None) -> dict[str, Any]:
    """把 Diagram IR 装配成 Excalidraw 原生绘图对象。

    positions：每个节点左上角坐标（缺省时用树形流程布局 + 旁注右列）。
    existing：已解析文档；提供时做声明式对账（复用 id、删除消失的引擎元素）。
    preserve_geometry：对账时保留现有元素的位置/尺寸/箭头走向（不再重算布局）；
        新增节点放在现有内容右侧。
    style：样式预设名（clean/hand/mono/night 及别名）；缺省取 diagram.style，
        再缺省用 clean。
    preserve_style：对账时保留现有元素的颜色/字体/粗糙度等样式；
        缺省与 preserve_geometry 一致（不显式指定样式就不改动已有外观）。
    """
    if (diagram.notation or "").strip().lower() == "chen":
        return build_chen_diagram(
            diagram, positions=positions, existing=existing,
            preserve_geometry=preserve_geometry, style=style,
            preserve_style=preserve_style)

    style_name = style or diagram.style or styles.DEFAULT_STYLE
    preset = styles.get_preset(style_name)
    if preserve_style is None:
        preserve_style = preserve_geometry
    style_locked = {n.sem_id for n in diagram.nodes if n.sem_id and n.style}

    nodes = diagram.nodes
    group_nodes = _validate_groups(nodes)
    group_sems = {g.sem_id for g in group_nodes}
    edge_tags = {e.sem_id or f"{e.src}>{e.dst}" for e in diagram.edges}
    for e in diagram.edges:
        if e.src in group_sems or e.dst in group_sems:
            raise ValueError(f"边 {e.src}>{e.dst} 不能连接到 group")
    for g in group_nodes:
        if g.sem_id in edge_tags:
            raise ValueError(f"group sem_id 与边 sem_id 冲突: {g.sem_id!r}")
    shape_idx = [i for i, n in enumerate(nodes) if _is_shape(n.kind)]
    ann_idx = [i for i, n in enumerate(nodes)
               if not _is_shape(n.kind) and n.kind != "group"]
    shape_nodes = [nodes[i] for i in shape_idx]

    # 位置
    if positions is None:
        if group_nodes:
            shape_pos = layout.grouped_layout(
                shape_nodes, diagram.edges, group_nodes, size_fn=_node_size,
                title_size_fn=lambda t: elements.estimate_text_size(
                    t, styles.GROUP_TITLE_FONT_SIZE))
        elif any(n.kind == "entity" for n in shape_nodes):
            shape_pos = layout.er_layout(shape_nodes, diagram.edges,
                                         size_fn=_node_size)
        elif diagram.edges:
            shape_pos = layout.flow(shape_nodes, diagram.edges, size_fn=_node_size)
        else:
            shape_pos = layout.vertical_flow(shape_nodes, size_fn=_node_size)
    else:
        shape_pos = [positions[i] for i in shape_idx]

    pos: dict[int, tuple[float, float]] = {}
    for k, i in enumerate(shape_idx):
        pos[i] = shape_pos[k]

    if ann_idx:
        min_x, min_y, max_x, max_y = layout.bounds(shape_pos, shape_nodes,
                                                   size_fn=_node_size)
        # ER 图右侧可能有自关联回环，旁注列留出更大间距
        ann_gap = (styles.ER_COMPONENT_GAP
                   if any(n.kind == "entity" for n in shape_nodes)
                   else styles.NOTE_GAP)
        ann_x = max_x + ann_gap
        ann_y = min_y
        for i in ann_idx:
            _, th = elements.estimate_text_size(nodes[i].text)
            pos[i] = (ann_x, ann_y)
            ann_y += th + styles.VGAP

    # 保留几何：已存在节点沿用原坐标；新增节点放到现有内容右侧
    sem_to_existing_el: dict[str, dict] = {}
    if preserve_geometry and existing is not None:
        for e in existing.elements:
            sd = (e.get("customData") or {}).get("semId")
            if sd and e.get("type") != "arrow" and not e.get("isDeleted"):
                sem_to_existing_el.setdefault(sd, e)

        for i, node in enumerate(nodes):
            ex = sem_to_existing_el.get(node.sem_id) if node.sem_id else None
            if ex and isinstance(ex.get("x"), (int, float)):
                pos[i] = (ex["x"], ex["y"])

        new_idx = [i for i, n in enumerate(nodes)
                   if n.kind != "group"
                   and not (n.sem_id and n.sem_id in sem_to_existing_el)]
        if new_idx:
            drawn = [e for e in existing.elements
                     if not e.get("isDeleted") and isinstance(e.get("x"), (int, float))]
            if drawn:
                right_x = max(e["x"] + e.get("width", 0) for e in drawn) + styles.HGAP
                top_y = min(e["y"] for e in drawn)
            else:
                right_x, top_y = 0.0, 0.0
            y = top_y
            max_new_w = 0.0
            for i in new_idx:
                node = nodes[i]
                w, h = _node_size(node) if _is_shape(node.kind) \
                    else elements.estimate_text_size(node.text)
                pos[i] = (right_x, y)
                max_new_w = max(max_new_w, w)
                y += h + styles.VGAP
            # 新增旁注列放在新增形状列右侧
            ann_new = [i for i in new_idx if not _is_shape(nodes[i].kind)]
            if ann_new and any(_is_shape(nodes[i].kind) for i in new_idx):
                y = top_y
                for i in ann_new:
                    _, th = elements.estimate_text_size(nodes[i].text)
                    pos[i] = (right_x + max_new_w + styles.NOTE_GAP, y)
                    y += th + styles.VGAP

    # 环境：若对账，则以现有元素的最大 index / 全部 id 为种子，避免冲突
    existing_elements = existing.elements if existing is not None else None
    existing_ids = None
    last_index = None
    if existing_elements is not None:
        existing_ids = {e.get("id") for e in existing_elements if e.get("id")}
        last_index = max((e.get("index") for e in existing_elements if e.get("index")),
                         default=None)
    env = elements.Env(existing_ids=existing_ids, last_index=last_index)

    new_elements: list[dict] = []
    sem_to_index: dict[str, int] = {n.sem_id: i for i, n in enumerate(nodes)
                                    if n.sem_id}
    node_els: dict[int, dict] = {}
    node_elements_by_idx: dict[int, list[dict]] = {}

    # 分组背景框先创建，保证绘制在成员卡片下方
    group_box_info = _build_group_boxes(
        env, nodes, group_nodes, pos, sem_to_index, _node_size, preset,
        new_elements)

    for i, node in enumerate(nodes):
        if node.kind == "group":
            continue
        x, y = pos[i]
        if not _is_shape(node.kind):
            tw, th = elements.estimate_text_size(node.text)
            fam = preset["note_font_family"] if node.kind == "note" \
                else preset["font_family"]
            t = elements.text(env, x, y, node.text, width=tw, height=th,
                              stroke_color=node.style.get("textColor", preset["text"]),
                              font_family=node.style.get("fontFamily", fam),
                              font_size=node.style.get("fontSize", preset["font_size"]),
                              auto_resize=True)
            _tag(t, node.sem_id)
            new_elements.append(t)
            node_els[i] = t
            node_elements_by_idx[i] = [t]
            continue

        if node.kind == "uml_class":
            w, h = uml_class_size(node.text)
            els, box = _build_uml_class(env, node, x, y, w, h, preset)
            new_elements.extend(els)
        elif node.kind == "entity":
            w, h = entity_size(node)
            els, box = _build_entity(env, node, x, y, w, h, preset)
            new_elements.extend(els)
        else:
            w, h = layout.node_size(node.kind)
            shape = _make_shape(env, node, x, y, w, h, preset)
            _tag(shape, node.sem_id)
            new_elements.append(shape)
            els = [shape]
            if node.text:
                t = _label_text(env, node, shape, preset)
                _tag(t, node.sem_id and f"{node.sem_id}::text")
                new_elements.append(t)
                els.append(t)
            box = shape
        node_els[i] = box
        node_elements_by_idx[i] = els

    # 把 group 背景框、顶部色带、标题与全部成员元素放进同一个 Excalidraw 外层 group
    for g, member_idxs, rect, hdr, title_el in group_box_info:
        gid = _group_element_id(g)
        member_els = []
        for mi in member_idxs:
            member_els.extend(node_elements_by_idx.get(mi, []))
        elements.group(member_els + [rect, hdr]
                       + ([title_el] if title_el else []), gid)

    # 连线标签避让：节点、旁注、组标题和已放标签
    label_obstacles: list[tuple[float, float, float, float]] = []
    for box in node_els.values():
        if isinstance(box.get("x"), (int, float)):
            label_obstacles.append(
                (box["x"], box["y"], box.get("width", 0.0),
                 box.get("height", 0.0)))
    for _g, _mi, _rect, _hdr, title_el in group_box_info:
        if title_el:
            label_obstacles.append(
                (title_el["x"], title_el["y"],
                 title_el["width"], title_el["height"]))

    # 连线
    def _index_for(ref: str) -> int:
        if ref in sem_to_index:
            return sem_to_index[ref]
        if ref.isdigit() and int(ref) in node_els:
            return int(ref)
        raise KeyError(f"无法定位边端点: {ref}")

    def _el_for(ref: str) -> dict:
        return node_els[_index_for(ref)]

    def _node_for(ref: str) -> models.Node:
        return nodes[_index_for(ref)]

    # 同一张表同一侧可能接多条关系：按对端位置排序，把连接点分散到侧边上
    side_fracs: dict[tuple[int, str], float] = {}
    side_groups: dict[tuple[str, str], list[tuple[int, str, float]]] = {}
    for ei, edge in enumerate(diagram.edges):
        try:
            se, de = _el_for(edge.src), _el_for(edge.dst)
            sn, dn = _node_for(edge.src), _node_for(edge.dst)
        except KeyError:
            continue
        if not _is_er_edge(edge, sn, dn) or se.get("id") == de.get("id"):
            continue
        s_side, d_side = connectors.er_sides(se, de)
        sb, db = connectors.bbox(se), connectors.bbox(de)
        s_other = (db[1] + db[3] / 2.0 if s_side in ("left", "right")
                   else db[0] + db[2] / 2.0)
        d_other = (sb[1] + sb[3] / 2.0 if d_side in ("left", "right")
                   else sb[0] + sb[2] / 2.0)
        side_groups.setdefault((se["id"], s_side), []).append(
            (ei, "start", s_other))
        side_groups.setdefault((de["id"], d_side), []).append(
            (ei, "end", d_other))
    for items in side_groups.values():
        items.sort(key=lambda t: (t[2], t[0]))
        k = len(items)
        if k == 1:
            side_fracs[(items[0][0], items[0][1])] = 0.5
            continue
        step = min(0.16, 0.5 / k)
        for j, (ei, which, _o) in enumerate(items):
            side_fracs[(ei, which)] = 0.5 + (j - (k - 1) / 2.0) * step

    for ei, edge in enumerate(diagram.edges):
        src_el, dst_el = _el_for(edge.src), _el_for(edge.dst)
        edge_tag = edge.sem_id or f"{edge.src}>{edge.dst}"
        if _is_er_edge(edge, _node_for(edge.src), _node_for(edge.dst)):
            new_elements.extend(
                _build_er_edge(
                    env, edge, edge_tag, src_el, dst_el, preset,
                    start_frac=side_fracs.get((ei, "start"), 0.5),
                    end_frac=side_fracs.get((ei, "end"), 0.5)))
            continue

        a = _arrow_for_edge(env, edge, src_el, dst_el, preset)
        _tag(a, edge_tag)
        new_elements.append(a)
        if edge.label:
            t = _place_edge_label(env, a, edge.label, preset, edge_tag,
                                  label_obstacles)
            elements.bind_text(a, t["id"])
            new_elements.append(t)

    # 图标题：居中放在主图上方（中文标题按约定由 spec 提供）
    if diagram.title:
        boxes = [b for b in node_els.values()
                 if b.get("type") in ("rectangle", "diamond", "ellipse")]
        boxes.extend(info[2] for info in group_box_info)
        if boxes:
            min_x = min(b["x"] for b in boxes)
            max_x = max(b["x"] + b.get("width", 0) for b in boxes)
            min_y = min(b["y"] for b in boxes)
        else:
            min_x = max_x = min_y = 0.0
        tw, th = elements.estimate_text_size(
            diagram.title, styles.TITLE_FONT_SIZE)
        t = elements.text(
            env, min_x + (max_x - min_x - tw) / 2.0,
            min_y - th - styles.TITLE_GAP, diagram.title,
            width=tw, height=th, stroke_color=preset["text"],
            font_family=preset["font_family"],
            font_size=styles.TITLE_FONT_SIZE,
            text_align=styles.TEXT_ALIGN_CENTER,
            vertical_align=styles.V_ALIGN_TOP, auto_resize=True)
        _tag(t, styles.TITLE_SEM_ID)
        new_elements.append(t)

    old_card_sizes: dict[str, tuple[float, float]] = {}
    if existing_elements is not None:
        for e in existing_elements:
            sd = (e.get("customData") or {}).get("semId")
            if sd and e.get("type") == "rectangle":
                old_card_sizes.setdefault(
                    sd, (e.get("width", 0.0), e.get("height", 0.0)))
        dynamic = {n.sem_id for n in nodes
                   if n.kind in ("uml_class", "entity", "group") and n.sem_id}
        new_elements = _reconcile(new_elements, existing_elements,
                                  preserve_geometry=preserve_geometry,
                                  preserve_style=preserve_style,
                                  style_locked_sems=style_locked,
                                  dynamic_size_sems=dynamic)

    # 对齐实体子元素、图标题与 ER 关系装饰到最终几何
    _sync_entity_layout(new_elements, nodes)
    _sync_group_boxes(new_elements, nodes)
    _sync_title(new_elements)
    if existing_elements is not None and preserve_geometry:
        by_sem_new = {(e.get("customData") or {}).get("semId"): e
                      for e in new_elements
                      if (e.get("customData") or {}).get("semId")}
        changed_ids: set[str] = set()
        for node in nodes:
            if node.kind != "entity" or not node.sem_id:
                continue
            card = by_sem_new.get(node.sem_id)
            old = old_card_sizes.get(node.sem_id)
            if card and old and (
                    abs(card.get("width", 0) - old[0]) > 0.5
                    or abs(card.get("height", 0) - old[1]) > 0.5):
                changed_ids.add(card["id"])
        _resize_er_arrows(new_elements, changed_ids)
    _sync_edge_decor(new_elements)
    if existing_elements is not None:
        _refresh_versions(new_elements, existing_elements)

    # 按分数索引排序，保持与插件保存时一致的数组顺序（含保留的手绘元素）
    new_elements.sort(key=lambda e: e.get("index") or "")

    if existing is not None:
        # 修改现有文件：保留 appState（滚动/缩放/主题/画笔状态），避免视图被重置
        app_state = dict(existing.app_state)
    else:
        app_state = dict(styles.DEFAULT_APP_STATE)
        app_state["theme"] = diagram.canvas.theme or preset["theme"]
        app_state["viewBackgroundColor"] = (diagram.canvas.background
                                            or preset["background"])
        app_state["currentItemStrokeColor"] = preset["stroke"]
        app_state["currentItemFontFamily"] = preset["font_family"]

    return {
        "type": "excalidraw",
        "version": 2,
        "source": diagram.meta.get("source", styles.DEFAULT_SOURCE),
        "elements": new_elements,
        "appState": app_state,
        "files": dict(existing.files) if existing is not None else {},
    }


# --------------------------------------------------------------------------- #
# Chen 记法（矩形实体 / 菱形关系 / 椭圆属性）
# --------------------------------------------------------------------------- #

def _chen_entity_name(node: models.Node) -> str:
    """概念图实体显示名：优先 label（中文业务名），否则回退 text。"""
    return (node.label or node.text or "").strip()


def _contains_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in (text or ""))


def _chen_entity_rect_size(node: models.Node) -> tuple[float, float]:
    tw, th = elements.estimate_text_size(
        _chen_entity_name(node), styles.CHEN_ENTITY_FONT_SIZE)
    return (max(styles.CHEN_ENTITY_MIN_W, tw + 2 * styles.CHEN_ENTITY_PAD),
            max(styles.CHEN_ENTITY_H, th + 2 * styles.CHEN_ENTITY_PAD))


def _chen_cluster_size(node: models.Node) -> tuple[float, float]:
    return _chen_entity_rect_size(node)


def _chen_cluster_id(node: models.Node) -> str:
    key = node.sem_id or node.text or "chen"
    return "g" + hashlib.sha1(("chen:" + key).encode("utf-8")).hexdigest()[:11]


def _chen_label(env: elements.Env, shape: dict, text: str, font_size: float,
                color: str, font_family: int) -> dict:
    tw, th = elements.estimate_text_size(text, font_size)
    cx = shape["x"] + shape["width"] / 2.0
    cy = shape["y"] + shape["height"] / 2.0
    t = elements.text(
        env, cx - tw / 2.0, cy - th / 2.0, text, width=tw, height=th,
        container_id=shape["id"], stroke_color=color,
        font_family=font_family, font_size=font_size,
        text_align=styles.TEXT_ALIGN_CENTER,
        vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
    elements.bind_text(shape, t["id"])
    return t


def _chen_relation_size(text: str) -> tuple[float, float]:
    tw, th = elements.estimate_text_size(text, styles.CHEN_REL_FONT_SIZE)
    return (max(styles.CHEN_REL_MIN_W, tw + 70),
            max(styles.CHEN_REL_MIN_H, th + 60))


def _chen_support_to_edge(size: tuple[float, float],
                          u: tuple[float, float]) -> float:
    """包围盒/菱形沿方向 u 的半投影长度（菱形与 AABB 投影结果相同）。"""
    return size[0] / 2.0 * abs(u[0]) + size[1] / 2.0 * abs(u[1])


def _chen_exit_dist(size: tuple[float, float],
                    u: tuple[float, float]) -> float:
    """从中心沿 u 方向走到包围盒边界的距离。"""
    wx, wy = size[0] / 2.0, size[1] / 2.0
    tx = wx / abs(u[0]) if abs(u[0]) > 1e-9 else float("inf")
    ty = wy / abs(u[1]) if abs(u[1]) > 1e-9 else float("inf")
    return min(tx, ty)


def _chen_relation_center(a_center: tuple[float, float],
                          b_center: tuple[float, float],
                          a_size: tuple[float, float],
                          b_size: tuple[float, float],
                          offset: float,
                          rel_size: tuple[float, float] | None = None):
    dx, dy = b_center[0] - a_center[0], b_center[1] - a_center[1]
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return None
    u = (dx / dist, dy / dist)

    t0 = _chen_exit_dist(a_size, u)
    t1 = dist - _chen_exit_dist(b_size, u)
    # 菱形自身也要落在两实体之间的空隙里，不能只按中心连线取中点
    if rel_size is not None:
        support = _chen_support_to_edge(rel_size, u)
        t0 += support
        t1 -= support
    mid = (t0 + t1) / 2.0 if t1 >= t0 else dist / 2.0
    perp = (-u[1], u[0])
    return (a_center[0] + u[0] * mid + perp[0] * offset,
            a_center[1] + u[1] * mid + perp[1] * offset)


def _chen_box_overlaps(box: tuple[float, float, float, float],
                       obstacles: list[tuple[float, float, float, float]],
                       pad: float = 0.0) -> bool:
    x, y, w, h = box
    for ox, oy, ow, oh in obstacles:
        if (x < ox + ow + pad and ox < x + w + pad
                and y < oy + oh + pad and oy < y + h + pad):
            return True
    return False


def _chen_center_free(center: tuple[float, float],
                      size: tuple[float, float],
                      obstacles: list[tuple[float, float, float, float]],
                      pad: float) -> bool:
    return not _chen_box_overlaps(
        (center[0] - size[0] / 2.0, center[1] - size[1] / 2.0,
         size[0], size[1]), obstacles, pad)


def _segment_hits_box(p: tuple[float, float], q: tuple[float, float],
                      box: tuple[float, float, float, float]) -> bool:
    """线段是否与轴对齐矩形相交（Liang–Barsky 裁剪）。"""
    x, y, w, h = box
    xmin, ymin, xmax, ymax = x, y, x + w, y + h
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - xmin), (dx, xmax - p[0]),
                   (-dy, p[1] - ymin), (dy, ymax - p[1])):
        if abs(pk) < 1e-12:
            if qk < 0:
                return False
        else:
            t = qk / pk
            if pk < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def _chen_find_free_center(preferred: tuple[float, float],
                           size: tuple[float, float],
                           obstacles: list[tuple[float, float, float, float]],
                           u: tuple[float, float],
                           pad: float = styles.CHEN_REL_CLEARANCE,
                           segments_clear=None
                           ) -> tuple[float, float]:
    """在 preferred 附近按 u/perp 方向搜索不与障碍物重叠的菱形中心。

    segments_clear(center) 可额外要求中心到两端实体的连线不穿过其他实体。
    """
    def ok(cand):
        return (_chen_center_free(cand, size, obstacles, pad)
                and (segments_clear is None or segments_clear(cand)))

    if ok(preferred):
        return preferred
    perp = (-u[1], u[0])
    step = styles.CHEN_SEARCH_STEP
    for ring in range(1, styles.CHEN_SEARCH_RINGS + 1):
        coords = []
        for i in range(-ring, ring + 1):
            coords.append((i, -ring))
            coords.append((i, ring))
        for j in range(-ring + 1, ring):
            coords.append((-ring, j))
            coords.append((ring, j))
        coords.sort(key=lambda c: (abs(c[0]) + abs(c[1]), c[0], c[1]))
        for ax, ay in coords:
            cand = (preferred[0] + u[0] * ax * step + perp[0] * ay * step,
                    preferred[1] + u[1] * ax * step + perp[1] * ay * step)
            if ok(cand):
                return cand
    return preferred


def _chen_self_loop_center(a_center: tuple[float, float],
                           a_size: tuple[float, float],
                           rel_size: tuple[float, float],
                           base_angle: float,
                           obstacles: list[tuple[float, float, float, float]]
                           ) -> tuple[float, float]:
    """自关联菱形绕着实体找空位：优先“远离邻居”的方向，再左右旋转扩大距离。"""
    order = (0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6)
    step = styles.CHEN_SEARCH_STEP
    fallback = None
    for ring in range(0, styles.CHEN_SEARCH_RINGS + 1):
        for k in order:
            angle = base_angle + k * math.pi / 6.0
            u = (math.cos(angle), math.sin(angle))
            dist = (_chen_exit_dist(a_size, u)
                    + _chen_support_to_edge(rel_size, u)
                    + styles.CHEN_REL_CLEARANCE + ring * step)
            cand = (a_center[0] + u[0] * dist,
                    a_center[1] + u[1] * dist)
            if fallback is None:
                fallback = cand
            if _chen_center_free(cand, rel_size, obstacles,
                                 styles.CHEN_REL_CLEARANCE):
                return cand
    return fallback


def _chen_card_label(env: elements.Env, line: dict, which: str,
                     card: connectors.Cardinality, preset: dict,
                     font_family: int,
                     obstacles: list[tuple[float, float, float, float]],
                     lateral: float = 0.0, tag: str = ""):
    """在实体端附近放置基数标签，自动避开实体、菱形和其他标签。"""
    if not card.display:
        return None
    pts = _absolute_points(line)
    if len(pts) < 2:
        return None
    if which == "start":
        base, other = pts[0], pts[1]
    else:
        base, other = pts[-1], pts[-2]
    u = _unit_vec(base, other)
    perp = (-u[1], u[0])
    fs = preset.get("label_font_size", 14)
    tw, th = elements.estimate_text_size(card.display, fs)

    alongs = [16.0]
    for d in (8.0, 16.0, 24.0, 32.0, 40.0, 48.0, 56.0, 64.0, 72.0, 80.0):
        alongs.extend((16.0 + d, 16.0 - d))
    laterals = [lateral]
    for d in range(12, 205, 12):
        laterals.extend((lateral + d, lateral - d))
    candidates: list[tuple[float, float, float]] = []
    for lat in laterals:
        for along in alongs:
            score = math.hypot(along - 16.0, lat - lateral)
            candidates.append((score, along, lat))
    candidates.sort(key=lambda c: c[0])

    chosen = None
    for _score, along, lat in candidates:
        px = base[0] + u[0] * along + perp[0] * lat
        py = base[1] + u[1] * along + perp[1] * lat
        box = (px - tw / 2.0, py - th / 2.0, tw, th)
        if not _chen_box_overlaps(box, obstacles,
                                  styles.CHEN_LABEL_CLEARANCE):
            chosen = (px, py)
            break
    if chosen is None:
        # 实在没有空隙时退回默认位置，validator 会提示重叠
        chosen = (base[0] + u[0] * 20.0 + perp[0] * (12.0 + lateral),
                  base[1] + u[1] * 20.0 + perp[1] * (12.0 + lateral))
    px, py = chosen
    el = elements.text(
        env, px - tw / 2.0, py - th / 2.0, card.display,
        width=tw, height=th,
        stroke_color=preset["colors"].get("chen_line", preset["text"]),
        font_family=font_family, font_size=fs,
        text_align=styles.TEXT_ALIGN_CENTER,
        vertical_align=styles.V_ALIGN_MIDDLE, auto_resize=True)
    if tag:
        _tag(el, tag)
    obstacles.append((el["x"], el["y"], el["width"], el["height"]))
    return el


def _build_chen_entity(env: elements.Env, node: models.Node,
                       cluster_pos: tuple[float, float],
                       cluster_size: tuple[float, float], preset: dict,
                       dynamic_sems: set[str]) -> tuple[list[dict], dict]:
    """经典 Chen 概念图实体：只有矩形和中文业务名，不生成任何属性。"""
    colors = preset["colors"]
    line_color = colors.get("chen_line", preset["stroke"])
    ew, eh = _chen_entity_rect_size(node)
    cx = cluster_pos[0] + cluster_size[0] / 2.0
    cy = cluster_pos[1] + cluster_size[1] / 2.0
    ex, ey = cx - ew / 2.0, cy - eh / 2.0
    rect = elements.rectangle(
        env, ex, ey, ew, eh,
        background=node.style.get("backgroundColor",
                                   colors.get("chen_entity", "#e7f5ff")),
        stroke_color=node.style.get("strokeColor", line_color),
        stroke_width=node.style.get("strokeWidth", preset["stroke_width"]),
        stroke_style=node.style.get("strokeStyle", preset["stroke_style"]),
        roughness=node.style.get("roughness", preset["roughness"]),
        fill_style="solid",
        roundness=node.style.get("roundness", preset["roundness"]))
    _tag(rect, node.sem_id)
    els = [rect]
    t = _chen_label(
        env, rect, _chen_entity_name(node), styles.CHEN_ENTITY_FONT_SIZE,
        node.style.get("textColor",
                       colors.get("chen_entity_text", preset["text"])),
        node.style.get("fontFamily", preset["font_family"]))
    _tag(t, node.sem_id and f"{node.sem_id}::text")
    dynamic_sems.add(f"{node.sem_id}::text")
    els.append(t)
    elements.group(els, _chen_cluster_id(node))
    return els, rect


def _validate_chen_input(diagram: models.Diagram) -> None:
    """经典 Chen 概念图输入校验：中文实体名、中文联系名、合法基数。"""
    for n in diagram.nodes:
        if n.kind != "entity":
            continue
        name = _chen_entity_name(n)
        if not _contains_cjk(name):
            raise ValueError(
                f"经典 Chen 概念图的实体 {n.sem_id!r} 需要中文业务名称（node.label）")
    for e in diagram.edges:
        label = (e.label or "").strip()
        if not label or not _contains_cjk(label):
            raise ValueError(
                f"经典 Chen 概念图的联系 {e.src}>{e.dst} 需要中文业务名称（edge.label）")
        if e.cardinality:
            left, right = connectors.parse_cardinality(e.cardinality)
            for card in (left, right):
                if card.display and not card.known:
                    raise ValueError(
                        f"经典 Chen 概念图不支持的基数写法: {e.cardinality!r}")


def _validate_chen_output(elements: list[dict]) -> None:
    """生成后校验：只允许实体矩形、联系菱形、连线与文本，不含属性/物理信息。"""
    allowed = {"rectangle", "diamond", "arrow", "text"}
    physical = ("bigint", "varchar", "numeric", "timestamp",
                "decimal", "PK ", "FK ", "UQ ")
    for e in elements:
        if e.get("isDeleted"):
            continue
        t = e.get("type")
        if t not in allowed:
            raise ValueError(
                f"经典 Chen 概念图不允许出现 {t!r} 元素（只应有矩形/菱形/连线/文本）")
        sd = (e.get("customData") or {}).get("semId") or ""
        if "::attr::" in sd or "::attrline::" in sd:
            raise ValueError("经典 Chen 概念图不允许属性椭圆或属性连线")
        if t == "arrow":
            if "::line::" not in sd:
                raise ValueError("经典 Chen 概念图只允许联系连线箭头元素")
            if e.get("startArrowhead") or e.get("endArrowhead"):
                raise ValueError("经典 Chen 概念图的联系连线不应有箭头")
        if t == "text":
            txt = e.get("text") or ""
            if any(tok in txt for tok in physical):
                raise ValueError(
                    f"经典 Chen 概念图不允许数据库物理信息: {txt!r}")


def build_chen_diagram(diagram: models.Diagram,
                       positions: list[tuple[float, float]] | None = None,
                       existing: models.Document | None = None,
                       preserve_geometry: bool = False,
                       style: str | None = None,
                       preserve_style: bool | None = None) -> dict[str, Any]:
    """经典 Chen 概念 ER 图：矩形实体 + 菱形联系 + 连线 + 基数，无属性。"""
    style_name = style or diagram.style or styles.DEFAULT_STYLE
    preset = styles.get_preset(style_name)
    if preserve_style is None:
        preserve_style = preserve_geometry
    style_locked = {n.sem_id for n in diagram.nodes if n.sem_id and n.style}
    nodes = diagram.nodes
    for n in nodes:
        if n.kind not in ("entity", "group", "note", "text"):
            raise ValueError(
                f"Chen 模式只支持 entity/group/note/text，遇到 kind={n.kind!r}")
    group_nodes = _validate_groups(nodes)
    group_sems = {g.sem_id for g in group_nodes}
    entity_pairs = [(i, n) for i, n in enumerate(nodes) if n.kind == "entity"]
    entity_nodes = [n for _i, n in entity_pairs]
    entity_by_sem: dict[str, models.Node] = {}
    for n in entity_nodes:
        if not n.sem_id:
            raise ValueError("Chen 模式的 entity 必须有 sem_id")
        entity_by_sem[n.sem_id] = n
    for e in diagram.edges:
        if e.src in group_sems or e.dst in group_sems:
            raise ValueError(f"边 {e.src}>{e.dst} 不能连接到 group")
        if e.src not in entity_by_sem or e.dst not in entity_by_sem:
            raise ValueError(f"Chen 边 {e.src}>{e.dst} 的端点不是 entity")
    _validate_chen_input(diagram)
    ann_pairs = [(i, n) for i, n in enumerate(nodes)
                 if n.kind in ("note", "text")]

    size_fn = _chen_cluster_size
    rel_size_by_edge: dict[int, tuple[float, float]] = {
        ei: _chen_relation_size((e.label or "").strip())
        for ei, e in enumerate(diagram.edges)}
    max_rel_w = max((s[0] for s in rel_size_by_edge.values()), default=0.0)
    max_rel_h = max((s[1] for s in rel_size_by_edge.values()), default=0.0)
    # 基数标签要能塞进实体与菱形之间的空隙（如 0..1 / 1..N）
    card_font_size = preset.get("label_font_size", 14)
    max_card_w = 0.0
    for e in diagram.edges:
        left, right = connectors.parse_cardinality(e.cardinality)
        for card in (left, right):
            if card.display:
                max_card_w = max(max_card_w, elements.estimate_text_size(
                    card.display, card_font_size)[0])
    label_corridor = (max_card_w + 2 * styles.CHEN_LABEL_CLEARANCE + 4.0
                      if max_card_w else 0.0)
    # 实体之间要留出放菱形和基数标签的空隙；同一列里还要让从同一实体
    # 扇形分出的多个菱形在垂直方向错开（中点间距是实体间距的一半）。
    chen_hgap = max(styles.ER_HGAP,
                    max_rel_w + 2 * max(styles.CHEN_REL_CLEARANCE,
                                        label_corridor))
    chen_vgap = max(styles.ER_VGAP,
                    2 * (max_rel_h + styles.CHEN_REL_CLEARANCE)
                    - styles.CHEN_ENTITY_H)
    pair_counts: dict[tuple[str, str], int] = {}
    for e in diagram.edges:
        key = tuple(sorted((e.src, e.dst)))
        pair_counts[key] = pair_counts.get(key, 0) + 1
    max_parallel = max(pair_counts.values(), default=1)
    parallel_span = ((max_parallel - 1) / 2.0
                     * (max_rel_h + styles.CHEN_REL_CLEARANCE))
    # 组内菱形/自关联会伸到成员块外，组块四周预留空间给它们
    chen_margin = (max(max_rel_w, max_rel_h) / 2.0
                   + styles.CHEN_REL_CLEARANCE + 20.0 + parallel_span)
    if positions is None:
        if group_nodes:
            entity_pos = layout.grouped_layout(
                entity_nodes, diagram.edges, group_nodes, size_fn=size_fn,
                title_size_fn=lambda t: elements.estimate_text_size(
                    t, styles.GROUP_TITLE_FONT_SIZE),
                hgap=chen_hgap, vgap=chen_vgap,
                content_margin=chen_margin)
        elif diagram.edges:
            entity_pos = layout.er_layout(
                entity_nodes, diagram.edges, size_fn=size_fn,
                hgap=chen_hgap, vgap=chen_vgap)
        else:
            entity_pos = layout.vertical_flow(entity_nodes, size_fn=size_fn)
    else:
        entity_pos = [positions[i] for i, _n in entity_pairs]

    pos: dict[int, tuple[float, float]] = {}
    for k, (i, _n) in enumerate(entity_pairs):
        pos[i] = entity_pos[k]
    if ann_pairs:
        _min_x, min_y, max_x, _max_y = layout.bounds(
            entity_pos, entity_nodes, size_fn=size_fn)
        ann_x = max_x + styles.NOTE_GAP
        ann_y = min_y
        for i, n in ann_pairs:
            _, th = elements.estimate_text_size(n.text)
            pos[i] = (ann_x, ann_y)
            ann_y += th + styles.VGAP

    # 保留现有实体中心；属性/关系/连线等自动元素由 dynamic_position_sems 重算
    sem_to_existing_el: dict[str, dict] = {}
    if preserve_geometry and existing is not None:
        for e in existing.elements:
            sd = (e.get("customData") or {}).get("semId")
            if sd and e.get("type") != "arrow" and not e.get("isDeleted"):
                sem_to_existing_el.setdefault(sd, e)
        for i, n in enumerate(nodes):
            if n.kind == "group":
                continue
            ex = sem_to_existing_el.get(n.sem_id) if n.sem_id else None
            if not ex or not isinstance(ex.get("x"), (int, float)):
                continue
            if n.kind == "entity":
                cw, ch = size_fn(n)
                ecx = ex["x"] + ex.get("width", 0) / 2.0
                ecy = ex["y"] + ex.get("height", 0) / 2.0
                pos[i] = (ecx - cw / 2.0, ecy - ch / 2.0)
            else:
                pos[i] = (ex["x"], ex["y"])
        new_pairs = [(i, n) for i, n in enumerate(nodes)
                     if n.kind != "group"
                     and not (n.sem_id and n.sem_id in sem_to_existing_el)]
        if new_pairs:
            drawn = [e for e in existing.elements
                     if not e.get("isDeleted")
                     and isinstance(e.get("x"), (int, float))]
            if drawn:
                right_x = max(e["x"] + e.get("width", 0)
                              for e in drawn) + styles.HGAP
                top_y = min(e["y"] for e in drawn)
            else:
                right_x, top_y = 0.0, 0.0
            y = top_y
            max_w = 0.0
            for i, n in new_pairs:
                if n.kind == "entity":
                    w, h = size_fn(n)
                else:
                    w, h = elements.estimate_text_size(n.text)
                pos[i] = (right_x, y)
                max_w = max(max_w, w)
                y += h + styles.VGAP
            ann_new = [(i, n) for i, n in new_pairs
                       if n.kind in ("note", "text")]
            if ann_new and any(n.kind == "entity" for _i, n in new_pairs):
                y = top_y
                for i, n in ann_new:
                    _, th = elements.estimate_text_size(n.text)
                    pos[i] = (right_x + max_w + styles.NOTE_GAP, y)
                    y += th + styles.VGAP

    existing_elements = existing.elements if existing is not None else None
    existing_ids = None
    last_index = None
    if existing_elements is not None:
        existing_ids = {e.get("id") for e in existing_elements if e.get("id")}
        last_index = max((e.get("index") for e in existing_elements
                          if e.get("index")), default=None)
    env = elements.Env(existing_ids=existing_ids, last_index=last_index)

    new_elements: list[dict] = []
    sem_to_index = {n.sem_id: i for i, n in enumerate(nodes) if n.sem_id}
    node_els: dict[int, dict] = {}
    node_elements_by_idx: dict[int, list[dict]] = {}
    dynamic_size: set[str] = set()
    dynamic_pos: set[str] = set()

    group_box_info = _build_group_boxes(
        env, nodes, group_nodes, pos, sem_to_index, size_fn, preset,
        new_elements)
    domain_gid: dict[str, str] = {}
    for g in group_nodes:
        gid = _group_element_id(g)
        for m in g.members:
            domain_gid[m] = gid

    entity_centers: dict[str, tuple[float, float]] = {}
    for i, n in entity_pairs:
        cw, ch = size_fn(n)
        x, y = pos[i]
        entity_centers[n.sem_id] = (x + cw / 2.0, y + ch / 2.0)
    # 自关联回环放在“远离其他邻居”的一侧，避免与普通关系菱形重叠
    self_loop_angle: dict[str, float] = {}
    for n in entity_nodes:
        if not any(e.src == e.dst == n.sem_id for e in diagram.edges):
            continue
        a = entity_centers[n.sem_id]
        dirs: list[float] = []
        for e in diagram.edges:
            if e.src == e.dst:
                continue
            if e.src == n.sem_id:
                b = entity_centers[e.dst]
                dirs.append(math.atan2(b[1] - a[1], b[0] - a[0]))
            elif e.dst == n.sem_id:
                b = entity_centers[e.src]
                dirs.append(math.atan2(b[1] - a[1], b[0] - a[0]))
        if dirs:
            sx = sum(math.cos(x) for x in dirs)
            sy = sum(math.sin(x) for x in dirs)
            base = (math.atan2(sy, sx)
                    if abs(sx) + abs(sy) > 1e-9 else 0.0)
            self_loop_angle[n.sem_id] = base + math.pi
        else:
            self_loop_angle[n.sem_id] = 0.0

    for i, n in entity_pairs:
        cw, ch = size_fn(n)
        els, rect = _build_chen_entity(
            env, n, pos[i], (cw, ch), preset, dynamic_pos)
        new_elements.extend(els)
        node_els[i] = rect
        node_elements_by_idx[i] = els
        dynamic_size.add(n.sem_id)
        dynamic_pos.add(n.sem_id)  # 实体矩形按“保留的中心”重算左上角

    # 图例 / 补充注释
    for i, n in ann_pairs:
        x, y = pos[i]
        tw, th = elements.estimate_text_size(n.text)
        fam = (preset["note_font_family"] if n.kind == "note"
               else preset["font_family"])
        t = elements.text(
            env, x, y, n.text, width=tw, height=th,
            stroke_color=n.style.get("textColor", preset["text"]),
            font_family=n.style.get("fontFamily", fam),
            font_size=n.style.get("fontSize", preset["font_size"]),
            auto_resize=True)
        _tag(t, n.sem_id)
        new_elements.append(t)
        node_elements_by_idx[i] = [t]

    entity_index = {n.sem_id: i for i, n in entity_pairs}
    tag_counts: dict[str, int] = {}
    for e in diagram.edges:
        base = e.sem_id or f"{e.src}>{e.dst}"
        tag_counts[base] = tag_counts.get(base, 0) + 1
    tag_seen: dict[str, int] = {}
    relation_groups: list[tuple[str, str, list[dict]]] = []
    colors = preset["colors"]
    line_color = colors.get("chen_line", preset["stroke"])
    font_family = preset["font_family"]

    # 同一实体上的多个基数标签沿垂直方向错开，避免重叠
    incidents: dict[str, list[tuple[int, str]]] = {
        n.sem_id: [] for n in entity_nodes}
    for ei, e in enumerate(diagram.edges):
        incidents[e.src].append((ei, "src"))
        incidents[e.dst].append((ei, "dst"))
    incident_lateral: dict[tuple[int, str], float] = {}
    for items in incidents.values():
        k = len(items)
        for j, (ei, which) in enumerate(items):
            incident_lateral[(ei, which)] = (j - (k - 1) / 2.0) * 20.0

    # 先给所有联系菱形找位置：实体是障碍物，普通关系先放，自关联最后放。
    relation_centers: dict[int, tuple[float, float]] = {}
    base_obstacles: list[tuple[float, float, float, float]] = []
    entity_boxes: dict[str, tuple[float, float, float, float]] = {}
    for i, n in entity_pairs:
        x, y = pos[i]
        w, h = size_fn(n)
        box = (x, y, w, h)
        base_obstacles.append(box)
        entity_boxes[n.sem_id] = box
    for _i, _n in ann_pairs:
        for el in node_elements_by_idx.get(_i, []):
            base_obstacles.append(
                (el["x"], el["y"], el["width"], el["height"]))
    group_boxes: dict[str, list[tuple[float, float, float, float]]] = {}
    group_titles: list[tuple[float, float, float, float]] = []
    for g, _mi, rect, hdr, title_el in group_box_info:
        gid = _group_element_id(g)
        boxes = [(rect["x"], rect["y"], rect["width"], rect["height"]),
                 (hdr["x"], hdr["y"], hdr["width"], hdr["height"])]
        if title_el:
            tb = (title_el["x"], title_el["y"],
                  title_el["width"], title_el["height"])
            boxes.append(tb)
            group_titles.append(tb)
        group_boxes[gid] = boxes

    def relation_group(e: models.Edge) -> str | None:
        g1 = domain_gid.get(e.src)
        return g1 if g1 and g1 == domain_gid.get(e.dst) else None

    def diamond_obstacles(rg: str | None,
                          placed: list[tuple[float, float, float, float]]
                          ) -> list[tuple[float, float, float, float]]:
        out = list(base_obstacles) + list(placed)
        for gid, boxes in group_boxes.items():
            # 组内联系自己的组框不参与避让：组框随后会扩大包住它
            if gid != rg:
                out.extend(boxes)
        return out

    placed_diamonds: list[tuple[float, float, float, float]] = []
    placed_pairs: dict[tuple[str, str], int] = {}
    for ei, e in enumerate(diagram.edges):
        if e.src == e.dst:
            continue
        dw, dh = rel_size_by_edge[ei]
        key = tuple(sorted((e.src, e.dst)))
        idx = placed_pairs.get(key, 0)
        placed_pairs[key] = idx + 1
        offset = (idx - (pair_counts[key] - 1) / 2.0) * (
            dh + styles.CHEN_REL_CLEARANCE)
        src_node, dst_node = entity_by_sem[e.src], entity_by_sem[e.dst]
        a_center, b_center = entity_centers[e.src], entity_centers[e.dst]
        center = _chen_relation_center(
            a_center, b_center, size_fn(src_node), size_fn(dst_node),
            offset, rel_size=(dw, dh))
        if center is None:
            center = (a_center[0] + dw / 2.0 + 80.0, a_center[1])
        dx, dy = b_center[0] - a_center[0], b_center[1] - a_center[1]
        dist = math.hypot(dx, dy)
        u = (dx / dist, dy / dist) if dist > 1e-9 else (1.0, 0.0)

        def segments_clear(cand, _src=e.src, _dst=e.dst,
                           _a=a_center, _b=b_center):
            for sem, box in entity_boxes.items():
                if sem == _src or sem == _dst:
                    continue
                if (_segment_hits_box(cand, _a, box)
                        or _segment_hits_box(cand, _b, box)):
                    return False
            return True

        center = _chen_find_free_center(
            center, (dw, dh),
            diamond_obstacles(relation_group(e), placed_diamonds), u,
            segments_clear=segments_clear)
        relation_centers[ei] = center
        placed_diamonds.append(
            (center[0] - dw / 2.0, center[1] - dh / 2.0, dw, dh))
    for ei, e in enumerate(diagram.edges):
        if e.src != e.dst:
            continue
        dw, dh = rel_size_by_edge[ei]
        center = _chen_self_loop_center(
            entity_centers[e.src], size_fn(entity_by_sem[e.src]),
            (dw, dh), self_loop_angle.get(e.src, 0.0),
            diamond_obstacles(relation_group(e), placed_diamonds))
        relation_centers[ei] = center
        placed_diamonds.append(
            (center[0] - dw / 2.0, center[1] - dh / 2.0, dw, dh))

    # 基数标签避让所有实体/菱形/组标题/其他标签，但不避让组框（标签在组内）
    label_obstacles = (list(base_obstacles) + list(placed_diamonds)
                       + list(group_titles))

    for ei, e in enumerate(diagram.edges):
        src_node, dst_node = entity_by_sem[e.src], entity_by_sem[e.dst]
        src_rect = node_els[entity_index[e.src]]
        dst_rect = node_els[entity_index[e.dst]]
        label = (e.label or "").strip()
        dw, dh = rel_size_by_edge[ei]
        center = relation_centers[ei]
        base_tag = e.sem_id or f"{e.src}>{e.dst}"
        tag = base_tag
        if tag_counts[base_tag] > 1:
            ti = tag_seen.get(base_tag, 0)
            tag_seen[base_tag] = ti + 1
            tag = f"{base_tag}#{ti + 1}"
        diamond = elements.diamond(
            env, center[0] - dw / 2.0, center[1] - dh / 2.0, dw, dh,
            background=colors.get("chen_relation", "#fff3bf"),
            stroke_color=line_color,
            stroke_width=preset["stroke_width"],
            stroke_style=preset["stroke_style"],
            roughness=preset["roughness"], fill_style="solid")
        _tag(diamond, f"{tag}::rel")
        dynamic_pos.add(f"{tag}::rel")
        rel_els: list[dict] = [diamond]
        rel_text = _chen_label(
            env, diamond, label, styles.CHEN_REL_FONT_SIZE,
            colors.get("chen_relation_text", preset["text"]), font_family)
        _tag(rel_text, f"{tag}::rel::text")
        dynamic_pos.add(f"{tag}::rel::text")
        rel_els.append(rel_text)
        line_a = connectors.bound_arrow(
            env, src_rect, diamond, start_arrowhead=None, end_arrowhead=None,
            stroke_color=line_color, stroke_width=1, roughness=0)
        _tag(line_a, f"{tag}::line::a")
        dynamic_pos.add(f"{tag}::line::a")
        rel_els.append(line_a)
        line_b = connectors.bound_arrow(
            env, diamond, dst_rect, start_arrowhead=None, end_arrowhead=None,
            stroke_color=line_color, stroke_width=1, roughness=0)
        _tag(line_b, f"{tag}::line::b")
        dynamic_pos.add(f"{tag}::line::b")
        rel_els.append(line_b)
        if (line_a["startBinding"]["elementId"] != src_rect["id"]
                or line_a["endBinding"]["elementId"] != diamond["id"]
                or line_b["startBinding"]["elementId"] != diamond["id"]
                or line_b["endBinding"]["elementId"] != dst_rect["id"]):
            raise ValueError(f"联系 {e.src}>{e.dst} 的连线端点不正确")
        left, right = connectors.parse_cardinality(e.cardinality)
        card_a = _chen_card_label(
            env, line_a, "start", left, preset, font_family, label_obstacles,
            incident_lateral.get((ei, "src"), 0.0), tag=f"{tag}::card::a")
        if card_a:
            dynamic_pos.add(f"{tag}::card::a")
            rel_els.append(card_a)
        card_b = _chen_card_label(
            env, line_b, "end", right, preset, font_family, label_obstacles,
            incident_lateral.get((ei, "dst"), 0.0), tag=f"{tag}::card::b")
        if card_b:
            dynamic_pos.add(f"{tag}::card::b")
            rel_els.append(card_b)
        new_elements.extend(rel_els)
        relation_groups.append((e.src, e.dst, rel_els))

    # 域分组：成员聚类 + 组框；同域关系也放进同一个外层 group
    for g, member_idxs, rect, hdr, title_el in group_box_info:
        gid = _group_element_id(g)
        member_els: list[dict] = []
        for mi in member_idxs:
            member_els.extend(node_elements_by_idx.get(mi, []))
        elements.group(member_els + [rect, hdr]
                       + ([title_el] if title_el else []), gid)
    group_relation_sems: dict[str, list[str]] = {}
    for src, dst, rels in relation_groups:
        g1 = domain_gid.get(src)
        if g1 and g1 == domain_gid.get(dst):
            elements.group(rels, g1)
            for el in rels:
                sd = (el.get("customData") or {}).get("semId") or ""
                if sd.endswith("::rel"):
                    group_relation_sems.setdefault(g1, []).append(sd)

    # 图标题：放在所有实体/属性/关系/组框上方
    if diagram.title:
        boxes = [e for e in new_elements
                 if e.get("type") in ("rectangle", "diamond", "ellipse")]
        if boxes:
            min_x = min(e["x"] for e in boxes)
            max_x = max(e["x"] + e.get("width", 0) for e in boxes)
            min_y = min(e["y"] for e in boxes)
        else:
            min_x = max_x = min_y = 0.0
        tw, th = elements.estimate_text_size(
            diagram.title, styles.TITLE_FONT_SIZE)
        t = elements.text(
            env, min_x + (max_x - min_x - tw) / 2.0,
            min_y - th - styles.TITLE_GAP, diagram.title,
            width=tw, height=th, stroke_color=preset["text"],
            font_family=preset["font_family"],
            font_size=styles.TITLE_FONT_SIZE,
            text_align=styles.TEXT_ALIGN_CENTER,
            vertical_align=styles.V_ALIGN_TOP, auto_resize=True)
        _tag(t, styles.TITLE_SEM_ID)
        new_elements.append(t)

    if existing_elements is not None:
        dynamic = {n.sem_id for n in nodes
                   if n.kind in ("entity", "group") and n.sem_id}
        new_elements = _reconcile(
            new_elements, existing_elements,
            preserve_geometry=preserve_geometry,
            preserve_style=preserve_style,
            style_locked_sems=style_locked,
            dynamic_size_sems=dynamic,
            dynamic_position_sems=dynamic_pos)
    _sync_group_boxes(new_elements, nodes, group_relation_sems)
    _sync_title(new_elements)
    if existing_elements is not None:
        _refresh_versions(new_elements, existing_elements)
    new_elements.sort(key=lambda e: e.get("index") or "")
    _validate_chen_output(new_elements)

    if existing is not None:
        app_state = dict(existing.app_state)
    else:
        app_state = dict(styles.DEFAULT_APP_STATE)
        app_state["theme"] = diagram.canvas.theme or preset["theme"]
        app_state["viewBackgroundColor"] = (diagram.canvas.background
                                            or preset["background"])
        app_state["currentItemStrokeColor"] = preset["stroke"]
        app_state["currentItemFontFamily"] = preset["font_family"]
    return {
        "type": "excalidraw",
        "version": 2,
        "source": diagram.meta.get("source", styles.DEFAULT_SOURCE),
        "elements": new_elements,
        "appState": app_state,
        "files": dict(existing.files) if existing is not None else {},
    }
