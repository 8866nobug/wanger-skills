import unittest

from excalidraw import builder, cli, connectors, diff, layout, models, styles, validator


def entity(sem_id, name, fields):
    return models.Node("entity", name, sem_id=sem_id, fields=fields)


def by_sem(obj):
    return {(e.get("customData") or {}).get("semId"): e
            for e in obj["elements"]
            if (e.get("customData") or {}).get("semId")}


def to_doc(obj):
    return models.Document(elements=obj["elements"], app_state=obj["appState"],
                           files=obj["files"], source=obj["source"])


USER = entity("user", "user", [
    {"name": "id", "type": "bigint", "pk": True},
    {"name": "account_id", "type": "bigint", "fk": True},
    {"name": "email", "type": "varchar(255)", "unique": True},
])

ORDER = entity("order", "order", [
    {"name": "id", "type": "bigint", "pk": True},
    {"name": "user_id", "type": "bigint", "fk": True},
    {"name": "total", "type": "numeric(12,2)"},
])


class TestCardinality(unittest.TestCase):
    def test_parse_common_forms(self):
        cases = {
            "1:N": ((False, False, "1"), (True, True, "N")),
            "0..1:N": ((False, True, "0..1"), (True, True, "N")),
            "N:M": ((True, True, "N"), (True, True, "M")),
            "1:1": ((False, False, "1"), (False, False, "1")),
            "1..N:0..1": ((True, False, "1..N"), (False, True, "0..1")),
            "N": ((False, False, ""), (True, True, "N")),
        }
        for spec, (left, right) in cases.items():
            a, b = connectors.parse_cardinality(spec)
            self.assertEqual((a.many, a.optional, a.display), left, spec)
            self.assertEqual((b.many, b.optional, b.display), right, spec)

    def test_unknown_value_keeps_label(self):
        a = connectors.parse_cardinality("1:whatever")[1]
        self.assertFalse(a.known)
        self.assertEqual(a.display, "whatever")


class TestEntityCard(unittest.TestCase):
    def test_fields_badges_and_title(self):
        obj = builder.build_diagram(models.Diagram(nodes=[USER]))
        els = by_sem(obj)
        self.assertEqual(els["user"]["type"], "rectangle")
        self.assertEqual(els["user::title"]["text"], "user")
        self.assertEqual(els["user::f0::badge"]["text"], "PK")
        self.assertEqual(els["user::f1::badge"]["text"], "FK")
        self.assertEqual(els["user::f2::badge"]["text"], "UQ")
        self.assertEqual(els["user::f0::type"]["text"], "bigint")
        self.assertEqual(els["user::f0::name"]["text"], "id")

    def test_all_parts_grouped_together(self):
        obj = builder.build_diagram(models.Diagram(nodes=[USER]))
        groups = {tuple(e.get("groupIds") or ())
                  for e in obj["elements"]
                  if (e.get("customData") or {}).get("semId", "").startswith("user")}
        self.assertEqual(len(groups), 1)
        self.assertTrue(next(iter(groups)))

    def test_field_rows_inside_card(self):
        obj = builder.build_diagram(models.Diagram(nodes=[USER]))
        els = by_sem(obj)
        card = els["user"]
        for i in range(3):
            for part in ("name", "type"):
                el = els[f"user::f{i}::{part}"]
                self.assertGreaterEqual(el["x"], card["x"])
                self.assertLessEqual(el["x"] + el["width"], card["x"] + card["width"])
                self.assertGreaterEqual(el["y"], card["y"])
                self.assertLessEqual(el["y"] + el["height"], card["y"] + card["height"])

    def test_size_grows_with_content(self):
        small, _ = builder.entity_size(
            entity("a", "a", [{"name": "id", "type": "int"}]))
        big, bh = builder.entity_size(entity("b", "b", [
            {"name": "a_very_long_column_name", "type": "numeric(12,2)"},
            {"name": "another_column", "type": "varchar(255)"},
            {"name": "third_column", "type": "timestamp"},
        ]))
        self.assertGreater(big, small)
        self.assertGreater(bh, 0)


