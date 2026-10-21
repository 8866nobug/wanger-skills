import contextlib
import io
import json
import os
import tempfile
import unittest

from excalidraw import cli


SPEC1 = {
    "nodes": [
        {"kind": "terminator", "text": "开始", "sem_id": "start"},
        {"kind": "process", "text": "处理", "sem_id": "p1"},
        {"kind": "terminator", "text": "结束", "sem_id": "end"},
    ],
    "edges": [
        {"src": "start", "dst": "p1"},
        {"src": "p1", "dst": "end"},
    ],
}

SPEC2 = {
    "nodes": [
        {"kind": "terminator", "text": "开始", "sem_id": "start"},
        {"kind": "process", "text": "处理订单", "sem_id": "p1"},
        {"kind": "process", "text": "发送通知", "sem_id": "p2"},
        {"kind": "terminator", "text": "结束", "sem_id": "end"},
    ],
    "edges": [
        {"src": "start", "dst": "p1"},
        {"src": "p1", "dst": "p2"},
        {"src": "p2", "dst": "end"},
    ],
}


def run(args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = cli.main(args)
    return rc, out.getvalue(), err.getvalue()


class TestCliPlainExcalidraw(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        self.spec1 = self._spec("s1.json", SPEC1)
        self.spec2 = self._spec("s2.json", SPEC2)

    def _spec(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return path

    def _read_json(self, name):
        with open(os.path.join(self.dir, name), encoding="utf-8") as f:
            return json.load(f)

    def test_new_plain_and_patch_in_place(self):
        out = os.path.join(self.dir, "demo.excalidraw")
        rc, _stdout, _stderr = run([
            "new", "--spec", self.spec1, "--format", "excalidraw",
            "-o", out, "--no-backup"])
        self.assertEqual(rc, 0)
        data = self._read_json("demo.excalidraw")
        self.assertEqual(data["type"], "excalidraw")
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["source"], "https://excalidraw.com")
        self.assertTrue(data["elements"])

        rc, _stdout, _stderr = run([
            "patch", "--path", out, "--spec", self.spec2])
        self.assertEqual(rc, 0)
        data = self._read_json("demo.excalidraw")
        self.assertEqual(data["type"], "excalidraw")
        self.assertTrue(any(e.get("text") == "发送通知"
                            for e in data["elements"]))

        rc, _stdout, _stderr = run(["validate", "--path", out])
        self.assertEqual(rc, 0)
        rc, _stdout, _stderr = run(["get", "--path", out])
        self.assertEqual(rc, 0)

    def test_format_inferred_from_extension(self):
        plain = os.path.join(self.dir, "inferred.excalidraw")
        rc, _stdout, _stderr = run([
            "new", "--spec", self.spec1, "-o", plain, "--no-backup"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._read_json("inferred.excalidraw")["type"],
                         "excalidraw")

        md = os.path.join(self.dir, "inferred.excalidraw.md")
        rc, _stdout, _stderr = run([
            "new", "--spec", self.spec1, "-o", md, "--no-backup"])
        self.assertEqual(rc, 0)
        with open(md, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("```compressed-json", text)

    def test_cross_format_conversion(self):
        md = os.path.join(self.dir, "from-md.excalidraw.md")
        run(["new", "--spec", self.spec1, "-o", md, "--no-backup"])
        plain = os.path.join(self.dir, "converted.excalidraw")
        rc, _stdout, _stderr = run([
            "patch", "--path", md, "--spec", self.spec2,
            "-o", plain, "--no-backup"])
        self.assertEqual(rc, 0)
        self.assertEqual(self._read_json("converted.excalidraw")["type"],
                         "excalidraw")

        back = os.path.join(self.dir, "converted.excalidraw.md")
        rc, _stdout, _stderr = run([
            "patch", "--path", plain, "--spec", self.spec2,
            "-o", back, "--no-backup"])
        self.assertEqual(rc, 0)
        with open(back, encoding="utf-8") as f:
            self.assertIn("```compressed-json", f.read())


if __name__ == "__main__":
    unittest.main()
