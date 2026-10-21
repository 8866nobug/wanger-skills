"""绘图中间表示（Diagram IR）与原生文档模型。

设计目标（见 SKILL.md / references/）：
- IR 与 Excalidraw 原生格式解耦：用 Node / Edge 描述「要画什么」，
  builder 负责把 IR 转成原生元素 JSON。
- 原生元素在本工程中用 dict 表示，字段名与 Excalidraw JSON 完全一致，
  便于直接 json.dumps / json.loads。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --------------------------------------------------------------------------- #
# Diagram IR（语义层）
# --------------------------------------------------------------------------- #

@dataclass
class Node:
    """一个语义节点。

    kind 取值（与 elements/layout 约定一致）：
        process     处理步骤（矩形）
        decision    条件判断（菱形）
        terminator  开始 / 结束（椭圆）
        uml_class   UML 类框（矩形分区）
        entity      ER 实体表卡片（表名 + 字段列表）
        group       域/分组容器（带标题的背景框，members 为成员 sem_id）
        text        独立文本
        note        画布旁注（标准字体）

    entity 的 fields 为字段列表，每项形如：
        {"name": "id", "type": "bigint", "pk": true, "fk": false,
         "unique": false, "nullable": false, "default": "0"}
    其中 pk/fk/unique 为真时渲染 PK/FK/UQ 徽标；default 追加到类型列。
    Chen 概念模式不渲染 fields；实体显示名优先用 label（中文业务实体名），
    缺省才用 text。

    group 的 members 为成员节点的 sem_id 列表；组内节点会成块布局，
    并作为一个 Excalidraw 外层 group 与背景框一起拖动。
    """
    kind: str
    text: str
    sem_id: str | None = None              # 稳定语义 ID，用于幂等定位与连线引用
    style: dict[str, Any] = field(default_factory=dict)   # 覆盖 styles 默认值
    fields: list[dict[str, Any]] = field(default_factory=list)  # entity 字段列表
    members: list[str] = field(default_factory=list)            # group 成员 sem_id
    label: str = ""                                            # 概念图中文显示名


@dataclass
class Edge:
    """一条有向边，用语义 ID 引用起止节点。

    rel 用于 UML 关系："" / inherit / assoc / depend / compose / aggregate /
    er（ER 关系，两实体之间默认即 ER 连线）。
    arrow 用于普通流程图箭头：arrow | none | diamond | bar。
    cardinality 用于 ER：形如 "1:N" / "0..1:N" / "N:M" / "1:1"，
    冒号左侧作用于 src、右侧作用于 dst；也接受 "→" / "->" 分隔。
    sem_id 可选，用于区分同一对表之间的多条关系。
    """
    src: str
    dst: str
    label: str = ""
    arrow: str = "arrow"
    rel: str = ""
    cardinality: str = ""
    sem_id: str | None = None


@dataclass
class Canvas:
    """画布信息。width/height 为 0 时表示按内容自动计算。

    theme/background 为空时使用所选样式预设的默认值。
    """
    width: int = 0
    height: int = 0
    theme: str = ""
    background: str = ""


@dataclass
class Diagram:
    """绘图中间表示。

    style：样式预设名（clean / er / chen / hand / mono / night），空则用 DEFAULT_STYLE。
    notation：ER 记法，"crowfoot"（默认，表卡片+鸦爪）或 "chen"（矩形实体/菱形关系/椭圆属性）。
    title：图标题，渲染在主图上方居中；按约定使用中文。
    """
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    canvas: Canvas = field(default_factory=Canvas)
    style: str = ""
    notation: str = ""
    title: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# 原生文档（.excalidraw.md 解析结果）
# --------------------------------------------------------------------------- #

@dataclass
class Document:
    """一份 .excalidraw.md 的解析结果。"""
    elements: list[dict[str, Any]]
    app_state: dict[str, Any]
    files: dict[str, Any]
    source: str
    text_blocks: list[tuple[str, str]] = field(default_factory=list)  # (rawText, element_id)
    embedded_files: dict[str, str] = field(default_factory=dict)  # fileId -> [[Vault 文件链接]]
    frontmatter: str = ""
    raw_json: str = ""          # 解压后的原始 JSON 字符串（供高保真回写）
    path: str | None = None