class TestErEdge(unittest.TestCase):
    def _diagram(self, cardinality="1:N", self_loop=False):
        nodes = [USER, ORDER]
        if self_loop:
            edge = models.Edge("user", "user", cardinality=cardinality,
                               label="parent of", sem_id="loop")
        else:
            edge = models.Edge("user", "order", cardinality=cardinality,
                               label="places", sem_id="places")
        return models.Diagram(nodes=nodes, edges=[edge])

    def test_one_to_many_symbols_and_labels(self):
        obj = builder.build_diagram(self._diagram("1:N"))
        els = by_sem(obj)
        arrow = els["places"]
        self.assertTrue((arrow.get("customData") or {}).get("er"))
        self.assertEqual(arrow["startArrowhead"], "bar")
        self.assertIsNone(arrow["endArrowhead"])
        self.assertEqual(els["places::card::start::text"]["text"], "1")
        self.assertEqual(els["places::card::end::text"]["text"], "N")
        self.assertEqual(els["places::text"]["text"], "places")
        # 只有多端（dst）有鸦爪
        self.assertNotIn("places::crow::start::0", els)
        for i in range(3):
            self.assertIn(f"places::crow::end::{i}", els)
        self.assertEqual(arrow["startBinding"]["elementId"], els["user"]["id"])
        self.assertEqual(arrow["endBinding"]["elementId"], els["order"]["id"])

    def test_many_to_many_has_two_crowfeet(self):
        obj = builder.build_diagram(self._diagram("N:M"))
        els = by_sem(obj)
        for side in ("start", "end"):
            for i in range(3):
                self.assertIn(f"places::crow::{side}::{i}", els)
        self.assertIsNone(els["places"]["startArrowhead"])
        self.assertIsNone(els["places"]["endArrowhead"])

    def test_route_is_orthogonal(self):
        obj = builder.build_diagram(self._diagram("1:N"))
        arrow = by_sem(obj)["places"]
        pts = arrow["points"]
        for a, b in zip(pts, pts[1:]):
            self.assertTrue(abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6)

    def test_self_loop(self):
        obj = builder.build_diagram(self._diagram("0..1:N", self_loop=True))
        els = by_sem(obj)
        arrow = els["loop"]
        self.assertEqual(arrow["startBinding"]["elementId"],
                         arrow["endBinding"]["elementId"])
        self.assertGreaterEqual(len(arrow["points"]), 4)
        self.assertEqual(els["loop::card::start::text"]["text"], "0..1")
        self.assertEqual(els["loop::card::end::text"]["text"], "N")
        for i in range(3):
            self.assertIn(f"loop::crow::end::{i}", els)

    def test_er_diagram_valid(self):
        obj = builder.build_diagram(self._diagram("1:N"))
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))


class TestErLayout(unittest.TestCase):
    def _nodes_edges(self):
        account = entity("account", "account", [{"name": "id", "type": "bigint", "pk": True}])
        category = entity("category", "category", [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "parent_id", "type": "bigint", "fk": True},
        ])
        nodes = [USER, ORDER, account, category]
        edges = [
            models.Edge("account", "user", cardinality="1:N"),
            models.Edge("user", "order", cardinality="1:N"),
            models.Edge("category", "category", cardinality="0..1:N"),
        ]
        return nodes, edges

    def test_deterministic(self):
        nodes, edges = self._nodes_edges()
        size = lambda n: builder.entity_size(n)
        a = layout.er_layout(nodes, edges, size_fn=size)
        b = layout.er_layout(nodes, edges, size_fn=size)
        self.assertEqual(a, b)

    def test_no_overlap(self):
        nodes, edges = self._nodes_edges()
        pos = layout.er_layout(nodes, edges, size_fn=builder.entity_size)
        rects = [(x, y, *builder.entity_size(n)) for (x, y), n in zip(pos, nodes)]
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                x1, y1, w1, h1 = rects[i]
                x2, y2, w2, h2 = rects[j]
                overlap = (x1 < x2 + w2 and x2 < x1 + w1
                           and y1 < y2 + h2 and y2 < y1 + h1)
                self.assertFalse(overlap, (i, j))


