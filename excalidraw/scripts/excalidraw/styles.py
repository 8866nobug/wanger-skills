"""绘图样式规范常量与新建文件的默认 appState。

默认值取自 Vault 中真实 Excalidraw 文件（插件 zsviczian/obsidian-excalidraw-plugin
2.29.0）的观测结果，保证生成结果与该插件兼容。
"""
from __future__ import annotations

# 字体族（Excalidraw fontFamily 枚举，具体码值以插件为准）
FONT_HAND = 1        # 手绘字体（主流程用，值待插件确认）
FONT_NORMAL = 2      # 标准字体（旁注用，值待插件确认）
FONT_CODE = 3        # 等宽字体
FONT_DEFAULT = 5     # 观测到的默认字体码

# 颜色
STROKE = "#1e1e1e"
BACKGROUND_TRANSPARENT = "transparent"
COLOR_PROCESS = "#a5d8ff"       # 矩形（处理步骤）
COLOR_DECISION = "#ffd8a8"      # 菱形（条件判断）
COLOR_TERMINATOR = "#b2f2bb"    # 椭圆（开始 / 结束）
COLOR_UML_CLASS = "#fff2cc"     # UML 类框
COLOR_NOTE = "#ffffff"          # 旁注

# 描边与粗糙度（手绘风格）
STROKE_WIDTH = 2
STROKE_STYLE = "solid"
ROUGHNESS = 1
OPACITY = 100

# 文字
FONT_SIZE = 20
LINE_HEIGHT = 1.25
TITLE_FONT_SIZE = 28        # 图标题字号
TITLE_GAP = 36              # 标题与主图顶部的间距
TITLE_SEM_ID = "__title"    # 标题元素的语义 ID
TEXT_ALIGN_CENTER = "center"
TEXT_ALIGN_LEFT = "left"
TEXT_ALIGN_RIGHT = "right"
V_ALIGN_MIDDLE = "middle"
V_ALIGN_TOP = "top"

# 箭头
END_ARROWHEAD = "arrow"
START_ARROWHEAD = None

# UML 关系样式：rel -> (startArrowhead, endArrowhead, strokeStyle)
# 组合/聚合的菱形在「整体/拥有」端（即 src）。
UML_REL_STYLE = {
    "inherit":   (None, "triangle_outline", "solid"),   # 继承 / 实现（空心三角）
    "assoc":     (None, "arrow", "solid"),              # 关联
    "depend":    (None, "arrow", "dashed"),             # 依赖
    "compose":   ("diamond", None, "solid"),            # 组合（实心菱形）
    "aggregate": ("diamond_outline", None, "solid"),    # 聚合（空心菱形）
}

# 布局
NODE_W = 200            # 处理步骤默认宽
NODE_H = 60             # 处理步骤默认高
DECISION_W = 240        # 菱形默认宽
DECISION_H = 120        # 菱形默认高
TERMINATOR_W = 160      # 椭圆默认宽
TERMINATOR_H = 60       # 椭圆默认高
VGAP = 90               # 纵向节点间距（中心距）
HGAP = 80               # 横向节点间距（中心距）
NOTE_GAP = 120          # 主图与旁注列的水平间距
BINDING_GAP = 6.0       # 箭头端点与形状包围盒的间距（与插件实测一致）

# --------------------------------------------------------------------------- #
# ER 图（实体卡片 + 鸦爪关系线）
# --------------------------------------------------------------------------- #
ENTITY_MIN_W = 240          # 实体卡片最小宽
ENTITY_HEADER_H = 46        # 表名区高度
ENTITY_ROW_H = 30           # 单个字段行高
ENTITY_PAD = 14             # 卡片内边距
ENTITY_FIELD_FONT_SIZE = 15 # 字段文字大小
ENTITY_HEADER_FONT_SIZE = 18  # 表名文字大小
ENTITY_BADGE_W = 38         # PK/FK 徽标列宽
ENTITY_TYPE_GAP = 24        # 字段名与类型之间的最小间距
ER_HGAP = 170               # ER 布局列间距
ER_VGAP = 60                # ER 布局同列节点间距
ER_COMPONENT_GAP = 240      # 连通分量之间的间距
ER_MAX_ROW_W = 2800         # 连通分量换行宽度
ER_TOUCH_GAP = 2.0          # ER 连线端点与卡片的间距（几乎贴边）
CROWFOOT_LEN = 12.0         # 鸦爪符号长度
CROWFOOT_SPREAD = 8.5       # 鸦爪符号张角半宽
CARD_LABEL_GAP = 24.0       # 基数标签沿连线方向的偏移（避开鸦爪）
CARD_LABEL_PERP = 12.0      # 基数标签垂直连线方向的偏移

