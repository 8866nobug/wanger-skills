---
name: excalidraw
description: 创建、读取或修改 Obsidian Vault 中的 Excalidraw 图表（流程图 / ER 实体关系图（鸦爪或经典 Chen 概念图） / UML 类图 / 域分组容器 / 画布旁注）。当用户要求画流程图、ER 图、经典 Chen 概念 ER 图、数据库表关系图、类图、带分组的架构/域图、生成或改动 .excalidraw 文件、或分析与校验现有 Excalidraw 绘图时使用。分工：Claude 理解需求、分析笔记、设计图表语义并编写绘图 spec；确定性 Python 引擎（scripts/excalidraw/）负责元素生成、ID 管理、lz-string 解析/序列化、结构校验与安全写入（自动备份）。只使用标准库，不安装依赖。
argument-hint: "[new|get|validate|diff|patch] 图表的 spec 或目标文件"
allowed-tools: Read, Grep, Glob, Bash(python:*)
---

# Excalidraw 绘图引擎（excalidraw）

为 Obsidian Vault 中的 Excalidraw 图表提供**可测试、可复用**的生成 / 解析 / 校验 / 安全写入能力。

核心分工（不要混淆）：
- **Claude**：理解需求、阅读相关笔记、设计图表语义（节点/连线/分支/旁注）、编写绘图 spec、规划局部修改。
- **Python 引擎**：生成原生元素、分配 ID 与 index、lz-string 编解码、`.excalidraw.md` 容器读写、结构校验、备份与安全写入。

> ❌ 禁止：在未用引擎解析/校验的情况下，凭空手写完整 `.excalidraw.md` 内容并直接覆盖已有绘图。生成与写入必须走引擎。

## 0. 环境

- Vault 根目录：由用户环境决定。优先用 Obsidian MCP `vault_list` 确认，或读取环境变量 `EXCALIDRAW_VAULT`；不要把个人绝对路径写死。
- 绘图目录：`<Vault>/Excalidraw/`（`.excalidraw.md` 是 Markdown 容器文件，不是纯 JSON）
- 引擎入口：`~/.claude/skills/excalidraw/scripts/excalidraw_cli.py`（Python 3.10+，仅标准库）
- 路径含空格或反引号时，在 shell 里用单引号包裹并转义反引号。

## 1. 命令参考

引擎统一入口（在任意目录执行）：

```bash
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py <子命令> ...
```

| 子命令 | 用途 |
|---|---|
| `new` | 根据 spec 生成新绘图（`--spec-inline '<json>'` 或 `--spec <file>` 或 `--sample [flow\|er\|er-groups\|chen]`），`-o` 输出路径；`--style clean\|er\|chen\|hand\|mono\|night` 选样式 |
| `get` | 读取并概览绘图（元素数/类型分布/source + 校验结果） |
| `validate` | 校验结构与引用一致性（退出码非 0 表示有 error） |
| `diff` | 比较两个绘图的元素差异（added/removed/updated） |
| `patch` | 按 spec 增量修改现有绘图（声明式对账：复用 id、删除消失元素、保留手绘、**默认保留现有位置/尺寸/箭头/颜色字体**），`-o` 缺省原地回写（自动备份）；`--relayout` 强制重排，`--style` 强制换成指定预设 |

### new 的 spec 格式

```json
{
  "style": "clean",
  "nodes": [
    {"kind": "terminator", "text": "开始", "sem_id": "start"},
    {"kind": "process",     "text": "处理请求", "sem_id": "p1"},
    {"kind": "decision",    "text": "是否通过校验", "sem_id": "d1"},
    {"kind": "uml_class",   "text": "User\n---\nid: Long\nname: String", "sem_id": "c1"},
    {"kind": "note",        "text": "旁注：这里的逻辑见 xxx.md", "sem_id": "n1"}
  ],
  "edges": [
    {"src": "start", "dst": "p1"},
    {"src": "p1",    "dst": "d1"},
    {"src": "d1",    "dst": "c1", "label": "是"},
    {"src": "c1",    "dst": "c2", "rel": "inherit"}
  ]
}
```

