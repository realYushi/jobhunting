import unittest

from lib.identity import (
    BoardKey,
    ManualKey,
    from_dict,
    key_from_args,
)
from lib.paths import company_dirname


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


class SlugTests(unittest.TestCase):
    """JobKey.slug(company) owns the on-disk directory name.

    On-disk names must stay byte-identical to what company_dirname produced
    before slug() existed — existing applications/active/ and archive/ dirs
    must still be found.
    """

    def test_board_slug_is_company_suffixed_with_id8(self):
        key = BoardKey("seek", "91491952")
        self.assertEqual(
            key.slug("Caruso Software Limited"), "Caruso Software Limited-91491952"
        )

    def test_board_slug_truncates_long_ids_to_8_chars(self):
        key = BoardKey("hiringcafe", "erdu1sl82w0643qb")
        self.assertEqual(key.slug("Bellroy"), "Bellroy-erdu1sl8")

    def test_board_slug_matches_company_dirname(self):
        # Byte-identical to the legacy free-function form.
        key = BoardKey("seek", "12345678")
        self.assertEqual(key.slug("Acme Corp"), company_dirname("Acme Corp", "12345678"))

    def test_board_slugs_with_different_ids_do_not_collide(self):
        self.assertNotEqual(
            BoardKey("seek", "11111111").slug("Acme"),
            BoardKey("seek", "22222222").slug("Acme"),
        )

    def test_manual_slug_is_bare_company_with_display_casing(self):
        key = ManualKey("contact energy", "SWE")
        self.assertEqual(key.slug("Contact Energy"), "Contact Energy")
        self.assertEqual(key.slug("Contact Energy"), company_dirname("Contact Energy", None))

    def test_manual_slug_is_deterministic(self):
        key = ManualKey("Acme", "Engineer")
        self.assertEqual(key.slug("Acme"), key.slug("Acme"))

    def test_manual_collision_contract_same_company_different_positions(self):
        # PINNED CONTRACT: manual flows have no job_id, so two different
        # applications to the same company (different positions) map to the
        # SAME directory — the position does not disambiguate. Anyone changing
        # this must migrate existing on-disk directory names.
        engineer = ManualKey("Acme", "Engineer")
        designer = ManualKey("Acme", "Designer")
        self.assertNotEqual(engineer, designer)  # distinct keys...
        self.assertEqual(engineer.slug("Acme"), designer.slug("Acme"))  # ...same dir


if __name__ == "__main__":
    unittest.main()
