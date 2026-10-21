"""基础元素工厂：生成 Excalidraw 原生元素 dict。

字段 schema 取自 Vault 中真实文件（插件 2.29.0）的观测结果，
保证生成结果与插件兼容。所有工厂通过一个 Env 上下文分配唯一 id / index / 版本。
"""
from __future__ import annotations

import random
import time
from typing import Any

from . import ids, styles


class Env:
    """一次绘图生成的上下文：分配唯一 id、单调 index、版本号与时间戳。"""

    def __init__(self, existing_ids: set[str] | None = None,
                 last_index: str | None = None, t0: int | None = None):
        self.existing: set[str] = set(existing_ids or [])
        self._last_index = last_index
        self._t0 = t0 if t0 is not None else int(time.time() * 1000)
        self._version = 1
        self._rng = random.Random()

    def new_id(self) -> str:
        i = ids.ensure_unique(self.existing)
        self.existing.add(i)
        return i

    def next_index(self) -> str:
        self._last_index = ids.next_index(self._last_index)
        return self._last_index

    def now(self) -> int:
        return self._t0

    def version(self) -> int:
        v = self._version
        self._version += 1
        return v

    def seed(self) -> int:
        return self._rng.randrange(0, 2**31)

    def nonce(self) -> int:
        return self._rng.randrange(0, 2**31)


def _base(env: Env, etype: str, x: float, y: float, width: float, height: float,
          *, stroke_color: str = styles.STROKE,
          background: str = styles.BACKGROUND_TRANSPARENT,
          fill_style: str = "solid",
          stroke_width: int = styles.STROKE_WIDTH,
          stroke_style: str = styles.STROKE_STYLE,
          roughness: int = styles.ROUGHNESS,
          opacity: int = styles.OPACITY,
          roundness: dict | None = None) -> dict[str, Any]:
    return {
        "id": env.new_id(),
        "type": etype,
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "angle": 0,
        "strokeColor": stroke_color,
        "backgroundColor": background,
        "fillStyle": fill_style,
        "strokeWidth": stroke_width,
        "strokeStyle": stroke_style,
        "roughness": roughness,
        "opacity": opacity,
        "groupIds": [],
        "frameId": None,
        "index": env.next_index(),
        "roundness": roundness,
        "seed": env.seed(),
        "version": env.version(),
        "versionNonce": env.nonce(),
        "isDeleted": False,
        "boundElements": [],
        "updated": env.now(),
        "created": env.now(),
        "link": None,
        "locked": False,
        "hasTextLink": False,
    }


def rectangle(env: Env, x: float, y: float, w: float, h: float, **kw) -> dict:
    return _base(env, "rectangle", x, y, w, h, **kw)


def diamond(env: Env, x: float, y: float, w: float, h: float, **kw) -> dict:
    return _base(env, "diamond", x, y, w, h, **kw)


def ellipse(env: Env, x: float, y: float, w: float, h: float, **kw) -> dict:
    kw.setdefault("roundness", {"type": 2})
    return _base(env, "ellipse", x, y, w, h, **kw)


def _points_size(points: list[list[float]]) -> tuple[float, float]:
    """折线的包围盒宽高（points 可含负坐标，起始点通常为 [0,0]）。"""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def line(env: Env, x: float, y: float, points: list[list[float]], **kw) -> dict:
    w, h = _points_size(points)
    el = _base(env, "line", x, y, w, h, **kw)
    el["points"] = [list(p) for p in points]
    el["startBinding"] = None
    el["endBinding"] = None
    el["startArrowhead"] = None
    el["endArrowhead"] = None
    el["polygon"] = False
    return el


def arrow(env: Env, x: float, y: float, points: list[list[float]], *,
          start_binding: dict | None = None, end_binding: dict | None = None,
          start_arrowhead: str | None = None,
          end_arrowhead: str | None = styles.END_ARROWHEAD,
          elbowed: bool = False, **kw) -> dict:
    w, h = _points_size(points)
    el = _base(env, "arrow", x, y, w, h, **kw)
    el["points"] = [list(p) for p in points]
    el["startBinding"] = start_binding
    el["endBinding"] = end_binding
    el["startArrowhead"] = start_arrowhead
    el["endArrowhead"] = end_arrowhead
    el["elbowed"] = elbowed
    el["moveMidPointsWithElement"] = False
    return el


def _char_width(ch: str, font_size: float) -> float:
    # CJK 及全角字符宽度近似为 font_size；拉丁/数字约 0.55 * font_size。
    return font_size if ord(ch) > 0x2E80 else font_size * 0.55


def estimate_text_size(text: str, font_size: float = styles.FONT_SIZE,
                       line_height: float = styles.LINE_HEIGHT) -> tuple[float, float]:
    """粗略估算文本盒宽高（无字体度量库，仅供初始布局，插件打开后以实际渲染为准）。"""
    lines = text.split("\n")
    w = max((sum(_char_width(c, font_size) for c in line) for line in lines), default=0.0)
    h = len(lines) * font_size * line_height
    return w, h


def text(env: Env, x: float, y: float, content: str, *,
         width: float | None = None, height: float | None = None,
         container_id: str | None = None,
         font_family: int = styles.FONT_DEFAULT,
         font_size: float = styles.FONT_SIZE,
         text_align: str = styles.TEXT_ALIGN_LEFT,
         vertical_align: str = styles.V_ALIGN_TOP,
         auto_resize: bool = True, **kw) -> dict:
    if width is None or height is None:
        w, h = estimate_text_size(content, font_size)
        width = w if width is None else width
        height = h if height is None else height
    el = _base(env, "text", x, y, width, height,
               background=styles.BACKGROUND_TRANSPARENT,
               roundness=None, **kw)
    el.update({
        "text": content,
        "rawText": content,
        "fontSize": font_size,
        "baseFontSize": None,
        "fontFamily": font_family,
        "textAlign": text_align,
        "verticalAlign": vertical_align,
        "containerId": container_id,
        "originalText": content,
        "autoResize": auto_resize,
        "lineHeight": styles.LINE_HEIGHT,
        "labelPosition": None,
    })
    return el


def bind_text(shape: dict, text_id: str) -> None:
    """把 text 元素挂到容器 shape 的 boundElements（text 元素自身 containerId 已指向 shape）。"""
    shape.setdefault("boundElements", [])
    if {"type": "text", "id": text_id} not in shape["boundElements"]:
        shape["boundElements"].append({"type": "text", "id": text_id})


def bind_arrow(shape: dict, arrow_id: str) -> None:
    """把箭头登记到形状的 boundElements，插件据此在移动形状时更新箭头。"""
    shape.setdefault("boundElements", [])
    if {"type": "arrow", "id": arrow_id} not in shape["boundElements"]:
        shape["boundElements"].append({"type": "arrow", "id": arrow_id})


def group(els: list[dict], group_id: str) -> None:
    """把一组元素放进同一个 Excalidraw group，拖动时整体移动。"""
    for el in els:
        ids = el.setdefault("groupIds", [])
        if group_id not in ids:
            ids.append(group_id)