- `kind`：`terminator`（椭圆，开始/结束）、`process`（矩形）、`decision`（菱形）、`uml_class`（类框）、`entity`（ER 表卡片）、`group`（域容器，`members` 为成员 `sem_id`）、`text`（独立文本）、`note`（旁注，标准字体）。
- `uml_class` 用 `\n---\n` 分隔「类名 / 属性 / 方法」三段，渲染为带分隔线的类框。
- `entity.label`（可选）：经典 Chen 概念图的中文业务实体名；Chen 模式优先使用，缺省回退 `text`。
- `sem_id`：稳定语义 ID，供 `edges` 引用，也用于幂等定位。
- `edge.label` 会在箭头中点旁生成标签文本。
- `edge.rel`（UML 关系，可选）：`inherit` / `assoc` / `depend` / `compose` / `aggregate`，控制箭头样式（组合/聚合的菱形在 `src` 端）。
- `edge.cardinality`（ER 关系，可选）：`"1:N"` / `"0..1:N"` / `"N:M"` / `"1:1"`，冒号左侧作用于 `src`、右侧作用于 `dst`；`1` 画竖杠，`N` 画鸦爪，并在两端生成基数标签。
- `edge.sem_id`（可选）：区分同一对表之间的多条关系（缺省用 `src>dst`）。
- `title`（可选）：图标题，渲染在主图上方居中；按约定使用中文。
- `notation`（可选）：`"crowfoot"`（默认，表卡片 + 鸦爪）或 `"chen"`（经典 Chen 概念图，见下节）。
- 布局：有边时用**分层流程布局**（分支横向展开、汇合点按父节点重心居中，多轮 barycenter 扫描降低边交叉）；含 `entity` 时改用 **ER 布局**（按连通分量 BFS 分列、列内中位数排序、分量网格铺开）；无边的节点纵向排列；`note`/`text` 放在主图右侧独立旁注列；流程/UML 边标签会在线段中点附近搜索空位，避免压住节点和其他标签。
- 箭头两端**绑定到形状**（`startBinding`/`endBinding`，`mode: "orbit"`）：在 Obsidian 中拖动形状时箭头会自动跟随。
- `style`（可选）：样式预设名，缺省 `clean`。也可用 CLI `--style` 覆盖。
- `node.style`（可选）：按节点局部覆盖 `backgroundColor` / `strokeColor` / `textColor` / `fontFamily` / `fontSize` / `strokeWidth` / `strokeStyle` / `roughness` / `roundness`。`entity` 额外支持 `headerColor`（表头色带）与 `headerTextColor`（表名颜色）。

### ER 图的 spec 格式

```json
{
  "style": "er",
  "title": "订单与用户 ER 图",
  "nodes": [
    {"kind": "entity", "text": "user", "sem_id": "user",
     "fields": [
       {"name": "id", "type": "bigint", "pk": true},
       {"name": "account_id", "type": "bigint", "fk": true},
       {"name": "email", "type": "varchar(255)", "unique": true},
       {"name": "name", "type": "varchar(80)"},
       {"name": "created_at", "type": "timestamp"}
     ]},
    {"kind": "entity", "text": "order", "sem_id": "order",
     "fields": [
       {"name": "id", "type": "bigint", "pk": true},
       {"name": "user_id", "type": "bigint", "fk": true},
       {"name": "total", "type": "numeric(12,2)"}
     ]}
  ],
  "edges": [
    {"src": "user", "dst": "order", "cardinality": "1:N",
     "label": "下单", "sem_id": "user_order"}
  ]
}
```

字段可选项：`pk`（PK 徽标，橙色）、`fk`（FK 徽标，蓝色）、`unique`（UQ 徽标）、
`default`（追加到类型列，如 `"= 'pending'"`）。表卡片由「表名色带 + 字段行」组成，
字段名左对齐、类型右对齐；同一张表的多条关系会自动分散到卡片同侧的不同连接点。
两条 `entity` 之间的边即使不写 `cardinality` 也会按 ER 连线（正交折线、无箭头、无符号）。

### ER 内容与语言规范

写 ER spec 时必须遵守：

- **表名、字段名**：保留数据库实际英文标识符（snake_case），不翻译、不改写。
- **数据类型、约束标记**：保留数据库原始形式，如 `bigint`、`varchar(255)`、`numeric(12,2)`、`PK`、`FK`、`UQ`。
- **关系名称**（`edge.label`）：默认使用简洁准确的中文动词或动宾短语，如「下单」「包含」「归属」「关联」「支付」「归类」。
- **默认值、枚举值**：与数据库定义一致，不擅自翻译（如 `'pending'`、`'free'`、`'CNY'`）。
- **图标题、图例、分组标题、补充注释**：默认中文。标题用 spec `title`；图例/补充注释用 `note`；分组标题用 `text`（当前引擎不生成容器/分组框）。
- **混合排版**：中文标签与英文标识符分字段处理；不要把表名/字段名/类型翻译成中文，也不要把中文写进字段名。

