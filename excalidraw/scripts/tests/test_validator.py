import unittest

from excalidraw import builder, models, styles, validator


def _make_doc(elements=None, app_state=None):
    app_state = app_state if app_state is not None else dict(styles.DEFAULT_APP_STATE)
    return models.Document(elements=elements or [], app_state=app_state,
                           files={}, source=styles.DEFAULT_SOURCE)


class TestValidator(unittest.TestCase):
    def test_empty_document(self):
        issues = validator.validate_document(_make_doc())
        self.assertFalse(validator.has_errors(issues))

    def test_duplicate_id(self):
        el = {"id": "abc", "type": "text", "text": "x"}
        issues = validator.validate_document(_make_doc([el, dict(el)]))
        self.assertTrue(any(i["code"] == "duplicate-id" for i in issues))

    def test_dangling_container(self):
        el = {"id": "abc", "type": "text", "text": "x", "containerId": "nope"}
        issues = validator.validate_document(_make_doc([el]))
        self.assertTrue(any(i["code"] == "dangling-container" for i in issues))

    def test_dangling_bound(self):
        el = {"id": "abc", "type": "rectangle",
              "boundElements": [{"type": "text", "id": "nope"}]}
        issues = validator.validate_document(_make_doc([el]))
        self.assertTrue(any(i["code"] == "dangling-bound" for i in issues))

    def test_dangling_binding(self):
        el = {"id": "abc", "type": "arrow",
              "startBinding": {"elementId": "nope", "mode": "orbit",
                               "fixedPoint": [0.5, 0.5]}}
        issues = validator.validate_document(_make_doc([el]))
        self.assertTrue(any(i["code"] == "dangling-binding" for i in issues))

    def test_image_data_missing_warning(self):
        el = {"id": "img1", "type": "image", "fileId": "abc123"}
        issues = validator.validate_document(_make_doc([el]))
        self.assertTrue(any(i["code"] == "image-data-missing" for i in issues))

    def test_image_with_embedded_file_ok(self):
        el = {"id": "img1", "type": "image", "fileId": "abc123"}
        doc = _make_doc([el])
        doc.embedded_files = {"abc123": "[[pic.jpg]]"}
        issues = validator.validate_document(doc)
        self.assertFalse(any(i["code"] == "image-data-missing" for i in issues))

    def test_valid_built_document(self):
        d = models.Diagram(
            nodes=[models.Node("process", "A", sem_id="a"),
                   models.Node("process", "B", sem_id="b")],
            edges=[models.Edge("a", "b")],
        )
        obj = builder.build_diagram(d)
        doc = _make_doc(obj["elements"], obj["appState"])
        issues = validator.validate_document(doc)
        self.assertFalse(validator.has_errors(issues))


if __name__ == "__main__":
    unittest.main()
