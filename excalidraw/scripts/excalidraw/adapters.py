"""Excalidraw 文件格式适配：lz-string codec + .excalidraw.md 容器读写。

格式要点（均已用 Vault 真实文件验证）：
- .excalidraw.md 是 Markdown 容器，非纯 JSON。
- 绘图数据存放在 ```compressed-json 代码块中，为 LZ-String compressToBase64
  编码的 JSON（顶层键 type/version/source/elements/appState/files）。
- "## Text Elements" 段是 text 元素的 rawText + ^id，仅供检索/嵌入，
  权威数据在 JSON 中；序列化时从 elements 重新生成以保证同步。
"""
from __future__ import annotations

import json
import re
from typing import Any

from . import models, styles

_KEY_STR_BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="

_WARNING = (
    "==⚠  Switch to EXCALIDRAW VIEW in the MORE OPTIONS menu of this "
    "document. ⚠== You can decompress Drawing data with the command "
    "palette: 'Decompress current Excalidraw file'. For more info check in "
    "plugin settings under 'Saving'"
)

DEFAULT_FRONTMATTER = "---\n\nexcalidraw-plugin: parsed\ntags: [excalidraw]\n\n---\n"


# --------------------------------------------------------------------------- #
# LZ-String（compressToBase64 / decompressFromBase64）纯 Python 移植
# --------------------------------------------------------------------------- #

def _decompress(length: int, reset_value: int, get_next_value):
    dictionary = [0, 1, 2]
    enlarge_in = 4
    dict_size = 4
    num_bits = 3
    result: list[str] = []
    w = ""
    data_val = get_next_value(0)
    data_position = reset_value
    data_index = 1

    def read_bits(n: int) -> int:
        nonlocal data_val, data_position, data_index
        bits = 0
        power = 1
        for _ in range(n):
            resb = data_val & data_position
            data_position >>= 1
            if data_position == 0:
                data_position = reset_value
                data_val = get_next_value(data_index)
                data_index += 1
            bits |= (1 if resb > 0 else 0) * power
            power <<= 1
        return bits

    nxt = read_bits(2)
    if nxt == 0:
        c = chr(read_bits(8))
    elif nxt == 1:
        c = chr(read_bits(16))
    else:
        return ""
    dictionary.append(c)
    w = c
    result.append(c)

    while True:
        if data_index > length:
            return ""
        c = read_bits(num_bits)
        if c == 0:
            dictionary.append(chr(read_bits(8)))
            dict_size += 1
            c = dict_size - 1
            enlarge_in -= 1
        elif c == 1:
            dictionary.append(chr(read_bits(16)))
            dict_size += 1
            c = dict_size - 1
            enlarge_in -= 1
        elif c == 2:
            return "".join(result)

        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1

        if c < len(dictionary) and dictionary[c]:
            entry = dictionary[c]
        elif c == dict_size:
            entry = w + w[0]
        else:
            return None

        result.append(entry)
        dictionary.append(w + entry[0])
        dict_size += 1
        enlarge_in -= 1
        w = entry

        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1


def _to_units(s: str) -> str:
    """把 Python 字符串转为 UTF-16 code unit 序列（每个字符一个 unit）。

    lz-string（JS）按 UTF-16 code unit 处理字符串；Python 的 astral 字符
    （emoji 等，> 0xFFFF）需先拆成代理对，否则 ord() 写 16 位会丢高位。
    """
    if not s:
        return ""
    raw = s.encode("utf-16-le", "surrogatepass")
    return "".join(chr(raw[i] | (raw[i + 1] << 8)) for i in range(0, len(raw), 2))


def _from_units(u: str) -> str:
    """把 UTF-16 code unit 序列还原为 Python 字符串（合并代理对）。"""
    if not u:
        return ""
    raw = bytearray()
    for ch in u:
        o = ord(ch)
        if o > 0xFFFF:   # 理论上不会出现；兜底按完整码点编码
            raw.extend(ch.encode("utf-16-le", "surrogatepass"))
        else:
            raw.append(o & 0xFF)
            raw.append((o >> 8) & 0xFF)
    return raw.decode("utf-16-le", "surrogatepass")


def decompress_from_base64(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"\s+", "", s)
    units = _decompress(len(s), 32, lambda i: _KEY_STR_BASE64.index(s[i]))
    if units is None:
        return ""
    return _from_units(units)


