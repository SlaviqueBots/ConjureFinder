"""Sparse Tag Browser auto-update helpers (mirrors Conjure Finder)."""

from __future__ import annotations

import unittest
from pathlib import Path

from sparse_tags.updater import (
    DEFAULT_UPDATE_PORT,
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
        self.assertFalse(is_newer("1.0.0", "1.0.1"))

    def test_default_port_differs_from_conjure_finder(self) -> None:
        self.assertEqual(DEFAULT_UPDATE_PORT, 8768)

    def test_update_ps1_swaps_without_relaunch(self) -> None:
        text = build_update_ps1(
            pid=4242,
            current=Path(r"C:\Apps\Sparse Tag Browser.exe"),
            new_exe=Path(r"C:\Apps\Sparse Tag Browser.exe.new"),
        )
        self.assertIn("$pidToWait = 4242", text)
        self.assertIn("Copy-Item -LiteralPath $new -Destination $target", text)
        self.assertIn("Sparse Tag Browser.exe", text)
        self.assertNotIn("Start-Process -FilePath $target", text)

    def test_update_ps1_does_not_touch_sibling_tools_or_user_data(self) -> None:
        text = build_update_ps1(
            pid=1,
            current=Path(r"C:\Apps\Sparse Tag Browser.exe"),
            new_exe=Path(r"C:\Apps\Sparse Tag Browser.exe.new"),
        )
        self.assertIn("conjure_finder.env", text)
        self.assertIn("sparse_tags_", text)
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped.startswith("Remove-Item"):
                continue
            self.assertTrue(
                any(tok in stripped for tok in ("$bak", "$new", "$log", "$PSCommandPath")),
                msg=f"unexpected Remove-Item: {stripped}",
            )

    def test_update_bat_launches_powershell(self) -> None:
        text = build_update_bat(
            pid=4242,
            current=Path(r"C:\Apps\Sparse Tag Browser.exe"),
            new_exe=Path(r"C:\Apps\Sparse Tag Browser.exe.new"),
        )
        self.assertIn("powershell.exe", text)
        self.assertIn(UPDATE_PS1, text)


if __name__ == "__main__":
    unittest.main()
