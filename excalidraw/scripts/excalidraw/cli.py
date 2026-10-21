"""统一命令行入口。

用法（从 scripts/ 目录，或通过 excalidraw_cli.py 启动器）：
    python -m excalidraw new --sample -o out.excalidraw.md
    python -m excalidraw new --sample er -o er.excalidraw.md
    python -m excalidraw new --sample er-groups -o er-groups.excalidraw.md
    python -m excalidraw new --sample chen -o chen.excalidraw.md
    python -m excalidraw new --spec spec.json -o out.excalidraw.md
    python -m excalidraw get --path x.excalidraw.md
    python -m excalidraw validate --path x.excalidraw.md
    python -m excalidraw diff --old a.excalidraw.md --new b.excalidraw.md
    python -m excalidraw patch --path x.excalidraw.md --spec spec.json
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import adapters, builder, diff, models, styles, validator, writer

# 内置样板：覆盖全部形状类型 + 文本 + 箭头
SAMPLE_SPEC: dict[str, Any] = {
    "nodes": [
        {"kind": "terminator", "text": "开始", "sem_id": "start"},
        {"kind": "process", "text": "获取请求体", "sem_id": "s1"},
        {"kind": "decision", "text": "是否通过校验", "sem_id": "d1"},
        {"kind": "process", "text": "处理业务", "sem_id": "s2"},
        {"kind": "terminator", "text": "结束", "sem_id": "end"},
    ],
    "edges": [
        {"src": "start", "dst": "s1"},
        {"src": "s1", "dst": "d1"},
        {"src": "d1", "dst": "s2", "label": "是"},
        {"src": "s2", "dst": "end"},
    ],
}

# 内置 ER 样板：账号 / 用户 / 订单 / 商品 / 支付 + 自关联分类
ER_SAMPLE_SPEC: dict[str, Any] = {
    "style": "er",
    "title": "电商订单数据库 ER 图",
    "nodes": [
        {"kind": "entity", "text": "account", "sem_id": "account", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "name", "type": "varchar(120)"},
            {"name": "plan", "type": "varchar(32)", "default": "'free'"},
            {"name": "created_at", "type": "timestamp"},
        ]},
        {"kind": "entity", "text": "user", "sem_id": "user", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "account_id", "type": "bigint", "fk": True},
            {"name": "email", "type": "varchar(255)", "unique": True},
            {"name": "name", "type": "varchar(80)"},
            {"name": "created_at", "type": "timestamp"},
        ]},
        {"kind": "entity", "text": "category", "sem_id": "category", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "parent_id", "type": "bigint", "fk": True},
            {"name": "name", "type": "varchar(120)"},
        ]},
        {"kind": "entity", "text": "product", "sem_id": "product", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "category_id", "type": "bigint", "fk": True},
            {"name": "sku", "type": "varchar(64)", "unique": True},
            {"name": "name", "type": "varchar(160)"},
            {"name": "price", "type": "numeric(10,2)"},
        ]},
        {"kind": "entity", "text": "order", "sem_id": "order", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "user_id", "type": "bigint", "fk": True},
            {"name": "status", "type": "varchar(32)", "default": "'pending'"},
            {"name": "total", "type": "numeric(12,2)"},
            {"name": "created_at", "type": "timestamp"},
        ]},
        {"kind": "entity", "text": "order_item", "sem_id": "order_item", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "order_id", "type": "bigint", "fk": True},
            {"name": "product_id", "type": "bigint", "fk": True},
            {"name": "quantity", "type": "int"},
            {"name": "unit_price", "type": "numeric(10,2)"},
        ]},
        {"kind": "entity", "text": "payment", "sem_id": "payment", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "order_id", "type": "bigint", "fk": True},
            {"name": "amount", "type": "numeric(12,2)"},
            {"name": "method", "type": "varchar(32)"},
            {"name": "paid_at", "type": "timestamp"},
        ]},
        {"kind": "note",
         "text": "图例\nPK = 主键　FK = 外键　UQ = 唯一\n1:N = 一对多　0..1 = 可选单条",
         "sem_id": "legend"},
    ],
    "edges": [
        {"src": "account", "dst": "user", "cardinality": "1:N",
         "label": "包含", "sem_id": "account_user"},
        {"src": "user", "dst": "order", "cardinality": "1:N",
         "label": "下单", "sem_id": "user_order"},
        {"src": "order", "dst": "order_item", "cardinality": "1:N",
         "label": "包含", "sem_id": "order_item_edge"},
        {"src": "product", "dst": "order_item", "cardinality": "1:N",
         "label": "关联", "sem_id": "product_item"},
        {"src": "order", "dst": "payment", "cardinality": "1:N",
         "label": "支付", "sem_id": "order_payment"},
        {"src": "category", "dst": "category", "cardinality": "0..1:N",
         "label": "归属", "sem_id": "category_parent"},
        {"src": "category", "dst": "product", "cardinality": "1:N",
         "label": "归类", "sem_id": "category_product"},
    ],
}

# 分组版 ER 样板：按业务域把表装进带中文标题的背景框
ER_GROUP_SAMPLE_SPEC: dict[str, Any] = {
    **ER_SAMPLE_SPEC,
    "title": "电商订单数据库 ER 图（按域分组）",
    "nodes": [
        {"kind": "group", "text": "用户域", "sem_id": "grp_user",
         "members": ["account", "user"]},
        {"kind": "group", "text": "交易域", "sem_id": "grp_trade",
         "members": ["order", "order_item", "payment"]},
        {"kind": "group", "text": "商品域", "sem_id": "grp_product",
         "members": ["category", "product"]},
    ] + ER_SAMPLE_SPEC["nodes"],
    "edges": ER_SAMPLE_SPEC["edges"],
}

# 内置经典 Chen 概念图样板：矩形实体 + 菱形联系 + 基数（无属性）
CHEN_SAMPLE_SPEC: dict[str, Any] = {
    "style": "chen",
    "notation": "chen",
    "title": "订单业务概念 ER 图",
    "nodes": [
        {"kind": "entity", "text": "user", "label": "用户",
         "sem_id": "user", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "name", "type": "varchar(80)"},
            {"name": "email", "type": "varchar(255)", "unique": True},
        ]},
        {"kind": "entity", "text": "order", "label": "订单",
         "sem_id": "order", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "user_id", "type": "bigint", "fk": True},
            {"name": "total", "type": "numeric(12,2)"},
            {"name": "status", "type": "varchar(32)", "default": "'pending'"},
        ]},
        {"kind": "entity", "text": "product", "label": "商品",
         "sem_id": "product", "fields": [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "sku", "type": "varchar(64)", "unique": True},
            {"name": "name", "type": "varchar(160)"},
            {"name": "price", "type": "numeric(10,2)"},
        ]},
        {"kind": "note",
         "text": "图例\n矩形 = 业务实体　菱形 = 业务联系\n1 / N / M / 0..1 / 0..N = 联系基数",
         "sem_id": "legend"},
    ],
    "edges": [
        {"src": "user", "dst": "order", "cardinality": "1:N",
         "label": "下单", "sem_id": "user_order"},
        {"src": "order", "dst": "product", "cardinality": "N:M",
         "label": "包含", "sem_id": "order_product"},
    ],
}


def diagram_from_spec(spec: dict[str, Any]) -> models.Diagram:
    nodes = [models.Node(**n) for n in spec.get("nodes", [])]
    edges = [models.Edge(**e) for e in spec.get("edges", [])]
    canvas = models.Canvas(**spec.get("canvas", {}))
    return models.Diagram(nodes=nodes, edges=edges, canvas=canvas,
                          style=spec.get("style", ""),
                          notation=spec.get("notation", ""),
                          title=spec.get("title", ""),
                          meta=spec.get("meta", {}))


def _style_arg(value: str) -> str:
    """argparse 校验：样式名（含别名）必须存在于预设表。"""
    try:
        styles.get_preset(value)
    except KeyError as e:
        raise argparse.ArgumentTypeError(e.args[0]) from None
    return value


def _load_spec(args) -> dict[str, Any]:
    sample = getattr(args, "sample", None)
    if sample:
        if sample == "er":
            return ER_SAMPLE_SPEC
        if sample == "er-groups":
            return ER_GROUP_SAMPLE_SPEC
        if sample == "chen":
            return CHEN_SAMPLE_SPEC
        return SAMPLE_SPEC
    if getattr(args, "spec_inline", None):
        return json.loads(args.spec_inline)
    with open(args.spec, encoding="utf-8") as f:
        return json.load(f)


def cmd_new(args) -> int:
    spec = _load_spec(args)
    diagram = diagram_from_spec(spec)
    obj = builder.build_diagram(diagram, style=args.style)

    doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                          files=obj["files"], source=obj["source"])
    issues = validator.validate_document(doc)
    if validator.has_errors(issues):
        print("生成结果校验失败：", file=sys.stderr)
        print(validator.format_issues(issues), file=sys.stderr)
        return 1

    backup = writer.write_document(args.out, obj["elements"], obj["appState"],
                                   files=obj["files"], source=obj["source"],
                                   backup_file=not args.no_backup)
    suffix = f"（备份：{backup}）" if backup else ""
    print(f"已写入 {args.out}{suffix}")
    for i in validator.format_issues(issues).splitlines():
        print(f"  {i}")
    return 0


def _read_doc(path: str) -> models.Document:
    with open(path, encoding="utf-8") as f:
        return adapters.parse_md(f.read(), path=path)


def cmd_get(args) -> int:
    doc = _read_doc(args.path)
    counts: dict[str, int] = {}
    for e in doc.elements:
        t = e.get("type", "?")
        counts[t] = counts.get(t, 0) + 1
    print(f"路径: {doc.path}")
    print(f"元素数: {len(doc.elements)}")
    print(f"类型分布: {counts}")
    print(f"source: {doc.source}")
    print(validator.format_issues(validator.validate_document(doc)))
    return 0


def cmd_validate(args) -> int:
    doc = _read_doc(args.path)
    issues = validator.validate_document(doc)
    print(validator.format_issues(issues))
    return 1 if validator.has_errors(issues) else 0


def cmd_diff(args) -> int:
    old = _read_doc(args.old).elements
    new = _read_doc(args.new).elements
    print(diff.format_diff(diff.diff_elements(old, new)))
    return 0


def cmd_patch(args) -> int:
    doc = _read_doc(args.path)
    spec = _load_spec(args)
    diagram = diagram_from_spec(spec)
    explicit_style = bool(args.style or diagram.style)
    obj = builder.build_diagram(diagram, existing=doc,
                                preserve_geometry=not args.relayout,
                                style=args.style,
                                preserve_style=not explicit_style)

    new_doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                              files=obj["files"], source=obj["source"])
    issues = validator.validate_document(new_doc)
    if validator.has_errors(issues):
        print("补丁结果校验失败：", file=sys.stderr)
        print(validator.format_issues(issues), file=sys.stderr)
        return 1

    out = args.out or args.path
    backup = writer.write_document(out, obj["elements"], obj["appState"],
                                   files=obj["files"], source=obj["source"],
                                   frontmatter=doc.frontmatter,
                                   embedded_files=doc.embedded_files,
                                   text_order=[eid for _, eid in doc.text_blocks],
                                   backup_file=not args.no_backup)
    print("变更统计（按元素 id）：")
    print(diff.format_diff(diff.diff_elements(doc.elements, obj["elements"])))
    suffix = f"（备份：{backup}）" if backup else ""
    print(f"已写入 {out}{suffix}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="excalidraw", description="Excalidraw 绘图引擎")
    sub = p.add_subparsers(dest="command", required=True)

    pn = sub.add_parser("new", help="根据 spec 生成新绘图")
    src = pn.add_mutually_exclusive_group(required=True)
    src.add_argument("--sample", nargs="?", const="flow",
                     choices=("flow", "er", "er-groups", "chen"),
                     help="使用内置样板：flow（流程图，默认）、er（实体关系图）、er-groups（按域分组的 ER 图）或 chen（经典 Chen 概念图）")
    src.add_argument("--spec", help="spec JSON 文件路径")
    src.add_argument("--spec-inline", help="内联 spec JSON 字符串")
    pn.add_argument("-o", "--out", required=True, help="输出 .excalidraw.md 路径")
    pn.add_argument("--style", type=_style_arg, metavar="NAME",
                    help="样式预设：clean / er / chen / hand / mono / night（别名 default/print/erd/database/sketch/grayscale/dark）")
    pn.add_argument("--no-backup", action="store_true", help="覆盖时不备份")
    pn.set_defaults(func=cmd_new)

    pg = sub.add_parser("get", help="读取并概览绘图")
    pg.add_argument("--path", required=True)
    pg.set_defaults(func=cmd_get)

    pv = sub.add_parser("validate", help="校验绘图结构与引用")
    pv.add_argument("--path", required=True)
    pv.set_defaults(func=cmd_validate)

    pd = sub.add_parser("diff", help="比较两个绘图的元素差异")
    pd.add_argument("--old", required=True)
    pd.add_argument("--new", required=True)
    pd.set_defaults(func=cmd_diff)

    pp = sub.add_parser("patch", help="按 spec 增量修改现有绘图（声明式对账）")
    psrc = pp.add_mutually_exclusive_group(required=True)
    psrc.add_argument("--spec", help="spec JSON 文件路径")
    psrc.add_argument("--spec-inline", help="内联 spec JSON 字符串")
    pp.add_argument("--path", required=True, help="现有 .excalidraw.md 路径")
    pp.add_argument("-o", "--out", help="输出路径（缺省原地回写）")
    pp.add_argument("--relayout", action="store_true",
                    help="按 spec 重新计算全部坐标（缺省保留现有位置/尺寸/箭头）")
    pp.add_argument("--style", type=_style_arg, metavar="NAME",
                    help="改用指定样式预设重绘（缺省保留现有颜色/字体等外观）")
    pp.add_argument("--no-backup", action="store_true", help="回写时不备份")
    pp.set_defaults(func=cmd_patch)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