def _compress(uncompressed: str, bits_per_char: int, get_char_from_int) -> str:
    dictionary: dict[str, int] = {}
    dictionary_to_create: dict[str, bool] = {}
    w = ""
    enlarge_in = 2
    dict_size = 3
    num_bits = 2
    data: list[str] = []
    data_val = 0
    data_position = 0

    def write_bit(bit: int) -> None:
        nonlocal data_val, data_position
        data_val = (data_val << 1) | bit
        if data_position == bits_per_char - 1:
            data_position = 0
            data.append(get_char_from_int(data_val))
            data_val = 0
        else:
            data_position += 1

    def write_bits_reversed(value: int, n: int) -> None:
        for _ in range(n):
            write_bit(value & 1)
            value >>= 1

    for c in uncompressed:
        if c not in dictionary:
            dictionary[c] = dict_size
            dict_size += 1
            dictionary_to_create[c] = True
        wc = w + c
        if wc in dictionary:
            w = wc
        else:
            if w in dictionary_to_create:
                if ord(w[0]) < 256:
                    write_bits_reversed(0, num_bits)
                    write_bits_reversed(ord(w[0]), 8)
                else:
                    write_bits_reversed(1, num_bits)
                    write_bits_reversed(ord(w[0]), 16)
                enlarge_in -= 1
                if enlarge_in == 0:
                    enlarge_in = 2 ** num_bits
                    num_bits += 1
                del dictionary_to_create[w]
            else:
                write_bits_reversed(dictionary[w], num_bits)
            enlarge_in -= 1
            if enlarge_in == 0:
                enlarge_in = 2 ** num_bits
                num_bits += 1
            dictionary[wc] = dict_size
            dict_size += 1
            w = c

    if w != "":
        if w in dictionary_to_create:
            if ord(w[0]) < 256:
                write_bits_reversed(0, num_bits)
                write_bits_reversed(ord(w[0]), 8)
            else:
                write_bits_reversed(1, num_bits)
                write_bits_reversed(ord(w[0]), 16)
            enlarge_in -= 1
            if enlarge_in == 0:
                enlarge_in = 2 ** num_bits
                num_bits += 1
            del dictionary_to_create[w]
        else:
            write_bits_reversed(dictionary[w], num_bits)
        enlarge_in -= 1
        if enlarge_in == 0:
            enlarge_in = 2 ** num_bits
            num_bits += 1

    write_bits_reversed(2, num_bits)

    while True:
        data_val = (data_val << 1)
        if data_position == bits_per_char - 1:
            data.append(get_char_from_int(data_val))
            break
        else:
            data_position += 1

    return "".join(data)


def compress_to_base64(s: str) -> str:
    res = _compress(_to_units(s), 6, lambda a: _KEY_STR_BASE64[a])
    pad = {0: "", 1: "===", 2: "==", 3: "="}[len(res) % 4]
    return res + pad


# --------------------------------------------------------------------------- #
# JSON 序列化（与 Excalidraw 一致：tab 缩进、保留非 ASCII）
# --------------------------------------------------------------------------- #

def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent="\t")


def json_loads(raw: str) -> Any:
    return json.loads(raw)


# --------------------------------------------------------------------------- #
# .excalidraw.md 容器
# --------------------------------------------------------------------------- #

def text_blocks_from_elements(elements: list[dict]) -> list[tuple[str, str]]:
    """从 elements 生成 (rawText, id) 列表，供 "## Text Elements" 段。"""
    blocks: list[tuple[str, str]] = []
    for e in elements:
        if e.get("type") == "text" and not e.get("isDeleted"):
            content = e.get("rawText")
            if content is None:
                content = e.get("text", "")
            blocks.append((content, e["id"]))
    return blocks


def parse_text_elements(section: str) -> list[tuple[str, str]]:
    """尽力解析 "## Text Elements" 段为 (rawText, id)。

    注意：JSON 是权威数据，此解析仅用于检查/展示；序列化时从 elements 重新生成。
    """
    blocks: list[tuple[str, str]] = []
    for chunk in section.split("\n\n"):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        m = re.search(r" (\^[A-Za-z0-9]+)$", chunk)
        if m:
            content = chunk[:m.start()]
            eid = m.group(1)[1:]
            blocks.append((content, eid))
        else:
            blocks.append((chunk, ""))
    return blocks


