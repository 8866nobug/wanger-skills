"""ID 生成、分配与冲突检测。

Excalidraw 原生元素 id 为 8 位字母数字（如 "fzdFohwE"）；元素另有
``index`` 字段（分数索引，决定渲染顺序），形如 "a0"、"a1"、"Zx"。
本模块生成同规格 id 与单调递增的 index。
"""
from __future__ import annotations

import secrets
import string

_ELEMENT_ALPHABET = string.ascii_letters + string.digits

# index 使用的 base62 字母表（与 Excalidraw 分数索引一致：数字 < 大写 < 小写）
_INDEX_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"


def new_id(length: int = 8) -> str:
    """生成一个 8 位字母数字 id（与 Excalidraw 规格一致）。"""
    return "".join(secrets.choice(_ELEMENT_ALPHABET) for _ in range(length))


def is_valid_id(value: str) -> bool:
    return (
        isinstance(value, str)
        and 1 <= len(value) <= 64
        and all(c in _ELEMENT_ALPHABET for c in value)
    )


def detect_collisions(ids: list[str]) -> list[str]:
    """返回重复出现的 id（去重，按首次出现顺序）。"""
    seen: set[str] = set()
    dup: list[str] = []
    for i in ids:
        if i in seen:
            dup.append(i)
        seen.add(i)
    return list(dict.fromkeys(dup))


def ensure_unique(existing: set[str], generator=None) -> str:
    """生成一个不与 existing 冲突的 id。"""
    gen = generator or new_id
    while True:
        i = gen()
        if i not in existing:
            return i


# --------------------------------------------------------------------------- #
# 分数索引（简化实现）
# --------------------------------------------------------------------------- #
# Phase 1 只做「追加式」单调索引：从 "a0" 起按 base62 递增。
# 不支持在任意两个已有 index 之间插入（完整分数索引属后续 Phase）。

def first_index() -> str:
    return "a0"


def next_index(prev: str | None) -> str:
    """返回大于 prev 的下一个 index。prev 为 None 时返回首个 index。"""
    if prev is None or prev == "":
        return first_index()
    chars = list(prev)
    i = len(chars) - 1
    while i >= 0:
        pos = _INDEX_ALPHABET.index(chars[i])
        if pos < len(_INDEX_ALPHABET) - 1:
            chars[i] = _INDEX_ALPHABET[pos + 1]
            return "".join(chars)
        chars[i] = _INDEX_ALPHABET[0]
        i -= 1
    # 全部溢出：在前面补一个最小有效前缀（如 "z" -> "a0z" 语义上的下一位）
    return _INDEX_ALPHABET[0] + "".join(chars)


def next_index_after(existing: list[str]) -> str:
    """返回大于现有所有 index 的下一个 index。"""
    if not existing:
        return first_index()
    return next_index(max(existing))
