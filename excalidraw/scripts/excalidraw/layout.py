"""布局与间距。

提供基础纵向/横向线性布局、树形流程布局（含决策分支）、ER 连通分量布局、
分组布局、Chen 概念图菱形避让与画布范围计算。
"""
from __future__ import annotations

from collections import deque

from . import models, styles


def node_size(kind: str) -> tuple[float, float]:
    if kind == "decision":
        return styles.DECISION_W, styles.DECISION_H
    if kind == "terminator":
        return styles.TERMINATOR_W, styles.TERMINATOR_H
    if kind == "uml_class":
        return styles.NODE_W, styles.NODE_H * 2
    if kind == "entity":
        return (styles.ENTITY_MIN_W,
                styles.ENTITY_HEADER_H + 4 * styles.ENTITY_ROW_H + styles.ENTITY_PAD)
    if kind in ("text", "note"):
        return 0.0, 0.0
    return styles.NODE_W, styles.NODE_H   # process


def vertical_flow(nodes: list[models.Node], x_center: float = 0.0,
                  y_start: float = 0.0,
                  size_fn=None) -> list[tuple[float, float]]:
    """纵向线性布局：返回每个节点的左上角坐标。"""
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    positions: list[tuple[float, float]] = []
    y = y_start
    for node in nodes:
        w, h = size_fn(node)
        positions.append((x_center - w / 2.0, y))
        y += h + styles.VGAP
    return positions


def horizontal_flow(nodes: list[models.Node], y_center: float = 0.0,
                    x_start: float = 0.0,
                    size_fn=None) -> list[tuple[float, float]]:
    """横向线性布局：返回每个节点的左上角坐标。"""
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    positions: list[tuple[float, float]] = []
    x = x_start
    for node in nodes:
        w, h = size_fn(node)
        positions.append((x, y_center - h / 2.0))
        x += w + styles.HGAP
    return positions


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    m = len(s) // 2
    return s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


def _place_row(row: list[int], desired: dict[int, float], col: list[float]) -> None:
    """按 desired 顺序摆放一行：贪心保证相邻间隔 >= 1，并整体居中到期望位置。"""
    if not row:
        return
    vals: list[float] = []
    prev: float | None = None
    for u in row:
        c = desired.get(u)
        if c is None:
            c = (prev + 1.0) if prev is not None else 0.0
        if prev is not None and c < prev + 1.0:
            c = prev + 1.0
        vals.append(c)
        prev = c
    shift = (sum(desired.get(u, 0.0) for u in row) / len(row)
             - sum(vals) / len(vals))
    for u, v in zip(row, vals):
        col[u] = v + shift


def _count_crossings(row_of: list, col: list[float],
                     pairs: list[tuple[int, int]]) -> int:
    """统计同一行对上的边交叉数（两条边端点次序相反即交叉）。"""
    groups: dict[tuple, list[tuple[int, int]]] = {}
    for s, d in pairs:
        groups.setdefault((row_of[s], row_of[d]), []).append((s, d))
    total = 0
    for grp in groups.values():
        for i in range(len(grp)):
            s1, d1 = grp[i]
            for j in range(i + 1, len(grp)):
                s2, d2 = grp[j]
                if (col[s1] - col[s2]) * (col[d1] - col[d2]) < 0:
                    total += 1
    return total


def count_crossings(nodes: list[models.Node], edges: list[models.Edge],
                    positions: list[tuple[float, float]]) -> int:
    """按最终坐标统计边交叉数（供测试与诊断）。"""
    sem = {n.sem_id if n.sem_id else str(i): i for i, n in enumerate(nodes)}
    cx = [positions[i][0] + node_size(nodes[i].kind)[0] / 2.0
          for i in range(len(nodes))]
    row = [positions[i][1] for i in range(len(nodes))]
    pairs = [(sem[e.src], sem[e.dst]) for e in edges
             if e.src in sem and e.dst in sem and sem[e.src] != sem[e.dst]]
    return _count_crossings(row, cx, pairs)


