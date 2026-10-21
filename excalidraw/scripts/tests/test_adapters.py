import json
import unittest

from excalidraw import adapters, builder, models, styles


class TestLzString(unittest.TestCase):
    def test_roundtrip_ascii(self):
        s = '{"type":"excalidraw","version":2}'
        self.assertEqual(adapters.decompress_from_base64(adapters.compress_to_base64(s)), s)

    def test_roundtrip_cjk(self):
        s = json.dumps({"text": "是否匹配系统白名单", "n": 123.456}, ensure_ascii=False)
        self.assertEqual(adapters.decompress_from_base64(adapters.compress_to_base64(s)), s)

    def test_roundtrip_empty(self):
        self.assertEqual(adapters.decompress_from_base64(adapters.compress_to_base64("")), "")

    def test_roundtrip_emoji(self):
        # astral 字符（代理对）必须按 UTF-16 code unit 编码
        for s in ("😀", "流程 🚀 结束", "👨‍👩‍👧‍👦", "a😀b中文🚀"):
            self.assertEqual(
                adapters.decompress_from_base64(adapters.compress_to_base64(s)), s)

    def test_emoji_in_document_roundtrip(self):
        d = models.Diagram(nodes=[models.Node("process", "🚀 发布 😀", sem_id="p1")])
        obj = builder.build_diagram(d)
        text = adapters.serialize_md(obj["elements"], obj["appState"])
        doc = adapters.parse_md(text)
        self.assertEqual(doc.elements, obj["elements"])


class TestMarkdownContainer(unittest.TestCase):
    def _sample_doc(self):
        d = models.Diagram(
            nodes=[
                models.Node("terminator", "开始", sem_id="start"),
                models.Node("process", "步骤一", sem_id="s1"),
                models.Node("terminator", "结束", sem_id="end"),
            ],
            edges=[models.Edge("start", "s1"), models.Edge("s1", "end")],
        )
        return builder.build_diagram(d)

    def test_serialize_parse_roundtrip(self):
        obj = self._sample_doc()
        text = adapters.serialize_md(obj["elements"], obj["appState"])
        doc = adapters.parse_md(text)
        self.assertEqual(doc.elements, obj["elements"])
        self.assertEqual(doc.app_state, obj["appState"])

    def test_serialize_contains_expected_sections(self):
        obj = self._sample_doc()
        text = adapters.serialize_md(obj["elements"], obj["appState"])
        self.assertIn("excalidraw-plugin: parsed", text)
        self.assertIn("## Text Elements", text)
        self.assertIn("## Drawing", text)
        self.assertIn("```compressed-json", text)

    def test_text_blocks_from_elements(self):
        obj = self._sample_doc()
        blocks = adapters.text_blocks_from_elements(obj["elements"])
        texts = {content for content, _ in blocks}
        self.assertIn("开始", texts)
        self.assertIn("步骤一", texts)
        self.assertIn("结束", texts)

    def test_embedded_files_roundtrip(self):
        obj = self._sample_doc()
        emb = {"172c032297d93bbffc1c21086424aa3db5784fb8":
               "[[{EAE1902D-1656-CF38-020E-0B506800B696}.jpg]]"}
        text = adapters.serialize_md(obj["elements"], obj["appState"],
                                     embedded_files=emb)
        self.assertIn("## Embedded Files", text)
        doc = adapters.parse_md(text)
        self.assertEqual(doc.embedded_files, emb)
        # 再次序列化保持该段
        text2 = adapters.serialize_md(doc.elements, doc.app_state,
                                      embedded_files=doc.embedded_files)
        self.assertEqual(adapters.parse_md(text2).embedded_files, emb)

    def test_no_embedded_section_when_empty(self):
        obj = self._sample_doc()
        text = adapters.serialize_md(obj["elements"], obj["appState"])
        self.assertNotIn("## Embedded Files", text)


class TestPlainExcalidraw(unittest.TestCase):
    def _sample_obj(self):
        d = models.Diagram(nodes=[
            models.Node("terminator", "开始", sem_id="start"),
            models.Node("process", "处理", sem_id="p1"),
            models.Node("terminator", "结束", sem_id="end"),
        ], edges=[models.Edge("start", "p1"), models.Edge("p1", "end")])
        return builder.build_diagram(d)

    def test_serialize_parse_roundtrip(self):
        obj = self._sample_obj()
        text = adapters.serialize_excalidraw(
            obj["elements"], obj["appState"], files=obj["files"],
            source=styles.STANDALONE_SOURCE)
        data = json.loads(text)
        self.assertEqual(data["type"], "excalidraw")
        self.assertEqual(data["version"], 2)
        self.assertEqual(data["source"], styles.STANDALONE_SOURCE)
        self.assertIn("elements", data)
        doc = adapters.parse_excalidraw(text)
        self.assertEqual(doc.elements, obj["elements"])
        self.assertEqual(doc.app_state, obj["appState"])
        self.assertEqual(doc.files, obj["files"])

    def test_parse_rejects_missing_elements(self):
        with self.assertRaises(ValueError):
            adapters.parse_excalidraw('{"type": "excalidraw"}')

    def test_parse_rejects_non_object(self):
        with self.assertRaises(ValueError):
            adapters.parse_excalidraw('[]')


if __name__ == "__main__":
    unittest.main()
