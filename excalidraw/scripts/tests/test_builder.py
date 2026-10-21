import unittest

from excalidraw import builder, elements, models, styles, validator


class TestBuilder(unittest.TestCase):
    def _sample_diagram(self):
        return models.Diagram(
            nodes=[
                models.Node("terminator", "开始", sem_id="start"),
                models.Node("process", "步骤一", sem_id="s1"),
                models.Node("decision", "是否继续", sem_id="d1"),
                models.Node("terminator", "结束", sem_id="end"),
            ],
            edges=[
                models.Edge("start", "s1"),
                models.Edge("s1", "d1"),
                models.Edge("d1", "end", label="否"),
            ],
        )

    def test_build_has_all_shape_types(self):
        obj = builder.build_diagram(self._sample_diagram())
        types = {e["type"] for e in obj["elements"]}
        self.assertTrue({"ellipse", "rectangle", "diamond", "arrow", "text"} <= types)

    def test_build_valid(self):
        obj = builder.build_diagram(self._sample_diagram())
        doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                              files=obj["files"], source=obj["source"])
        self.assertFalse(validator.has_errors(validator.validate_document(doc)))

    def test_edges_produce_arrows(self):
        obj = builder.build_diagram(self._sample_diagram())
        arrows = [e for e in obj["elements"] if e["type"] == "arrow"]
        self.assertEqual(len(arrows), 3)

    def test_idempotent_structure(self):
        a = builder.build_diagram(self._sample_diagram())
        b = builder.build_diagram(self._sample_diagram())
        self.assertEqual(len(a["elements"]), len(b["elements"]))
        self.assertEqual([e["type"] for e in a["elements"]],
                         [e["type"] for e in b["elements"]])

    def test_arrows_are_bound_with_orbit(self):
        obj = builder.build_diagram(self._sample_diagram())
        by_id = {e["id"]: e for e in obj["elements"]}
        arrows = [e for e in obj["elements"] if e["type"] == "arrow"]
        self.assertTrue(arrows)
        for a in arrows:
            for key in ("startBinding", "endBinding"):
                b = a[key]
                self.assertIsNotNone(b)
                self.assertEqual(b["mode"], "orbit")
                self.assertEqual(len(b["fixedPoint"]), 2)
                self.assertTrue(0.0 <= b["fixedPoint"][0] <= 1.0)
                self.assertTrue(0.0 <= b["fixedPoint"][1] <= 1.0)
                target = by_id[b["elementId"]]
                refs = [x for x in target.get("boundElements") or []
                        if x.get("type") == "arrow" and x.get("id") == a["id"]]
                self.assertTrue(refs)

    def test_edge_label_avoids_obstacle(self):
        env = elements.Env()
        arrow = elements.arrow(env, 0.0, 0.0, [[0.0, 0.0], [200.0, 0.0]],
                               end_arrowhead=None)
        obstacle = (80.0, -20.0, 40.0, 40.0)
        t = builder._place_edge_label(
            env, arrow, "是", styles.get_preset("clean"), "e::text", [obstacle])
        self.assertFalse(builder._chen_box_overlaps(
            (t["x"], t["y"], t["width"], t["height"]), [obstacle], 0.0))


if __name__ == "__main__":
    unittest.main()
