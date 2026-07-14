from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from kindle_vocab_app.kindle_device import find_kindle_presence


class KindlePresenceTests(unittest.TestCase):
    def test_named_volume_is_detected_without_searching_for_vocab_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            kindle_root = Path(temporary) / "Kindle"
            kindle_root.mkdir()

            presence = find_kindle_presence([kindle_root])

            self.assertIsNotNone(presence)
            assert presence is not None
            self.assertIn("Kindle", presence.label)
            self.assertEqual(presence.signature[0], "volume")

    def test_unrelated_volume_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            unrelated_root = Path(temporary) / "Backup"
            unrelated_root.mkdir()

            self.assertIsNone(find_kindle_presence([unrelated_root]))


if __name__ == "__main__":
    unittest.main()
