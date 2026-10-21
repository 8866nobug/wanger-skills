import re
import unittest
from collections import Counter

from excalidraw import builder, cli, diff, models, styles, validator

CJK = re.compile(r"[一-鿿]")


def by_sem(obj):
    return {(e.get("customData") or {}).get("semId"): e
            for e in obj["elements"]
            if (e.get("customData") or {}).get("semId")}


def to_doc(obj):
    return models.Document(elements=obj["elements"], app_state=obj["appState"],
                           files=obj["files"], source=obj["source"])


def inside(box, el):
    return (box["x"] <= el["x"]
            and box["y"] <= el["y"]
            and el["x"] + el["width"] <= box["x"] + box["width"]
            and el["y"] + el["height"] <= box["y"] + box["height"])


def entity(sem_id, name, fields=None, label=""):
    return models.Node("entity", name, sem_id=sem_id, fields=fields or [],
                       label=label)


class TestChenSample(unittest.TestCase):
    def setUp(self):
        self.obj = builder.build_diagram(
            cli.diagram_from_spec(cli.CHEN_SAMPLE_SPEC))
        self.els = by_sem(self.obj)

    def test_builds_as_conceptual_diagram(self):
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(self.obj))))
        counts = Counter(e["type"] for e in self.obj["elements"])
        self.assertEqual(counts["rectangle"], 3)   # 三个实体
        self.assertEqual(counts["diamond"], 2)     # 两个联系
        self.assertEqual(counts["arrow"], 4)       # 每个联系两条线
        self.assertEqual(counts["ellipse"], 0)     # 禁止属性椭圆
        self.assertEqual(counts["line"], 0)

    def test_no_attributes_or_physical_details(self):
        for e in self.obj["elements"]:
            sem = (e.get("customData") or {}).get("semId") or ""
            self.assertNotIn("::attr::", sem)
            self.assertNotIn("::attrline::", sem)
            self.assertNotEqual(e["type"], "ellipse")
            if e["type"] == "text":
                txt = e.get("text") or ""
                for token in ("bigint", "varchar", "numeric", "timestamp",
                              "PK ", "FK ", "UQ ", "user_id", "sku", "email"):
                    self.assertNotIn(token, txt, txt)
        self.assertEqual(self.els["user::text"]["text"], "用户")
        self.assertEqual(self.els["order::text"]["text"], "订单")
        self.assertEqual(self.els["product::text"]["text"], "商品")

    def test_relationship_diamonds_and_cardinality(self):
        self.assertEqual(self.els["user_order::rel::text"]["text"], "下单")
        self.assertEqual(self.els["order_product::rel::text"]["text"], "包含")
        labels = {sd: e["text"] for sd, e in self.els.items()
                  if "::card::" in (sd or "")}
        self.assertEqual(labels["user_order::card::a"], "1")
        self.assertEqual(labels["user_order::card::b"], "N")
        self.assertEqual(labels["order_product::card::a"], "N")
        self.assertEqual(labels["order_product::card::b"], "M")

    def test_relation_lines_have_no_arrowheads(self):
        for e in self.obj["elements"]:
            if e["type"] == "arrow":
                self.assertIsNone(e.get("startArrowhead"))
                self.assertIsNone(e.get("endArrowhead"))

    def test_no_group_unless_requested(self):
        self.assertNotIn("grp_trade", self.els)
        self.assertFalse(any("::hdr" in (sd or "") for sd in self.els))

    def test_language_conventions(self):
        spec = cli.CHEN_SAMPLE_SPEC
        self.assertTrue(CJK.search(spec["title"]))
        for node in spec["nodes"]:
            if node["kind"] == "entity":
                self.assertTrue(CJK.search(node["label"]))
                self.assertFalse(CJK.search(node["text"]))
        for edge in spec["edges"]:
            self.assertTrue(CJK.search(edge["label"]))
        self.assertTrue(CJK.search(self.els["legend"]["text"]))


class TestChenGroup(unittest.TestCase):
    def test_group_encloses_entities_when_requested(self):
        nodes = [
            models.Node("group", "交易域", sem_id="grp",
                        members=["order", "product"]),
            entity("order", "order", [{"name": "id", "type": "bigint"}], "订单"),
            entity("product", "product", [], "商品"),
            entity("user", "user", [], "用户"),
        ]
        edges = [
            models.Edge("order", "product", cardinality="N:M",
                        label="包含", sem_id="op"),
            models.Edge("user", "order", cardinality="1:N",
                        label="下单", sem_id="uo"),
        ]
        obj = builder.build_diagram(models.Diagram(
            notation="chen", nodes=nodes, edges=edges))
        els = by_sem(obj)
        box = els["grp"]
        self.assertTrue(inside(box, els["order"]))
        self.assertTrue(inside(box, els["product"]))
        self.assertFalse(inside(box, els["user"]))
        self.assertIn(box["groupIds"][0], els["order"]["groupIds"])
        self.assertIn(box["groupIds"][0], els["op::rel"]["groupIds"])
        self.assertNotIn(box["groupIds"][0],
                         els["uo::rel"].get("groupIds") or [])
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


