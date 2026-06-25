from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_bot.normalization import expanded_query_terms


class NormalizationTests(unittest.TestCase):
    def test_expanded_query_terms_do_not_fragment_known_aliases(self) -> None:
        terms = expanded_query_terms("內耗或自我消耗")

        self.assertIn("內耗", terms)
        self.assertIn("自我消耗", terms)
        self.assertNotIn("自我", terms)
        self.assertNotIn("消耗", terms)

    def test_expanded_query_terms_still_fragments_unknown_cjk_terms(self) -> None:
        terms = expanded_query_terms("學習節奏")

        self.assertIn("學習節奏", terms)
        self.assertIn("學習", terms)
        self.assertIn("節奏", terms)


if __name__ == "__main__":
    unittest.main()