# --------------------------------------------------------------------------- #
# 分组 / 域容器
# --------------------------------------------------------------------------- #
GROUP_PAD = 24              # 容器内边距
GROUP_HEADER_H = 44         # 容器标题区高度
GROUP_GAP = 90              # 容器之间的间距
GROUP_MIN_W = 240           # 容器最小宽
GROUP_TITLE_FONT_SIZE = 18  # 容器标题字号

# --------------------------------------------------------------------------- #
# 经典 Chen 概念 ER 图（矩形实体 / 菱形联系 / 连线 + 基数）
# --------------------------------------------------------------------------- #
CHEN_ENTITY_FONT_SIZE = 18
CHEN_ENTITY_PAD = 20
CHEN_ENTITY_MIN_W = 140
CHEN_ENTITY_H = 60
CHEN_REL_FONT_SIZE = 14
CHEN_REL_MIN_W = 130
CHEN_REL_MIN_H = 90
CHEN_REL_CLEARANCE = 24     # 联系菱形与实体/其他菱形的最小间距
CHEN_LABEL_CLEARANCE = 6    # 基数标签与其他元素的最小间距
CHEN_SEARCH_STEP = 12       # 冲突避让搜索步长
CHEN_SEARCH_RINGS = 60      # 冲突避让最大搜索环数（约 720px）

# --------------------------------------------------------------------------- #
# 样式预设
# --------------------------------------------------------------------------- #
# 每套预设覆盖：画布主题/底色、线条、字体、圆角、粗糙度、各类节点填充色。
# 模型只需在 spec 里写 "style": "<预设名>"（或 CLI --style），不用逐项给颜色。
#
# fontFamily 码值：2=Helvetica（印刷体）、5=Excalifont（手绘）、3=Cascadia（等宽）
# roughness：0=规整直尺线、1=手绘抖动、2=更夸张的手绘

