# 样式规范（styles.py）

样式由脚本里的 `STYLE_PRESETS` 定义，模型只需选择预设名（spec `"style"` 或 CLI `--style`）。
**不要用提示词逐项指定颜色/字体**：提示词无法保证一致性，也无法控制引擎未实现的字段。

## 1. 预设一览

| 预设 | 别名 | 字体 | roughness | 圆角 | 画布 | 适用 |
|---|---|---|---|---|---|---|
| `clean`（默认） | `default` / `print` | Helvetica (2) | 0（规整） | 无（直角） | 白底 | 文档、工程图、汇报 |
| `er` | `erd` / `database` / `schema` | Helvetica (2) | 0 | 有 | 白底 | ER 图、数据库设计 |
| `chen` | — | Helvetica (2) | 0 | 无（直角实体） | 白底 | 经典 Chen 概念 ER 图 |
| `hand` | `sketch` | Excalifont (5) | 1（手绘） | 有 | 白底 | 白板、草图、头脑风暴 |
| `mono` | `grayscale` / `grey` | Helvetica (2) | 0 | 无（直角） | 白底 | 打印、黑白文档 |
| `night` | `dark` | Helvetica (2) | 0 | 有 | `#141414` 深底 | 投屏、深色主题 |

| 预设 | process 填充 | decision 填充 | terminator 填充 | UML 类框填充 | 线条 / 文字 |
|---|---|---|---|---|---|
| `clean` | `#e7f5ff` | `#fff9db` | `#ebfbee` | `#f3f0ff` | `#1e1e1e` |
| `er` | `#e7f5ff` | `#fff9db` | `#ebfbee` | `#f3f0ff` | `#495057` |
| `hand` | `#a5d8ff` | `#ffd8a8` | `#b2f2bb` | `#fff2cc` | `#1e1e1e` |
| `mono` | `#f1f3f5` | `#e9ecef` | `#f8f9fa` | `#ffffff` | `#212529` |
| `night` | `#1971c2` | `#e8590c` | `#2b8a3e` | `#5f3dc4` | `#f8f9fa` / 文字 `#ffffff` |

ER 实体专用颜色（所有预设都提供，`er` 为默认值）：

| 颜色键 | `er` 值 | 用途 |
|---|---|---|
| `entity` | `#ffffff` | 卡片底色 |
| `entity_header` | `#dbe4ff` | 表头色带 |
| `entity_header_text` | `#364fc7` | 表名文字 |
| `entity_muted` | `#868e96` | 字段类型 / 基数标签 |
| `entity_pk` | `#e8590c` | PK 徽标 |
| `entity_fk` | `#1c7ed6` | FK 徽标 |
| `entity_border` | `#ced4da` | 卡片边框 / 分隔线 |
| `group_fill` | `#e9ecef` | 分组顶部色带填充 |
| `group_border` | `#adb5bd` | 分组虚线边框 |
| `group_title` | `#495057` | 分组标题文字 |

Chen 专用颜色（`chen` 预设默认值）：

| 颜色键 | 值 | 用途 |
|---|---|---|
| `chen_entity` | `#e7f5ff` | 实体矩形 |
| `chen_entity_text` | `#1971c2` | 实体名 |
| `chen_relation` | `#fff3bf` | 联系菱形 |
| `chen_relation_text` | `#e67700` | 联系动词 |
| `chen_line` | `#868e96` | 联系线 / 基数标签 |

> `chen_attribute` / `chen_attribute_text` 键保留用于兼容旧文件；经典 Chen 概念图不生成属性椭圆。

公共参数：`strokeWidth=2`（`er` / `chen` 为 1）、`fontSize=20`、边标签 `16`（`er` / `chen` 为 14）、图标题 `28`、`fillStyle=solid`、`opacity=100`；
旁注（`note`）在所有预设下都用标准字体（Helvetica），避免手绘字体影响可读性。

## 2. 使用方式

```json
{"style": "hand", "nodes": [...], "edges": [...]}
```

```bash
excalidraw_cli.py new --sample --style mono -o demo.excalidraw.md
excalidraw_cli.py patch --path x.excalidraw.md --spec spec.json --style night
```

- `new` 不传时默认 `clean`；
- `patch` 不传 `--style` 时**保留现有元素的颜色/字体/粗糙度**（只改结构），传了才整体换风格；
- `canvas.theme` / `canvas.background` 可覆盖预设的画布设置（新建时生效）。

## 3. 节点级覆盖（`node.style`）

```json
{"kind": "process", "text": "异常分支", "sem_id": "err",
 "style": {"backgroundColor": "#ffe3e3", "strokeColor": "#c92a2a"}}
```

支持键：`backgroundColor`、`strokeColor`、`textColor`、`fontFamily`、`fontSize`、
`strokeWidth`、`strokeStyle`、`roughness`、`roundness`。未给出的键沿用预设。
该节点在 `patch` 时视为显式指定，不会被“保留现有样式”覆盖。

## 4. 字体码值

| 常量 | 码值 | 说明 |
|---|---|---|
| `FONT_HAND` | 1 | Virgil（旧手绘字体） |
| `FONT_NORMAL` | 2 | Helvetica（印刷体） |
| `FONT_CODE` | 3 | Cascadia（等宽） |
| `FONT_DEFAULT` | 5 | Excalifont（新手绘字体，插件默认） |

## 5. 箭头

- 普通流程：`endArrowhead = "arrow"`、`startArrowhead = null`；
- UML 关系见 `UML_REL_STYLE`：继承=`triangle_outline`、依赖=虚线箭头、组合=`diamond`（src 端）、聚合=`diamond_outline`（src 端）；
- ER 关系：`1` 端用原生 `bar` 箭头，`N` 端用 3 条短线模拟鸦爪（插件 2.29.0 无 `crowfoot` 箭头类型）；两端都有基数文字；
- 经典 Chen 概念图：实体-联系、联系-实体均为无箭头连线（两端 `arrowhead = null`），基数用文字标在实体端；不生成属性线；
- 端点默认在包围盒外 6px（`BINDING_GAP`）；ER 连线贴边 2px（`ER_TOUCH_GAP`），以保证鸦爪与卡片相接。

## 6. 新增预设

在 `STYLE_PRESETS` 里加一套（键齐全），必要时在 `STYLE_ALIASES` 加别名，然后补
`tests/test_styles.py` 断言关键属性即可；无需改 builder。
