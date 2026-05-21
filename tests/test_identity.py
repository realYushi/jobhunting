import unittest

from tools.lib.identity import (
    BoardKey,
    ManualKey,
    from_dict,
    key_from_args,
)


class BoardKeyTests(unittest.TestCase):
    def test_equality_is_case_insensitive_on_source(self):
        # Scrapers may emit "Seek" / "SEEK" / "seek"; all should dedup together.
        self.assertEqual(BoardKey("seek", "123"), BoardKey("Seek", "123"))

    def test_inequality_on_job_id(self):
        self.assertNotEqual(BoardKey("seek", "123"), BoardKey("seek", "124"))

    def test_inequality_on_source(self):
        self.assertNotEqual(BoardKey("seek", "123"), BoardKey("linkedin", "123"))

    def test_rejects_empty(self):
        with self.assertRaises(ValueError):
            BoardKey("", "123")
        with self.assertRaises(ValueError):
            BoardKey("seek", "")

    def test_hashable(self):
        # Used as dict / set key for in-memory dedup.
        s = {BoardKey("seek", "1"), BoardKey("seek", "1"), BoardKey("seek", "2")}
        self.assertEqual(len(s), 2)


class ManualKeyTests(unittest.TestCase):
    def test_equality_lowercased(self):
        # User typing "Acme" vs scraped "ACME" should collide.
        self.assertEqual(
            ManualKey("Acme Corp", "Senior Engineer"),
            ManualKey("acme corp", "senior engineer"),
        )

    def test_distinct_from_boardkey(self):
        # Cross-variant equality must be false even when strings overlap.
        self.assertNotEqual(BoardKey("seek", "Acme"), ManualKey("seek", "Acme"))


class SerializationTests(unittest.TestCase):
    def test_board_round_trip(self):
        k = BoardKey("seek", "91491952")
        self.assertEqual(from_dict(k.to_dict()), k)

    def test_manual_round_trip(self):
        k = ManualKey("Caruso Software Limited", "Software Engineer")
        self.assertEqual(from_dict(k.to_dict()), k)

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            from_dict({"kind": "lol"})


class KeyFromArgsTests(unittest.TestCase):
    def test_prefers_board_when_source_and_id_present(self):
        self.assertEqual(
            key_from_args("seek", "1", "Co", "Role"),
            BoardKey("seek", "1"),
        )

    def test_falls_back_to_manual(self):
        self.assertEqual(
            key_from_args(None, None, "Co", "Role"),
            ManualKey("Co", "Role"),
        )

    def test_partial_source_only_falls_back(self):
        # Source without job_id is not enough to dedup against a board listing.
        self.assertEqual(
            key_from_args("seek", None, "Co", "Role"),
            ManualKey("Co", "Role"),
        )


if __name__ == "__main__":
    unittest.main()
