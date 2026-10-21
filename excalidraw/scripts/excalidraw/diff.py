"""元素级差异分析。"""
from __future__ import annotations

from typing import Any


def diff_elements(old: list[dict], new: list[dict]) -> dict[str, Any]:
    """比较两组元素（以 id 为键），返回 added / removed / updated。

    updated 仅报告顶层字段发生变化的元素 id（不做深度差异）。
    """
    old_map = {e.get("id"): e for e in old if isinstance(e, dict) and e.get("id")}
    new_map = {e.get("id"): e for e in new if isinstance(e, dict) and e.get("id")}

    added = [i for i in new_map if i not in old_map]
    removed = [i for i in old_map if i not in new_map]
    updated = [i for i in new_map if i in old_map and old_map[i] != new_map[i]]
    return {"added": added, "removed": removed, "updated": updated}


def format_diff(d: dict[str, Any]) -> str:
    lines = [
        f"added:   {len(d['added'])} {d['added']}",
        f"removed: {len(d['removed'])} {d['removed']}",
        f"updated: {len(d['updated'])} {d['updated']}",
    ]
    return "\n".join(lines)
