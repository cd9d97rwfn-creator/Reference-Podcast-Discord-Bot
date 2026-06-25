from __future__ import annotations

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import patch

from reference_bot.config import _parse_optional_int, load_settings


class ConfigTests(unittest.TestCase):
    def test_parse_optional_int(self) -> None:
        cases: list[tuple[str | None, int | None]] = [
            (None, None),
            ("", None),
            ("  ", None),
            ("123456789", 123456789),
        ]

        for raw_value, expected in cases:
            with self.subTest(raw_value=raw_value):
                self.assertEqual(_parse_optional_int(raw_value), expected)

    def test_parse_optional_int_rejects_non_numeric_value(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "DISCORD_GUILD_ID"):
            _parse_optional_int("not-a-number")

    def test_load_settings_includes_database_path(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "DISCORD_TOKEN": "token",
                "DATABASE_PATH": "custom.sqlite3",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertEqual(settings.discord_token, "token")
        self.assertEqual(settings.database_path, "custom.sqlite3")


if __name__ == "__main__":
    unittest.main()
