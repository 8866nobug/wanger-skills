import unittest

from excalidraw import builder, models, validator


class TestUml(unittest.TestCase):
    def _class_node(self, sem_id, name):
        return models.Node(
            "uml_class",
            f"{name}\n---\n+attr: int\n---\n+method()",
            sem_id=sem_id,
        )

    def test_uml_class_three_sections(self):
        diagram = models.Diagram(nodes=[self._class_node("A", "Person")])
        obj = builder.build_diagram(diagram)
        rects = [e for e in obj["elements"] if e["type"] == "rectangle"]
        lines = [e for e in obj["elements"] if e["type"] == "line"]
        texts = [e for e in obj["elements"] if e["type"] == "text"]
        self.assertEqual(len(rects), 1)
        self.assertEqual(len(lines), 2)   # 两条分隔线
        self.assertEqual(len(texts), 3)   # 类名 / 属性 / 方法

    def test_uml_inherit_arrowhead(self):
        base = self._class_node("Base", "Base")
        derived = self._class_node("Derived", "Derived")
        diagram = models.Diagram(nodes=[base, derived],
                                 edges=[models.Edge("Derived", "Base", rel="inherit")])
        obj = builder.build_diagram(diagram)
        arrows = [e for e in obj["elements"] if e["type"] == "arrow"]
        self.assertEqual(len(arrows), 1)
        self.assertEqual(arrows[0]["endArrowhead"], "triangle_outline")

    def test_uml_compose_diamond_at_owner(self):
        whole = self._class_node("Whole", "Whole")
        part = self._class_node("Part", "Part")
        diagram = models.Diagram(nodes=[whole, part],
                                 edges=[models.Edge("Whole", "Part", rel="compose")])
        obj = builder.build_diagram(diagram)
        arrows = [e for e in obj["elements"] if e["type"] == "arrow"]
        self.assertEqual(len(arrows), 1)
        self.assertEqual(arrows[0]["startArrowhead"], "diamond")
        self.assertIsNone(arrows[0]["endArrowhead"])

    def test_uml_valid(self):
        base = self._class_node("Base", "Base")
        derived = self._class_node("Derived", "Derived")
        diagram = models.Diagram(nodes=[base, derived],
                                 edges=[models.Edge("Derived", "Base", rel="depend")])
        obj = builder.build_diagram(diagram)
        doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                              files=obj["files"], source=obj["source"])
        self.assertFalse(validator.has_errors(validator.validate_document(doc)))


if __name__ == "__main__":
    unittest.main()
