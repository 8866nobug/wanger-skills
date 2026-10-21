import unittest

from excalidraw import ids


class TestIds(unittest.TestCase):
    def test_new_id_format(self):
        for _ in range(200):
            i = ids.new_id()
            self.assertEqual(len(i), 8)
            self.assertTrue(ids.is_valid_id(i))

    def test_new_id_uniqueness(self):
        seen = {ids.new_id() for _ in range(5000)}
        self.assertEqual(len(seen), 5000)

    def test_detect_collisions(self):
        self.assertEqual(ids.detect_collisions(["a", "b", "a", "c", "b"]), ["a", "b"])
        self.assertEqual(ids.detect_collisions(["a", "b"]), [])

    def test_ensure_unique(self):
        existing = {"abc"}
        seq = iter(["abc", "abc", "xyz"])
        got = ids.ensure_unique(existing, generator=lambda: next(seq))
        self.assertEqual(got, "xyz")

    def test_next_index_increment(self):
        self.assertEqual(ids.first_index(), "a0")
        self.assertEqual(ids.next_index("a0"), "a1")
        self.assertEqual(ids.next_index("a9"), "aA")
        self.assertEqual(ids.next_index("aZ"), "aa")
        self.assertEqual(ids.next_index("az"), "b0")
        self.assertEqual(ids.next_index_after(["a0", "a3"]), "a4")


if __name__ == "__main__":
    unittest.main()