class TestChenSelfLoop(unittest.TestCase):
    def test_self_loop_placed_away_from_other_relations(self):
        a = entity("a", "node", [], "节点")
        b = entity("b", "other", [], "其他")
        obj = builder.build_diagram(models.Diagram(
            notation="chen", nodes=[a, b],
            edges=[models.Edge("a", "a", cardinality="0..1:N",
                               label="归属", sem_id="loop"),
                   models.Edge("a", "b", cardinality="1:N",
                               label="关联", sem_id="ab")]))
        els = by_sem(obj)
        x, y = els["loop::rel"], els["ab::rel"]
        overlap = not (x["x"] + x["width"] <= y["x"]
                       or y["x"] + y["width"] <= x["x"]
                       or x["y"] + x["height"] <= y["y"]
                       or y["y"] + y["height"] <= x["y"])
        self.assertFalse(overlap)
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


def _dense_diagram(grouped=False):
    nodes = []
    if grouped:
        nodes.extend([
            models.Node("group", "用户域", sem_id="g1",
                        members=["user", "address"]),
            models.Node("group", "交易域", sem_id="g2",
                        members=["order", "payment", "cart"]),
            models.Node("group", "商品域", sem_id="g3",
                        members=["product", "category"]),
        ])
    names = [("user", "用户"), ("order", "订单"), ("product", "商品"),
             ("category", "商品分类"), ("payment", "支付记录"),
             ("address", "收货地址"), ("cart", "购物车")]
    nodes.extend(entity(s, s, [], label) for s, label in names)
    edges = [
        models.Edge("user", "order", cardinality="1:N",
                    label="下单", sem_id="e1"),
        models.Edge("user", "address", cardinality="1:N",
                    label="收货", sem_id="e2"),
        models.Edge("order", "product", cardinality="N:M",
                    label="包含", sem_id="e3"),
        models.Edge("order", "payment", cardinality="1:N",
                    label="支付", sem_id="e4"),
        models.Edge("product", "category", cardinality="N:1",
                    label="归属", sem_id="e5"),
        models.Edge("cart", "user", cardinality="N:1",
                    label="属于", sem_id="e6"),
        models.Edge("cart", "product", cardinality="N:M",
                    label="加购", sem_id="e7"),
        models.Edge("category", "category", cardinality="0..1:N",
                    label="上级分类", sem_id="e8"),
        models.Edge("order", "address", cardinality="N:1",
                    label="配送", sem_id="e9"),
        models.Edge("user", "product", cardinality="N:M",
                    label="收藏", sem_id="e10"),
    ]
    return models.Diagram(notation="chen", nodes=nodes, edges=edges)


def _overlap_count(obj):
    """独立于 validator 的 AABB 检查：实体/联系菱形/自由文本。"""
    els = [e for e in obj["elements"]
           if not e.get("isDeleted") and isinstance(e.get("x"), (int, float))]
    group_sems = set()
    for e in els:
        sd = (e.get("customData") or {}).get("semId") or ""
        if sd.endswith("::hdr"):
            group_sems.add(sd[:-5])
    shapes, texts = [], []
    for e in els:
        sd = (e.get("customData") or {}).get("semId") or ""
        box = (e["x"], e["y"], e.get("width", 0), e.get("height", 0))
        if e["type"] in ("rectangle", "diamond"):
            if sd in group_sems or sd.endswith("::hdr"):
                continue
            shapes.append(box)
        elif e["type"] == "text" and not e.get("containerId"):
            texts.append(box)

    def hit(a, b):
        return (a[0] < b[0] + b[2] and b[0] < a[0] + a[2]
                and a[1] < b[1] + b[3] and b[1] < a[1] + a[3])

    n = 0
    for i, a in enumerate(shapes):
        for b in shapes[i + 1:]:
            n += hit(a, b)
    for t in texts:
        for s in shapes:
            n += hit(t, s)
    for i, a in enumerate(texts):
        for b in texts[i + 1:]:
            n += hit(a, b)
    return n


