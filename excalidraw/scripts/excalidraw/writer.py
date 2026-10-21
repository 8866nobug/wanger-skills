"""备份、安全写入与恢复。

新建 / 完整替换 / 增量修改走不同路径；写入失败时保留原始文件。
"""
from __future__ import annotations

import os
import shutil
import time

from . import adapters


def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup(path: str) -> str:
    """为已有文件创建 .bak-<timestamp> 备份，返回备份路径。"""
    if not os.path.exists(path):
        return ""
    backup_path = f"{path}.bak-{_stamp()}"
    shutil.copy2(path, backup_path)
    return backup_path


def atomic_write(path: str, content: str) -> None:
    """写入临时文件后原子重命名，避免半写入。"""
    tmp = f"{path}.tmp-{_stamp()}-{os.getpid()}"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    os.replace(tmp, path)


def write_new(path: str, content: str) -> None:
    """新建文件；目标已存在则报错（默认禁止静默覆盖）。"""
    if os.path.exists(path):
        raise FileExistsError(f"目标已存在，拒绝覆盖：{path}")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    atomic_write(path, content)


def write_replace(path: str, content: str, *, backup_file: bool = True) -> str:
    """完整替换：先备份，再原子写入，返回备份路径（未备份则为空串）。"""
    if not os.path.exists(path):
        atomic_write(path, content)
        return ""
    backup_path = backup(path) if backup_file else ""
    atomic_write(path, content)
    return backup_path


def write_excalidraw(path: str, doc_or_elements, app_state=None, *,
                     files=None, source=None,
                     backup_file: bool = True) -> str:
    """把 Document（或 elements + app_state）写成标准 ``.excalidraw`` JSON。

    与 ``write_document`` 一样：目标已存在时先备份，使用原子写入。
    """
    from . import models
    if isinstance(doc_or_elements, models.Document):
        doc = doc_or_elements
        text = adapters.serialize_excalidraw(
            doc.elements, doc.app_state, files=doc.files, source=doc.source)
    else:
        text = adapters.serialize_excalidraw(
            doc_or_elements, app_state, files=files, source=source)
    if os.path.exists(path):
        return write_replace(path, text, backup_file=backup_file)
    write_new(path, text)
    return ""


def write_document(path: str, doc_or_elements, app_state=None, *,
                   files=None, source=None, frontmatter=None,
                   embedded_files=None, text_order=None,
                   backup_file: bool = True) -> str:
    """把 Document（或 elements + app_state）序列化并安全写入。

    目标已存在时视为「完整替换」，先备份；不存在时视为「新建」。
    返回备份路径（未备份则为空串）。
    """
    from . import models
    if isinstance(doc_or_elements, models.Document):
        doc = doc_or_elements
        text = adapters.serialize_md(doc.elements, doc.app_state,
                                     files=doc.files, source=doc.source,
                                     frontmatter=doc.frontmatter,
                                     embedded_files=doc.embedded_files,
                                     text_order=[eid for _, eid in doc.text_blocks])
    else:
        text = adapters.serialize_md(doc_or_elements, app_state,
                                     files=files, source=source,
                                     frontmatter=frontmatter,
                                     embedded_files=embedded_files,
                                     text_order=text_order)
    if os.path.exists(path):
        return write_replace(path, text, backup_file=backup_file)
    write_new(path, text)
    return ""
