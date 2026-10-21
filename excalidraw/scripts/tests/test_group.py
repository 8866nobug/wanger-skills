import re
import unittest

from excalidraw import builder, cli, diff, models, styles, validator

CJK = re.compile(r"[一-鿿]")


def entity(sem_id, name, fields=None):
    return models.Node(
        "entity", name, sem_id=sem_id,
        fields=fields or [{"name": "id", "type": "bigint", "pk": True}])


def group(sem_id, title, members):
    return models.Node("group", title, sem_id=sem_id, members=members)


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


class TestGroupRender(unittest.TestCase):
    def _diagram(self):
        return models.Diagram(
            nodes=[
                group("grp_trade", "交易域", ["user", "order"]),
                entity("user", "user"),
                entity("order", "order"),
            ],
            edges=[models.Edge("user", "order", cardinality="1:N",
                               label="下单", sem_id="user_order")],
            title="订单 ER 图",
        )

    def test_box_title_and_membership(self):
        obj = builder.build_diagram(self._diagram())
        els = by_sem(obj)
        box, hdr = els["grp_trade"], els["grp_trade::hdr"]
        title = els["grp_trade::title"]
        self.assertEqual(box["type"], "rectangle")
        self.assertEqual(box["backgroundColor"], "transparent")
        self.assertEqual(hdr["backgroundColor"],
                         styles.get_preset("clean")["colors"]["group_fill"])
        self.assertEqual(title["text"], "交易域")
        self.assertIn(box["groupIds"][0], hdr["groupIds"])
        self.assertIn(box["groupIds"][0], title["groupIds"])
        for m in ("user", "order"):
            card = els[m]
            self.assertTrue(inside(box, card), m)
            self.assertIn(box["groupIds"][0], card["groupIds"])
            self.assertEqual(len(card["groupIds"]), 2)  # 实体组 + 域组
        # 背景框/色带先创建，绘制在成员卡片下方
        self.assertLess(box["index"], els["user"]["index"])
        self.assertLess(hdr["index"], els["user"]["index"])

    def test_main_title_above_group_box(self):
        obj = builder.build_diagram(self._diagram())
        els = by_sem(obj)
        title, box = els["__title"], els["grp_trade"]
        self.assertLess(title["y"] + title["height"], box["y"])

    def test_validator_ok(self):
        obj = builder.build_diagram(self._diagram())
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


class TestGroupLayout(unittest.TestCase):
    def test_two_groups_do_not_overlap(self):
        nodes = [
            group("ga", "用户域", ["account", "user"]),
            group("gb", "交易域", ["order", "item"]),
            entity("account", "account"),
            entity("user", "user"),
            entity("order", "order"),
            entity("item", "order_item"),
        ]
        edges = [models.Edge("account", "user", cardinality="1:N"),
                 models.Edge("order", "item", cardinality="1:N")]
        obj = builder.build_diagram(models.Diagram(nodes=nodes, edges=edges))
        els = by_sem(obj)
        a, b = els["ga"], els["gb"]
        overlap = (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
                   and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])
        self.assertFalse(overlap)
        for box_sem, members in (("ga", ("account", "user")),
                                 ("gb", ("order", "item"))):
            for m in members:
                self.assertTrue(inside(els[box_sem], els[m]), (box_sem, m))

    def test_group_around_process_nodes(self):
        nodes = [
            group("g", "处理域", ["a", "b"]),
            models.Node("process", "读取", sem_id="a"),
            models.Node("process", "写入", sem_id="b"),
        ]
        obj = builder.build_diagram(models.Diagram(
            nodes=nodes, edges=[models.Edge("a", "b", label="下一步")]))
        els = by_sem(obj)
        self.assertTrue(inside(els["g"], els["a"]))
        self.assertTrue(inside(els["g"], els["b"]))
        self.assertIn(els["g"]["groupIds"][0], els["a"]["groupIds"])
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))

    def test_layout_is_deterministic(self):
        nodes = [
            group("ga", "用户域", ["user"]),
            entity("user", "user"),
            entity("order", "order"),
        ]
        d = models.Diagram(nodes=nodes,
                           edges=[models.Edge("user", "order", cardinality="1:N")])
        a = builder.build_diagram(d)
        b = builder.build_diagram(d)
        pa = {sem: (els["x"], els["y"]) for sem, els in by_sem(a).items()
              if els["type"] == "rectangle"}
        pb = {sem: (els["x"], els["y"]) for sem, els in by_sem(b).items()
              if els["type"] == "rectangle"}
        self.assertEqual(pa, pb)


