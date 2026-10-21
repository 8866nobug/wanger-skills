import unittest

from excalidraw import builder, cli, models, styles


def _diagram(style=""):
    return models.Diagram(
        nodes=[
            models.Node("terminator", "开始", sem_id="s"),
            models.Node("process", "处理", sem_id="p"),
            models.Node("decision", "判断", sem_id="d"),
            models.Node("note", "旁注", sem_id="n"),
        ],
        edges=[models.Edge("s", "p"), models.Edge("p", "d", label="是")],
        style=style,
    )


def _by_sem(obj, sem):
    for e in obj["elements"]:
        if (e.get("customData") or {}).get("semId") == sem:
            return e
    raise AssertionError(f"找不到 semId={sem}")


class TestStylePresets(unittest.TestCase):
    def test_all_presets_have_required_keys(self):
        required = ("theme", "background", "stroke", "text", "arrow_stroke",
                    "font_family", "note_font_family", "font_size",
                    "label_font_size", "stroke_width", "stroke_style",
                    "roughness", "fill_style", "roundness", "colors")
        for name in styles.style_names():
            preset = styles.get_preset(name)
            for key in required:
                self.assertIn(key, preset, f"{name} 缺少 {key}")
            for kind in ("process", "decision", "terminator", "uml_class"):
                self.assertIn(kind, preset["colors"], f"{name} 缺少颜色 {kind}")
            for kind in ("entity", "entity_header", "entity_header_text",
                         "entity_muted", "entity_pk", "entity_fk",
                         "entity_border", "group_fill", "group_border",
                         "group_title", "chen_entity", "chen_entity_text",
                         "chen_attribute", "chen_attribute_text",
                         "chen_relation", "chen_relation_text", "chen_line"):
                self.assertIn(kind, preset["colors"], f"{name} 缺少 ER/Chen 颜色 {kind}")

    def test_unknown_style_raises(self):
        with self.assertRaises(KeyError):
            styles.get_preset("nope")

    def test_aliases(self):
        self.assertEqual(styles.get_preset("print")["font_family"], 2)
        self.assertEqual(styles.get_preset("sketch")["roughness"], 1)
        self.assertEqual(styles.get_preset("dark")["theme"], "dark")
        self.assertEqual(styles.get_preset("default"), styles.get_preset("clean"))

    def test_clean_is_print_like(self):
        obj = builder.build_diagram(_diagram("clean"))
        rect = _by_sem(obj, "p")
        text = _by_sem(obj, "p::text")
        self.assertEqual(rect["roughness"], 0)
        self.assertEqual(rect["backgroundColor"], "#e7f5ff")
        self.assertIsNone(rect["roundness"])      # 直角框
        self.assertEqual(text["fontFamily"], 2)   # Helvetica
        self.assertEqual(text["strokeColor"], "#1e1e1e")
        self.assertEqual(obj["appState"]["theme"], "light")

    def test_hand_is_sketchy(self):
        obj = builder.build_diagram(_diagram("hand"))
        rect = _by_sem(obj, "p")
        text = _by_sem(obj, "p::text")
        note = _by_sem(obj, "n")
        self.assertEqual(rect["roughness"], 1)
        self.assertEqual(rect["backgroundColor"], "#a5d8ff")
        self.assertEqual(text["fontFamily"], 5)   # Excalifont
        self.assertEqual(note["fontFamily"], 2)   # 旁注仍用标准字体

    def test_mono_is_grayscale(self):
        obj = builder.build_diagram(_diagram("mono"))
        rect = _by_sem(obj, "p")
        self.assertEqual(rect["backgroundColor"], "#f1f3f5")
        self.assertEqual(rect["strokeColor"], "#212529")
        self.assertIsNone(rect["roundness"])      # 直角
        self.assertEqual(rect["roughness"], 0)

    def test_night_is_dark(self):
        obj = builder.build_diagram(_diagram("night"))
        rect = _by_sem(obj, "p")
        text = _by_sem(obj, "p::text")
        self.assertEqual(obj["appState"]["theme"], "dark")
        self.assertEqual(obj["appState"]["viewBackgroundColor"], "#141414")
        self.assertEqual(rect["strokeColor"], "#f8f9fa")
        self.assertEqual(text["strokeColor"], "#ffffff")
        self.assertEqual(rect["backgroundColor"], "#1971c2")

    def test_default_style_is_clean(self):
        obj = builder.build_diagram(_diagram())
        self.assertEqual(_by_sem(obj, "p")["roughness"], 0)
        self.assertEqual(_by_sem(obj, "p::text")["fontFamily"], 2)

    def test_diagram_style_field(self):
        obj = builder.build_diagram(_diagram("hand"))
        self.assertEqual(_by_sem(obj, "p")["roughness"], 1)

    def test_cli_style_override_wins(self):
        obj = builder.build_diagram(_diagram("clean"), style="hand")
        self.assertEqual(_by_sem(obj, "p")["roughness"], 1)

    def test_spec_style_parsed(self):
        d = cli.diagram_from_spec({"style": "mono", "nodes": [], "edges": []})
        self.assertEqual(d.style, "mono")

    def test_per_node_background_override(self):
        d = _diagram("clean")
        d.nodes[1].style = {"backgroundColor": "#ff0000"}
        obj = builder.build_diagram(d)
        self.assertEqual(_by_sem(obj, "p")["backgroundColor"], "#ff0000")
        self.assertEqual(_by_sem(obj, "p")["roughness"], 0)  # 其余仍用预设

    def test_canvas_override(self):
        d = _diagram("clean")
        d.canvas = models.Canvas(theme="dark", background="#000000")
        obj = builder.build_diagram(d)
        self.assertEqual(obj["appState"]["theme"], "dark")
        self.assertEqual(obj["appState"]["viewBackgroundColor"], "#000000")


class TestPatchStyle(unittest.TestCase):
    def _doc(self, style="clean"):
        obj = builder.build_diagram(_diagram(style))
        return models.Document(elements=obj["elements"], app_state=obj["appState"],
                               files=obj["files"], source=obj["source"])

    def test_patch_preserves_custom_style(self):
        doc = self._doc("clean")
        for e in doc.elements:
            if (e.get("customData") or {}).get("semId") == "p":
                e["backgroundColor"] = "#ff0000"
                e["roughness"] = 2
        obj = builder.build_diagram(_diagram("clean"), existing=doc,
                                    preserve_geometry=True)
        rect = _by_sem(obj, "p")
        self.assertEqual(rect["backgroundColor"], "#ff0000")
        self.assertEqual(rect["roughness"], 2)

    def test_patch_style_flag_restyles(self):
        doc = self._doc("clean")
        obj = builder.build_diagram(_diagram("hand"), existing=doc,
                                    preserve_geometry=True,
                                    style="hand", preserve_style=False)
        rect = _by_sem(obj, "p")
        label = _by_sem(obj, "p::text")
        self.assertEqual(rect["roughness"], 1)
        self.assertEqual(rect["backgroundColor"], "#a5d8ff")
        self.assertEqual(label["fontFamily"], 5)   # 换风格时字体也要跟着换


if __name__ == "__main__":
    unittest.main()
