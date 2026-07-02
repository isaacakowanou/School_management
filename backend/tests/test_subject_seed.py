import unittest
from collections import Counter

from constants import CLASSES_BY_LEVEL_GROUP, level_group_for_class_name, normalize_class_name
from subject_catalog import build_subject_rows, load_catalog


class SubjectSeedTests(unittest.TestCase):
    """Integrity of the GGFK catalog seed (A1.9).

    Exercises the same load + build path the Alembic seed migration runs, so a
    catalog edit that breaks an invariant fails here before it ships.
    """

    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog()
        cls.rows = build_subject_rows(cls.catalog)

    def test_total_subject_count_is_78(self):
        self.assertEqual(len(self.rows), 78)

    def test_counts_per_level_group(self):
        counts = Counter(row["level_group"] for row in self.rows)
        self.assertEqual(
            counts,
            {
                "NURSERY": 20,
                "PRIMARY": 17,
                "COLLEGE_FIRST_CYCLE": 22,
                "COLLEGE_SECOND_CYCLE": 19,
            },
        )

    def test_counts_per_section(self):
        counts = Counter((row["level_group"], row["section"]) for row in self.rows)
        self.assertEqual(
            counts,
            {
                ("NURSERY", "FRENCH"): 14,
                ("NURSERY", "ENGLISH"): 6,
                ("PRIMARY", "FRENCH"): 13,
                ("PRIMARY", "ENGLISH"): 4,
                ("COLLEGE_FIRST_CYCLE", "FRENCH"): 9,
                ("COLLEGE_FIRST_CYCLE", "ENGLISH"): 13,
                ("COLLEGE_SECOND_CYCLE", "FRENCH"): 8,
                ("COLLEGE_SECOND_CYCLE", "ENGLISH"): 11,
            },
        )

    def test_sections_are_valid_language_groups(self):
        self.assertEqual({row["section"] for row in self.rows}, {"FRENCH", "ENGLISH"})

    def test_espagnol_restricted_to_4eme_3eme(self):
        espagnol = [row for row in self.rows if row["name_fr"] == "Espagnol"]
        self.assertEqual(len(espagnol), 1)
        self.assertEqual(espagnol[0]["level_group"], "COLLEGE_FIRST_CYCLE")
        self.assertEqual(espagnol[0]["applicable_classes"], ["4ème", "3ème"])

    def test_etudes_sociales_restricted_to_6eme_5eme(self):
        etudes = [row for row in self.rows if row["name_fr"] == "Etudes sociales"]
        self.assertEqual(len(etudes), 1)
        self.assertEqual(etudes[0]["applicable_classes"], ["6ème", "5ème"])

    def test_only_the_two_exceptions_restrict_classes(self):
        restricted = sorted(
            row["name_fr"] for row in self.rows if row["applicable_classes"] is not None
        )
        self.assertEqual(restricted, ["Espagnol", "Etudes sociales"])

    def test_unique_key_name_fr_level_group_section(self):
        keys = [(row["name_fr"], row["level_group"], row["section"]) for row in self.rows]
        self.assertEqual(len(keys), len(set(keys)))

    def test_sort_order_is_consecutive_within_each_section(self):
        # Bulletin position must be preserved: 1..N per (level_group, section).
        by_section = {}
        for row in self.rows:
            by_section.setdefault((row["level_group"], row["section"]), []).append(row["sort_order"])
        for key, orders in by_section.items():
            self.assertEqual(sorted(orders), list(range(1, len(orders) + 1)), key)

    def test_constants_taxonomy_matches_catalog(self):
        # The class filter in the subjects route resolves level groups through
        # constants.CLASSES_BY_LEVEL_GROUP; it must mirror the catalog.
        catalog_classes = {
            level_group: level["applicable_classes"]
            for level_group, level in self.catalog["subjects_by_level"].items()
        }
        self.assertEqual(catalog_classes, CLASSES_BY_LEVEL_GROUP)

    def test_level_group_resolver_accepts_spelling_variants(self):
        # Class rows are admin-typed, so every taxonomy name must resolve in
        # its canonical spelling AND accent-stripped / case / whitespace
        # variants ("6ème" == "6eme" == "6EME " == " 6ème").
        for level_group, class_names in CLASSES_BY_LEVEL_GROUP.items():
            for name in class_names:
                unaccented = normalize_class_name(name)
                for variant in (name, unaccented, unaccented.upper(), f"  {name}  "):
                    self.assertEqual(level_group_for_class_name(variant), level_group, variant)

    def test_level_group_resolver_rejects_unknown_names(self):
        self.assertIsNone(level_group_for_class_name("Classe spéciale"))
        self.assertIsNone(level_group_for_class_name(""))
        self.assertIsNone(level_group_for_class_name(None))

    def test_overrides_are_subsets_of_their_level_group_classes(self):
        for row in self.rows:
            if row["applicable_classes"] is not None:
                self.assertTrue(
                    set(row["applicable_classes"]) <= set(CLASSES_BY_LEVEL_GROUP[row["level_group"]]),
                    row["name_fr"],
                )


if __name__ == "__main__":
    unittest.main()