def parse_embedded_files(text: str) -> dict[str, str]:
    """解析 "## Embedded Files" 段：fileId -> [[Vault 文件链接]]。

    插件把图片存为 Vault 里的独立文件时，绘图 JSON 的 files 为空，
    映射关系记录在此段（例如 `172c…: [[{EAE1902D-…}.jpg]]`）。
    """
    m = re.search(r"## Embedded Files\n(.*?)\n\n%%", text, re.DOTALL)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line:
            continue
        mm = re.match(r"^([0-9A-Za-z]+):\s*(.+)$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip()
    return out


def parse_md(text: str, path: str | None = None) -> models.Document:
    """解析 .excalidraw.md 文本为 Document。"""
    m_json = re.search(r"```compressed-json\s*\n(.*?)\n```", text, re.DOTALL)
    if not m_json:
        raise ValueError("未找到 compressed-json 代码块")
    raw = decompress_from_base64(m_json.group(1))
    obj = json_loads(raw)

    text_blocks: list[tuple[str, str]] = []
    # 注意：Text Elements 之后可能是 "## Embedded Files" 或直接 "%%"
    m_te = re.search(r"## Text Elements\n(.*?)\n\n(?:## |%%)", text, re.DOTALL)
    if m_te:
        text_blocks = parse_text_elements(m_te.group(1))

    embedded_files = parse_embedded_files(text)

    m_fm = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    frontmatter = ("---\n" + m_fm.group(1) + "\n---\n") if m_fm else ""

    return models.Document(
        elements=obj.get("elements", []),
        app_state=obj.get("appState", {}),
        files=obj.get("files", {}),
        source=obj.get("source", ""),
        text_blocks=text_blocks,
        embedded_files=embedded_files,
        frontmatter=frontmatter,
        raw_json=raw,
        path=path,
    )


def parse_excalidraw(text: str, path: str | None = None) -> models.Document:
    """解析标准 Excalidraw JSON（``.excalidraw``）为 Document。

    这是与 Obsidian 插件容器无关的纯 JSON 格式：顶层为
    ``{type, version, source, elements, appState, files}``。
    """
    obj = json_loads(text)
    if not isinstance(obj, dict):
        raise ValueError("标准 .excalidraw 文件必须是 JSON 对象")
    elements = obj.get("elements")
    if not isinstance(elements, list):
        raise ValueError("标准 .excalidraw 文件缺少 elements 数组")
    app_state = obj.get("appState")
    files = obj.get("files")
    return models.Document(
        elements=elements,
        app_state=app_state if isinstance(app_state, dict) else {},
        files=files if isinstance(files, dict) else {},
        source=obj.get("source") or "",
        raw_json=text,
        path=path,
    )


def serialize_excalidraw(elements: list[dict], app_state: dict, *,
                         files: dict | None = None,
                         source: str | None = None) -> str:
    """序列化为标准 Excalidraw JSON（``.excalidraw``）。"""
    obj = {
        "type": "excalidraw",
        "version": 2,
        "source": source or styles.STANDALONE_SOURCE,
        "elements": elements,
        "appState": app_state or {},
        "files": files or {},
    }
    return json_dumps(obj) + "\n"


def serialize_md(elements: list[dict], app_state: dict, *,
                 files: dict | None = None, source: str | None = None,
                 frontmatter: str | None = None,
                 embedded_files: dict[str, str] | None = None,
                 text_order: list[str] | None = None) -> str:
    """把原生元素序列化为 .excalidraw.md 文本。

    embedded_files：fileId -> [[Vault 文件链接]]，会写回 "## Embedded Files" 段；
    缺省为空时不输出该段。修改已有文件时必须透传，否则图片引用会丢失。
    """
    source = source or styles.DEFAULT_SOURCE
    files = files or {}
    embedded_files = embedded_files or {}
    frontmatter = frontmatter if frontmatter is not None else DEFAULT_FRONTMATTER

    obj = {
        "type": "excalidraw",
        "version": 2,
        "source": source,
        "elements": elements,
        "appState": app_state,
        "files": files,
    }
    raw = json_dumps(obj)
    b64 = compress_to_base64(raw)
    # 插件格式：每 256 字符一段，段间空一行
    wrapped = "\n\n".join(b64[i:i + 256] for i in range(0, len(b64), 256))

    text_blocks = text_blocks_from_elements(elements)
    if text_order:
        rank = {eid: i for i, eid in enumerate(text_order)}
        text_blocks.sort(key=lambda b: rank.get(b[1], len(rank)))
    te = "\n\n".join(f"{content} ^{eid}" for content, eid in text_blocks)

    emb = ""
    if embedded_files:
        emb = ("## Embedded Files\n"
               + "\n".join(f"{fid}: {link}" for fid, link in embedded_files.items())
               + "\n\n")

    return (
        frontmatter
        + _WARNING + "\n\n\n"
        + "# Excalidraw Data\n\n"
        + "## Text Elements\n"
        + te + "\n\n"
        + emb
        + "%%\n## Drawing\n```compressed-json\n"
        + wrapped + "\n"
        + "```\n%%"
    )
