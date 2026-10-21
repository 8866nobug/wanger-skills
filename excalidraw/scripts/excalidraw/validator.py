"""文件结构、ID 与引用一致性校验。"""
from __future__ import annotations

from typing import Any

from . import ids, models

_LEVELS = ("error", "warning", "info")


def validate_document(doc: models.Document) -> list[dict[str, str]]:
    """校验一份解析后的文档，返回问题列表（按严重度排序）。

    每条问题形如 {"level": "error"|"warning"|"info", "code": str, "message": str}。
    结构校验通过不等于视觉渲染通过；视觉验收需用插件打开。
    """
    issues: list[dict[str, str]] = []
    elements = doc.elements

    if not isinstance(elements, list):
        return [{"level": "error", "code": "elements-not-list", "message": "elements 不是列表"}]

    id_map: dict[str, dict] = {}
    for i, e in enumerate(elements):
        if not isinstance(e, dict):
            issues.append({"level": "error", "code": "element-not-dict",
                           "message": f"elements[{i}] 不是对象"})
            continue
        eid = e.get("id")
        if not eid:
            issues.append({"level": "error", "code": "missing-id",
                           "message": f"elements[{i}] 缺少 id"})
            continue
        if not ids.is_valid_id(eid):
            issues.append({"level": "warning", "code": "invalid-id-format",
                           "message": f"id 格式异常: {eid!r}"})
        if eid in id_map:
            issues.append({"level": "error", "code": "duplicate-id",
                           "message": f"id 重复: {eid!r}"})
        id_map[eid] = e

    # 引用一致性
    for e in elements:
        if not isinstance(e, dict):
            continue
        eid = e.get("id", "?")
        cid = e.get("containerId")
        if cid is not None and cid not in id_map:
            issues.append({"level": "error", "code": "dangling-container",
                           "message": f"元素 {eid} 的 containerId 指向不存在的 {cid!r}"})
        for b in (e.get("boundElements") or []):
            if isinstance(b, dict) and b.get("id") and b["id"] not in id_map:
                issues.append({"level": "error", "code": "dangling-bound",
                               "message": f"元素 {eid} 的 boundElements 指向不存在的 {b['id']!r}"})
        for key in ("startBinding", "endBinding"):
            bd = e.get(key)
            if isinstance(bd, dict) and bd.get("elementId") \
                    and bd["elementId"] not in id_map:
                issues.append({"level": "error", "code": "dangling-binding",
                               "message": f"元素 {eid} 的 {key} 指向不存在的 {bd['elementId']!r}"})

        # 图片元素的数据来源：内嵌 files 或 "## Embedded Files" 的 Vault 链接
        if e.get("type") == "image":
            fid = e.get("fileId")
            if fid and fid not in (doc.files or {}) \
                    and fid not in (doc.embedded_files or {}):
                issues.append({"level": "warning", "code": "image-data-missing",
                               "message": f"图片元素 {eid} 的 fileId {fid!r} 在 files 与 Embedded Files 中均未找到"})

    if not doc.app_state:
        issues.append({"level": "warning", "code": "empty-appstate",
                       "message": "appState 为空"})

    # 经典 Chen 概念图：统计不同联系之间的连线交叉（提示，不阻断写入）
    chen_lines = []
    for e in elements:
        if not isinstance(e, dict) or e.get("type") != "arrow":
            continue
        sd = (e.get("customData") or {}).get("semId") or ""
        if "::line::" not in sd:
            continue
        pts = [(e.get("x", 0) + p[0], e.get("y", 0) + p[1])
               for p in (e.get("points") or [])]
        if len(pts) >= 2:
            tag = sd.split("::line::")[0]
            chen_lines.append((tag, pts[0], pts[-1]))
    crossings = 0
    for i in range(len(chen_lines)):
        t1, a, b = chen_lines[i]
        for j in range(i + 1, len(chen_lines)):
            t2, c, d = chen_lines[j]
            if t1 == t2:
                continue
            if (_near(a, c) or _near(a, d) or _near(b, c) or _near(b, d)):
                continue
            if _segments_cross(a, b, c, d):
                crossings += 1
    if crossings:
        issues.append({
            "level": "warning", "code": "chen-line-crossing",
            "message": f"经典 Chen 概念图检测到 {crossings} 处联系连线交叉，建议调整布局或使用分组"})

    # 经典 Chen 概念图：检查实体矩形 / 联系菱形 / 自由文本之间的块重叠
    if chen_lines:
        overlaps = _chen_overlaps(elements)
        if overlaps:
            issues.append({
                "level": "warning", "code": "chen-element-overlap",
                "message": f"经典 Chen 概念图检测到 {overlaps} 处元素重叠"
                           "（实体/联系/基数标签），建议重新布局或调整间距"})

    # 排序：error > warning > info
    order = {lv: i for i, lv in enumerate(_LEVELS)}
    issues.sort(key=lambda x: order.get(x["level"], 99))
    return issues


