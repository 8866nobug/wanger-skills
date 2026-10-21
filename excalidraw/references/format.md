# Excalidraw 文件格式（已验证，插件 2.29.0）

## 1. 容器结构

`.excalidraw.md` 是 **Markdown 容器文件**，不是纯 JSON。结构如下：

```
---
excalidraw-plugin: parsed
tags: [excalidraw]
---
==⚠  Switch to EXCALIDRAW VIEW ...==（固定警告行）
# Excalidraw Data

## Text Elements
{rawText} ^{元素id}          ← 每个 text 元素一条；多行文本用真实换行，^id 在末行

## Embedded Files
{fileId}: [[Vault 中的图片文件]]   ← 仅当有图片/附件时存在

%%
## Drawing
```compressed-json
<LZ-String base64，每 256 字符一段，段间空一行>
```
%%
```

- **权威数据在 `compressed-json` 里**；`## Text Elements` 段是 text 元素的 rawText + `^id`，仅供 Obsidian 检索/嵌入，由插件从 JSON 派生。
- 序列化时从 elements 重新生成 Text Elements 段，保证两者同步。
- **`## Embedded Files` 必须原样保留**：插件把图片存成 Vault 独立文件时，JSON 的 `files` 为空，fileId→文件路径的映射只记录在这一段。引擎若不回写该段，图片引用会丢失。

## 2. Drawing JSON 顶层键

解压后为 JSON 对象：

| 键 | 含义 |
|---|---|
| `type` | `"excalidraw"` |
| `version` | `2` |
| `source` | 插件来源（实测为 zsviczian/obsidian-excalidraw-plugin 2.29.0） |
| `elements` | 元素数组 |
| `appState` | 画布/工具状态（主题、背景、当前样式、scroll/zoom 等） |
| `files` | 内嵌资源（图片等），键为 fileId，值为 base64；**插件把图片存为 Vault 文件时此处为空**，映射见 `## Embedded Files` |

### 2.1 标准 `.excalidraw`（脱离 Obsidian）

标准 Excalidraw 文件就是上面这个顶层 JSON，**不需要** Markdown 容器、`## Text Elements` 或 `## Embedded Files`：

```json
{"type":"excalidraw","version":2,"source":"https://excalidraw.com",
 "elements":[...],"appState":{...},"files":{}}
```

- 引擎：`adapters.parse_excalidraw()` / `serialize_excalidraw()`；
- CLI：`new --format excalidraw`，或按 `-o` 的 `.excalidraw` 扩展名推断；
- `get` / `validate` / `diff` / `patch` 按扩展名自动识别；
- 标准格式的图片放在 `files`（fileId → base64）；Obsidian 的 Vault 图片映射不会自动转换，含图片时建议保留 `.excalidraw.md`。

## 3. 压缩算法：LZ-String `compressToBase64`

`compressed-json` 代码块内容 = LZ-String 库的 `compressToBase64(JSON字符串)`：

- 编码字符表：`keyStrBase64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="`（6 bit / 字符）。
- LZ 压缩：滑动字典 + 变长位数（初始 2 bit，字典增长时扩展）。
- 结尾按 `% 4` 补齐 `=`（1 个 `===`、2 个 `==`、3 个 `=`）。
- **按 UTF-16 code unit 编码**（JS `charCodeAt` 语义）：astral 字符（emoji 等）须先拆成代理对再压；引擎在 `_to_units` / `_from_units` 中处理。

本引擎 `adapters.py` 已提供纯 Python 实现 `compress_to_base64` / `decompress_from_base64`，**往返字节级一致**（已用 Vault 真实文件验证；emoji 已有单测覆盖）。

## 4. JSON 序列化约定

`json.dumps(obj, ensure_ascii=False, indent="\t")`（tab 缩进、保留非 ASCII、默认分隔符）。

## 5. 元素通用字段

每种元素（`rectangle`/`diamond`/`ellipse`/`line`/`arrow`/`text`）都含：

```jsonc
{
  "id": "8位字母数字", "type": "...", "x": 0, "y": 0, "width": 0, "height": 0,
  "angle": 0, "strokeColor": "#1e1e1e", "backgroundColor": "transparent",
  "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
  "roughness": 1, "opacity": 100, "groupIds": [], "frameId": null,
  "index": "a0", "roundness": null, "seed": 123, "version": 1, "versionNonce": 456,
  "isDeleted": false, "boundElements": [], "updated": 0, "created": 0,
  "link": null, "locked": false, "hasTextLink": false
}
```

- `id`：8 位字母数字（Excalidraw 规格）。
- `index`：分数索引（base62 排序键），决定渲染顺序。Phase 1 用单调递增（`a0`→`a1`→…）。
- `roundness`：rectangle 可为 `{"type":3}` 或 `null`；ellipse 为 `{"type":2}`；其余 `null`。
- `boundElements`：本元素绑定的子元素（如容器内文本 `{"type":"text","id":...}`）或连线引用。

## 6. 类型专有字段

- **line / arrow**：`points`（`[[x0,y0],[x1,y1]]` 相对坐标）、`startBinding`/`endBinding`、`startArrowhead`/`endArrowhead`；line 有 `polygon:false`，arrow 有 `elbowed:false`、`moveMidPointsWithElement:false`。
- **arrow 的 x/y/width/height 约定**：`x,y` = `points[0]` 位置，`width=|dx|`、`height=|dy|`，points 可为负。
- **箭头绑定（实测格式）**：`startBinding`/`endBinding` = `{"elementId": "<形状id>", "mode": "orbit", "fixedPoint": [fx, fy]}`，`fixedPoint` 为相对目标元素包围盒的 `[0,1]` 归一化坐标；同时目标元素 `boundElements` 中需有 `{"type":"arrow","id":"<箭头id>"}`。移动形状时插件据此自动更新箭头。
- **text**：`text`（含显示换行）、`rawText`（未折行原文）、`originalText`、`fontSize`、`fontFamily`、`textAlign`、`verticalAlign`、`containerId`（绑定的容器 id，无则 `null`）、`autoResize`、`lineHeight`、`labelPosition`。
- **Text Elements 段用 `rawText`**（不是 `text`），格式为 `{rawText} ^{id}`。

## 7. 图片 / 嵌入资源（已用真实文件验证）

插件默认把粘贴的图片保存为 **Vault 里的独立文件**（文件名 `{MD5}.扩展名`），绘图元素只记录：

- `image` 元素的 `fileId` = **图片内容的 SHA-1**（40 位十六进制）；
- 顶部 `## Embedded Files` 段：`fileId: [[{MD5}.jpg]]`；
- JSON 的 `files` 为 `{}`（不内嵌 base64）。

因此：`files` 为空 **不代表图片丢失**。校验/修改时必须同时检查 `Embedded Files`；引擎 `Document.embedded_files` 会解析并原样回写，`validate` 对两处都找不到 fileId 的图片给出 warning。

## 8. 其他未验证

- `.excalidrawlib`（库文件，`Excalidraw/Libraries/`）是另一套格式，本引擎暂不处理。
- `files` 内嵌 base64 的图片（插件设置改为内嵌时）尚未遇到真实样本。