STYLE_PRESETS: dict[str, dict] = {
    # 简洁归整：印刷体、无抖动、浅色填充、直角 —— 默认
    "clean": {
        "theme": "light",
        "background": "#ffffff",
        "stroke": "#1e1e1e",
        "text": "#1e1e1e",
        "arrow_stroke": "#1e1e1e",
        "font_family": 2,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 16,
        "stroke_width": 2,
        "stroke_style": "solid",
        "roughness": 0,
        "fill_style": "solid",
        "roundness": None,
        "colors": {
            "process": "#e7f5ff",
            "decision": "#fff9db",
            "terminator": "#ebfbee",
            "uml_class": "#f3f0ff",
            "entity": "#ffffff",
            "entity_header": "#e7f5ff",
            "entity_header_text": "#1971c2",
            "entity_muted": "#868e96",
            "entity_pk": "#e8590c",
            "entity_fk": "#1c7ed6",
            "entity_border": "#ced4da",
            "group_fill": "#e9ecef",
            "group_border": "#adb5bd",
            "group_title": "#495057",
            "chen_entity": "#e7f5ff",
            "chen_entity_text": "#1971c2",
            "chen_attribute": "#ebfbee",
            "chen_attribute_text": "#2b8a3e",
            "chen_relation": "#fff3bf",
            "chen_relation_text": "#e67700",
            "chen_line": "#868e96",
        },
    },
    # ER 专用：白色表卡片、淡靛蓝表头、灰色类型、橙色 PK / 蓝色 FK
    "er": {
        "theme": "light",
        "background": "#ffffff",
        "stroke": "#495057",
        "text": "#212529",
        "arrow_stroke": "#868e96",
        "font_family": 2,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 14,
        "stroke_width": 1,
        "stroke_style": "solid",
        "roughness": 0,
        "fill_style": "solid",
        "roundness": {"type": 3},
        "colors": {
            "process": "#e7f5ff",
            "decision": "#fff9db",
            "terminator": "#ebfbee",
            "uml_class": "#f3f0ff",
            "entity": "#ffffff",
            "entity_header": "#dbe4ff",
            "entity_header_text": "#364fc7",
            "entity_muted": "#868e96",
            "entity_pk": "#e8590c",
            "entity_fk": "#1c7ed6",
            "entity_border": "#ced4da",
            "group_fill": "#e9ecef",
            "group_border": "#adb5bd",
            "group_title": "#495057",
            "chen_entity": "#e7f5ff",
            "chen_entity_text": "#1971c2",
            "chen_attribute": "#ebfbee",
            "chen_attribute_text": "#2b8a3e",
            "chen_relation": "#fff3bf",
            "chen_relation_text": "#e67700",
            "chen_line": "#868e96",
        },
    },
    # Chen 记法：矩形实体（浅蓝）、菱形关系（浅黄）、椭圆属性（浅绿）
    "chen": {
        "theme": "light",
        "background": "#ffffff",
        "stroke": "#495057",
        "text": "#212529",
        "arrow_stroke": "#868e96",
        "font_family": 2,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 14,
        "stroke_width": 1,
        "stroke_style": "solid",
        "roughness": 0,
        "fill_style": "solid",
        "roundness": None,
        "colors": {
            "process": "#e7f5ff",
            "decision": "#fff9db",
            "terminator": "#ebfbee",
            "uml_class": "#f3f0ff",
            "entity": "#ffffff",
            "entity_header": "#dbe4ff",
            "entity_header_text": "#364fc7",
            "entity_muted": "#868e96",
            "entity_pk": "#e8590c",
            "entity_fk": "#1c7ed6",
            "entity_border": "#ced4da",
            "group_fill": "#e9ecef",
            "group_border": "#adb5bd",
            "group_title": "#495057",
            "chen_entity": "#e7f5ff",
            "chen_entity_text": "#1971c2",
            "chen_attribute": "#ebfbee",
            "chen_attribute_text": "#2b8a3e",
            "chen_relation": "#fff3bf",
            "chen_relation_text": "#e67700",
            "chen_line": "#868e96",
        },
    },
    # 手绘：Excalifont + 抖动线条 + 原有高饱和马卡龙色
    "hand": {
        "theme": "light",
        "background": "#ffffff",
        "stroke": "#1e1e1e",
        "text": "#1e1e1e",
        "arrow_stroke": "#1e1e1e",
        "font_family": 5,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 16,
        "stroke_width": 2,
        "stroke_style": "solid",
        "roughness": 1,
        "fill_style": "solid",
        "roundness": {"type": 3},
        "colors": {
            "process": "#a5d8ff",
            "decision": "#ffd8a8",
            "terminator": "#b2f2bb",
            "uml_class": "#fff2cc",
            "entity": "#ffffff",
            "entity_header": "#ffec99",
            "entity_header_text": "#1e1e1e",
            "entity_muted": "#868e96",
            "entity_pk": "#e8590c",
            "entity_fk": "#1971c2",
            "entity_border": "#1e1e1e",
            "group_fill": "#fff9db",
            "group_border": "#1e1e1e",
            "group_title": "#1e1e1e",
            "chen_entity": "#a5d8ff",
            "chen_entity_text": "#1e1e1e",
            "chen_attribute": "#b2f2bb",
            "chen_attribute_text": "#1e1e1e",
            "chen_relation": "#ffd8a8",
            "chen_relation_text": "#1e1e1e",
            "chen_line": "#1e1e1e",
        },
    },
    # 灰度打印：白/浅灰填充、直角、黑色细线，适合嵌入文档或打印
    "mono": {
        "theme": "light",
        "background": "#ffffff",
        "stroke": "#212529",
        "text": "#212529",
        "arrow_stroke": "#212529",
        "font_family": 2,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 16,
        "stroke_width": 2,
        "stroke_style": "solid",
        "roughness": 0,
        "fill_style": "solid",
        "roundness": None,
        "colors": {
            "process": "#f1f3f5",
            "decision": "#e9ecef",
            "terminator": "#f8f9fa",
            "uml_class": "#ffffff",
            "entity": "#ffffff",
            "entity_header": "#f1f3f5",
            "entity_header_text": "#212529",
            "entity_muted": "#868e96",
            "entity_pk": "#212529",
            "entity_fk": "#212529",
            "entity_border": "#ced4da",
            "group_fill": "#f1f3f5",
            "group_border": "#adb5bd",
            "group_title": "#212529",
            "chen_entity": "#f1f3f5",
            "chen_entity_text": "#212529",
            "chen_attribute": "#ffffff",
            "chen_attribute_text": "#212529",
            "chen_relation": "#e9ecef",
            "chen_relation_text": "#212529",
            "chen_line": "#212529",
        },
    },
    # 深色演示：深底浅字、高对比填充，适合投屏/大屏
    "night": {
        "theme": "dark",
        "background": "#141414",
        "stroke": "#f8f9fa",
        "text": "#ffffff",
        "arrow_stroke": "#f8f9fa",
        "font_family": 2,
        "note_font_family": 2,
        "font_size": 20,
        "label_font_size": 16,
        "stroke_width": 2,
        "stroke_style": "solid",
        "roughness": 0,
        "fill_style": "solid",
        "roundness": {"type": 3},
        "colors": {
            "process": "#1971c2",
            "decision": "#e8590c",
            "terminator": "#2b8a3e",
            "uml_class": "#5f3dc4",
            "entity": "#1e1e1e",
            "entity_header": "#364fc7",
            "entity_header_text": "#dbe4ff",
            "entity_muted": "#adb5bd",
            "entity_pk": "#ffa94d",
            "entity_fk": "#74c0fc",
            "entity_border": "#495057",
            "group_fill": "#25262b",
            "group_border": "#495057",
            "group_title": "#dee2e6",
            "chen_entity": "#1971c2",
            "chen_entity_text": "#ffffff",
            "chen_attribute": "#2b8a3e",
            "chen_attribute_text": "#ffffff",
            "chen_relation": "#e8590c",
            "chen_relation_text": "#ffffff",
            "chen_line": "#adb5bd",
        },
    },
}

