"""Version compare + update script helpers for Conjure Finder auto-update."""

from __future__ import annotations

import unittest
from pathlib import Path

from conjure_finder.updater import (
    UPDATE_PS1,
    build_update_bat,
    build_update_ps1,
    is_newer,
    parse_version,
)


class VersionCompareTests(unittest.TestCase):
    def test_parse(self) -> None:
        self.assertEqual(parse_version("1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version("v1.0"), (1, 0, 0))

    def test_newer(self) -> None:
        self.assertTrue(is_newer("1.0.1", "1.0.0"))
        self.assertTrue(is_newer("1.1.0", "1.0.9"))
        self.assertFalse(is_newer("1.0.0", "1.0.0"))
        self.assertFalse(is_newer("1.0.0", "1.0.1"))

    def test_update_ps1_swaps_without_relaunch(self) -> None:
        text = build_update_ps1(
            pid=4242,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        self.assertIn("$pidToWait = 4242", text)
        self.assertIn("Copy-Item -LiteralPath $new -Destination $target", text)
        self.assertIn("explorer.exe", text)
        self.assertIn("_UPDATE_START_HERE.txt", text)
        self.assertIn("Conjure Finder.exe", text)
        self.assertNotIn("Start-Process -FilePath $target", text)
        self.assertNotIn("$pid =", text)

    def test_update_bat_launches_powershell(self) -> None:
        text = build_update_bat(
            pid=4242,
            current=Path(r"C:\Apps\Conjure Finder.exe"),
            new_exe=Path(r"C:\Apps\Conjure Finder.exe.new"),
        )
        self.assertIn("powershell.exe", text)
        self.assertIn(UPDATE_PS1, text)


if __name__ == "__main__":
    unittest.main()