> 引擎不会自动翻译任何内容；以上规则由编写 spec 的 Claude 执行。英文标识符和中文说明可以同时出现，但必须各归其位。

### 分组 / 域容器（group）

```json
{
  "nodes": [
    {"kind": "group", "text": "交易域", "sem_id": "grp_trade",
     "members": ["order", "order_item", "payment"]},
    {"kind": "entity", "text": "order", "sem_id": "order", "fields": [...]}
  ]
}
```

- `group` 是**视觉容器**：透明底 + 顶部色带 + 虚线边框 + 左上角中文标题；透明底保证 patch 新增组时也不会盖住已有卡片；
- `members` 必须是形状节点（`entity` / `process` / `decision` / `terminator` / `uml_class`）的 `sem_id`，不能是 `note` / `text`，也不能一个节点属于多个组；
- 组成员在布局时**单独成块**（含 `entity` 用 ER 布局，其余用流程布局），组块之间按网格铺开；跨组边仍正常绘制，但不参与组内布局；
- 成员元素和背景框会放进同一个 **Excalidraw 外层 group**（实体自身的 group 为内层，`groupIds` 顺序为内→外），拖动组内任意元素会整体移动；
- 自关联节点在组内会尽量排到右侧，让回环落在组外空白处；
- `group` 目前只支持**一层**，不支持组嵌套；`sem_id` 必须唯一且不能与普通节点冲突。

内置分组样例：

```bash
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample er-groups -o er-groups.excalidraw.md
```

### 经典 Chen 概念 ER 图（`notation: "chen"`）

只表达**业务实体、实体之间的业务联系及联系基数**；不展示属性，也不展示任何数据库物理实现细节。

```json
{
  "style": "chen",
  "notation": "chen",
  "title": "订单业务概念 ER 图",
  "nodes": [
    {"kind": "entity", "text": "user", "label": "用户", "sem_id": "user",
     "fields": [{"name": "id", "type": "bigint", "pk": true}]},
    {"kind": "entity", "text": "order", "label": "订单", "sem_id": "order",
     "fields": [{"name": "id", "type": "bigint", "pk": true}]}
  ],
  "edges": [
    {"src": "user", "dst": "order", "cardinality": "1:N",
     "label": "下单", "sem_id": "user_order"}
  ]
}
```

- **实体**：矩形，内部使用 `label`（中文业务实体名）；缺省才回退 `text`。默认要求名称为中文。
- **联系**：每条 `edge` 生成一个菱形，内部是 `edge.label` 的中文业务动词/短语；**必须有中文 label**，不会自动填「关联」，也不会从外键或字段推断联系。
- **关系**：实体与菱形之间用无箭头连线连接。
- **基数**：在连线靠近实体的一端标注 `1` / `N` / `M`，也支持 `0..1` / `0..N` / `1..N`；未提供 `cardinality` 时不标注，不擅自推断。基数由 spec 显式给出，引擎只校验写法，不推断业务规则。
- **禁止**：属性椭圆、字段名、数据类型、PK/FK/UQ、默认值、索引等物理信息。`entity.fields` 在 Chen 模式下会被**完全忽略**，同一份 spec 仍可用于鸦爪模式。
- **布局**：实体矩形按 `er_layout` 分列，列间距/行间距根据实际菱形尺寸自动放大；联系菱形放在两个实体之间的空隙中，并按 AABB 做冲突避让（实体、其他菱形、组标题、旁注），同一对实体的多条联系沿垂直方向错开；自关联菱形绕实体旋转搜索空位；基数标签在实体端附近搜索无冲突位置。优先减少连线交叉。已有 Chen 图不会自动重排，需重新 `new` 或 `patch --relayout` 才会应用新的防重叠布局。
- **分组**：`group` 仅在明确需要业务域时使用；组框会扩大以包住组内实体**和组内联系菱形**（包括自关联），同域联系放入同一外层 group，跨域联系菱形独立并避开组框。
- **生成后校验**：只允许实体矩形、联系菱形、联系连线与文本；检测属性/字段/物理信息、联系端点是否正确、联系连线是否误带箭头、基数写法是否合法；连线交叉以 `chen-line-crossing` warning 提示，实体/菱形/基数标签的块重叠以 `chen-element-overlap` warning 提示。
- **限制**：Chen 模式只接受 `entity` / `group` / `note` / `text`；`entity` 必须有 `sem_id`，边的两端必须是 entity；暂不支持弱实体、多值/复合属性、关系属性、全/部分参与等扩展记法。