# 常用别名（大小写不敏感）
STYLE_ALIASES = {
    "default": "clean",
    "print": "clean",
    "sketch": "hand",
    "grayscale": "mono",
    "grey": "mono",
    "dark": "night",
    "erd": "er",
    "database": "er",
    "schema": "er",
}

DEFAULT_STYLE = "clean"


def style_names() -> list[str]:
    return list(STYLE_PRESETS)


def get_preset(name: str | None = None) -> dict:
    """按名称取样式预设（未知名称抛出带可选列表的 KeyError）。"""
    key = (name or DEFAULT_STYLE).strip().lower()
    key = STYLE_ALIASES.get(key, key)
    if key not in STYLE_PRESETS:
        raise KeyError(
            f"未知样式 {name!r}；可选：{', '.join(STYLE_PRESETS)}"
            f"（别名：{', '.join(STYLE_ALIASES)}）")
    preset = dict(STYLE_PRESETS[key])
    preset["colors"] = dict(preset["colors"])
    return preset


# 新建文件的默认来源（与 Vault 插件版本一致）
DEFAULT_SOURCE = (
    "https://github.com/zsviczian/obsidian-excalidraw-plugin/releases/tag/2.29.0"
)
# 标准 .excalidraw（脱离 Obsidian）的来源标记
STANDALONE_SOURCE = "https://excalidraw.com"

# 新建文件的默认 appState（基于观测到的模板，重置滚动与缩放）
DEFAULT_APP_STATE: dict = {
    "theme": "light",
    "viewBackgroundColor": "#ffffff",
    "currentItemStrokeColor": STROKE,
    "currentItemBackgroundColor": BACKGROUND_TRANSPARENT,
    "currentItemFillStyle": "solid",
    "currentItemStickynoteStrokeColor": STROKE,
    "currentItemStrokeWidthKey": "medium",
    "currentItemStrokeVariability": "constant",
    "currentItemStrokeStyle": STROKE_STYLE,
    "currentItemRoughness": ROUGHNESS,
    "currentItemOpacity": OPACITY,
    "currentItemFontFamily": FONT_DEFAULT,
    "currentItemFontSize": FONT_SIZE,
    "currentItemTextAlign": "left",
    "currentItemStartArrowhead": START_ARROWHEAD,
    "currentItemEndArrowhead": END_ARROWHEAD,
    "currentItemArrowType": "round",
    "currentItemFrameRole": None,
    "scrollX": 0,
    "scrollY": 0,
    "zoom": {"value": 1},
    "currentItemRoundness": "round",
    "gridSize": 20,
    "gridStep": 5,
    "gridModeEnabled": False,
    "gridColor": {
        "Bold": "rgba(179, 179, 179, 0.5)",
        "Regular": "rgba(204, 204, 204, 0.5)",
    },
    "colorTopPicks": {
        "elementStroke": None,
        "elementBackground": None,
        "bucketFill": None,
        "stickyNoteStroke": None,
        "stickyNoteBackground": None,
    },
    "fontTopPicks": None,
    "currentStrokeOptions": None,
    "frameRendering": {
        "enabled": True,
        "clip": True,
        "name": True,
        "outline": True,
        "markerName": True,
        "markerEnabled": True,
    },
    "objectsSnapModeEnabled": False,
    "activeTool": {
        "type": "selection",
        "customType": None,
        "locked": False,
        "fromSelection": False,
        "lastActiveTool": None,
    },
    "disableContextMenu": False,
    "bindingPreference": "enabled",
    "isMidpointSnappingEnabled": True,
    "boxSelectionMode": "contain",
    "inputDevice": "auto",
}