def flow(nodes: list[models.Node], edges: list[models.Edge],
         size_fn=None) -> list[tuple[float, float]]:
    """分层流程布局（自上而下，分支横向展开，含交叉最小化）。

    - 行（depth）按最长路径（拓扑序）确定；
    - 列（x）用 barycenter/median 启发式上下扫描若干轮：每行按父节点（向下）
      或子节点（向上）列位置的中位数排序，再贪心拉开，降低边交叉；
    - 取交叉数最少的一轮结果。
    返回每个节点的左上角坐标，顺序与 nodes 一致。
    """
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    n = len(nodes)
    if n == 0:
        return []
    if n == 1:
        w, h = size_fn(nodes[0])
        return [(-w / 2.0, 0.0)]

    sem = [node.sem_id if node.sem_id else str(i) for i, node in enumerate(nodes)]
    idx = {s: i for i, s in enumerate(sem)}
    adj: list[list[int]] = [[] for _ in range(n)]
    indeg = [0] * n
    parents: list[list[int]] = [[] for _ in range(n)]
    for e in edges:
        s = idx.get(e.src)
        d = idx.get(e.dst)
        if s is None or d is None or s == d:
            continue
        if d not in adj[s]:
            adj[s].append(d)
            indeg[d] += 1
        if s not in parents[d]:
            parents[d].append(s)

    # 最长路径深度（行号）
    depth = [0] * n
    q = deque(i for i in range(n) if indeg[i] == 0)
    remaining = indeg[:]
    max_depth = 0
    while q:
        u = q.popleft()
        for v in adj[u]:
            depth[v] = max(depth[v], depth[u] + 1)
            max_depth = max(max_depth, depth[v])
            remaining[v] -= 1
            if remaining[v] == 0:
                q.append(v)

    # 有环或不可达的节点：放到已有最大深度之后（避免重叠）
    for i in range(n):
        if remaining[i] > 0:
            depth[i] = max_depth + 1
    max_depth = max(depth)

    by_row: dict[int, list[int]] = {}
    for i in range(n):
        by_row.setdefault(depth[i], []).append(i)
    if not by_row:
        return []

    edge_pairs = [(s, d) for s in range(n) for d in adj[s]]

    # 初始摆放：根按输入顺序，其余按父节点重心
    col = [0.0] * n
    order: dict[int, list[int]] = {r: list(by_row[r]) for r in by_row}
    _place_row(order.get(0, []),
               {u: float(k) for k, u in enumerate(order.get(0, []))}, col)
    for r in range(1, max_depth + 1):
        row = order.get(r, [])
        desired = {}
        for u in row:
            m = _median([col[p] for p in parents[u]])
            desired[u] = m if m is not None else float(len(row) - 1) / 2.0
        row.sort(key=lambda u: desired[u])
        _place_row(row, desired, col)

    best_cross = _count_crossings(depth, col, edge_pairs)
    best_col = col[:]

    # 上下扫描（barycenter/median 启发式）若干轮，保留交叉最少的结果
    for _ in range(4):
        for r in range(1, max_depth + 1):
            row = order.get(r, [])
            desired = {}
            for u in row:
                m = _median([col[p] for p in parents[u]])
                desired[u] = m if m is not None else col[u]
            row.sort(key=lambda u: desired[u])
            _place_row(row, desired, col)
        for r in range(max_depth - 1, -1, -1):
            row = order.get(r, [])
            desired = {}
            for u in row:
                m = _median([col[c] for c in adj[u]])
                desired[u] = m if m is not None else col[u]
            row.sort(key=lambda u: desired[u])
            _place_row(row, desired, col)
        cross = _count_crossings(depth, col, edge_pairs)
        if cross < best_cross:
            best_cross = cross
            best_col = col[:]

    col = best_col

    # 列宽/行高取最大节点尺寸 + 间距
    col_w = max(size_fn(node)[0] for node in nodes) + styles.HGAP
    row_h = max(size_fn(node)[1] for node in nodes) + styles.VGAP

    positions: list[tuple[float, float]] = []
    for i, node in enumerate(nodes):
        w, h = size_fn(node)
        cx = col[i] * col_w + col_w / 2.0
        x = cx - w / 2.0
        y = depth[i] * row_h
        positions.append((x, y))
    return positions


