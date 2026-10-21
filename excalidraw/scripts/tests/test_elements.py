import unittest

from excalidraw import elements


class TestElements(unittest.TestCase):
    def setUp(self):
        self.env = elements.Env()

    def _common_fields(self, el, etype):
        self.assertEqual(el["type"], etype)
        self.assertIn("id", el)
        self.assertIn("index", el)
        self.assertIn("boundElements", el)
        self.assertIn("points", el) if etype in ("line", "arrow") else None

    def test_rectangle(self):
        el = elements.rectangle(self.env, 0, 0, 100, 50)
        self._common_fields(el, "rectangle")
        self.assertEqual((el["width"], el["height"]), (100, 50))

    def test_diamond(self):
        el = elements.diamond(self.env, 0, 0, 200, 100)
        self.assertEqual(el["type"], "diamond")

    def test_ellipse(self):
        el = elements.ellipse(self.env, 0, 0, 120, 60)
        self.assertEqual(el["type"], "ellipse")
        self.assertEqual(el["roundness"], {"type": 2})

    def test_arrow(self):
        el = elements.arrow(self.env, 0, 0, [[0, 0], [100, 0]])
        self._common_fields(el, "arrow")
        self.assertEqual(el["endArrowhead"], "arrow")
        self.assertEqual(el["points"], [[0, 0], [100, 0]])
        self.assertEqual((el["width"], el["height"]), (100, 0))

    def test_line(self):
        el = elements.line(self.env, 0, 0, [[0, 0], [0, 80]])
        self.assertEqual(el["type"], "line")
        self.assertEqual(el["endArrowhead"], None)

    def test_text(self):
        el = elements.text(self.env, 10, 10, "你好")
        self.assertEqual(el["type"], "text")
        self.assertEqual(el["text"], "你好")
        self.assertEqual(el["rawText"], "你好")

    def test_bind_text(self):
        shape = elements.rectangle(self.env, 0, 0, 100, 50)
        t = elements.text(self.env, 0, 0, "x", container_id=shape["id"])
        elements.bind_text(shape, t["id"])
        self.assertIn({"type": "text", "id": t["id"]}, shape["boundElements"])

    def test_ids_unique_within_env(self):
        ids = [self.env.new_id() for _ in range(100)]
        self.assertEqual(len(set(ids)), 100)


if __name__ == "__main__":
    unittest.main()