内置样例（三个业务实体、两条联系、无属性）：

```bash
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample chen -o chen-demo.excalidraw.md
```

### 样式预设

| 预设 | 别名 | 适用 | 特征 |
|---|---|---|---|
| `clean` | `default` / `print` | 默认，文档/工程图 | Helvetica、无手绘抖动（roughness 0）、浅色填充、直角 |
| `er` | `erd` / `database` / `schema` | ER 图 / 数据库设计 | 白色圆角表卡片、淡靛蓝表头、灰色类型、橙色 PK / 蓝色 FK、细灰连线 |
| `chen` | — | 经典 Chen 概念 ER 图 | 浅蓝实体矩形、浅黄联系菱形、细灰连线、直角实体 |
| `hand` | `sketch` | 白板/草图风格 | Excalifont 手绘字体、roughness 1、高饱和马卡龙色 |
| `mono` | `grayscale` / `grey` | 打印/黑白文档 | 白灰填充、黑线、直角、Helvetica |
| `night` | `dark` | 投屏/深色主题 | 深色画布 `#141414`、浅色线条与文字、高对比填充 |

> 分组容器颜色键：`group_fill`（背景）、`group_border`（边框）、`group_title`（标题），所有预设都提供。

> 样式由 `scripts/excalidraw/styles.py` 的 `STYLE_PRESETS` 统一定义；**不要在提示词里逐项指定颜色**，用预设名即可。需要新风格时在 `STYLE_PRESETS` 加一套并补测试。

### 常用调用示例

```bash
# 新建流程图（内联 spec，默认 clean 样式）
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new \
  --spec-inline '{"nodes":[{"kind":"terminator","text":"开始","sem_id":"s"},{"kind":"terminator","text":"结束","sem_id":"e"}],"edges":[{"src":"s","dst":"e"}]}' \
  -o '<Vault>/Excalidraw/demo.excalidraw.md'

# 新建 ER 图（内置 7 表样板：账号/用户/订单/商品/支付 + 自关联分类）
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample er \
  -o '<Vault>/Excalidraw/er-demo.excalidraw.md'

# 新建按业务域分组的 ER 图（用户域 / 交易域 / 商品域）
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample er-groups \
  -o '<Vault>/Excalidraw/er-groups-demo.excalidraw.md'

# 新建经典 Chen 概念 ER 图（实体矩形 / 联系菱形 / 基数，无属性）
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample chen \
  -o '<Vault>/Excalidraw/chen-demo.excalidraw.md'

# 手绘风格 / 灰度打印 / 深色演示
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py new --sample --style hand -o demo-hand.excalidraw.md
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py patch --path '<file>' --spec spec.json --style mono

# 校验 / 概览
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py validate --path '<vault>/Excalidraw/demo.excalidraw.md'
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py get --path '<vault>/Excalidraw/demo.excalidraw.md'
```

## 2. 标准工作流

### 2.1 新建图表
1. 理解需求，必要时先读相关笔记（`Read` / Obsidian MCP）确定要表达的内容。
2. 设计节点与连线（含判断分支、循环、异常、try-catch 等，见 `references/elements.md`）。
3. 用 `new --spec-inline` 生成到 `<Vault>/Excalidraw/` 目标路径（文件名用 `主题 时间戳.excalidraw.md`，或沿用 Obsidian 默认命名）。
4. 引擎会自动校验结构；若返回 error，按提示修正 spec。
5. 提醒用户用 Obsidian 打开做**视觉验收**（结构校验通过 ≠ 渲染正确）。

### 2.2 读取 / 检查已有图表
用 `get --path` 或 `validate --path` 先了解现状，**不要**直接猜测文件内容。

### 2.3 局部修改已有图表
用 `patch` 做声明式增量修改：给出「修改后的完整 spec」，引擎按 `sem_id` 对账——
- 复用未变化元素的 id（幂等，重复执行不产生重复元素 / 无 diff）；
- 删除 spec 中已消失的引擎元素；
- 保留无 `sem_id` 的手绘元素；
- **默认保留**已存在元素的坐标、形状尺寸、箭头走向/绑定，以及颜色/字体等外观（用户在 Obsidian 里改过的样式不会被抹掉）；
- 自动修复绑定：旧版无绑定的箭头会补上 orbit 绑定；形状被移动导致箭头端点陈旧时，按 `fixedPoint` 重算端点；
- 新增节点放在现有内容右侧；
- 输出 added/removed/updated 差异报告，缺省原地回写并自动备份。