def er_layout(nodes: list[models.Node], edges: list[models.Edge],
              size_fn=None,
              hgap: float = styles.ER_HGAP,
              vgap: float = styles.ER_VGAP,
              comp_gap: float = styles.ER_COMPONENT_GAP,
              max_row_w: float = styles.ER_MAX_ROW_W) -> list[tuple[float, float]]:
    """ER 图布局：按连通分量分别做 BFS 分层，再按网格铺开。

    - 每个连通分量以度数最高的实体为根做无向 BFS，层号即列号；
    - 每列内按邻居位置中位数排序，降低交叉；
    - 列宽/行高按实际卡片尺寸计算，短列垂直居中；
    - 各分量按大小排序后从左到右摆放，超宽自动换行。
    返回每个节点左上角坐标，顺序与 nodes 一致。
    """
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    n = len(nodes)
    if n == 0:
        return []
    if n == 1:
        w, h = size_fn(nodes[0])
        return [(0.0, 0.0)]

    sem = [node.sem_id if node.sem_id else str(i) for i, node in enumerate(nodes)]
    idx = {s: i for i, s in enumerate(sem)}
    adj: list[set[int]] = [set() for _ in range(n)]
    for e in edges:
        s, d = idx.get(e.src), idx.get(e.dst)
        if s is None or d is None or s == d:
            continue
        adj[s].add(d)
        adj[d].add(s)

    # 连通分量（按输入顺序发现，稍后按大小排序）
    seen = [False] * n
    comps: list[list[int]] = []
    for i in range(n):
        if seen[i]:
            continue
        stack = [i]
        seen[i] = True
        comp: list[int] = []
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in sorted(adj[u], reverse=True):
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(sorted(comp))
    comps.sort(key=lambda c: (-len(c), c[0]))

    positions: list[tuple[float, float]] = [(0.0, 0.0)] * n
    cursor_x = cursor_y = shelf_h = 0.0
    for comp in comps:
        comp_pos, comp_w, comp_h = _er_component(
            nodes, comp, adj, size_fn, hgap, vgap)
        if cursor_x > 0 and cursor_x + comp_w > max_row_w:
            cursor_x = 0.0
            cursor_y += shelf_h + comp_gap
            shelf_h = 0.0
        for i, (x, y) in comp_pos.items():
            positions[i] = (x + cursor_x, y + cursor_y)
        cursor_x += comp_w + comp_gap
        shelf_h = max(shelf_h, comp_h)

    min_x = min(p[0] for p in positions)
    min_y = min(p[1] for p in positions)
    return [(x - min_x, y - min_y) for x, y in positions]