class TestChenOverlap(unittest.TestCase):
    def test_dense_fanout_has_no_block_overlap(self):
        obj = builder.build_diagram(_dense_diagram())
        self.assertEqual(_overlap_count(obj), 0)
        issues = validator.validate_document(to_doc(obj))
        self.assertFalse([i for i in issues
                          if i["code"] == "chen-element-overlap"], issues)

    def test_grouped_dense_has_no_block_overlap(self):
        obj = builder.build_diagram(_dense_diagram(grouped=True))
        self.assertEqual(_overlap_count(obj), 0)
        issues = validator.validate_document(to_doc(obj))
        self.assertFalse([i for i in issues
                          if i["code"] == "chen-element-overlap"], issues)

    def test_dense_noop_patch_is_empty(self):
        first = builder.build_diagram(_dense_diagram())
        second = builder.build_diagram(_dense_diagram(),
                                       existing=to_doc(first),
                                       preserve_geometry=True)
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d, {"added": [], "removed": [], "updated": []})

    def test_validator_flags_moved_diamond_overlap(self):
        obj = builder.build_diagram(_dense_diagram())
        els = by_sem(obj)
        diamond = els["e1::rel"]
        node = els["order"]
        diamond["x"], diamond["y"] = node["x"], node["y"]
        issues = validator.validate_document(to_doc(obj))
        self.assertTrue([i for i in issues
                         if i["code"] == "chen-element-overlap"], issues)


class TestChenLineOfSight(unittest.TestCase):
    def test_relation_avoids_intervening_entity(self):
        nodes = [entity("a", "a", [], "实体甲"),
                 entity("b", "b", [], "实体乙"),
                 entity("c", "c", [], "实体丙")]
        obj = builder.build_diagram(
            models.Diagram(
                notation="chen", nodes=nodes,
                edges=[models.Edge("a", "c", label="关联", sem_id="ac")]),
            positions=[(0.0, 0.0), (0.0, 200.0), (0.0, 400.0)])
        els = by_sem(obj)
        mid = els["b"]
        mid_box = (mid["x"], mid["y"], mid["width"], mid["height"])
        rel = els["ac::rel"]
        center = (rel["x"] + rel["width"] / 2.0,
                  rel["y"] + rel["height"] / 2.0)
        for sem in ("a", "c"):
            ent = els[sem]
            ent_center = (ent["x"] + ent["width"] / 2.0,
                          ent["y"] + ent["height"] / 2.0)
            self.assertFalse(
                builder._segment_hits_box(center, ent_center, mid_box))
        self.assertFalse(builder._chen_box_overlaps(
            (rel["x"], rel["y"], rel["width"], rel["height"]),
            [mid_box], 0.0))


class TestChenPatch(unittest.TestCase):
    def test_noop_patch_is_empty(self):
        first = builder.build_diagram(
            cli.diagram_from_spec(cli.CHEN_SAMPLE_SPEC))
        second = builder.build_diagram(
            cli.diagram_from_spec(cli.CHEN_SAMPLE_SPEC),
            existing=to_doc(first), preserve_geometry=True)
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d, {"added": [], "removed": [], "updated": []})

    def test_moved_entity_recomputes_relations(self):
        first = builder.build_diagram(
            cli.diagram_from_spec(cli.CHEN_SAMPLE_SPEC))
        doc = to_doc(first)
        for e in doc.elements:
            if (e.get("customData") or {}).get("semId") == "order":
                e["x"] += 200
                e["y"] += 100
        obj = builder.build_diagram(
            cli.diagram_from_spec(cli.CHEN_SAMPLE_SPEC),
            existing=doc, preserve_geometry=True)
        els = by_sem(obj)
        self.assertAlmostEqual(
            els["order::text"]["x"] + els["order::text"]["width"] / 2.0,
            els["order"]["x"] + els["order"]["width"] / 2.0, delta=1.0)
        self.assertNotEqual(els["user_order::rel"]["x"],
                            by_sem(first)["user_order::rel"]["x"])
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


class TestChenValidation(unittest.TestCase):
    def test_rejects_non_entity_nodes(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[models.Node("process", "步骤", sem_id="p")]))

    def test_rejects_edge_to_non_entity(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[entity("a", "a", [], "实体"),
                       models.Node("note", "注释", sem_id="n")],
                edges=[models.Edge("a", "n", label="关联")]))

    def test_requires_chinese_relationship_label(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[entity("a", "a", [], "实体一"),
                       entity("b", "b", [], "实体二")],
                edges=[models.Edge("a", "b")]))

    def test_rejects_english_relationship_label(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[entity("a", "a", [], "实体一"),
                       entity("b", "b", [], "实体二")],
                edges=[models.Edge("a", "b", label="places")]))

    def test_requires_chinese_entity_name(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[entity("a", "user")]))

    def test_rejects_invalid_cardinality(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                notation="chen",
                nodes=[entity("a", "a", [], "实体一"),
                       entity("b", "b", [], "实体二")],
                edges=[models.Edge("a", "b", label="关联",
                                   cardinality="1:whatever")]))


class TestChenStyle(unittest.TestCase):
    def test_chen_preset_colors(self):
        preset = styles.get_preset("chen")
        for key in ("chen_entity", "chen_entity_text",
                    "chen_attribute", "chen_attribute_text",
                    "chen_relation", "chen_relation_text", "chen_line"):
            self.assertIn(key, preset["colors"])


if __name__ == "__main__":
    unittest.main()
