import unittest

from excalidraw import builder, diff, models, validator


class TestPatch(unittest.TestCase):
    def _spec_diagram(self):
        return models.Diagram(
            nodes=[
                models.Node("terminator", "开始", sem_id="start"),
                models.Node("process", "步骤一", sem_id="s1"),
                models.Node("terminator", "结束", sem_id="end"),
            ],
            edges=[models.Edge("start", "s1"), models.Edge("s1", "end")],
        )

    def _build_doc(self, diagram=None):
        obj = builder.build_diagram(diagram or self._spec_diagram())
        return models.Document(elements=obj["elements"], app_state=obj["appState"],
                               files=obj["files"], source=obj["source"])

    def test_patch_idempotent_no_duplicates(self):
        first = self._build_doc()
        obj = builder.build_diagram(self._spec_diagram(), existing=first)
        ids1 = [e["id"] for e in obj["elements"]]
        self.assertEqual(len(ids1), len(set(ids1)))  # 无重复 id

        # 再用第一次 patch 的结果作为 existing，重复执行得到相同 id 集合
        second_doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                                     files=obj["files"], source=obj["source"])
        second = builder.build_diagram(self._spec_diagram(), existing=second_doc)
        ids2 = [e["id"] for e in second["elements"]]
        self.assertEqual(ids1, ids2)

    def test_patch_preserves_existing_ids(self):
        first = self._build_doc()
        obj = builder.build_diagram(self._spec_diagram(), existing=first)
        orig_ids = {e["id"] for e in first.elements}
        new_ids = {e["id"] for e in obj["elements"]}
        self.assertTrue(orig_ids <= new_ids)  # 未变化的元素复用原 id

    def test_patch_removes_deleted_node(self):
        first = self._build_doc()
        reduced = models.Diagram(
            nodes=[
                models.Node("terminator", "开始", sem_id="start"),
                models.Node("terminator", "结束", sem_id="end"),
            ],
            edges=[models.Edge("start", "end")],
        )
        obj = builder.build_diagram(reduced, existing=first)
        sem_ids = {(e.get("customData") or {}).get("semId") for e in obj["elements"]}
        self.assertNotIn("s1", sem_ids)
        self.assertNotIn("s1::text", sem_ids)
        self.assertIn("start>end", sem_ids)

    def test_patch_keeps_manual_elements(self):
        first = self._build_doc()
        # 模拟用户手绘元素（无 customData.semId）
        first.elements.append({
            "id": "manual1", "type": "rectangle",
            "x": 0, "y": 0, "width": 50, "height": 50, "index": "z9",
        })
        obj = builder.build_diagram(self._spec_diagram(), existing=first)
        ids = [e["id"] for e in obj["elements"]]
        self.assertIn("manual1", ids)

    def test_patch_reconcile_no_dangling(self):
        # 复用 id 后 containerId / boundElements 引用必须同步重映射
        first = self._build_doc()
        obj = builder.build_diagram(self._spec_diagram(), existing=first)
        doc = models.Document(elements=obj["elements"], app_state=obj["appState"],
                              files=obj["files"], source=obj["source"])
        self.assertFalse(validator.has_errors(validator.validate_document(doc)))

    def test_patch_noop_clean_diff(self):
        # 相同 spec 重复 patch：无新增 / 无删除 / 无更新（彻底幂等）
        first = self._build_doc()
        obj = builder.build_diagram(self._spec_diagram(), existing=first)
        d = diff.diff_elements(first.elements, obj["elements"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["removed"], [])
        self.assertEqual(d["updated"], [])

    def test_patch_preserves_manual_position(self):
        first = self._build_doc()
        # 模拟用户在 Obsidian 中拖动节点 s1
        for e in first.elements:
            if (e.get("customData") or {}).get("semId") == "s1":
                e["x"] += 500
                e["y"] += 300
        obj = builder.build_diagram(self._spec_diagram(), existing=first,
                                    preserve_geometry=True)
        moved = [e for e in obj["elements"]
                 if (e.get("customData") or {}).get("semId") == "s1"][0]
        original = [e for e in first.elements
                    if (e.get("customData") or {}).get("semId") == "s1"][0]
        self.assertEqual((moved["x"], moved["y"]), (original["x"], original["y"]))
        # 绑定箭头仍指向该形状
        arrows = [e for e in obj["elements"] if e["type"] == "arrow"]
        self.assertTrue(any(a["startBinding"]["elementId"] == moved["id"]
                            or a["endBinding"]["elementId"] == moved["id"]
                            for a in arrows))

    def test_patch_relayout_recomputes_position(self):
        first = self._build_doc()
        for e in first.elements:
            if (e.get("customData") or {}).get("semId") == "s1":
                e["x"] += 500
        obj = builder.build_diagram(self._spec_diagram(), existing=first,
                                    preserve_geometry=False)
        s1 = [e for e in obj["elements"]
              if (e.get("customData") or {}).get("semId") == "s1"][0]
        fresh = builder.build_diagram(self._spec_diagram())
        expected = [e for e in fresh["elements"]
                    if (e.get("customData") or {}).get("semId") == "s1"][0]
        self.assertEqual(s1["x"], expected["x"])  # 已按 spec 重算

    def test_patch_upgrades_unbound_arrows(self):
        # 旧版本生成的箭头没有绑定：patch 时应补上 orbit 绑定
        first = self._build_doc()
        for e in first.elements:
            if e["type"] == "arrow":
                e["startBinding"] = None
                e["endBinding"] = None
        obj = builder.build_diagram(self._spec_diagram(), existing=first,
                                    preserve_geometry=True)
        for a in (e for e in obj["elements"] if e["type"] == "arrow"):
            self.assertIsNotNone(a["startBinding"])
            self.assertIsNotNone(a["endBinding"])

    def test_patch_preserves_files(self):
        first = self._build_doc()
        first.files = {"f1": {"id": "f1", "mimeType": "image/png",
                              "dataURL": "data:image/png;base64,AAAA"}}
        obj = builder.build_diagram(self._spec_diagram(), existing=first,
                                    preserve_geometry=True)
        self.assertEqual(obj["files"], first.files)

    def test_patch_relabel_marks_update(self):
        first = self._build_doc()
        changed = models.Diagram(
            nodes=[
                models.Node("terminator", "开始", sem_id="start"),
                models.Node("process", "步骤一（改）", sem_id="s1"),
                models.Node("terminator", "结束", sem_id="end"),
            ],
            edges=[models.Edge("start", "s1"), models.Edge("s1", "end")],
        )
        obj = builder.build_diagram(changed, existing=first)
        d = diff.diff_elements(first.elements, obj["elements"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["removed"], [])
        self.assertTrue(len(d["updated"]) >= 1)  # 至少 s1 的形状/文本发生变化


if __name__ == "__main__":
    unittest.main()