def _er_component(nodes: list[models.Node], comp: list[int],
                  adj: list[set[int]], size_fn, hgap: float, vgap: float):
    """单个连通分量：BFS 分层 + 列内中位数排序，返回 (位置表, 宽, 高)。"""
    if len(comp) == 1:
        i = comp[0]
        w, h = size_fn(nodes[i])
        return {i: (0.0, 0.0)}, w, h

    hub = max(comp, key=lambda u: (len(adj[u]), -u))
    layer = {hub: 0}
    q = deque([hub])
    while q:
        u = q.popleft()
        for v in sorted(adj[u], key=lambda v: (-len(adj[v]), v)):
            if v not in layer:
                layer[v] = layer[u] + 1
                q.append(v)

    by_layer: dict[int, list[int]] = {}
    for u in comp:
        by_layer.setdefault(layer[u], []).append(u)
    rows = sorted(by_layer)
    order = {r: sorted(by_layer[r], key=lambda u: (-len(adj[u]), u))
             for r in rows}

    def positions_in_layers() -> dict[int, float]:
        return {u: k for r in rows for k, u in enumerate(order[r])}

    # 3 轮 barycenter（上→下、下→上），按邻居列位置中位数排序
    for _ in range(3):
        pos = positions_in_layers()
        for r in rows[1:]:
            def key_down(u, r=r, pos=pos):
                vals = [pos[v] for v in adj[u] if v in pos and layer[v] < r]
                return _median(vals) if vals else pos[u]
            order[r].sort(key=key_down)
            pos = positions_in_layers()
        for r in reversed(rows[:-1]):
            def key_up(u, r=r, pos=pos):
                vals = [pos[v] for v in adj[u] if v in pos and layer[v] > r]
                return _median(vals) if vals else pos[u]
            order[r].sort(key=key_up)
            pos = positions_in_layers()

    sizes = {u: size_fn(nodes[u]) for u in comp}
    col_w = {r: max(sizes[u][0] for u in order[r]) + hgap for r in rows}
    col_x: dict[int, float] = {}
    x = 0.0
    for r in rows:
        col_x[r] = x
        x += col_w[r]
    col_h = {r: sum(sizes[u][1] for u in order[r])
             + vgap * (len(order[r]) - 1) for r in rows}
    max_h = max(col_h.values())

    out: dict[int, tuple[float, float]] = {}
    for r in rows:
        y = (max_h - col_h[r]) / 2.0
        for u in order[r]:
            w, h = sizes[u]
            out[u] = (col_x[r] + (col_w[r] - hgap - w) / 2.0, y)
            y += h + vgap
    return out, sum(col_w.values()), max_h


