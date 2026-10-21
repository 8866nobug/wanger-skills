import os
import tempfile
import unittest

from excalidraw import builder, models, writer


class TestWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def _sample_text(self):
        d = models.Diagram(nodes=[models.Node("process", "A")])
        obj = builder.build_diagram(d)
        return obj

    def test_write_new_refuses_existing(self):
        p = os.path.join(self.dir, "a.excalidraw.md")
        writer.write_new(p, "hello")
        with self.assertRaises(FileExistsError):
            writer.write_new(p, "overwrite")

    def test_write_replace_creates_backup(self):
        p = os.path.join(self.dir, "a.excalidraw.md")
        writer.write_new(p, "old")
        backup = writer.write_replace(p, "new")
        self.assertTrue(backup)
        self.assertTrue(os.path.exists(backup))
        with open(backup, encoding="utf-8") as f:
            self.assertEqual(f.read(), "old")
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), "new")

    def test_write_document_roundtrip(self):
        p = os.path.join(self.dir, "a.excalidraw.md")
        obj = self._sample_text()
        writer.write_document(p, obj["elements"], obj["appState"])
        from excalidraw import adapters
        with open(p, encoding="utf-8") as f:
            doc = adapters.parse_md(f.read())
        self.assertEqual(doc.elements, obj["elements"])

    def test_write_excalidraw_roundtrip(self):
        p = os.path.join(self.dir, "a.excalidraw")
        obj = self._sample_text()
        writer.write_excalidraw(p, obj["elements"], obj["appState"],
                                files=obj["files"])
        from excalidraw import adapters
        with open(p, encoding="utf-8") as f:
            doc = adapters.parse_excalidraw(f.read())
        self.assertEqual(doc.elements, obj["elements"])
        self.assertEqual(doc.app_state, obj["appState"])


if __name__ == "__main__":
    unittest.main()