class TestGroupPatch(unittest.TestCase):
    def _diagram(self):
        return models.Diagram(
            nodes=[
                group("grp", "交易域", ["user", "order"]),
                entity("user", "user"),
                entity("order", "order"),
            ],
            edges=[models.Edge("user", "order", cardinality="1:N",
                               label="下单", sem_id="user_order")],
            title="订单 ER 图",
        )

    def test_noop_patch_is_empty(self):
        first = builder.build_diagram(self._diagram())
        second = builder.build_diagram(self._diagram(), existing=to_doc(first))
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d, {"added": [], "removed": [], "updated": []})

    def test_patch_add_group_around_existing_members(self):
        # patch 新增的组框 index 会落在已有成员之后；透明底 + 顶部色带保证不遮挡卡片
        base = models.Diagram(
            nodes=[entity("user", "user"), entity("order", "order")],
            edges=[models.Edge("user", "order", cardinality="1:N")])
        first = builder.build_diagram(base)
        grouped = models.Diagram(
            nodes=[group("grp", "交易域", ["user", "order"]),
                   entity("user", "user"), entity("order", "order")],
            edges=[models.Edge("user", "order", cardinality="1:N")])
        obj = builder.build_diagram(grouped, existing=to_doc(first),
                                    preserve_geometry=True)
        els = by_sem(obj)
        box, hdr = els["grp"], els["grp::hdr"]
        self.assertEqual(box["backgroundColor"], "transparent")
        self.assertGreater(box["index"], els["user"]["index"])
        for m in ("user", "order"):
            self.assertTrue(inside(box, els[m]), m)
            self.assertIn(box["groupIds"][0], els[m]["groupIds"])
        # 顶部色带只占标题区，不覆盖成员卡片
        self.assertLessEqual(hdr["y"] + hdr["height"], els["user"]["y"])
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))

    def test_box_follows_moved_member(self):
        first = builder.build_diagram(self._diagram())
        orig_x, orig_y = by_sem(first)["user"]["x"], by_sem(first)["user"]["y"]
        doc = to_doc(first)
        for e in doc.elements:
            if (e.get("customData") or {}).get("semId") == "user":
                e["x"] += 300
                e["y"] += 150
        obj = builder.build_diagram(self._diagram(), existing=doc,
                                    preserve_geometry=True)
        els = by_sem(obj)
        box, title, user = els["grp"], els["grp::title"], els["user"]
        self.assertEqual((user["x"], user["y"]), (orig_x + 300, orig_y + 150))
        self.assertTrue(inside(box, user))
        self.assertAlmostEqual(title["x"], box["x"] + styles.GROUP_PAD)
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


class TestGroupValidation(unittest.TestCase):
    def test_unknown_member(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                nodes=[group("g", "域", ["nope"]), entity("a", "a")]))

    def test_duplicate_membership(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                nodes=[group("g1", "域1", ["a"]),
                       group("g2", "域2", ["a"]),
                       entity("a", "a")]))

    def test_sem_id_collision(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                nodes=[group("a", "域", ["b"]), entity("a", "a"),
                       entity("b", "b")]))

    def test_member_must_be_shape(self):
        note = models.Node("note", "注释", sem_id="n1")
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                nodes=[group("g", "域", ["n1"]), note]))

    def test_edge_cannot_target_group(self):
        with self.assertRaises(ValueError):
            builder.build_diagram(models.Diagram(
                nodes=[group("g", "域", ["a"]), entity("a", "a"),
                       entity("b", "b")],
                edges=[models.Edge("g", "b")]))


class TestGroupSample(unittest.TestCase):
    def test_grouped_sample_builds(self):
        obj = builder.build_diagram(
            cli.diagram_from_spec(cli.ER_GROUP_SAMPLE_SPEC))
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))
        els = by_sem(obj)
        for sem in ("grp_user", "grp_trade", "grp_product"):
            self.assertIn(sem, els)
            self.assertIn(f"{sem}::hdr", els)
            self.assertIn(f"{sem}::title", els)
            self.assertTrue(CJK.search(els[f"{sem}::title"]["text"]))
        self.assertTrue(CJK.search(els["__title"]["text"]))
        self.assertIn("legend", els)
        for box_sem, members in (
                ("grp_user", ("account", "user")),
                ("grp_trade", ("order", "order_item", "payment")),
                ("grp_product", ("category", "product"))):
            for m in members:
                self.assertTrue(inside(els[box_sem], els[m]), (box_sem, m))

    def test_self_loop_member_sits_on_group_right(self):
        # category 有自关联，分组布局应把它排到 product 右侧，避免回环压住组内卡片
        obj = builder.build_diagram(
            cli.diagram_from_spec(cli.ER_GROUP_SAMPLE_SPEC))
        els = by_sem(obj)
        self.assertGreater(els["category"]["x"], els["product"]["x"])


if __name__ == "__main__":
    unittest.main()