class TestErPatch(unittest.TestCase):
    def _diagram(self):
        return models.Diagram(
            nodes=[USER, ORDER],
            edges=[models.Edge("user", "order", cardinality="1:N",
                               label="places", sem_id="places")])

    def test_noop_patch_is_empty(self):
        first = builder.build_diagram(self._diagram())
        second = builder.build_diagram(self._diagram(), existing=to_doc(first))
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d, {"added": [], "removed": [], "updated": []})

    def test_straight_edge_patch_is_noop(self):
        # 同高卡片 -> 2 点直线 ER 边；patch 不能按普通箭头的 6px 外扩改写端点
        a = entity("a", "a", [{"name": "id", "type": "bigint", "pk": True}])
        b = entity("b", "b", [{"name": "id", "type": "bigint", "pk": True}])
        spec = models.Diagram(nodes=[a, b],
                              edges=[models.Edge("a", "b", cardinality="1:N")])
        first = builder.build_diagram(spec)
        arrow = [e for e in first["elements"] if e["type"] == "arrow"][0]
        self.assertEqual(len(arrow["points"]), 2)
        second = builder.build_diagram(spec, existing=to_doc(first))
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d, {"added": [], "removed": [], "updated": []})

    def test_preserves_card_position_and_realigns_children(self):
        first = builder.build_diagram(self._diagram())
        doc = to_doc(first)
        for e in doc.elements:
            if (e.get("customData") or {}).get("semId") == "user":
                e["x"] += 333
                e["y"] += 111
        obj = builder.build_diagram(self._diagram(), existing=doc,
                                    preserve_geometry=True)
        els = by_sem(obj)
        card = els["user"]
        moved = [e for e in doc.elements
                 if (e.get("customData") or {}).get("semId") == "user"][0]
        self.assertEqual((card["x"], card["y"]), (moved["x"], moved["y"]))
        title = els["user::title"]
        self.assertAlmostEqual(title["x"],
                               card["x"] + (card["width"] - title["width"]) / 2.0)
        self.assertAlmostEqual(title["y"],
                               card["y"] + (styles.ENTITY_HEADER_H - title["height"]) / 2.0)
        name = els["user::f0::name"]
        self.assertGreater(name["x"], card["x"])
        self.assertLess(name["x"] + name["width"], card["x"] + card["width"])
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))

    def test_field_change_resizes_card(self):
        first = builder.build_diagram(self._diagram())
        old_width = by_sem(first)["user"]["width"]
        changed = entity("user", "user", [
            {"name": "id", "type": "bigint", "pk": True},
            {"name": "account_id", "type": "bigint", "fk": True},
            {"name": "email_address", "type": "varchar(320)", "unique": True},
        ])
        spec = models.Diagram(
            nodes=[changed, ORDER],
            edges=[models.Edge("user", "order", cardinality="1:N",
                               label="places", sem_id="places")])
        obj = builder.build_diagram(spec, existing=to_doc(first),
                                    preserve_geometry=True)
        els = by_sem(obj)
        self.assertGreater(els["user"]["width"], old_width)
        self.assertEqual(els["user::f2::name"]["text"], "email_address")
        # 卡片变宽后，绑定到它右侧的 ER 连线端点应跟着重算
        arrow = els["places"]
        card = els["user"]
        self.assertAlmostEqual(
            arrow["x"], card["x"] + card["width"] + styles.ER_TOUCH_GAP,
            places=1)
        d = diff.diff_elements(first["elements"], obj["elements"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["removed"], [])
        self.assertGreater(len(d["updated"]), 0)


class TestTitle(unittest.TestCase):
    def test_title_rendered_above_and_centered(self):
        diagram = models.Diagram(nodes=[USER], title="用户表 ER 图")
        obj = builder.build_diagram(diagram)
        els = by_sem(obj)
        title, card = els["__title"], els["user"]
        self.assertEqual(title["text"], "用户表 ER 图")
        self.assertLess(title["y"] + title["height"], card["y"])
        self.assertAlmostEqual(title["x"] + title["width"] / 2.0,
                               card["x"] + card["width"] / 2.0, delta=1.0)

    def test_title_patch_updates_text(self):
        first = builder.build_diagram(
            models.Diagram(nodes=[USER], title="旧标题"))
        second = builder.build_diagram(
            models.Diagram(nodes=[USER], title="新标题"),
            existing=to_doc(first))
        self.assertEqual(by_sem(second)["__title"]["text"], "新标题")
        d = diff.diff_elements(first["elements"], second["elements"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["removed"], [])
        self.assertGreater(len(d["updated"]), 0)

    def test_no_title_means_no_title_element(self):
        obj = builder.build_diagram(models.Diagram(nodes=[USER]))
        self.assertNotIn("__title", by_sem(obj))


class TestErStyleAndSample(unittest.TestCase):
    def test_er_preset_colors(self):
        preset = styles.get_preset("er")
        for key in ("entity", "entity_header", "entity_header_text",
                    "entity_muted", "entity_pk", "entity_fk", "entity_border"):
            self.assertIn(key, preset["colors"])
        self.assertEqual(styles.get_preset("erd")["theme"], "light")

    def test_builtin_er_sample_builds(self):
        diagram = cli.diagram_from_spec(cli.ER_SAMPLE_SPEC)
        obj = builder.build_diagram(diagram)
        self.assertFalse(validator.has_errors(
            validator.validate_document(to_doc(obj))))
        self.assertTrue(any(e["type"] == "arrow" for e in obj["elements"]))
        self.assertTrue(any(e["type"] == "text" and e.get("text") == "PK"
                            for e in obj["elements"]))
        els = by_sem(obj)
        self.assertEqual(els["__title"]["text"], "电商订单数据库 ER 图")
        self.assertIn("legend", els)

    def test_sample_follows_language_conventions(self):
        import re
        cjk = re.compile(r"[一-鿿]")
        spec = cli.ER_SAMPLE_SPEC
        self.assertTrue(cjk.search(spec["title"]))
        for node in spec["nodes"]:
            if node["kind"] != "entity":
                continue
            self.assertFalse(cjk.search(node["text"]), node["text"])
            for f in node["fields"]:
                self.assertFalse(cjk.search(f["name"]), f["name"])
                self.assertFalse(cjk.search(str(f.get("type", ""))), f)
                if "default" in f:
                    self.assertFalse(cjk.search(str(f["default"])), f)
        for edge in spec["edges"]:
            self.assertTrue(cjk.search(edge.get("label", "")), edge)
        legend = [n for n in spec["nodes"] if n["kind"] == "note"][0]
        self.assertTrue(cjk.search(legend["text"]))


if __name__ == "__main__":
    unittest.main()