def _aabb(el: dict) -> tuple[float, float, float, float] | None:
    x, y = el.get("x"), el.get("y")
    w, h = el.get("width"), el.get("height")
    if not all(isinstance(v, (int, float)) for v in (x, y, w, h)):
        return None
    return (float(x), float(y), float(w), float(h))


def _boxes_overlap(a: tuple[float, float, float, float],
                   b: tuple[float, float, float, float]) -> bool:
    return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
            and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])


def _chen_overlaps(elements: list[dict]) -> int:
    """统计 Chen 图中实体矩形、联系菱形与自由文本之间的 AABB 重叠数。"""
    group_sems: set[str] = set()
    for e in elements:
        sd = (e.get("customData") or {}).get("semId") or ""
        if sd.endswith("::hdr"):
            group_sems.add(sd[:-5])
    shapes: list[tuple[str, tuple[float, float, float, float]]] = []
    texts: list[tuple[str, tuple[float, float, float, float]]] = []
    for e in elements:
        if not isinstance(e, dict) or e.get("isDeleted"):
            continue
        if e.get("type") not in ("rectangle", "diamond", "text"):
            continue
        sd = (e.get("customData") or {}).get("semId") or ""
        box = _aabb(e)
        if box is None:
            continue
        if e.get("type") in ("rectangle", "diamond"):
            if sd in group_sems or sd.endswith("::hdr"):
                continue  # 组框本身就包住成员，属于设计意图
            shapes.append((sd or e.get("id", "?"), box))
        elif not e.get("containerId"):
            texts.append((sd or e.get("text", "?"), box))
    count = 0
    for i, (_name, a) in enumerate(shapes):
        for _name2, b in shapes[i + 1:]:
            if _boxes_overlap(a, b):
                count += 1
    for _name, t in texts:
        for _sname, s in shapes:
            if _boxes_overlap(t, s):
                count += 1
    for i, (_name, a) in enumerate(texts):
        for _name2, b in texts[i + 1:]:
            if _boxes_overlap(a, b):
                count += 1
    return count


def _near(a, b, eps: float = 1.0) -> bool:
    return abs(a[0] - b[0]) <= eps and abs(a[1] - b[1]) <= eps


def _segments_cross(a, b, c, d, eps: float = 1e-6) -> bool:
    def orient(p, q, r):
        return ((q[0] - p[0]) * (r[1] - p[1])
                - (q[1] - p[1]) * (r[0] - p[0]))

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    return (((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps))
            and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)))


def has_errors(issues: list[dict[str, str]]) -> bool:
    return any(i["level"] == "error" for i in issues)


def format_issues(issues: list[dict[str, str]]) -> str:
    if not issues:
        return "OK：未发现问题"
    lines = [f"[{i['level'].upper()}] {i['code']}: {i['message']}" for i in issues]
    return "\n".join(lines)