def grouped_layout(nodes: list[models.Node], edges: list[models.Edge],
                   groups: list[models.Node], size_fn=None,
                   title_size_fn=None,
                   hgap: float = styles.ER_HGAP,
                   vgap: float = styles.ER_VGAP,
                   group_gap: float = styles.GROUP_GAP,
                   max_row_w: float = styles.ER_MAX_ROW_W,
                   content_margin: float = 0.0
                   ) -> list[tuple[float, float]]:
    """分组布局：每个 group 的成员单独布局成一个块，再按网格铺开。

    nodes 只包含形状节点；groups 是 kind=="group" 的节点列表（按 spec 顺序）。
    组内布局复用 er_layout（含 entity）或 flow/vertical_flow；跨组边不参与组内布局，
    但仍会在 builder 中正常绘制。返回与 nodes 对齐的左上角坐标。

    content_margin 在组内成员块四周预留额外空白，供组内自动元素（如 Chen
    联系菱形、自关联回环）占用，避免组框扩张后压到相邻组。
    """
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    if title_size_fn is None:
        title_size_fn = lambda t: (0.0, 0.0)
    n = len(nodes)
    if n == 0:
        return []
    if not groups:
        if any(node.kind == "entity" for node in nodes):
            return er_layout(nodes, edges, size_fn, hgap=hgap, vgap=vgap)
        return (flow(nodes, edges, size_fn) if edges
                else vertical_flow(nodes, size_fn))

    sem = [node.sem_id if node.sem_id else str(i) for i, node in enumerate(nodes)]
    idx = {s: i for i, s in enumerate(sem)}
    owner: dict[int, str] = {}
    member_idxs: list[list[int]] = []
    self_loops = {e.src for e in edges if e.src == e.dst}
    for g in groups:
        mi: list[int] = []
        for m in g.members or []:
            if m not in idx:
                raise ValueError(
                    f"group {g.sem_id or g.text!r} 的成员 {m!r} 不是形状节点")
            i = idx[m]
            if i in owner:
                raise ValueError(
                    f"节点 {m!r} 同时属于 group {owner[i]!r} 和 {g.sem_id or g.text!r}")
            owner[i] = g.sem_id or g.text or "?"
            mi.append(i)
        if not mi:
            raise ValueError(f"group {g.sem_id or g.text!r} 没有成员")
        # 自关联节点尽量排到组内右侧，让回环落在组外空白处
        mi.sort(key=lambda i: (sem[i] in self_loops, i))
        member_idxs.append(mi)

    def local(indices: list[int]):
        sub_nodes = [nodes[i] for i in indices]
        sub_sems = {sem[i] for i in indices}
        sub_edges = [e for e in edges
                     if e.src in sub_sems and e.dst in sub_sems]
        if any(node.kind == "entity" for node in sub_nodes):
            pos = er_layout(sub_nodes, sub_edges, size_fn, hgap=hgap, vgap=vgap)
        elif sub_edges:
            pos = flow(sub_nodes, sub_edges, size_fn)
        else:
            pos = vertical_flow(sub_nodes, size_fn)
        if not pos:
            return {}, 0.0, 0.0
        min_x = min(p[0] for p in pos)
        min_y = min(p[1] for p in pos)
        pos = [(x - min_x, y - min_y) for x, y in pos]
        _, _, max_x, max_y = bounds(pos, sub_nodes, size_fn)
        return dict(zip(indices, pos)), max_x, max_y

    # 未分组节点先放一块，再放各个组；这样跨组边优先从左侧接入第一个组
    items: list[tuple[list[int], dict[int, tuple[float, float]],
                      float, float, float, float, bool]] = []
    rest = [i for i in range(n) if i not in owner]
    if rest:
        positions, block_w, block_h = local(rest)
        items.append((rest, positions, block_w, block_h,
                      block_w, block_h, False))
    for gi, mi in enumerate(member_idxs):
        positions, block_w, block_h = local(mi)
        tw, _th = title_size_fn(groups[gi].text or "")
        m = content_margin
        box_w = max(block_w + 2 * m + 2 * styles.GROUP_PAD,
                    tw + 2 * styles.GROUP_PAD, styles.GROUP_MIN_W)
        box_h = (block_h + styles.GROUP_HEADER_H + 2 * m
                 + styles.GROUP_PAD)
        items.append((mi, positions, block_w, block_h,
                      box_w, box_h, True))

    out: list[tuple[float, float]] = [(0.0, 0.0)] * n
    cursor_x = cursor_y = shelf_h = 0.0
    for _mi, positions, block_w, block_h, box_w, box_h, is_group in items:
        if cursor_x > 0 and cursor_x + box_w > max_row_w:
            cursor_x = 0.0
            cursor_y += shelf_h + group_gap
            shelf_h = 0.0
        if is_group:
            inner_x = cursor_x + (box_w - block_w) / 2.0
            inner_y = cursor_y + styles.GROUP_HEADER_H + content_margin
        else:
            inner_x, inner_y = cursor_x, cursor_y
        for i, (x, y) in positions.items():
            out[i] = (x + inner_x, y + inner_y)
        cursor_x += box_w + group_gap
        shelf_h = max(shelf_h, box_h)
    return out


def bounds(positions: list[tuple[float, float]],
           nodes: list[models.Node], size_fn=None) -> tuple[float, float, float, float]:
    """计算元素包围盒 (min_x, min_y, max_x, max_y)。"""
    if size_fn is None:
        size_fn = lambda n: node_size(n.kind)
    if not positions:
        return (0.0, 0.0, 0.0, 0.0)
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for (x, y), node in zip(positions, nodes):
        w, h = size_fn(node)
        min_x = min(min_x, x)
        min_y = min(min_y, y)
        max_x = max(max_x, x + w)
        max_y = max(max_y, y + h)
    return (min_x, min_y, max_x, max_y)