```bash
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py patch \
  --path '<vault>/Excalidraw/demo.excalidraw.md' \
  --spec-inline '{"nodes":[...],"edges":[...]}'            # 或 --spec file.json / -o 输出到别处
# 需要按 spec 重新排版时：
python ~/.claude/skills/excalidraw/scripts/excalidraw_cli.py patch --relayout ...
```

> 注意：若只需改一处文本，也要给全量 spec（含未改节点）。结构（谁连谁、有哪些节点）仍以 spec 为真相；`--relayout` 会丢弃手动拖动的位置并整体重排。

## 3. 安全规则（必须遵守）

1. **新建 / 完整替换 / 增量修改走不同路径**；默认禁止静默覆盖：目标已存在时 `new` 会失败，替换需显式走备份路径。
2. **修改现有绘图前先备份**：引擎的 `write_replace` 默认创建 `.bak-<时间戳>`。
3. **写入前先校验**：`validate` 存在 error 时不写入。
4. **保留未修改元素的 id 与属性**：不要重新生成已有元素的 id。
5. **写入失败保留原文件**：引擎用临时文件 + 原子重命名。
6. **不直接改 Vault 里的 `.excalidraw.md`**（除非通过引擎）；也不要改动 `Excalidraw/Libraries/` 与 `Excalidraw/Templates/`。

## 4. 按需加载参考文档

- 文件格式与 lz-string：`references/format.md`
- 元素与图表规范（流程图/UML/旁注）：`references/elements.md`
- 布局与间距：`references/layout.md`
- 样式规范：`references/style.md`

## 5. 已知限制

- 布局为「分层 + barycenter/median 上下扫描」启发式，边交叉显著降低但不保证全局最优；非常规复杂图建议生成后手动微调。
- 普通流程图箭头为直线且已做 orbit 绑定（移动形状会跟随）；引擎不支持任意折线/拐弯箭头，手动改过的折线在 `--relayout` 后会被还原为直线。
- ER 连线是引擎手工路由的正交折线（`elbowed=false`），跨多列的远距离边可能穿过中间的表卡片；`patch --relayout` 会重新路由。ER 卡片尺寸变化时，`patch` 会自动重算绑定到它的连线端点。
- 当前插件（Excalidraw 2.29.0）没有原生鸦爪箭头，鸦爪用 3 条短线元素模拟；在 Obsidian 里手动拖表后装饰不会自动跟随，重新执行 `patch` 会按箭头最终几何重算。同理，字段文字是分组而非容器绑定，手动改卡片尺寸后需 patch 才会重新对齐。
- ER 卡片尺寸由内容估算（无字体度量），Obsidian 实际渲染后若表名/字段过长，卡片可能略紧；生成后以插件渲染为准。
- `group` 只支持一层，不支持嵌套；成员只能是形状节点；跨组边不参与组内排序，可能穿过组边框或组内其他卡片，复杂图建议生成后手动微调。
- patch 新增 group 时按成员现有位置包框；若成员原本分散，框会很大，建议同时用 `--relayout` 让组内成员重新成块。
- 经典 Chen 概念图按设计不显示任何属性；`entity.fields` 会被忽略。暂不支持弱实体、多值/复合属性、关系属性、全/部分参与等扩展记法，也不从外键自动推断联系。实体和联系名称要求中文，联系必须有 `edge.label`。跨域联系的菱形不属于任一分组，移动某个域时它不会跟随，重新 patch 会按实体新位置重算；连线交叉只做启发式规避和 warning 提示。
- `patch` 默认保留现有坐标；若在 Obsidian 外直接改文件移动了形状（未联动箭头），箭头端点可能滞后，用 `--relayout` 可修正。
- 图片：插件默认把图片存为 Vault 独立文件，绘图 JSON 的 `files` 为空，映射在顶部 `## Embedded Files` 段（`fileId: [[文件]]`）。引擎已解析并原样回写该段，`patch` 不会丢图；**引擎不生成图片元素**，只保留已有图片。若手动增删 `Embedded Files`，需要同步 `image` 元素的 `fileId`（= 图片内容 SHA-1）。
- 文本宽高为估算（无字体度量库），插件打开后以实际渲染为准。
- lz-string 已覆盖 UTF-16 代理对（emoji 等 astral 字符）；lone surrogate 等非法输入未定义。

## 6. 测试

```bash
cd ~/.claude/skills/excalidraw/scripts && python -m unittest discover -s tests -t .
```
